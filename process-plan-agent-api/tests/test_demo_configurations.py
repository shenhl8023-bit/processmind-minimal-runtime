"""Configuration rules have the same independent inclusion paths in native and CAD Demo routes."""
from copy import deepcopy
import pytest
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.demo_tables import DemoTableError, compile_demo_tables
from app.services.rule_packages.planner import plan_route
from test_demo_tables import downstream_engine, enabled, route_for

COPPER = 'project_factor.manual_process_9db2c854'
HEAT = 'project_factor.manual_process_22693293'

def leaf(field, value, op='eq'):
    return {'field': field, 'op': op, 'value': value}

def relation(source, target='strip', kind='trigger_after', match='all'):
    return {'relation_type': kind, 'source_process_ids': [source], 'target_process_ids': [target], 'source_match': match}

def configuration(process_id, occurrence, when=None, relations=()):
    return {'process_id': process_id, 'occurrence': occurrence, 'when': when, 'relations': list(relations),
            'source': 'user_confirmed', 'source_segment_id': process_id, 'source_text': '用户配置',
            'confirmed_by': '测试', 'confirmed_at': '2026-10-27T10:00:00+00:00'}

def package_payload(*, extra_conditions=(), extra_triggers=(), extra_configurations=()):
    return {
        'manifest': {'package_name': 'config-test', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [
            {'key': COPPER, 'label': '是否镀铜', 'type': 'boolean', 'source': '用户直接设定'},
            {'key': HEAT, 'label': '是否热处理', 'type': 'boolean', 'source': '用户直接设定'},
            {'key': 'material.grade', 'label': '材料', 'type': 'single_select',
             'options': [{'value': v, 'label': v} for v in ('9Cr18', '4Cr14Ni14W2Mo')]},
            {'key': 'precision.it_grade', 'label': 'IT等级', 'type': 'number'},
        ]},
        'route_catalog': {'processes': [
            {'process_id': 'base', 'display_name': '清洗', 'main': True, 'default_sequence': 1},
            {'process_id': 'copper', 'display_name': '镀铜', 'default_sequence': 2},
            {'process_id': 'heat', 'display_name': '热处理', 'default_sequence': 3},
            {'process_id': 'strip', 'display_name': '除铜', 'default_sequence': 4},
            {'process_id': 'inspect', 'display_name': '检验', 'default_sequence': 5},
        ]},
        'route_rules': {'rules': [], 'process_relations': [], 'process_configurations': [
            configuration('copper', 'manual', leaf(COPPER, True)),
            configuration('heat', 'manual', leaf(HEAT, True)),
            configuration('strip', 'conditional', {'all': [leaf('material.grade', '9Cr18'), *extra_conditions]},
                          [relation('copper'), *extra_triggers]),
            *extra_configurations,
        ]},
    }

def demo_selected(tables, inputs):
    selected = []
    for process in tables['full_route_table']:
        pid = process['process_id']
        if enabled(tables['rule_table'], pid, {**inputs, 'selected_processes': selected}):
            selected.append(pid)
    return selected

@pytest.mark.parametrize('copper,material,want', [
    (True, '9Cr18', ['base', 'copper', 'strip']),
    (False, '9Cr18', ['base']),
    (True, '4Cr14Ni14W2Mo', ['base', 'copper']),
    (False, '4Cr14Ni14W2Mo', ['base']),
])
def test_configuration_material_condition_and_trigger_must_both_match(copper, material, want):
    package = RulePackageV2.model_validate(package_payload())
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: copper, HEAT: False, 'material.grade': material, 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': material}) == want
    assert plan_route(package, inputs).selected_process_ids == want

@pytest.mark.parametrize('rank,heat,want', [
    (7, True, ['base', 'copper', 'heat', 'strip', 'inspect']),
    (8, True, ['base', 'copper', 'heat']),
    (7, False, ['base', 'copper']),
])
def test_configuration_condition_and_each_trigger_are_combined_gates(rank, heat, want):
    package = RulePackageV2.model_validate(package_payload(
        extra_conditions=[leaf('precision.it_grade', 7, 'lte')], extra_triggers=[relation('heat')],
        extra_configurations=[configuration('inspect', 'conditional', relations=[relation('strip', 'inspect')])],
    ))
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: True, HEAT: heat, 'material.grade': '9Cr18', 'precision.it_grade': rank}
    assert demo_selected(tables, {**inputs, 'material': '9Cr18'}) == want
    assert plan_route(package, inputs).selected_process_ids == want

