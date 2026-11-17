from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.route_merge.saved_route_segments import build_saved_route_version_segments
from app.services.rule_packages.mother_route import MotherRouteError, build_mother_route
from app.services.rule_packages.process_identity import route_process_identities


def test_route_process_identity_prefers_persisted_export_id():
    identities = route_process_identities([
        {"id": "segment-heat", "normalized_step_name": "淬火", "export_process_id": "process_heat_treatment"},
        {"id": "segment-mark", "normalized_step_name": "标记"},
    ])

    assert [item.export_process_id for item in identities] == [
        "process_heat_treatment",
        "segment-mark",
    ]


@pytest.mark.parametrize("name", ["淬火", "真空淬火", "车外圆", "检验"])
@pytest.mark.parametrize("as_object", [False, True])
def test_same_name_nodes_keep_their_own_identity_after_reorder(name, as_object):
    route = [{"id": "segment-1", "normalized_step_name": name},
             {"id": "segment-2", "normalized_step_name": name}]
    if as_object:
        route = [SimpleNamespace(**item) for item in route]
    expected = {"segment-1": "segment-1", "segment-2": "segment-2"}
    for items in (route, list(reversed(route))):
        assert {item.segment_id: item.export_process_id
                for item in route_process_identities(iter(items))} == expected


@pytest.mark.parametrize("item,expected", [
    ({"id": "segment-heat", "normalized_step_name": "淬火"}, "process_quench"),
    ({"id": "segment-heat", "process_name": "真空淬火"}, "process_quench"),
    ({"id": "process_heat", "normalized_step_name": "淬火"}, "process_heat"),
    ({"id": "segment-cut", "normalized_step_name": "车外圆"}, "segment-cut"),
    ({"id": "segment-heat", "export_process_id": "custom-heat", "name": "淬火"}, "custom-heat"),
])
def test_uncollided_legacy_export_identity_is_unchanged(item, expected):
    assert route_process_identities([item])[0].export_process_id == expected


@pytest.mark.parametrize("fixed", [
    {"id": "process_quench", "normalized_step_name": "淬火"},
    {"id": "legacy-quench", "export_process_id": "process_quench", "normalized_step_name": "淬火"},
])
def test_implicit_alias_does_not_steal_an_existing_process_identity(fixed):
    fresh = {"id": "fresh-quench", "normalized_step_name": "淬火"}
    expected = {fixed["id"]: "process_quench", "fresh-quench": "fresh-quench"}
    for route in ([fixed, fresh], [fresh, fixed]):
        assert {item.segment_id: item.export_process_id
                for item in route_process_identities(route)} == expected


def test_disambiguation_reserves_persisted_ids_and_other_segment_ids():
    route = [
        {"id": "heat", "normalized_step_name": "淬火"},
        {"id": "other-heat", "normalized_step_name": "淬火"},
        {"id": "fixed", "export_process_id": "heat", "normalized_step_name": "车外圆"},
        {"id": "heat__2", "normalized_step_name": "检验"},
    ]
    expected = {"heat": "heat__3", "other-heat": "other-heat", "fixed": "heat", "heat__2": "heat__2"}
    for items in (route, list(reversed(route))):
        assert {item.segment_id: item.export_process_id
                for item in route_process_identities(items)} == expected


def test_saved_repeated_identities_survive_rebuild_rename_and_removal():
    route = [{"id": "seg-quench-1", "normalized_step_name": "淬火", "source_operation_ids": [1]},
             {"id": "seg-quench-2", "normalized_step_name": "淬火", "source_operation_ids": [2]}]
    original = deepcopy(route)
    saved = build_saved_route_version_segments(route, [], 1)
    assert route == original
    assert [item["export_process_id"] for item in saved] == ["seg-quench-1", "seg-quench-2"]
    saved[0]["normalized_step_name"] = "真空淬火"
    rebuilt = build_saved_route_version_segments(list(reversed(saved)), [], 1)
    assert [item["export_process_id"] for item in rebuilt] == ["seg-quench-2", "seg-quench-1"]
    assert build_saved_route_version_segments(rebuilt[:1], [], 1)[0]["export_process_id"] == "seg-quench-2"
    mother = build_mother_route(rebuilt, [{"id": 1, "step_items": []}, {"id": 2, "step_items": []}])
    assert list(mother) == ["seg-quench-2", "seg-quench-1"]
    assert mother["seg-quench-1"]["source_operation_ids"] == [1]
    assert mother["seg-quench-2"]["source_operation_ids"] == [2]


