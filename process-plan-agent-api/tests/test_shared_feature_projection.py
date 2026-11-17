"""Shared executable fields must be derived from saved, authored confirmations."""

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services.rule_packages.condition_contracts import RuleConditionCandidate
from app.services.rule_packages.confirmation_validation import require_confirmed_user_rule_sources
from app.services.rule_packages.contracts import InputField, InputSchemaV2, RulePackageV2
from app.services.rule_packages.input_validation import validate_inputs
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.validator import validate_rule_package


THROUGH = '孔(通孔)'
BLIND = '孔(盲孔)'
SCOPES = {THROUGH: 'project_factor.feature_5b54_28_901a_5b54_29',
          BLIND: 'project_factor.feature_5b54_28_76f2_5b54_29'}
SIDES = ['A侧', 'B侧', '中间', '周边', '所有方位']
AT = datetime(2026, 11, 16, 8, tzinfo=timezone.utc)


def saved_candidate(process='drill', *, kind='process_configuration', features=None, direction='A侧', threshold=7, suffix='it', options=None):
    scope = 'project_factor.operation_' + process
    definitions = [
        {'key': scope + '.features', 'label': '加工对象的特征', 'type': 'multi_select',
         'operators': ['contains_any', 'contains'], 'options': [{'value': name, 'label': name} for name in [THROUGH, BLIND]]},
        {'key': scope + '.direction', 'label': '同一加工对象的方位', 'type': 'single_select',
         'operators': ['eq'], 'options': [{'value': side, 'label': side} for side in (options or SIDES)]},
        {'key': scope + '.' + suffix, 'label': '加工对象的实际精度', 'type': 'number',
         'operators': ['lte'], 'unit': 'IT' if suffix == 'it' else 'μm',
         'validation': {'min': 5, 'max': 10} if suffix == 'it' else {'min': 0}},
    ]
    for field in definitions:
        field.update(category='本项目条件', source='已确认对象；工序=' + process, required=False, allow_custom=False)
    when = {'all': [
        {'field': scope + '.features', 'op': 'contains_any', 'value': features or [THROUGH, BLIND]},
        {'field': scope + '.direction', 'op': 'eq', 'value': direction},
        {'field': scope + '.' + suffix, 'op': 'lte', 'value': threshold},
    ]}
    data = {'kind': kind, 'field_definitions': definitions, 'evidence': '已确认加工对象', 'preview': '按已确认条件生成'}
    if kind == 'condition':
        data.update(when=when, then={'include_process_ids': [process]})
    else:
        data['configuration'] = {'process_id': process, 'occurrence': 'conditional', 'when': when, 'relations': []}
    return RuleConditionCandidate.model_validate(data)


def when_of(candidate):
    return candidate.configuration.when if candidate.configuration else candidate.when


def expected_fields(names=(THROUGH, BLIND), *, suffix='it', sides=None):
    fields = []
    for name in names:
        scope = SCOPES[name]
        fields.extend([
            {'key': scope + '.present', 'label': name, 'type': 'boolean', 'required': False,
             'source': '本项目特征输入', 'allow_custom': False},
            {'key': scope + '.direction', 'label': name + '的方位', 'type': 'single_select', 'required': False,
             'source': '本项目特征输入', 'allow_custom': False,
             'options': [{'value': side, 'label': side} for side in (sides or SIDES)]},
            {'key': scope + '.' + suffix, 'label': name + ('的实际尺寸精度等级' if suffix == 'it' else '的实际Ra要求值'),
             'type': 'number', 'required': False, 'source': '本项目特征输入', 'allow_custom': False,
             'unit': 'IT' if suffix == 'it' else 'μm',
             'validation': {'min': 5, 'max': 10} if suffix == 'it' else {'min': 0}},
        ])
    return fields


def expected_when(names=(THROUGH, BLIND), *, direction='A侧', threshold=7, suffix='it'):
    branches = []
    for name in names:
        scope = SCOPES[name]
        sides = ['A侧', 'B侧', '所有方位'] if direction == '所有方位' else [direction, '所有方位']
        branches.append({'all': [
            {'field': scope + '.present', 'op': 'eq', 'value': True},
            {'field': scope + '.direction', 'op': 'in', 'value': sides},
            {'field': scope + '.' + suffix, 'op': 'lte', 'value': threshold},
        ]})
    return branches[0] if len(branches) == 1 else {'any': branches}


