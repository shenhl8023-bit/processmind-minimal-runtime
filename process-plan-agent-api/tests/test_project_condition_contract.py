"""Current-project candidates stay distinct from legacy package definitions."""

import pytest

from app.routers.rule_packages import get_condition_fields
from app.services.rule_packages import condition_registry as registry
from app.services.rule_packages.condition_contracts import CanonicalConditionField
from app.services.rule_packages.contracts import ConditionNode, InputSchemaV2
from app.services.rule_packages.expression_engine import evaluate_condition
from app.services.rule_packages.input_validation import validate_inputs


@pytest.mark.parametrize('direction,matched', [('A侧', True), ('B侧', True), ('中间', False), ('周边', False)])
def test_newly_authored_all_directions_is_only_the_a_b_range(direction, matched):
    from app.services.rule_packages.condition_contracts import RuleConditionCandidate
    from app.services.rule_packages.project_conditions import normalize_project_authored_candidate
    fields = registry.project_condition_fields('drill', '钻孔')
    feature = next(field for field in fields if field.key.endswith('.features'))
    position = next(field for field in fields if field.key.endswith('.direction'))
    candidate = RuleConditionCandidate.model_validate({
        'kind': 'process_configuration',
        'configuration': {'process_id': 'drill', 'occurrence': 'conditional', 'when': {'all': [
            {'field': feature.key, 'op': 'contains_any', 'value': ['孔(通孔)']},
            {'field': position.key, 'op': 'eq', 'value': '所有方位'},
        ]}},
        'field_definitions': [feature.model_dump(), position.model_dump()],
    })
    result = normalize_project_authored_candidate(candidate)
    assert evaluate_condition(result.configuration.when, {feature.key: ['孔(通孔)'], position.key: direction}).matched is matched
    assert position.key in {field.key for field in result.field_definitions}


def test_project_field_labels_are_neutral_but_node_scopes_and_domains_stay_distinct():
    first = registry.project_condition_fields('drill', '钻孔')
    second = registry.project_condition_fields('drill-two', '钻孔')
    assert [field.label for field in first] == [
        '加工对象的特征', '同一加工对象的方位',
        '孔、孔(盲孔)、孔(通孔)、内圆柱面的实际尺寸精度等级',
        '孔、孔(盲孔)、孔(通孔)、内圆柱面的实际Ra要求值',
        '材料牌号', '目标硬度制', '目标硬度下限（含）', '目标硬度上限（含）',
        '当前部位是否有明确钻孔要求',
    ]
    assert [field.label for field in second] == [field.label for field in first]
    for one, two in zip(first, second):
        assert (one.type, one.operators, one.options, one.unit, one.validation) == (
            two.type, two.operators, two.options, two.unit, two.validation)
        if one.key != 'project_factor.material_grade':
            assert one.key != two.key
            assert '工序=drill' in one.source


@pytest.mark.parametrize('value', [7.5, -2, 19])
def test_authored_project_it_threshold_is_an_it_grade_not_a_decimal(value):
    fields = registry.project_condition_fields('grind', '磨外圆')
    definition = next(field for field in fields if field.key.endswith('.it'))
    assert registry.validate_condition_tree(ConditionNode(field=definition.key, op='lte', value=value), {definition.key: definition})


def test_authored_target_hardness_requires_the_entire_interval_and_its_scale():
    fields = {field.key: field for field in registry.project_condition_fields('quench', '淬火')}
    key = next(key for key in fields if key.endswith('.hardness_min'))
    assert any('完整' in issue for issue in registry.validate_condition_tree(ConditionNode(field=key, op='gte', value=55), fields))


def test_condition_values_follow_the_candidates_own_frozen_domain():
    definition = next(field for field in registry.project_condition_fields('drill', '钻孔') if field.key.endswith('.features'))
    when = ConditionNode(field=definition.key, op='contains_any', value=['未确认的新特征'])
    assert registry.validate_condition_tree(when, {definition.key: definition})
    definition.options = [{'value': '未确认的新特征', 'label': '已冻结旧候选'}]
    assert registry.validate_condition_tree(when, {definition.key: definition}) == []


@pytest.mark.parametrize('process_name', ['淬火', '渗氮', '硬质阳极化', '去毛刺', '清洗', '终检验'])
def test_requirement_fields_are_owned_by_the_exact_operation_and_repeated_node(process_name):
    one = registry.project_condition_fields('node-one', process_name)
    two = registry.project_condition_fields('node-two', process_name)
    first = [field for field in one if field.key.endswith('.requirement')]
    second = next(field for field in two if field.key.endswith('.requirement'))
    assert len(first) == 1
    assert process_name in first[0].label
    assert first[0].key != second.key
    assert first[0].operators == ['eq']


