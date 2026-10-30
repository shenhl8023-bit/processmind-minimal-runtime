import pytest
from pydantic import ValidationError

from app.services.rule_packages.condition_contracts import RuleConditionCandidate, RuleConditionProcessOption
from app.services.rule_packages.condition_parser import validate_candidate
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.planner import RoutePlanningError, plan_route
from app.services.rule_packages.validator import validate_rule_package


def relation(source='copper', target='strip', kind='trigger_after'):
    return {'relation_type': kind, 'source_process_ids': [source], 'target_process_ids': [target], 'source_match': 'all'}


def configuration(process_id='strip', occurrence='conditional', when=None, relations=None, **metadata):
    return {'process_id': process_id, 'occurrence': occurrence, 'when': when, 'relations': relations or [], **metadata}


def package_payload():
    return {
        'manifest': {'package_name': '联动测试', 'project_id': 12, 'scope': {'key': '12'}},
        'input_schema': {'fields': [
            {'key': 'copper', 'label': '是否镀铜', 'type': 'boolean'},
            {'key': 'material.grade', 'label': '材料', 'type': 'single_select', 'options': [{'value': '9Cr18', 'label': '9Cr18'}, {'value': 'other', 'label': '其他'}]},
            {'key': 'precision', 'label': '精度', 'type': 'number'},
        ]},
        'route_catalog': {'processes': [
            {'process_id': 'prepare', 'display_name': '准备', 'main': True, 'default_sequence': 1},
            {'process_id': 'copper', 'display_name': '镀铜', 'default_sequence': 2},
            {'process_id': 'strip', 'display_name': '除铜', 'default_sequence': 3},
            {'process_id': 'inspect', 'display_name': '检验', 'default_sequence': 4},
        ]},
        'route_rules': {'rules': [], 'process_configurations': [
            configuration('copper', when={'field': 'copper', 'op': 'eq', 'value': True}),
            configuration(when={'all': [
                {'field': 'material.grade', 'op': 'eq', 'value': '9Cr18'},
                {'field': 'precision', 'op': 'lte', 'value': 8},
            ]}, relations=[relation()]),
        ]},
    }


@pytest.mark.parametrize('copper,material,precision,expected', [
    (True, '9Cr18', 7, ['prepare', 'copper', 'strip']),
    (False, '9Cr18', 7, ['prepare']),
    (True, 'other', 7, ['prepare', 'copper']),
    (True, '9Cr18', 9, ['prepare', 'copper']),
    (False, 'other', 7, ['prepare']),
])
def test_configuration_condition_and_trigger_must_both_match(copper, material, precision, expected):
    package = RulePackageV2.model_validate(package_payload())
    result = plan_route(package, {'copper': copper, 'material': {'grade': material}, 'precision': precision})
    assert result.selected_process_ids == expected


def test_trigger_alone_can_include_a_process_without_a_field_condition():
    payload = package_payload()
    payload['route_rules']['process_configurations'][1]['when'] = None
    payload['route_rules']['process_configurations'].append(configuration('inspect', relations=[relation('strip', 'inspect')]))
    package = RulePackageV2.model_validate(payload)
    assert plan_route(package, {'copper': True, 'material': {'grade': 'other'}, 'precision': 7}).selected_process_ids == ['prepare', 'copper', 'strip', 'inspect']
    assert plan_route(package, {'copper': False, 'material': {'grade': '9Cr18'}, 'precision': 7}).selected_process_ids == ['prepare']


@pytest.mark.parametrize('copper,inspect_main,expected', [
    (True, False, ['prepare', 'copper']),
    (False, True, ['prepare', 'inspect']),
    (True, True, ['prepare', 'copper', 'inspect', 'strip']),
])
def test_every_trigger_relation_must_match(copper, inspect_main, expected):
    payload = package_payload()
    payload['route_catalog']['processes'][3]['main'] = inspect_main
    payload['route_rules']['process_configurations'][1]['when'] = None
    payload['route_rules']['process_configurations'][1]['relations'] = [relation(), relation('inspect')]
    assert plan_route(RulePackageV2.model_validate(payload), {'copper': copper}).selected_process_ids == expected


def test_order_only_does_not_trigger_optional_process():
    payload = package_payload()
    payload['route_rules']['process_configurations'][1]['relations'] = [relation(kind='order_after')]
    result = plan_route(RulePackageV2.model_validate(payload), {'copper': True, 'material': {'grade': 'other'}, 'precision': 7})
    assert result.selected_process_ids == ['prepare', 'copper']