def test_order_only_configuration_does_not_trigger_current_process():
    payload = package_payload()
    payload['route_rules']['process_configurations'][2]['relations'] = [relation('copper', kind='order_after')]
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: False, HEAT: False, 'material.grade': '9Cr18', 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': '9Cr18'}) == ['base', 'strip']
    assert plan_route(package, inputs).selected_process_ids == ['base', 'strip']

def test_legacy_trigger_cannot_bypass_configuration_material_gate():
    payload = package_payload()
    payload['route_rules']['process_relations'] = [{'relation_id': 'legacy', **relation('base')}]
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: False, HEAT: False, 'material.grade': '4Cr14Ni14W2Mo', 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': '4Cr14Ni14W2Mo'}) == ['base']
    assert plan_route(package, inputs).selected_process_ids == ['base']

def test_configuration_predicate_fields_are_collected_from_factor_dictionary():
    payload = package_payload()
    payload['factor_dictionary'] = deepcopy(payload['input_schema'])
    payload['input_schema']['fields'] = payload['input_schema']['fields'][:2]
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    assert {f['key'] for f in tables['factor_table']} == {COPPER, HEAT, 'material'}

@pytest.mark.parametrize('kind,source,code', [
    ('requires', 'copper', 'unsupported_requires'),
    ('conflicts', 'copper', 'unsupported_conflicts'),
    ('order_after', 'inspect', 'route_order_conflict'),
])
def test_configuration_unsupported_dependencies_have_explicit_diagnostics(kind, source, code):
    payload = package_payload()
    payload['route_rules']['process_configurations'][2]['relations'] = [relation(source, kind=kind)]
    package = RulePackageV2.model_validate(payload)
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(package, route_for(package))
    assert any(issue['code'] == code for issue in caught.value.issues)

def test_configuration_numeric_equality_retains_no_approximation_guard():
    package = RulePackageV2.model_validate(package_payload(extra_conditions=[leaf('precision.it_grade', 7)]))
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(package, route_for(package))
    assert any(issue['code'] == 'unsupported_numeric_equality' for issue in caught.value.issues)


@pytest.mark.parametrize('copper,material,want', [
    (True, '9Cr18', ['base', 'copper', 'strip']),
    (True, '4Cr14Ni14W2Mo', ['base', 'copper', 'strip']),
    (False, '4Cr14Ni14W2Mo', ['base']),
])
def test_configuration_any_condition_also_requires_its_trigger(copper, material, want):
    payload = package_payload()
    payload['route_rules']['process_configurations'][2]['when'] = {'any': [
        leaf('material.grade', '9Cr18'), leaf('material.grade', '4Cr14Ni14W2Mo'),
    ]}
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: copper, HEAT: False, 'material.grade': material, 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': material}) == want
    assert plan_route(package, inputs).selected_process_ids == want


@pytest.mark.parametrize('copper,heat,want', [
    (False, False, ['base']),
    (True, False, ['base', 'copper', 'strip']),
    (False, True, ['base', 'heat', 'strip']),
])
def test_existing_any_source_group_is_not_flattened_into_all(copper, heat, want):
    payload = package_payload()
    payload['route_rules']['process_configurations'][2]['when'] = None
    payload['route_rules']['process_configurations'][2]['relations'] = [{
        'relation_type': 'trigger_after', 'source_process_ids': ['copper', 'heat'],
        'target_process_ids': ['strip'], 'source_match': 'any',
    }]
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: copper, HEAT: heat, 'material.grade': '4Cr14Ni14W2Mo', 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': '4Cr14Ni14W2Mo'}) == want
    assert plan_route(package, inputs).selected_process_ids == want


