"""Replacement regression coverage for retired domain-package workflows.

The old package CRUD/binding/enrichment contracts are intentionally removed.
These checks preserve the ordinary route workflow and the separate process
knowledge API while proving legacy package context cannot affect new routes.
"""

import asyncio
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.main import app
from app.models.models import DocumentOperationDetail, Project, RouteMergeSnapshot
from app.services.route_merge.workspace import (
    ensure_route_merge_snapshot,
    route_merge_source_signature,
)


def test_domain_package_api_is_not_registered_and_process_knowledge_api_remains():
    paths = set(app.openapi()["paths"])

    assert "/api/domain-knowledge/packages" not in paths
    assert "/api/projects/{project_id}/domain-knowledge-package" not in paths
    assert "/api/knowledge/domain-candidates" not in paths
    assert "/api/knowledge/search" in paths
    assert "/api/knowledge/evidence" in paths


def test_new_route_merge_payload_has_no_domain_package_context():
    from app.services.route_merge.workspace import build_route_merge_snapshot_payload

    payload = build_route_merge_snapshot_payload(
        project_id=1,
        raw_operations=[{"id": 1, "name": "精车削", "sequence": 10}],
        detail_rows=[],
    )

    assert "knowledge_package" not in payload
    assert "domain_evidence" not in payload
    assert payload["normalized_superset_route"]


def test_legacy_enriched_snapshot_rebuild_preserves_review_state_and_details(tmp_path, monkeypatch):
    import app.services.route_merge.workspace as workspace

    monkeypatch.setattr(workspace, "UPLOAD_DIR", tmp_path / "uploads")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy-domain.db'}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    operations = [{"id": 1, "name": "精车", "sequence": 10}]
    legacy_review_state = {"s-domain": {"action": "keep_separate", "reviewed_by": "审核人"}}

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(Project(id=1, name="迁移兼容"))
            db.add(DocumentOperationDetail(
                project_id=1,
                pdf_name="test.pdf",
                operation_seq=10,
                operation_name="精车",
                normalized_name="精车",
                operation_content="精加工",
            ))
            db.add(RouteMergeSnapshot(
                project_id=1,
                source_signature=route_merge_source_signature(operations, [], []).replace("v34|", "v33|", 1),
                knowledge_package_json='{"package_id":"legacy","version":1}',
                superset_route_json=json.dumps(operations, ensure_ascii=False),
                merge_groups_json=json.dumps([{
                    "id": "domain-group",
                    "source_nodes": ["精车"],
                    "source_operation_ids": [1],
                    "normalized_step_name": "精车",
                    "review_status": "merged",
                    "domain_evidence": [{"resource_id": "legacy-rule"}],
                }], ensure_ascii=False),
                merge_suggestions_json="[]",
                normalized_superset_route_json="[]",
                review_state_json=json.dumps(legacy_review_state, ensure_ascii=False),
            ))
            await db.commit()

    async def exercise():
        await setup()
        async with factory() as db:
            load_counts = {"operations": 0, "details": 0}

            async def load_operations():
                load_counts["operations"] += 1
                return operations

            async def load_details():
                load_counts["details"] += 1
                return []

            payload = await ensure_route_merge_snapshot(1, db, load_operations, load_details)
            second_payload = await ensure_route_merge_snapshot(1, db, load_operations, load_details)
            details_count = await db.scalar(select(func.count()).select_from(DocumentOperationDetail))
            snapshot = await db.scalar(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 1))
            return payload, second_payload, load_counts, details_count, snapshot

    try:
        payload, second_payload, load_counts, details_count, snapshot = asyncio.run(exercise())
    finally:
        asyncio.run(engine.dispose())

    assert "knowledge_package" not in payload
    assert "domain_evidence" not in payload
    assert payload["review_state"] == legacy_review_state
    assert second_payload == payload
    assert load_counts == {"operations": 1, "details": 1}
    assert payload["merge_groups"][0]["review_status"] == "merged"
    assert "domain_evidence" not in payload["merge_groups"][0]
    assert details_count == 1
    assert snapshot.knowledge_package_json == '{"package_id":"legacy","version":1}'