@pytest.mark.parametrize('actual,status,included', [(4, 422, False), (11, 422, False), (7.5, 422, False), (6, 200, True), (8, 200, False)])
def test_simulation_api_enforces_actual_it_and_evaluates_it7_boundary(actual, status, included):
    from fastapi.testclient import TestClient
    from app.main import app
    key = 'project_factor.operation_a.it'
    package = {
        'manifest': {'package_name': 'IT boundary', 'project_id': 1, 'scope': {'key': '1'}},
        'input_schema': {'fields': [{'key': key, 'label': '实际精度', 'type': 'number', 'unit': 'IT', 'validation': {'min': 1, 'max': 18}}]},
        'route_catalog': {'processes': [{'process_id': 'base', 'display_name': '准备', 'main': True}, {'process_id': 'grind', 'display_name': '磨外圆'}]},
        'route_rules': {'rules': [{'rule_id': 'grind-it', 'when': {'field': key, 'op': 'lte', 'value': 7}, 'then': {'include_process_ids': ['grind']}}]},
        'test_cases': [{'case_id': 'positive', 'input': {key: 6}, 'expect': {'included_process_ids': ['base', 'grind']}}],
    }
    response = TestClient(app).post('/api/extract/finalized-rule-packages/simulate', json={'package': package, 'inputs': {key: actual}})
    assert response.status_code == status, response.text
    if status == 200:
        assert ('grind' in response.json()['plan']['selected_process_ids']) is included


@pytest.mark.asyncio
async def test_editor_registry_excludes_retired_candidates_without_breaking_legacy_validation():
    response = await get_condition_fields()
    keys = {field.key for field in response.fields}
    assert not any(key.startswith(('tolerance.', 'geometry.')) for key in keys)
    assert not keys & {'precision.grades', 'special.requirements', 'cad.features'}
    assert registry.validate_condition_tree(ConditionNode(field='tolerance.roundness_mm', op='lte', value=.01)) == []


def test_project_candidates_expose_full_drilling_domain_and_all_twelve_expressions():
    fields = registry.project_condition_fields('drill', '钻孔')
    features = next(field for field in fields if field.key.endswith('.features'))
    assert [option['value'] for option in features.options] == ['孔', '孔(盲孔)', '孔(通孔)', '内圆柱面']
    assert features.operators == ['contains_any']
    direction = next(field for field in fields if field.key.endswith('.direction'))
    assert [option['value'] for option in direction.options] == ['A侧', 'B侧', '中间', '周边', '所有方位']
    assert direction.operators == ['eq']
    assert set(registry.PROJECT_CONDITION_EXPRESSIONS) == {'C01a', 'C01b', 'J01', 'J02', 'R01', 'R02', 'R03', 'B01', 'B02', 'M01', 'Q01', 'Y01'}


def test_feature_and_direction_cannot_be_combined_from_two_different_objects():
    fields = {key: CanonicalConditionField(key=key, label=key, category='加工对象', type=kind, operators=[op])
              for key, kind, op in [
                  ('project_factor.operation_a.features', 'multi_select', 'contains_any'),
                  ('project_factor.operation_b.direction', 'single_select', 'eq')]}
    when = ConditionNode.model_validate({'all': [
        {'field': 'project_factor.operation_a.features', 'op': 'contains_any', 'value': ['孔(盲孔)', '孔(通孔)']},
        {'field': 'project_factor.operation_b.direction', 'op': 'eq', 'value': '周边'},
    ]})
    assert any('同一加工对象' in issue for issue in registry.validate_condition_tree(when, fields))


@pytest.mark.parametrize('features,direction,other_direction,matched', [
    (['孔(盲孔)'], '周边', 'A侧', True),
    (['孔(通孔)'], '周边', 'A侧', True),
    (['孔'], '周边', 'A侧', False),
    (['孔(盲孔)'], 'A侧', '周边', False),
])
def test_drilling_any_feature_and_direction_match_the_same_object(features, direction, other_direction, matched):
    scope = 'project_factor.operation_1a78c49e'
    when = ConditionNode.model_validate({'all': [
        {'field': scope + '.features', 'op': 'contains_any', 'value': ['孔(盲孔)', '孔(通孔)']},
        {'field': scope + '.direction', 'op': 'eq', 'value': '周边'},
    ]})
    inputs = {'project_factor': {'operation_1a78c49e': {'features': features, 'direction': direction},
                                'operation_other': {'direction': other_direction}}}
    assert evaluate_condition(when, inputs).matched is matched


@pytest.mark.parametrize('value', [4, 11, 7.5, True, 'IT7', '7', float('nan'), float('inf')])
def test_actual_project_it_rejects_invalid_values_even_if_old_rule_definition_allows_them(value):
    schema = InputSchemaV2(fields=[{'key': 'project_factor.operation_a.it', 'label': '实际精度', 'type': 'number', 'unit': 'IT', 'validation': {'min': 1, 'max': 18}}])
    errors = validate_inputs(schema, {'project_factor': {'operation_a': {'it': value}}})
    assert errors


@pytest.mark.parametrize('key,unit', [('precision.dimension_it', None), ('project_factor.precision_for_object', 'IT')])
@pytest.mark.parametrize('value', [4, 11, 7.5])
def test_actual_it_semantics_also_cover_legacy_and_explicit_unit_fields(key, unit, value):
    schema = InputSchemaV2(fields=[{'key': key, 'label': '实际精度', 'type': 'number', 'unit': unit}])
    assert validate_inputs(schema, {key: value})


@pytest.mark.parametrize('value,matched', [(5, True), (6, True), (7, True), (8, False), (9, False), (10, False)])
def test_legal_actual_it_values_are_independent_of_rule_threshold(value, matched):
    key = 'project_factor.operation_a.it'
    schema = InputSchemaV2(fields=[{'key': key, 'label': '实际精度', 'type': 'number', 'unit': 'IT'}])
    assert validate_inputs(schema, {key: value}) == []
    assert evaluate_condition(ConditionNode(field=key, op='lte', value=7), {key: value}).matched is matched