def test_manual_configuration_false_cannot_be_overridden_by_legacy_trigger():
    payload = package_payload()
    payload['route_rules']['process_relations'] = [{'relation_id': 'legacy', **relation('base', 'copper')}]
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: False, HEAT: False, 'material.grade': '4Cr14Ni14W2Mo', 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': '4Cr14Ni14W2Mo'}) == ['base']
    assert plan_route(package, inputs).selected_process_ids == ['base']


def test_always_configuration_keeps_independent_mainline_dependency():
    payload = package_payload()
    payload['route_catalog']['processes'][1]['main'] = True
    payload['route_rules']['process_configurations'][0] = configuration(
        'copper', 'always', relations=[relation('base', 'copper', 'requires')],
    )
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: False, HEAT: False, 'material.grade': '9Cr18', 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': '9Cr18'}) == ['base', 'copper', 'strip']
    assert plan_route(package, inputs).selected_process_ids == ['base', 'copper', 'strip']


def test_disabled_configuration_does_not_suppress_legacy_trigger():
    payload = package_payload()
    payload['route_rules']['process_configurations'][2]['enabled'] = False
    payload['route_rules']['process_relations'] = [{'relation_id': 'legacy', **relation('copper')}]
    package = RulePackageV2.model_validate(payload)
    tables = compile_demo_tables(package, route_for(package))
    inputs = {COPPER: True, HEAT: False, 'material.grade': '4Cr14Ni14W2Mo', 'precision.it_grade': 7}
    assert demo_selected(tables, {**inputs, 'material': '4Cr14Ni14W2Mo'}) == ['base', 'copper', 'strip']
    assert plan_route(package, inputs).selected_process_ids == ['base', 'copper', 'strip']

def test_actual_downstream_engine_executes_configuration_boolean_and_linked_gate(downstream_engine):
    package = RulePackageV2.model_validate(package_payload())
    tables = compile_demo_tables(package, route_for(package))
    engine = downstream_engine(tables['factor_table'], tables['full_route_table'], tables['rule_table'])
    request = {'input_json': [], 'manual_defaults': {'material_grade': '9Cr18'},
               'manual': {'factor_overrides': {COPPER: True, HEAT: False}}}
    assert [p['process_name'] for p in engine.run(request)['route']] == ['清洗', '镀铜', '除铜']
    request['manual_defaults']['material_grade'] = '9Cr18'
    request['manual']['factor_overrides'][COPPER] = False
    assert [p['process_name'] for p in engine.run(request)['route']] == ['清洗']
    request['manual']['factor_overrides'][COPPER] = True
    request['manual_defaults']['material_grade'] = '4Cr14Ni14W2Mo'
    assert [p['process_name'] for p in engine.run(request)['route']] == ['清洗', '镀铜']


@pytest.mark.parametrize('branch', ['leaf', 'all', 'any'])
def test_configuration_optional_negation_has_explicit_missing_input_diagnostic(branch):
    condition = leaf('project_factor.category', 'A')
    if branch != 'leaf':
        condition = {branch: [condition, leaf('project_factor.approved', True)]}
    payload = {
        'manifest': {'package_name': '通用取反条件', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [
            {'key': 'project_factor.category', 'label': '类别', 'type': 'single_select', 'options': [{'value': v, 'label': v} for v in ('A', 'B')]},
            {'key': 'project_factor.approved', 'label': '审核通过', 'type': 'boolean'},
        ]},
        'route_catalog': {'processes': [{'process_id': 'custom_base', 'display_name': '准备', 'main': True}, {'process_id': 'custom_measure', 'display_name': '测量'}]},
        'route_rules': {'rules': [], 'process_configurations': [configuration('custom_measure', 'conditional', {'not': condition})]},
    }
    package = RulePackageV2.model_validate(payload)
    assert plan_route(package, {}).selected_process_ids == ['custom_base']
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(package, route_for(package))
    assert any(issue['code'] == 'unsupported_optional_negation' and '类别' in issue['message'] for issue in caught.value.issues)


