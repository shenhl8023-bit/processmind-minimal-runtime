import json
from datetime import datetime
from types import SimpleNamespace

from app.schemas.schemas import (
    NormalizedRouteSegmentOut,
    NormalizedRouteSegmentSaveItem,
    SavedNormalizedRouteSegmentOut,
)
from app.services.route_analysis_helpers import serialize_saved_normalized_route_version
from app.services.route_merge.saved_route_segments import build_saved_route_version_segments


def test_template_group_aliases_default_to_empty_for_legacy_route_items():
    save_item = NormalizedRouteSegmentSaveItem(id="segment-1", normalized_step_name="Drill")
    normalized_item = NormalizedRouteSegmentOut(
        id="segment-1",
        sequence=10,
        normalized_step_name="Drill",
    )
    saved_item = SavedNormalizedRouteSegmentOut(
        id="segment-1",
        sequence=10,
        normalized_step_name="Drill",
    )

    assert save_item.template_group_aliases == []
    assert normalized_item.template_group_aliases == []
    assert saved_item.template_group_aliases == []


def test_template_group_aliases_round_trip_without_changing_operation_names():
    aliases = [
        {
            "source_operation_id": 201,
            "alias": "钻孔（A侧/外环槽）",
            "template_group_id": "outer-groove-a",
            "template_group_path": ["A侧", "外环槽"],
        },
        {
            "source_operation_id": 202,
            "alias": "铣扁（A侧/外环槽）",
            "template_group_id": "outer-groove-a",
            "template_group_path": ["A侧", "外环槽"],
        },
        {
            "source_operation_id": 999,
            "alias": "已移回右侧的工序（A侧/外环槽）",
            "template_group_id": "outer-groove-a",
            "template_group_path": ["A侧", "外环槽"],
        },
    ]
    item = NormalizedRouteSegmentSaveItem(
        id="segment-1",
        normalized_step_name="钻孔",
        source_operation_ids=[201, 202],
        source_nodes=["钻孔", "铣扁"],
        source_operation_names=["钻孔", "铣扁"],
        template_group_aliases=aliases,
    )

    saved_segments = build_saved_route_version_segments([item], [], total_docs=1)
    assert saved_segments[0]["normalized_step_name"] == "钻孔"
    assert saved_segments[0]["source_operation_names"] == ["钻孔", "铣扁"]
    assert saved_segments[0]["template_group_aliases"] == aliases[:2]

    version_row = SimpleNamespace(
        id=7,
        project_id=3,
        version=1,
        source_signature="test-signature",
        saved_by="tester",
        created_at=datetime(2026, 7, 23),
        total_docs=1,
        segment_count=1,
        route_json=json.dumps(saved_segments, ensure_ascii=False),
    )
    response = serialize_saved_normalized_route_version(version_row)

    assert response.segments[0].normalized_step_name == "钻孔"
    assert response.segments[0].source_operation_names == ["钻孔", "铣扁"]
    assert [alias.model_dump() for alias in response.segments[0].template_group_aliases] == aliases[:2]
