from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.rule_packages import template_mapping_requirements as subject


@pytest.mark.asyncio
@pytest.mark.parametrize('change,ready', [
    ('valid', True), ('removed_process', False), ('removed_step', False),
    ('removed_candidate', False), ('other_process_source', False), ('auxiliary_target', False),
])
async def test_final_mapping_must_still_belong_to_current_route(monkeypatch, change, ready):
    process = SimpleNamespace(process_id='final_turning', source_operation_ids=[7], template_group_aliases=[],
                              steps=[SimpleNamespace(step_id='final_hole')])
    package = SimpleNamespace(manifest=SimpleNamespace(project_id=1),
                              route_catalog=SimpleNamespace(processes=[process]))
    mapping = SimpleNamespace(source_operation_id=7, source_step_order=1, source_step_name='钻孔',
                              status='confirmed', template_group_path=['A侧', '孔'], candidate_features=['孔'],
                              final_targets=[{'process_id': 'final_turning', 'step_id': 'final_hole'}])
    template = SimpleNamespace(tree=[{'path': ['A侧', '孔'], 'children': [], 'feature_selections': ['孔']}],
                               mappings=[], step_mappings=[mapping], mapping_output=[{
                                   'process_id': 'final_turning', 'steps': [
                                       {'step_id': 'final_hole', 'candidates': {'A侧/孔': ['孔']}}
                                   ]
                               }])
    if change == 'removed_process':
        mapping.final_targets[0]['process_id'] = 'old_process'
    elif change == 'removed_step':
        process.steps = []
    elif change == 'removed_candidate':
        template.mapping_output[0]['steps'][0]['candidates'] = {}
    elif change == 'other_process_source':
        process.source_operation_ids = [8]
        package.route_catalog.processes.append(SimpleNamespace(process_id='other', source_operation_ids=[7],
                                                               template_group_aliases=[], steps=[]))
    elif change == 'auxiliary_target':
        template.mapping_output[0]['process_type'] = '辅助工序'
    monkeypatch.setattr(subject, 'get_project_group_template', AsyncMock(return_value=object()))
    monkeypatch.setattr(subject, 'serialize_project_group_template', lambda _: template)
    monkeypatch.setattr(subject, '_load_source_step_items', AsyncMock(return_value={7: ['钻孔']}))

    blockers = await subject.validate_rule_package_template_mapping(None, package)

    assert (not blockers) is ready


@pytest.mark.asyncio
async def test_source_catalog_appends_attached_steps_after_primary_steps(monkeypatch):
    # The source tree separates attached steps, while mappings use one continuous
    # original index. Publication must rebuild the same identity as the mapping UI.
    monkeypatch.setattr(subject, 'build_superset_process_tree', lambda **_: [{
        'id': 7, 'step_items': ['钻孔', '铰孔'], 'attached_step_items': ['孔口倒角', '去毛刺'],
    }])
    rows = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    db = SimpleNamespace(execute=AsyncMock(return_value=rows))
    assert await subject._load_source_step_items(db, 1) == {7: ['钻孔', '铰孔', '孔口倒角', '去毛刺']}