def test_adding_a_repeat_preserves_the_previously_saved_single_node_alias():
    first = build_saved_route_version_segments([{"id": "first", "normalized_step_name": "淬火"}], [], 1)[0]
    second = {"id": "second", "normalized_step_name": "淬火"}
    saved = build_saved_route_version_segments([second, first], [], 1)
    assert [item["export_process_id"] for item in saved] == ["second", "process_quench"]
    assert [item.export_process_id for item in route_process_identities(saved)] == ["second", "process_quench"]


def test_saved_segment_id_matches_the_identity_used_for_rule_binding():
    saved = build_saved_route_version_segments([
        {"id": " seg-quench-1 ", "normalized_step_name": "淬火"},
        {"id": "seg-quench-2", "normalized_step_name": "淬火"},
    ], [], 1)
    assert [(item["id"], item["export_process_id"]) for item in saved] == [
        ("seg-quench-1", "seg-quench-1"), ("seg-quench-2", "seg-quench-2")]


def test_duplicate_explicit_exports_remain_invalid_without_silently_rebinding_rules():
    route = [{"id": "first", "normalized_step_name": "淬火", "export_process_id": "fixed"},
             {"id": "second", "normalized_step_name": "淬火", "export_process_id": "fixed"}]
    saved = build_saved_route_version_segments(route, [], 1)
    assert [item["export_process_id"] for item in saved] == ["fixed", "fixed"]
    with pytest.raises(MotherRouteError, match="重复"):
        build_mother_route(saved, [])


@pytest.mark.parametrize("name,expected", [("淬火", "process_quench"), ("车外圆", "repeated")])
def test_duplicate_segment_ids_do_not_receive_synthetic_occurrence_ids(name, expected):
    route = [{"id": "repeated", "normalized_step_name": name},
             {"id": "repeated", "normalized_step_name": name}]
    saved = build_saved_route_version_segments(route, [], 1)
    assert [item["export_process_id"] for item in saved] == [expected, expected]
    with pytest.raises(MotherRouteError, match="重复"):
        build_mother_route(saved, [])


@pytest.mark.parametrize("name", [
    "下料", "备料", "下料（锯床）", "毛坯准备", "下料备料", "下料准备",
    "开料", "切料", "下料准备（锯床）", "开料/备料", "切料／下料",
    "下料备料#2", "下料#1", "备料#2", "下料/备料", "下料／备料",
])
def test_preparation_with_legacy_turning_family_remains_auxiliary(name):
    mother = build_mother_route([{"id": "prepare", "normalized_step_name": name,
                                 "step_family": "车削/成形类", "phase": "rough",
                                 "source_operation_ids": [1]}],
                               [{"id": 1, "step_items": ["锯断棒料"]}])
    assert mother["prepare"]["auxiliary"] is True
    assert [step["name"] for step in mother["prepare"]["steps"]] == ["锯断棒料"]


@pytest.mark.parametrize("name", ["车削下料", "下料/钻孔", "钻孔／备料#2", "下料加工"])
def test_turning_that_mentions_blanking_is_still_machining(name):
    mother = build_mother_route([{"id": "turn", "normalized_step_name": name,
                                 "step_family": "车削/成形类", "phase": "rough",
                                 "source_operation_ids": []}], [])
    assert mother["turn"]["auxiliary"] is False