def test_legacy_trigger_cannot_bypass_configuration_gate():
    payload = package_payload()
    payload['route_rules']['process_relations'] = [{'relation_id': 'legacy', **relation('prepare')}]
    assert plan_route(RulePackageV2.model_validate(payload), {'copper': False}).selected_process_ids == ['prepare']


def test_required_configured_process_cannot_bypass_failed_gate():
    payload = package_payload()
    payload['route_catalog']['processes'][0]['constraints'] = {'requires': ['strip']}
    with pytest.raises(RoutePlanningError, match='(?:条件|规则|配置|未满足)'):
        plan_route(RulePackageV2.model_validate(payload), {'copper': False, 'material': {'grade': 'other'}})


def test_required_legacy_process_can_trigger_configured_chain():
    payload = package_payload()
    payload['route_rules']['process_configurations'] = [configuration('strip', relations=[relation()])]
    payload['route_catalog']['processes'][0]['constraints'] = {'requires': ['copper']}
    assert plan_route(RulePackageV2.model_validate(payload), {}).selected_process_ids == ['copper', 'prepare', 'strip']


def test_candidate_keeps_complex_conditions_and_relations_together():
    when = {'all': [{'field': 'material.grade', 'op': 'eq', 'value': '9Cr18'}, {'not': {'field': 'cad.features', 'op': 'contains', 'value': '槽类特征'}}]}
    candidate = RuleConditionCandidate.model_validate({'kind': 'process_configuration', 'configuration': configuration(when=when, relations=[relation()])})
    assert candidate.model_dump(by_alias=True)['configuration']['when']['all'][1]['not']['value'] == '槽类特征'
    assert validate_candidate(candidate, [RuleConditionProcessOption(process_id=p, display_name=p) for p in ('copper', 'strip')], current_process_id='strip') == []


@pytest.mark.parametrize('config', [configuration(occurrence='always', when={'field': 'material.grade', 'op': 'eq', 'value': '9Cr18'}), configuration(occurrence='always', relations=[relation()]), configuration()])
def test_candidate_rejects_ambiguous_occurrence_shapes(config):
    with pytest.raises(ValidationError):
        RuleConditionCandidate.model_validate({'kind': 'process_configuration', 'configuration': config})


def test_legacy_package_dump_omits_empty_configurations(rule_package_v2):
    assert 'process_configurations' not in rule_package_v2.model_dump(mode='json', by_alias=True)['route_rules']


def test_validator_rejects_unknown_configuration_field_and_cycles():
    payload = package_payload()
    payload['route_rules']['process_configurations'][0]['when']['field'] = 'missing'
    payload['route_rules']['process_configurations'][0]['relations'] = [relation('strip', 'copper')]
    report = validate_rule_package(RulePackageV2.model_validate(payload))
    assert {'unknown_input_field', 'dependency_cycle'}.issubset({e.code for e in report.errors})


def test_validator_rejects_main_flag_that_bypasses_configuration():
    payload = package_payload()
    payload['route_catalog']['processes'][2]['main'] = True
    report = validate_rule_package(RulePackageV2.model_validate(payload))
    assert 'configuration_main_mismatch' in {e.code for e in report.errors}


@pytest.mark.parametrize('step_id', ['shared-step', 'strip'])
def test_validator_rejects_step_ids_colliding_across_the_public_node_namespace(step_id):
    payload = package_payload()
    payload['route_catalog']['processes'][0]['steps'] = [{'step_id': step_id, 'name': '准备工步'}]
    if step_id == 'shared-step':
        payload['route_catalog']['processes'][1]['steps'] = [{'step_id': step_id, 'name': '镀铜工步'}]
    report = validate_rule_package(RulePackageV2.model_validate(payload))
    assert report.valid is False
    assert 'duplicate_node_id' in {error.code for error in report.errors}


@pytest.mark.parametrize('actual', ['M2', ' w6mo5cr4v2 '])
def test_validator_executes_test_cases_with_the_same_canonical_inputs_as_simulation(actual):
    payload = package_payload()
    payload['input_schema']['fields'] = [{
        'key': 'material.grade', 'label': '材料', 'type': 'single_select',
        'options': [{'value': 'W6Mo5Cr4V2', 'label': 'W6Mo5Cr4V2', 'aliases': ['M2']}],
    }]
    payload['route_rules'] = {'rules': [{
        'rule_id': 'material', 'when': {'field': 'material.grade', 'op': 'eq', 'value': 'W6Mo5Cr4V2'},
        'then': {'include_process_ids': ['copper']},
    }]}
    payload['test_cases'] = [{'case_id': 'normalized-material', 'input': {'material': {'grade': actual}},
                              'expect': {'included_process_ids': ['prepare', 'copper']}}]
    report = validate_rule_package(RulePackageV2.model_validate(payload))
    assert report.valid is True, report.errors
    assert report.test_results[0].passed is True