def package_for(candidates, *, projected=True, suffix='it', sides=None):
    fields = expected_fields(suffix=suffix, sides=sides) if projected else [
        {key: value for key, value in field.model_dump().items() if key in InputField.model_fields}
        for candidate in candidates for field in candidate.field_definitions
    ]
    rules, configurations = [], []
    processes = [{'process_id': 'prepare', 'display_name': '准备', 'main': True, 'default_sequence': 1}]
    for index, candidate in enumerate(candidates):
        process = candidate.configuration.process_id if candidate.configuration else candidate.then.include_process_ids[0]
        processes.append({'process_id': process, 'display_name': process, 'default_sequence': index + 2})
        metadata = {'source': 'user_confirmed', 'source_segment_id': process, 'source_text': '确认-' + process,
                    'confirmed_by': '审核员', 'confirmed_at': AT.isoformat()}
        original = when_of(candidate).model_dump(by_alias=True, exclude_none=True)
        names = original['all'][0]['value']
        when = expected_when(names, direction=original['all'][1]['value'], threshold=original['all'][2]['value'], suffix=suffix) if projected else original
        if candidate.configuration:
            configurations.append({'process_id': process, 'occurrence': 'conditional', 'when': when, 'relations': [], **metadata})
        else:
            rules.append({'rule_id': 'confirmed.' + process, 'when': when, 'then': candidate.then.model_dump(), **metadata})
    facts = {SCOPES[THROUGH] + '.present': True, SCOPES[THROUGH] + '.direction': 'A侧', SCOPES[THROUGH] + '.' + suffix: 6}
    if not projected:
        facts = {field.key: ([THROUGH] if field.key.endswith('.features') else 'A侧' if field.key.endswith('.direction') else 6)
                 for candidate in candidates for field in candidate.field_definitions}
    return RulePackageV2.model_validate({
        'manifest': {'package_name': '共享特征执行回归', 'project_id': 7, 'route_version_id': 1, 'scope': {'key': '7'}},
        'factor_dictionary': {'fields': fields}, 'input_schema': {'fields': fields},
        'route_catalog': {'processes': processes}, 'route_rules': {'rules': rules, 'process_configurations': configurations},
        'test_cases': [{'case_id': 'shared-input-hit', 'input': facts,
                        'expect': {'included_process_ids': [p['process_id'] for p in processes]}}],
    })


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all([Project(id=7, name='隔离共享输入'), NormalizedRouteVersion(id=1, project_id=7, version=1, route_json='[]')])
        await db.commit()
        yield db
    await engine.dispose()


async def persist(db, candidates):
    rows = []
    for candidate in candidates:
        process = candidate.configuration.process_id if candidate.configuration else candidate.then.include_process_ids[0]
        row = NormalizedRouteSegmentRuleReview(project_id=7, route_version_id=1, segment_id=process, decision='accepted',
            condition_status='confirmed', condition_source_text='确认-' + process,
            condition_confirmed_json=candidate.model_dump_json(by_alias=True),
            condition_confirmed_by='审核员', condition_confirmed_at=AT)
        db.add(row)
        rows.append(row)
    await db.commit()
    return rows


async def audit(package, db):
    await require_confirmed_user_rule_sources(package, project_id=7, route_version_id=1, db=db)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
async def test_real_source_audit_accepts_only_saved_projection_and_keeps_saved_original(session, kind):
    candidate = saved_candidate(kind=kind)
    rows = await persist(session, [candidate])
    original = rows[0].condition_confirmed_json
    package = package_for([candidate])
    assert validate_rule_package(package).valid
    await audit(package, session)
    assert rows[0].condition_confirmed_json == original
    # No shared schema: historical literal checks remain intact.
    await audit(package_for([candidate], projected=False), session)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
