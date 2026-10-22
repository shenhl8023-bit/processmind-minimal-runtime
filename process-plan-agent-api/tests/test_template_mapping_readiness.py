from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.services.rule_packages import template_mapping_requirements as subject


def package():
    return SimpleNamespace(route_rules=SimpleNamespace(rules=[], process_relations=[]), manifest=SimpleNamespace(project_id=1), route_catalog=SimpleNamespace(processes=[
        SimpleNamespace(process_id='a', display_name='车', source_operation_ids=[7], template_group_aliases=[], main=True, steps=[]),
        SimpleNamespace(process_id='b', display_name='包装', source_operation_ids=[8], template_group_aliases=[], main=True, steps=[]),
    ]))


def template(step=True, **changes):
    result = dict(tree=[dict(path=['外圆'], children=[], feature_selections=['外圆柱面'])], mappings=[], step_mappings=[])
    if step:
        result['step_mappings'] = [SimpleNamespace(source_operation_id=7, source_step_order=1, status='confirmed', template_group_path=['外圆'], candidate_features=['外圆柱面'], source_step_name='车外圆')]
    result.update(changes)
    return SimpleNamespace(**result)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['partial_step', 'partial_legacy', 'deleted_path', 'deleted_feature', 'deleted_source', 'zero', 'unconfirmed'])
async def test_requires_one_valid_mapping_only(monkeypatch, kind):
    current = template()
    if kind == 'partial_legacy':
        current = template(False, mappings=[SimpleNamespace(source_operation_id=7, template_group_path=['外圆'], feature_selections=['外圆柱面'])])
    if kind == 'deleted_path': current.tree = []
    if kind == 'deleted_feature': current.step_mappings[0].candidate_features = ['不存在']
    if kind == 'deleted_source': current.step_mappings[0].source_operation_id = 999
    if kind == 'zero': current = template(False)
    if kind == 'unconfirmed': current.step_mappings[0].status = 'draft'
    monkeypatch.setattr(subject, 'get_project_group_template', AsyncMock(return_value=object()))
    monkeypatch.setattr(subject, 'serialize_project_group_template', lambda _: current)
    monkeypatch.setattr(subject, '_load_source_step_items', AsyncMock(return_value={7: ['车外圆']}), raising=False)
    blockers = await subject.validate_rule_package_template_mapping(None, package())
    assert bool(blockers) == (kind not in ('partial_step', 'partial_legacy'))


@pytest.mark.asyncio
async def test_requires_at_least_one_valid_feature_mapping_per_template_leaf(monkeypatch):
    current = template()
    current.tree.append(dict(path=['内孔'], children=[], feature_selections=['内孔柱面']))
    package_with_two_groups = package()
    monkeypatch.setattr(subject, 'get_project_group_template', AsyncMock(return_value=object()))
    monkeypatch.setattr(subject, 'serialize_project_group_template', lambda _: current)
    monkeypatch.setattr(subject, '_load_source_step_items', AsyncMock(return_value={7: ['车外圆']}), raising=False)

    blockers = await subject.validate_rule_package_template_mapping(None, package_with_two_groups)

    assert len(blockers) == 1
    assert blockers[0].code == 'group_template_mapping_missing'
    assert '内孔' in blockers[0].message


@pytest.mark.asyncio
async def test_each_leaf_is_satisfied_by_any_valid_feature_mapping(monkeypatch):
    current = template()
    current.tree.append(dict(path=['内孔'], children=[], feature_selections=['内孔柱面']))
    second = SimpleNamespace(source_operation_id=7, source_step_order=1, status='confirmed',
                             template_group_path=['内孔'], candidate_features=['内孔柱面'], source_step_name='车外圆')
    current.step_mappings.append(second)
    monkeypatch.setattr(subject, 'get_project_group_template', AsyncMock(return_value=object()))
    monkeypatch.setattr(subject, 'serialize_project_group_template', lambda _: current)
    monkeypatch.setattr(subject, '_load_source_step_items', AsyncMock(return_value={7: ['车外圆']}), raising=False)

    blockers = await subject.validate_rule_package_template_mapping(None, package())

    assert blockers == []


@pytest.mark.asyncio
@pytest.mark.parametrize('source_steps,order,name,expected', [
    (['车外圆（留余量）'], 1, '车外圆（留余量）', True),
    (['车外圆'], 2, '车外圆', False),
    ([], 1, '已删除工步', False),
    (['车端面', '车外圆'], 1, '车外圆', False),
    ([' 车外圆 '], 1, '车外圆', True),
])
async def test_validates_original_step_identity_not_package_display_name(monkeypatch, source_steps, order, name, expected):
    current = template()
    current.step_mappings[0].source_step_order = order
    current.step_mappings[0].source_step_name = name
    current_package = package()
    current_package.route_catalog.processes[0].steps = [SimpleNamespace(name='车外圆')]
    monkeypatch.setattr(subject, 'get_project_group_template', AsyncMock(return_value=object()))
    monkeypatch.setattr(subject, 'serialize_project_group_template', lambda _: current)
    monkeypatch.setattr(subject, '_load_source_step_items', AsyncMock(return_value={7: source_steps}), raising=False)
    blockers = await subject.validate_rule_package_template_mapping(None, current_package)
    assert (not blockers) is expected