@pytest.mark.asyncio
async def test_configuration_save_reload_and_reject_wrong_segment(tmp_path):
    from fastapi import HTTPException
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.database import Base
    from app.models.models import NormalizedRouteVersion, NormalizedRouteSegmentRuleReview
    from app.services.rule_packages.condition_contracts import ManualRuleConditionRequest
    from app.services.rule_packages import condition_reviews

    assert hasattr(condition_reviews, 'set_process_configuration_review')
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'config.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    candidate = {'kind': 'process_configuration', 'configuration': configuration(when={'any': [
        {'field': 'material.grade', 'op': 'eq', 'value': '9Cr18'},
        {'field': 'material.grade', 'op': 'eq', 'value': 'other'},
    ]}, relations=[relation()])}
    try:
        async with factory() as session:
            session.add(NormalizedRouteVersion(id=1, project_id=7, version=1, route_json='[{"id":"segment-strip","export_process_id":"strip"},{"id":"copper"}]'))
            await session.commit()
            body = ManualRuleConditionRequest(project_id=7, route_id=1, segment_id='segment-strip', process_id='strip', source_text='材料满足且镀铜后安排除铜', candidate=candidate, processes=[RuleConditionProcessOption(process_id=p, display_name=p) for p in ('strip', 'copper')])
            response = await condition_reviews.set_process_configuration_review(body, session)
            assert response.review.status == 'confirmed'
            assert response.review.parser_version == 'configuration'
            assert response.review.confirmed.configuration.relations[0].source_process_ids == ['copper']
            assert len(response.review.confirmed.configuration.when.any_conditions) == 2
        async with factory() as session:
            row = (await session.execute(select(NormalizedRouteSegmentRuleReview))).scalar_one()
            assert condition_reviews.serialize_condition_review(row).confirmed == response.review.confirmed
            body.process_id = 'copper'
            with pytest.raises(HTTPException) as error:
                await condition_reviews.set_process_configuration_review(body, session)
            assert error.value.status_code == 422
    finally:
        await engine.dispose()


def test_manual_configuration_cannot_spoof_bool_switch():
    candidate = RuleConditionCandidate.model_validate({'kind': 'process_configuration', 'configuration': configuration('copper', 'manual', when={'field': 'material.grade', 'op': 'eq', 'value': '9Cr18'})})
    assert any('Bool' in issue for issue in validate_candidate(candidate, [RuleConditionProcessOption(process_id='copper', display_name='镀铜')], current_process_id='copper'))


@pytest.mark.parametrize('value,expected', [(True, ['prepare', 'copper', 'strip']), (False, ['prepare'])])
def test_manual_configuration_bool_drives_associated_process(value, expected):
    from app.services.rule_packages.condition_reviews import _manual_process_field_key
    payload = package_payload()
    key = _manual_process_field_key('copper')
    payload['input_schema']['fields'][0].update(key=key, source='用户直接设定')
    payload['route_rules']['process_configurations'][0].update(occurrence='manual', when={'field': key, 'op': 'eq', 'value': True})
    result = plan_route(RulePackageV2.model_validate(payload), {key: value, 'material': {'grade': '9Cr18'}, 'precision': 7})
    assert result.selected_process_ids == expected


def test_configuration_requires_adds_predecessor_and_conflict_remains_error():
    payload = package_payload()
    payload['route_rules']['process_configurations'] = [configuration('strip', when={'field': 'copper', 'op': 'eq', 'value': True}, relations=[relation(kind='requires')])]
    assert plan_route(RulePackageV2.model_validate(payload), {'copper': True}).selected_process_ids == ['prepare', 'copper', 'strip']
    payload['route_rules']['process_configurations'][0]['relations'].append(relation('prepare', kind='conflicts'))
    with pytest.raises(RoutePlanningError, match='不能同时'):
        plan_route(RulePackageV2.model_validate(payload), {'copper': True})


def test_compiler_keeps_configuration_atomic():
    from app.services.rule_packages.compiler import compile_rule_package
    from app.services.rule_packages.contracts import CompileRulePackageRequest
    payload = package_payload()
    request = CompileRulePackageRequest(project_id=12, package_name='配置', fields=payload['input_schema']['fields'], processes=payload['route_catalog']['processes'], process_configurations=payload['route_rules']['process_configurations'])
    package = compile_rule_package(request)
    assert len(package.route_rules.process_configurations) == 2
    assert package.route_rules.rules == []
    assert package.route_rules.process_relations == []