@pytest.mark.parametrize('mutation', ['threshold', 'field', 'reference', 'action', 'confirmation', 'omitted', 'dictionary', 'required', 'options', 'unit', 'validation'])
async def test_projected_source_audit_rejects_tampering(session, kind, mutation):
    candidate = saved_candidate(kind=kind)
    await persist(session, [candidate])
    package = package_for([candidate])
    item = (package.route_rules.rules if kind == 'condition' else package.route_rules.process_configurations)[0]
    if mutation == 'threshold':
        item.when.any_conditions[0].all_conditions[2].value = 9
    elif mutation == 'reference':
        item.when.any_conditions[0].all_conditions[2].field = SCOPES[BLIND] + '.it'
    elif mutation == 'field':
        package.input_schema.fields[0].label = '客户声称已确认'
    elif mutation == 'action':
        if kind == 'condition':
            item.then.include_process_ids = ['prepare']
        else:
            item.process_id = 'prepare'
    elif mutation == 'confirmation':
        item.confirmed_by = '其他人'
    elif mutation == 'omitted':
        package.route_rules.rules = []
        package.route_rules.process_configurations = []
    elif mutation == 'dictionary':
        package.factor_dictionary.fields.pop()
    elif mutation == 'required':
        package.input_schema.fields[0].required = True
    elif mutation == 'options':
        package.input_schema.fields[1].options.pop()
    elif mutation == 'unit':
        package.input_schema.fields[2].unit = 'mm'
    else:
        package.input_schema.fields[2].validation.max = 18
    with pytest.raises(HTTPException) as error:
        await audit(package, session)
    assert error.value.status_code == 409
    assert 'drill' in error.value.detail['segment_ids']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
async def test_audited_planner_cannot_mix_feature_direction_and_it_and_shares_thresholds(session, kind):
    candidates = [saved_candidate(kind=kind), saved_candidate('hone', kind=kind, features=[THROUGH], threshold=6)]
    await persist(session, candidates)
    package = package_for(candidates)
    await audit(package, session)
    through, blind = SCOPES[THROUGH], SCOPES[BLIND]
    facts = {through + '.present': True, through + '.direction': 'A侧', through + '.it': 9,
             blind + '.present': True, blind + '.direction': 'B侧', blind + '.it': 6}
    assert plan_route(package, facts).selected_process_ids == ['prepare']
    facts[through + '.it'] = 7
    assert plan_route(package, facts).selected_process_ids == ['prepare', 'drill']
    facts[through + '.it'] = 6
    assert plan_route(package, facts).selected_process_ids == ['prepare', 'drill', 'hone']
    facts[through + '.present'] = False
    assert plan_route(package, facts).selected_process_ids == ['prepare']
    assert validate_rule_package(package).valid
    package.input_schema.fields = [field for field in package.input_schema.fields if field.key != through + '.it']
    assert 'unknown_input_field' in {issue.code for issue in validate_rule_package(package).errors}


@pytest.mark.parametrize('value', [0, -0.1])
def test_shared_ra_requires_strictly_positive_actual_input(value):
    schema = InputSchemaV2(fields=[InputField(key=SCOPES[THROUGH] + '.ra', label='通孔Ra', type='number', unit='μm')])
    assert 'input_ra_invalid' in {issue.code for issue in validate_inputs(schema, {SCOPES[THROUGH] + '.ra': value})}
    assert validate_inputs(schema, {SCOPES[THROUGH] + '.ra': 0.8}) == []


def test_projection_matches_actual_typescript_fixture_without_mutation():
    from pathlib import Path
    from app.services.rule_packages.shared_feature_projection import lower_feature_inputs

    fixture = json.loads((Path(__file__).parent / 'fixtures/shared_feature_projection.json').read_text())
    for case in fixture['cases']:
        original = deepcopy(case['input'])
        assert lower_feature_inputs(case['input']) == case['expected'], case['id']
        assert case['input'] == original, case['id']


def set_when(candidate, node):
    from app.services.rule_packages.contracts import ConditionNode
    if candidate.configuration:
        candidate.configuration.when = ConditionNode.model_validate(node)
    else:
        candidate.when = ConditionNode.model_validate(node)


