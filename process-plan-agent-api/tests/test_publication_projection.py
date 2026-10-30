"""Publication must not turn unfinished geometry mappings into executable work."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from app.services.rule_packages.contracts import ProcessConfigurationV2, RulePackageV2
from app.services.rule_packages.demo_tables import DemoTableError, validate_demo_tables


def process(pid, steps=(), *, auxiliary=False):
    return {"process_id": pid, "process_name": pid, "process_type": "辅助工序" if auxiliary else "加工工序",
            "precision": "辅助工序" if auxiliary else "粗加工", "steps": list(steps)}


def step(sid, candidates):
    return {"step_id": sid, "step_name": sid, "candidates": candidates}


def tables(route, rules=None, factors=()):
    return {"full_route_table": route, "factor_table": list(factors),
            "rule_table": rules if rules is not None else [{"target": p["process_id"], "required": True} for p in route]}


def authoring(data, *, requires=None, relations=()):
    return RulePackageV2.model_validate({
        "manifest": {"package_name": "projection", "project_id": 1, "scope": {"key": "1"}},
        "input_schema": {"fields": []},
        "route_catalog": {"processes": [{
            "process_id": p["process_id"], "display_name": p["process_name"], "main": True,
            "default_sequence": index * 10,
            "steps": [{"step_id": s["step_id"], "name": s["step_name"]} for s in p["steps"]],
            "constraints": {"requires": (requires or {}).get(p["process_id"], [])},
        } for index, p in enumerate(data["full_route_table"])]},
        "route_rules": {"rules": [], "process_relations": list(relations)},
    })


def project(data, package=None):
    from app.services.rule_packages.publication_projection import project_publication_tables
    return project_publication_tables(data, package or authoring(data))


@pytest.fixture
def engine_class():
    path = Path('/Users/zhaoyongwei/Desktop/KmAI-Win7-SP1-x64-20261018-r24/KmMpsMcpServer/skills/process-route-generator/scripts/config_route_engine.py')
    if not path.is_file():
        pytest.skip('Actual KMAI engine unavailable')
    spec = importlib.util.spec_from_file_location('projection_kmai_engine', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ConfigRouteEngine


def test_export_keeps_mapped_steps_and_auxiliary_but_not_unmapped_machining():
    data = tables([
        process('clean', auxiliary=True),
        process('turn', [step('outer', {'A侧/外圆': ['外圆柱面']}), step('thread', {})]),
        process('lap', [step('center', {})]),
        process('inspect', auxiliary=True),
    ])
    original = deepcopy(data)
    output, report = project(data)
    assert [p['process_id'] for p in output['full_route_table']] == ['clean', 'turn', 'inspect']
    assert [s['step_id'] for s in output['full_route_table'][1]['steps']] == ['outer']
    assert output['rule_table'] == [{'target': 'clean', 'required': True},
                                    {'target': 'turn', 'when': True},
                                    {'target': 'inspect', 'required': True}]
    assert report['original_process_count'] == 4
    assert report['exported_process_count'] == 3
    assert report['original_step_count'] == 3
    assert report['exported_step_count'] == 1
    assert [p['process_id'] for p in report['excluded_processes']] == ['lap']
    assert [s['step_id'] for s in report['excluded_steps']] == ['thread', 'center']
    assert data == original
    validate_demo_tables(output)


def test_empty_feature_list_is_not_an_effective_mapping():
    output, _ = project(tables([process('bad', [step('s', {'A侧/孔': []})]), process('clean', auxiliary=True)]))
    assert [p['process_id'] for p in output['full_route_table']] == ['clean']


def test_no_deliverable_process_reports_missing_mapping_instead_of_an_empty_package():
    with pytest.raises(DemoTableError) as error:
        project(tables([process('unmapped', [step('s', {})])]))
    assert error.value.issues[0]['code'] == 'empty_export_route'


def test_removed_trigger_chain_cannot_publish_a_permanently_empty_delivery():
    from app.services.rule_packages.demo_tables import compile_demo_tables
    data = tables([process('gone', [step('s', {})]), process('rinse', auxiliary=True), process('inspect', auxiliary=True)])
    package = authoring(data, relations=[
        {'relation_id': 'wash', 'relation_type': 'trigger_after', 'source_process_ids': ['gone'], 'target_process_ids': ['rinse']},
        {'relation_id': 'check', 'relation_type': 'trigger_after', 'source_process_ids': ['rinse'], 'target_process_ids': ['inspect']},
    ])
    for p in package.route_catalog.processes[1:]:
        p.main = False
    with pytest.raises(DemoTableError) as error:
        project(compile_demo_tables(package, data['full_route_table']), package)
    assert error.value.issues[0]['code'] == 'empty_export_route'


def test_negating_a_permanently_disabled_process_keeps_a_viable_auxiliary(engine_class):
    data = tables([process('gone', [step('s', {})]), process('rinse', auxiliary=True), process('inspect', auxiliary=True)], [
        {'target': 'gone', 'required': True},
        {'target': 'rinse', 'when': {'field': 'selected_processes', 'op': 'contains', 'value': 'gone'}},
        {'target': 'inspect', 'when': {'not': {'field': 'selected_processes', 'op': 'contains', 'value': 'rinse'}}},
    ])
    output, _ = project(data)
    assert output['rule_table'] == [{'target': 'rinse', 'when': False}, {'target': 'inspect', 'when': True}]
    engine = engine_class(output['factor_table'], output['full_route_table'], output['rule_table'])
    assert [p['process_name'] for p in engine.run({})['route']] == ['inspect']


@pytest.mark.parametrize('match', ['all', 'any'])
@pytest.mark.parametrize('configured', [False, True])
def test_requires_relation_needs_every_source_even_when_source_match_is_any(match, configured):
    data = tables([process('gone', [step('s1', {})]),
                   process('present', [step('s2', {'A侧/孔': ['孔']})]), process('inspect', auxiliary=True)])
    package = authoring(data, relations=[{'relation_id': 'req', 'relation_type': 'requires',
                                         'source_process_ids': ['gone', 'present'], 'target_process_ids': ['inspect'],
                                         'source_match': match}])
    if configured:
        relation = package.route_rules.process_relations.pop()
        package.route_rules.process_configurations = [ProcessConfigurationV2.model_validate({
            'process_id': 'inspect', 'occurrence': 'always', 'relations': [{
                key: getattr(relation, key) for key in ('relation_type', 'source_process_ids', 'target_process_ids', 'source_match')
            }],
        })]
    with pytest.raises(DemoTableError) as error:
        project(data, package)
    assert error.value.issues[0]['prerequisite_process_ids'] == ['gone']


@pytest.mark.parametrize('match', ['all', 'any'])
@pytest.mark.parametrize('configured', [False, True])
def test_requires_relation_waits_for_every_source_in_actual_kmai(engine_class, match, configured):
    from app.services.rule_packages.demo_tables import compile_demo_tables
    data = tables([
        process('turn', [step('outer', {'A侧/外圆': ['外圆柱面']})]),
        process('slot', [step('mill', {'周边/槽': ['通槽']})]),
        process('inspect', auxiliary=True),
    ])
    package = authoring(data, relations=[{'relation_id': 'req', 'relation_type': 'requires',
                                         'source_process_ids': ['turn', 'slot'], 'target_process_ids': ['inspect'],
                                         'source_match': match}])
    if configured:
        relation = package.route_rules.process_relations.pop()
        package.route_rules.process_configurations = [ProcessConfigurationV2.model_validate({
            'process_id': 'inspect', 'occurrence': 'always', 'relations': [{
                key: getattr(relation, key) for key in ('relation_type', 'source_process_ids', 'target_process_ids', 'source_match')
            }],
        })]
    output, _ = project(compile_demo_tables(package, data['full_route_table']), package)
    engine = engine_class(output['factor_table'], output['full_route_table'], output['rule_table'])
    turning = {'group_path': 'A侧/外圆', 'features': [{'feature_select': '外圆柱面'}]}
    slotting = {'group_path': '周边/槽', 'features': [{'feature_select': '通槽'}]}
    assert [p['process_name'] for p in engine.run({'input_json': [turning]})['route']] == ['turn']
    assert [p['process_name'] for p in engine.run({'input_json': [turning, slotting]})['route']] == ['turn', 'slot', 'inspect']


def test_repeated_auxiliary_names_and_order_are_preserved():
    data = tables([process('clean1', auxiliary=True), process('clean2', auxiliary=True)])
    for p in data['full_route_table']:
        p['process_name'] = '清洗'
    output, _ = project(data)
    assert [p['process_id'] for p in output['full_route_table']] == ['clean1', 'clean2']


@pytest.mark.parametrize('condition,expected', [
    ({'all': [{'field': 'selected_processes', 'op': 'contains', 'value': 'gone'}, {'field': 'flag', 'op': 'eq', 'value': True}]}, False),
    ({'any': [{'field': 'selected_processes', 'op': 'contains', 'value': 'gone'}, {'field': 'flag', 'op': 'eq', 'value': True}]}, {'field': 'flag', 'op': 'eq', 'value': True}),
    ({'not': {'field': 'selected_processes', 'op': 'contains', 'value': 'gone'}}, True),
    ({'some': {'field': 'selected_processes', 'op': 'contains', 'value': 'gone'}}, False),
])
def test_removed_dependency_is_false_without_broadening_all_or_any(condition, expected):
    data = tables([process('gone', [step('s', {})]), process('next', auxiliary=True), process('clean', auxiliary=True)],
                  [{'target': 'gone', 'required': True}, {'target': 'next', 'when': condition}, {'target': 'clean', 'required': True}],
                  [{'key': 'flag', 'label': 'flag', 'type': 'bool', 'source': 'manual_defaults.flag', 'visible': True}])
    output, _ = project(data)
    assert output['rule_table'] == [{'target': 'next', 'when': expected}, {'target': 'clean', 'required': True}]
    validate_demo_tables(output)


def test_only_factors_made_unused_by_projection_are_removed():
    fs = [{'key': key, 'label': key, 'type': 'bool', 'source': f'manual_defaults.{key}', 'visible': True}
          for key in ['gone_switch', 'shared', 'public_input']]
    data = tables([process('gone', [step('s', {})]), process('clean', auxiliary=True)], [
        {'target': 'gone', 'when': {'field': 'gone_switch', 'op': 'eq', 'value': True}},
        {'target': 'clean', 'when': {'field': 'shared', 'op': 'eq', 'value': True}},
    ], fs)
    output, report = project(data)
    assert [f['key'] for f in output['factor_table']] == ['shared', 'public_input']
    assert report['removed_factor_keys'] == ['gone_switch']


def test_removed_required_prerequisite_blocks_publication():
    data = tables([process('gone', [step('s', {})]), process('inspect', auxiliary=True)])
    with pytest.raises(DemoTableError) as error:
        project(data, authoring(data, requires={'inspect': ['gone']}))
    assert error.value.issues[0]['code'] == 'unmapped_required_process'
    assert error.value.issues[0]['process_id'] == 'inspect'


def test_required_prerequisite_gates_auxiliary_when_geometry_does_not_match(engine_class):
    data = tables([process('turn', [step('s', {'A侧/外圆': ['外圆柱面']})]), process('inspect', auxiliary=True)])
    output, _ = project(data, authoring(data, requires={'inspect': ['turn']}))
    engine = engine_class(output['factor_table'], output['full_route_table'], output['rule_table'])
    assert engine.run({'input_json': [{'group_path': '周边/孔', 'features': [{'feature_select': '孔'}]}]})['route'] == []
    result = engine.run({'input_json': [{'group_path': 'A侧/外圆', 'features': [{'feature_select': '外圆柱面'}]}]})
    assert [p['process_name'] for p in result['route']] == ['turn', 'inspect']


def test_required_machining_has_no_empty_process_and_does_not_enable_unmapped_threads(engine_class):
    data = tables([process('turn', [step('outer', {'A侧/外圆': ['外圆柱面']}), step('thread', {})]),
                   process('slot', [step('mill', {'周边/槽': ['通槽']})]), process('clean', auxiliary=True)])
    output, _ = project(data)
    engine = engine_class(output['factor_table'], output['full_route_table'], output['rule_table'])
    result = engine.run({'input_json': [{'group_path': '周边/槽/', 'features': [{'feature_select': '通槽'}]}]})
    assert [p['process_name'] for p in result['route']] == ['slot', 'clean']
    assert result['route'][0]['steps'][0]['step_name'] == 'mill'
    result = engine.run({'input_json': [{'group_path': 'A侧/外圆/', 'features': [{'feature_select': '外圆柱面'}]}]})
    assert [s['step_name'] for s in result['route'][0]['steps']] == ['outer']


@pytest.mark.parametrize('group,feature,expected', [
    ('普通孔组', '孔', 0), ('普通孔组', '孔(通孔)', 1),
    ('中间通孔', '孔', 1), ('中间通孔', '孔(通孔)', 1),
    ('中间通孔', '孔(盲孔)', 0), ('假中间通孔', '孔', 0),
])
def test_specific_hole_type_uses_only_explicit_type_or_reviewed_group_context(engine_class, group, feature, expected):
    data = tables([process('drill', [step('through', {group: ['孔(通孔)']})])])
    output, _ = project(data)
    engine = engine_class(output['factor_table'], output['full_route_table'], output['rule_table'])
    result = engine.run({'input_json': [{'group_path': group, 'features': [{'feature_select': feature}]}]})
    assert len(result['route']) == expected