@pytest.mark.parametrize('copper,material,expected_strip', [(True, '9Cr18', True), (True, 'other', True), (True, 'third', False), (False, '9Cr18', False), (False, 'third', False)])
def test_any_factor_conditions_and_trigger_are_combined_gates(copper, material, expected_strip):
    payload = package_payload()
    payload['route_rules']['process_configurations'][1]['when'] = {'any': [
        {'field': 'material.grade', 'op': 'eq', 'value': '9Cr18'},
        {'field': 'material.grade', 'op': 'eq', 'value': 'other'},
    ]}
    package = RulePackageV2.model_validate(payload)
    result = plan_route(package, {'copper': copper, 'material': {'grade': material}})
    assert ('strip' in result.selected_process_ids) is expected_strip


def test_always_and_trigger_only_configuration_needs_no_artificial_inputs():
    payload = package_payload()
    payload['input_schema']['fields'] = []
    payload['route_rules']['process_configurations'] = [configuration('copper', 'always'), configuration('strip', relations=[relation()])]
    payload['route_catalog']['processes'][1]['main'] = True
    report = validate_rule_package(RulePackageV2.model_validate(payload))
    assert report.valid is True
    assert plan_route(RulePackageV2.model_validate(payload), {}).selected_process_ids == ['prepare', 'copper', 'strip']


def test_configuration_endpoint_saves_and_checks_workflow_revision(tmp_path):
    import asyncio
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.database import Base, get_db
    from app.main import app
    from app.models.models import NormalizedRouteVersion, Project

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'endpoint.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(Project(id=7, name='配置接口', status='ROUTE_SET_READY', workflow_revision=2))
            session.add(NormalizedRouteVersion(id=1, project_id=7, version=1, route_json='[{"id":"strip"},{"id":"copper"}]'))
            await session.commit()

    async def override_db():
        async with factory() as session:
            yield session

    asyncio.run(setup())
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    body = {
        'project_id': 7, 'route_id': 1, 'expected_workflow_revision': 2,
        'segment_id': 'strip', 'process_id': 'strip', 'source_text': '镀铜后安排除铜',
        'candidate': {'kind': 'process_configuration', 'configuration': configuration(relations=[relation()])},
        'processes': [{'process_id': p, 'display_name': p} for p in ('strip', 'copper')],
    }
    try:
        client = TestClient(app)
        response = client.post('/api/extract/finalized-rule-packages/rule-conditions/configuration', json=body)
        assert response.status_code == 200
        assert response.json()['review']['confirmed']['configuration']['relations'][0]['source_process_ids'] == ['copper']
        body['expected_workflow_revision'] = 1
        assert client.post('/api/extract/finalized-rule-packages/rule-conditions/configuration', json=body).status_code == 409
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        asyncio.run(engine.dispose())


@pytest.mark.asyncio
@pytest.mark.parametrize('relation_type', ['trigger_after', 'order_after', 'requires'])
async def test_configuration_save_rejects_cross_process_cycles_without_losing_saved_rule(tmp_path, relation_type):
    from fastapi import HTTPException
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.database import Base
    from app.models.models import NormalizedRouteVersion, NormalizedRouteSegmentRuleReview
    from app.services.rule_packages.condition_contracts import ManualRuleConditionRequest
    from app.services.rule_packages.condition_reviews import set_process_configuration_review, serialize_condition_review

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cycle.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add(NormalizedRouteVersion(id=1, project_id=7, version=1, route_json='[{"id":"surface_a"},{"id":"surface_b"}]'))
            await session.commit()
            processes = [{'process_id': pid, 'display_name': pid} for pid in ('surface_a', 'surface_b')]
            def request(pid, links):
                return ManualRuleConditionRequest(project_id=7, route_id=1, segment_id=pid, process_id=pid, source_text='通用工序顺序',
                    processes=processes, candidate={'kind': 'process_configuration', 'configuration': configuration(pid, 'conditional' if relation_type == 'trigger_after' and links else 'always', relations=links)})
            saved_b = await set_process_configuration_review(request('surface_b', []), session)
            await set_process_configuration_review(request('surface_a', [relation('surface_b', 'surface_a', relation_type)]), session)
            with pytest.raises(HTTPException) as caught:
                await set_process_configuration_review(request('surface_b', [relation('surface_a', 'surface_b', relation_type)]), session)
            assert caught.value.status_code == 422
            assert '环' in str(caught.value.detail)
        async with factory() as session:
            row = (await session.execute(select(NormalizedRouteSegmentRuleReview).where(NormalizedRouteSegmentRuleReview.segment_id == 'surface_b'))).scalar_one()
            assert serialize_condition_review(row).confirmed == saved_b.review.confirmed
    finally:
        await engine.dispose()