def package_from_saved_fixture(candidate, case_id):
    """Use independently executed TS output, not the Python implementation."""
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / 'fixtures/shared_feature_projection.json').read_text())
    case = next(case for case in fixture['cases'] if case['id'] == case_id)
    package = package_for([candidate])
    set_when(candidate, case['input']['rules'][0]['when'])
    definitions = {field['key']: field for field in case['input']['fields']}
    candidate.field_definitions = [field.model_copy(update={
        key: value for key, value in definitions[field.key].items()
    }) for field in candidate.field_definitions]
    output = case['expected']
    package.input_schema.fields = [InputField.model_validate(field) for field in output['fields']]
    package.factor_dictionary.fields = deepcopy(package.input_schema.fields)
    item = (package.route_rules.process_configurations or package.route_rules.rules)[0]
    from app.services.rule_packages.contracts import ConditionNode
    item.when = ConditionNode.model_validate(output['rules'][0]['when'])
    return package


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
@pytest.mark.parametrize('case_id', ['normalized-AB', 'scalar-all-directions', 'multiple-feature-predicates-preserved', 'precision-only-preserved'])
async def test_real_source_audit_handles_direction_and_preserved_forms(session, kind, case_id):
    candidate = saved_candidate(kind=kind)
    package = package_from_saved_fixture(candidate, case_id)
    if case_id == 'precision-only-preserved':
        # Historical precision-only confirmations define only that input.
        candidate.field_definitions = [field for field in candidate.field_definitions if field.key.endswith('.it')]
    await persist(session, [candidate])
    await audit(package, session)
    if case_id in ('normalized-AB', 'scalar-all-directions'):
        scope = SCOPES[THROUGH]
        for side in ['A侧', 'B侧', '所有方位']:
            facts = {scope + '.present': True, scope + '.direction': side, scope + '.it': 7}
            assert plan_route(package, facts).selected_process_ids == ['prepare', 'drill']
        assert plan_route(package, {scope + '.present': True, scope + '.direction': '中间', scope + '.it': 7}).selected_process_ids == ['prepare']


@pytest.mark.asyncio
@pytest.mark.parametrize('case_id', ['arbitrary-composite-preserved', 'custom-negation-preserved'])
async def test_shared_schema_cannot_bypass_original_authored_validation(session, case_id):
    candidate = saved_candidate()
    package = package_from_saved_fixture(candidate, case_id)
    # A shared schema must never authorize an unsupported saved authored form,
    # even if the client exports the exact expected preserved expression.
    package.input_schema.fields.extend(InputField.model_validate(field) for field in expected_fields())
    await persist(session, [candidate])
    with pytest.raises(HTTPException) as error:
        await audit(package, session)
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
async def test_saved_direction_options_union_without_changing_original_definitions(session, kind):
    candidates = [saved_candidate(kind=kind, options=['B侧', 'A侧']),
                  saved_candidate('hone', kind=kind, options=['所有方位', 'A侧', '中间'])]
    rows = await persist(session, candidates)
    originals = [row.condition_confirmed_json for row in rows]
    package = package_for(candidates, sides=['B侧', 'A侧', '所有方位', '中间'])
    await audit(package, session)
    assert [row.condition_confirmed_json for row in rows] == originals
    # Client cannot append a plausible but unwitnessed direction.
    from app.services.rule_packages.contracts import InputOption
    package.input_schema.fields[1].options.append(InputOption(value='周边', label='周边'))
    with pytest.raises(HTTPException):
        await audit(package, session)


@pytest.mark.asyncio
@pytest.mark.parametrize('conflict', ['unit', 'allow_custom', 'validation', 'option_label'])
async def test_saved_metadata_conflicts_fail_closed_even_when_client_keeps_first(session, conflict):
    candidates = [saved_candidate(), saved_candidate('hone')]
    field = candidates[1].field_definitions[2]
    if conflict == 'unit':
        field.unit = 'mm'
    elif conflict == 'allow_custom':
        field.allow_custom = True
    elif conflict == 'validation':
        field.validation = {'min': 5, 'max': 9}
    else:
        candidates[1].field_definitions[1].options[0]['label'] = '其他含义'
    await persist(session, candidates)
    with pytest.raises(HTTPException):
        await audit(package_for(candidates), session)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