@pytest.mark.parametrize('branch', ['leaf', 'all', 'any'])
def test_required_configuration_negation_matches_actual_downstream_engine(downstream_engine, branch):
    condition = leaf('project_factor.category', 'A')
    if branch != 'leaf':
        condition = {branch: [condition, leaf('project_factor.approved', True)]}
    package = RulePackageV2.model_validate({
        'manifest': {'package_name': '通用取反条件', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [
            {'key': 'project_factor.category', 'label': '类别', 'type': 'single_select', 'required': True, 'options': [{'value': v, 'label': v} for v in ('A', 'B')]},
            {'key': 'project_factor.approved', 'label': '审核通过', 'type': 'boolean', 'required': True},
        ]},
        'route_catalog': {'processes': [{'process_id': 'custom_base', 'display_name': '准备', 'main': True}, {'process_id': 'custom_measure', 'display_name': '测量'}]},
        'route_rules': {'rules': [], 'process_configurations': [configuration('custom_measure', 'conditional', {'not': condition})]},
    })
    tables = compile_demo_tables(package, route_for(package))
    engine = downstream_engine(tables['factor_table'], tables['full_route_table'], tables['rule_table'])
    for category, approved in [('A', True), ('A', False), ('B', True), ('B', False)]:
        inputs = {'project_factor.category': category, 'project_factor.approved': approved}
        native_ids = plan_route(package, inputs).selected_process_ids
        actual = engine.run({'input_json': [], 'manual': {'factor_overrides': inputs}})
        assert [p['process_name'] for p in actual['route']] == ['准备'] + (['测量'] if 'custom_measure' in native_ids else [])


@pytest.mark.parametrize('op,value', [('eq', False), ('eq', True), ('exists', None), ('not_exists', None)])
def test_optional_boolean_configuration_preserves_missing_versus_false(downstream_engine, op, value):
    condition = {'field': 'project_factor.optional_choice', 'op': op}
    if value is not None:
        condition['value'] = value
    package = RulePackageV2.model_validate({
        'manifest': {'package_name': '可选判断', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [{'key': 'project_factor.optional_choice', 'label': '可选判断', 'type': 'boolean'}]},
        'route_catalog': {'processes': [{'process_id': 'custom_base', 'display_name': '准备', 'main': True}, {'process_id': 'custom_measure', 'display_name': '测量'}]},
        'route_rules': {'rules': [], 'process_configurations': [configuration('custom_measure', 'conditional', condition)]},
    })
    tables = compile_demo_tables(package, route_for(package))
    engine = downstream_engine(tables['factor_table'], tables['full_route_table'], tables['rule_table'])
    for inputs in [{}, {'project_factor.optional_choice': False}, {'project_factor.optional_choice': True}]:
        native_ids = plan_route(package, inputs).selected_process_ids
        actual = engine.run({'input_json': [], 'manual': {'factor_overrides': inputs}})
        assert [p['process_name'] for p in actual['route']] == ['准备'] + (['测量'] if 'custom_measure' in native_ids else []), (op, inputs)


def test_optional_inequality_cannot_export_with_changed_missing_field_semantics():
    package = RulePackageV2.model_validate({
        'manifest': {'package_name': '可选判断', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [{'key': 'project_factor.category', 'label': '类别', 'type': 'single_select', 'options': [{'value': v, 'label': v} for v in ('A', 'B')]}]},
        'route_catalog': {'processes': [{'process_id': 'custom_base', 'display_name': '准备', 'main': True}, {'process_id': 'custom_measure', 'display_name': '测量'}]},
        'route_rules': {'rules': [], 'process_configurations': [configuration('custom_measure', 'conditional', leaf('project_factor.category', 'A', 'neq'))]},
    })
    assert plan_route(package, {}).selected_process_ids == ['custom_base']
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(package, route_for(package))
    assert any(issue['code'] == 'unsupported_optional_inequality' for issue in caught.value.issues)