async def test_actual_executable_revision_persists_projected_rules_and_uses_real_source_audit(session, kind):
    from types import SimpleNamespace
    from app.services.rule_packages.executable_revisions import save_revision, current_revision
    from app.services.rule_packages.contracts import ProcessStepV2

    candidates = [saved_candidate(kind=kind), saved_candidate('hone', kind=kind, threshold=6)]
    await persist(session, candidates)
    package = package_for(candidates)
    segments = []
    for process in package.route_catalog.processes:
        process.steps = [ProcessStepV2(step_id=process.process_id + '.step', name=process.display_name)]
        segments.append({'id': process.process_id, 'normalized_step_name': process.display_name,
                         'source_operation_ids': [], 'step_item_details': [
                             {'id': process.steps[0].step_id, 'text': process.display_name, 'kind': 'primary'}],
                         'doc_coverage': {'hit_docs': 1, 'total_docs': 1}})
    route = await session.get(NormalizedRouteVersion, 1)
    route.route_json = json.dumps(segments, ensure_ascii=False)
    await session.commit()
    project = await session.get(Project, 7)
    body = SimpleNamespace(**{name: getattr(package, name) for name in (
        'manifest', 'factor_dictionary', 'input_schema', 'route_catalog', 'route_rules', 'test_cases')},
        expected_executable_revision=0, route_version_id=1,
        package_name=package.manifest.package_name, rule_report_md='共享输入回归', created_by='审核员')
    revision = await save_revision(session, project, body)
    await session.commit()
    assert (await current_revision(session, 7)).id == revision.id
    stored = RulePackageV2.model_validate_json(revision.package_json)
    assert validate_rule_package(stored).valid
    assert stored.input_schema == package.input_schema
    through = SCOPES[THROUGH]
    assert plan_route(stored, {through + '.present': True, through + '.direction': '所有方位', through + '.it': 7}).selected_process_ids == ['prepare', 'drill']
    # A valid V2 package with a changed threshold still fails the real save audit.
    body.expected_executable_revision = 1
    item = (body.route_rules.rules or body.route_rules.process_configurations)[0]
    item.when.any_conditions[0].all_conditions[2].value = 9
    with pytest.raises(HTTPException) as error:
        await save_revision(session, project, body)
    assert error.value.status_code == 409
    assert 'drill' in error.value.detail['segment_ids']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
async def test_mixed_shared_and_frozen_operation_fields_keep_historical_predicates(session, kind):
    shared = saved_candidate(kind=kind)
    precision = saved_candidate('hone', kind=kind)
    package = package_for([shared, precision])
    frozen_key = 'project_factor.operation_hone.it'
    frozen = {'field': frozen_key, 'op': 'lte', 'value': 6}
    set_when(precision, frozen)
    from app.services.rule_packages.contracts import ConditionNode
    (package.route_rules.process_configurations or package.route_rules.rules)[1].when = ConditionNode.model_validate(frozen)
    definition = InputField.model_validate({key: value for key, value in precision.field_definitions[2].model_dump().items() if key in InputField.model_fields})
    package.input_schema.fields.append(definition)
    package.factor_dictionary.fields.append(definition.model_copy(deep=True))
    await persist(session, [shared, precision])
    await audit(package, session)
    through = SCOPES[THROUGH]
    facts = {through + '.present': True, through + '.direction': 'A侧', through + '.it': 7, frozen_key: 9}
    assert plan_route(package, facts).selected_process_ids == ['prepare', 'drill']
    facts[frozen_key] = 6
    assert plan_route(package, facts).selected_process_ids == ['prepare', 'drill', 'hone']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['condition', 'process_configuration'])
async def test_shared_ra_and_it_are_independent_after_real_audit(session, kind):
    it = saved_candidate(kind=kind)
    ra = saved_candidate('hone', kind=kind, features=[THROUGH], threshold=0.8, suffix='ra')
    package = package_for([it, saved_candidate('hone', kind=kind, features=[THROUGH])])
    from app.services.rule_packages.contracts import ConditionNode
    (package.route_rules.process_configurations or package.route_rules.rules)[1].when = ConditionNode.model_validate(
        expected_when([THROUGH], threshold=0.8, suffix='ra'))
    definition = expected_fields(names=[THROUGH], suffix='ra')[2]
    package.input_schema.fields.append(InputField.model_validate(definition))
    package.factor_dictionary.fields.append(InputField.model_validate(definition))
    await persist(session, [it, ra])
    await audit(package, session)
    scope = SCOPES[THROUGH]
    facts = {scope + '.present': True, scope + '.direction': 'A侧', scope + '.it': 7, scope + '.ra': 1.6}
    assert plan_route(package, facts).selected_process_ids == ['prepare', 'drill']
    facts[scope + '.it'] = 9
    facts[scope + '.ra'] = 0.8
    assert plan_route(package, facts).selected_process_ids == ['prepare', 'hone']
    assert validate_inputs(package.input_schema, facts) == []


@pytest.fixture
def shared_parameter_schema():
    definitions = expected_fields(names=[THROUGH])
    definitions.append(expected_fields(names=[THROUGH], suffix='ra')[2])
    return InputSchemaV2.model_validate({'fields': definitions})


@pytest.mark.parametrize('nested', [False, True])
@pytest.mark.parametrize('missing', ['direction', 'it', 'ra', 'all'])
def test_selected_shared_feature_requires_its_schema_parameters(shared_parameter_schema, nested, missing):
    scope = SCOPES[THROUGH]
    params = {'present': True, 'direction': 'A侧', 'it': 7, 'ra': 0.8}
    omitted = ['direction', 'it', 'ra'] if missing == 'all' else [missing]
    for suffix in omitted:
        params.pop(suffix)
    facts = {'project_factor': {scope.split('.')[1]: params}} if nested else {scope + '.' + key: value for key, value in params.items()}
    before = deepcopy(facts)
    errors = validate_inputs(shared_parameter_schema, facts)
    assert {(error.code, error.field, error.path) for error in errors} == {
        ('required_input_missing', scope + '.' + suffix, 'inputs.' + scope + '.' + suffix)
        for suffix in omitted}
    assert facts == before


@pytest.mark.parametrize('facts', [{}, {SCOPES[THROUGH] + '.present': False}])
def test_absent_or_false_shared_feature_accepts_omitted_parameters(shared_parameter_schema, facts):
    assert validate_inputs(shared_parameter_schema, facts) == []


def test_selected_shared_feature_accepts_filled_parameters(shared_parameter_schema):
    scope = SCOPES[THROUGH]
    assert validate_inputs(shared_parameter_schema, {
        scope + '.present': True, scope + '.direction': 'A侧', scope + '.it': 7, scope + '.ra': 0.8,
    }) == []


def test_shared_feature_it_rejects_decimal_without_an_explicit_unit(shared_parameter_schema):
    scope = SCOPES[THROUGH]
    for field in shared_parameter_schema.fields:
        if field.key == scope + '.it':
            field.unit = None
    errors = validate_inputs(shared_parameter_schema, {
        scope + '.present': True,
        scope + '.direction': 'A侧',
        scope + '.it': 6.5,
        scope + '.ra': 0.8,
    })
    assert [(issue.code, issue.field) for issue in errors] == [
        ('input_it_invalid', scope + '.it'),
    ]


@pytest.mark.parametrize('suffix,bad', [('present', 'true'), ('present', 1), ('direction', 1), ('it', '7'), ('it', True), ('ra', '0.8')])
def test_shared_parameter_wrong_types_keep_existing_errors(shared_parameter_schema, suffix, bad):
    scope = SCOPES[THROUGH]
    facts = {scope + '.present': True, scope + '.direction': 'A侧', scope + '.it': 7, scope + '.ra': 0.8}
    facts[scope + '.' + suffix] = bad
    assert [(issue.code, issue.field) for issue in validate_inputs(shared_parameter_schema, facts)] == [
        ('input_type_mismatch', scope + '.' + suffix)]