@pytest.mark.parametrize('op,value', [('eq', ''), ('in', ['', 'A']), ('contains', ''), ('exists', None), ('not_exists', None)])
def test_optional_scalar_enum_keeps_missing_distinct_from_explicit_empty(downstream_engine, op, value):
    condition = {'field': 'project_factor.category', 'op': op, **({'value': value} if value is not None else {})}
    package = RulePackageV2.model_validate({
        'manifest': {'package_name': '可选枚举', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [{'key': 'project_factor.category', 'label': '类别', 'type': 'single_select', 'options': [{'value': v, 'label': v} for v in ('A', 'B')]}]},
        'route_catalog': {'processes': [{'process_id': 'custom_base', 'display_name': '准备', 'main': True}, {'process_id': 'custom_measure', 'display_name': '测量'}]},
        'route_rules': {'rules': [], 'process_configurations': [configuration('custom_measure', 'conditional', condition)]},
    })
    tables = compile_demo_tables(package, route_for(package))
    engine = downstream_engine(tables['factor_table'], tables['full_route_table'], tables['rule_table'])
    for inputs in [{}, {'project_factor.category': ''}, {'project_factor.category': None}, {'project_factor.category': 'A'}, {'project_factor.category': 'B'}]:
        native_ids = plan_route(package, inputs).selected_process_ids
        actual = engine.run({'input_json': [], 'manual': {'factor_overrides': inputs}})
        assert [p['process_name'] for p in actual['route']] == ['准备'] + (['测量'] if 'custom_measure' in native_ids else []), (op, inputs)


def test_optional_empty_contains_all_cannot_silently_become_always_true():
    package = RulePackageV2.model_validate({
        'manifest': {'package_name': '可选多选', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [{'key': 'project_factor.tags', 'label': '标签', 'type': 'multi_select', 'options': [{'value': 'A', 'label': 'A'}]}]},
        'route_catalog': {'processes': [{'process_id': 'custom_base', 'display_name': '准备', 'main': True}, {'process_id': 'custom_measure', 'display_name': '测量'}]},
        'route_rules': {'rules': [], 'process_configurations': [configuration('custom_measure', 'conditional', leaf('project_factor.tags', [], 'contains_all'))]},
    })
    with pytest.raises(DemoTableError) as caught:
        compile_demo_tables(package, route_for(package))
    assert any(issue['code'] == 'unsupported_empty_collection_condition' for issue in caught.value.issues)


@pytest.mark.parametrize('cad,expected', [
    ([], ['准备']),
    ([{'group_path': 'A侧/外圆', 'features': [{'feature_select': '平面'}]}], ['准备']),
    ([{'group_path': 'A侧/外圆', 'features': [{'feature_select': '外圆柱面'}]}], ['准备', '精加工', '后处理']),
])
def test_actual_machining_candidate_realization_controls_following_process(downstream_engine, cad, expected):
    package = RulePackageV2.model_validate({
        'manifest': {'package_name': '加工联动', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [{'key': 'project_factor.enabled', 'label': '需要精加工', 'type': 'boolean'}]},
        'route_catalog': {'processes': [
            {'process_id': 'custom_base', 'display_name': '准备', 'main': True, 'default_sequence': 1},
            {'process_id': 'custom_machine', 'display_name': '精加工', 'default_sequence': 2, 'steps': [{'step_id': 'custom_machine.step1', 'name': '精车外圆'}]},
            {'process_id': 'custom_follow', 'display_name': '后处理', 'default_sequence': 3},
        ]},
        'route_rules': {'rules': [], 'process_configurations': [
            configuration('custom_machine', 'conditional', leaf('project_factor.enabled', True)),
            configuration('custom_follow', 'conditional', relations=[relation('custom_machine', 'custom_follow')]),
        ]},
    })
    tables = compile_demo_tables(package, route_for(package))
    engine = downstream_engine(tables['factor_table'], tables['full_route_table'], tables['rule_table'])
    actual = engine.run({'input_json': cad, 'manual': {'factor_overrides': {'project_factor.enabled': True}}})
    assert [p['process_name'] for p in actual['route']] == expected
    if len(expected) == 3:
        assert actual['route'][1]['steps'][0]['candidates'] == {'A侧/外圆': ['外圆柱面']}
    # The native endpoint accepts factor values only; it previews the factor
    # route. CAD geometry realizes its mapped steps in the downstream engine.
    assert plan_route(package, {'project_factor.enabled': True}).selected_process_ids == ['custom_base', 'custom_machine', 'custom_follow']