def test_shared_parameter_requirement_does_not_expand_schema_or_affect_custom_fields():
    scope = SCOPES[THROUGH]
    schema = InputSchemaV2.model_validate({'fields': [
        {'key': scope + '.present', 'label': '通孔', 'type': 'boolean'},
        {'key': scope + '.it', 'label': 'IT', 'type': 'number', 'unit': 'IT'},
        {'key': 'custom.present', 'label': '自定义开关', 'type': 'boolean'},
        {'key': 'custom.direction', 'label': '自定义方位', 'type': 'string'},
        {'key': 'project_factor.operation_legacy.it', 'label': '历史IT', 'type': 'number'},
        {'key': 'project_factor.feature_legacy.direction', 'label': '无共享开关的既有字段', 'type': 'string'},
        {'key': 'custom.required', 'label': '自定义必填', 'type': 'string', 'required': True},
    ]})
    assert validate_inputs(schema, {scope + '.present': True, scope + '.it': 7,
                                    'custom.present': True, 'custom.required': '已填'}) == []
    assert [(issue.code, issue.field) for issue in validate_inputs(schema, {})] == [
        ('required_input_missing', 'custom.required')]


@pytest.mark.parametrize('selected', [False, True])
def test_shared_presence_controls_required_metadata_only_for_its_own_scope(shared_parameter_schema, selected):
    for field in shared_parameter_schema.fields:
        if not field.key.endswith('.present'):
            field.required = True
    blind = expected_fields(names=[BLIND])
    shared_parameter_schema.fields.extend(InputField.model_validate(field) for field in blind)
    scope = SCOPES[THROUGH]
    facts = {scope + '.present': selected, SCOPES[BLIND] + '.present': False}
    issues = validate_inputs(shared_parameter_schema, facts)
    assert {issue.field for issue in issues} == ({scope + '.' + suffix for suffix in ['direction', 'it', 'ra']} if selected else set())


def actual_compile_cases():
    from pathlib import Path
    return json.loads((Path(__file__).parent / 'fixtures/shared_feature_compile_requests.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.asyncio
@pytest.mark.parametrize('case', actual_compile_cases(), ids=lambda case: case['id'])
async def test_actual_question_and_editor_requests_compile_audit_and_save(session, case):
    from types import SimpleNamespace
    from app.services.rule_packages.compiler import compile_rule_package
    from app.services.rule_packages.contracts import CompileRulePackageRequest
    from app.services.rule_packages.executable_revisions import save_revision, current_revision

    package = compile_rule_package(CompileRulePackageRequest.model_validate(case['request']))
    validation = validate_rule_package(package)
    assert validation.valid, [(error.code, error.path, error.message) for error in validation.errors]
    candidates = [RuleConditionCandidate.model_validate(card['conditionReview']['confirmed']) for card in case['cards']]
    rows = await persist(session, candidates)
    for row, card in zip(rows, case['cards']):
        row.condition_source_text = card['conditionText']
        row.condition_confirmed_by = card['conditionReview']['confirmed_by']
    segments = []
    for process in package.route_catalog.processes:
        card = next((card for card in case['cards'] if card['segment']['id'] == process.process_id), None)
        segment = card['segment'] if card else {
            'id': process.process_id, 'export_process_id': process.process_id,
            'normalized_step_name': process.display_name, 'sequence': 0,
            'doc_coverage': {'total_docs': 2, 'hit_docs': 2}, 'source_nodes': [],
        }
        segments.append({**segment, 'source_operation_ids': [], 'step_item_details': [
            {'id': step.step_id, 'text': step.name, 'kind': 'primary'} for step in process.steps]})
    route = await session.get(NormalizedRouteVersion, 1)
    route.route_json = json.dumps(segments, ensure_ascii=False)
    await session.commit()
    originals = [row.condition_confirmed_json for row in rows]
    await audit(package, session)
    project = await session.get(Project, 7)
    body = SimpleNamespace(**{name: getattr(package, name) for name in (
        'manifest', 'factor_dictionary', 'input_schema', 'route_catalog', 'route_rules', 'test_cases')},
        expected_executable_revision=0, route_version_id=1,
        package_name=package.manifest.package_name, rule_report_md='真实构建器回归', created_by='隔离回归')
    revision = await save_revision(session, project, body)
    await session.commit()
    assert (await current_revision(session, 7)).id == revision.id
    assert [row.condition_confirmed_json for row in rows] == originals
