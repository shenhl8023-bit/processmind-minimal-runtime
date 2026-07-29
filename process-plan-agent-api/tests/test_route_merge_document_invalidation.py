import asyncio
import json
import os
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import (
    Document,
    DocumentOperationDetail,
    FinalizedRulePackage,
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
    RouteMergeSnapshot,
)
from app.routers import documents as documents_router
from app.routers.generate import generate_route
from app.schemas.schemas import GenerateRequest
from app.services.route_analysis import ensure_saved_normalized_route_version
from app.services.route_merge import workspace as route_merge_workspace
from app.services.route_merge.workspace import (
    ensure_route_merge_snapshot,
    invalidate_project_route_merge_cache,
)
from app.services.rule_packages.loader import load_published_rule_package


@pytest.fixture
def route_merge_db(tmp_path):
    database_path = tmp_path / "route_merge_invalidation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    route_merge_workspace.ROUTE_MERGE_BUILD_LOCKS.clear()
    try:
        yield session_factory
    finally:
        route_merge_workspace.ROUTE_MERGE_BUILD_LOCKS.clear()
        asyncio.run(engine.dispose())


def _snapshot(project_id: int, source_signature: str) -> RouteMergeSnapshot:
    return RouteMergeSnapshot(
        project_id=project_id,
        source_signature=source_signature,
        superset_route_json="[]",
        merge_groups_json="[]",
        merge_suggestions_json="[]",
        normalized_superset_route_json="[]",
        review_state_json="{}",
    )


def _detail(project_id: int, document_id: int, operation_name: str) -> DocumentOperationDetail:
    return DocumentOperationDetail(
        project_id=project_id,
        document_id=document_id,
        pdf_name=f"doc-{document_id}.pdf",
        operation_seq=10,
        operation_name=operation_name,
        operation_content=f"{operation_name} content",
        page_no=1,
        normalized_name=operation_name,
    )


def _rule_package(
    project_id: int,
    version: int,
    *,
    status: str = "published",
) -> FinalizedRulePackage:
    return FinalizedRulePackage(
        project_id=project_id,
        version=version,
        package_name=f"project-{project_id}-rules-v{version}",
        schema_version="1.0",
        status=status,
        input_schema_json="{}",
        route_catalog_json="{}",
        route_rules_json="{}",
        rule_report_md="# test",
    )


def test_project_cache_invalidation_is_isolated_and_preserves_route_history(route_merge_db):
    session_factory = route_merge_db

    async def run():
        async with session_factory() as db:
            db.add_all([
                Project(id=1, name="项目一"),
                Project(id=2, name="项目二"),
                Document(id=11, project_id=1, filename="p1-a.pdf", original_name="p1-a.pdf", file_type="pdf"),
                Document(id=12, project_id=1, filename="p1-b.pdf", original_name="p1-b.pdf", file_type="pdf"),
                Document(id=21, project_id=2, filename="p2.pdf", original_name="p2.pdf", file_type="pdf"),
                _detail(1, 11, "旧工序一"),
                _detail(1, 12, "旧工序二"),
                _detail(2, 21, "项目二工序"),
                _snapshot(1, "project-1-old"),
                _snapshot(2, "project-2-current"),
            ])
            historical_version = NormalizedRouteVersion(
                project_id=1,
                version=1,
                source_signature="project-1-old",
                total_docs=2,
                segment_count=1,
                route_json=json.dumps([{"id": "old-segment", "normalized_step_name": "旧工序"}], ensure_ascii=False),
            )
            db.add(historical_version)
            await db.flush()
            db.add_all([
                NormalizedRouteSegmentFactorReview(
                    project_id=1,
                    route_version_id=historical_version.id,
                    segment_id="old-segment",
                    factor_name="材料",
                ),
                NormalizedRouteSegmentRuleReview(
                    project_id=1,
                    route_version_id=historical_version.id,
                    segment_id="old-segment",
                ),
            ])
            await db.commit()

            result = await invalidate_project_route_merge_cache(db, 1)
            await db.commit()

            assert result == {
                "route_merge_snapshots": 1,
                "document_operation_details": 2,
            }
            project_one_snapshots = (
                await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 1))
            ).scalars().all()
            project_two_snapshots = (
                await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 2))
            ).scalars().all()
            assert project_one_snapshots == []
            assert len(project_two_snapshots) == 1

            project_one_details = (
                await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 1))
            ).scalars().all()
            project_two_details = (
                await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 2))
            ).scalars().all()
            assert project_one_details == []
            assert [row.operation_name for row in project_two_details] == ["项目二工序"]

            versions = (
                await db.execute(select(NormalizedRouteVersion).where(NormalizedRouteVersion.project_id == 1))
            ).scalars().all()
            factor_reviews = (
                await db.execute(
                    select(NormalizedRouteSegmentFactorReview).where(
                        NormalizedRouteSegmentFactorReview.project_id == 1
                    )
                )
            ).scalars().all()
            rule_reviews = (
                await db.execute(
                    select(NormalizedRouteSegmentRuleReview).where(
                        NormalizedRouteSegmentRuleReview.project_id == 1
                    )
                )
            ).scalars().all()
            assert [row.id for row in versions] == [historical_version.id]
            assert len(factor_reviews) == 1
            assert len(rule_reviews) == 1

    asyncio.run(run())


def test_document_upload_invalidates_only_the_target_project(route_merge_db, tmp_path, monkeypatch):
    session_factory = route_merge_db
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(route_merge_workspace, "UPLOAD_DIR", upload_dir)

    async def run():
        async with session_factory() as db:
            historical_package = _rule_package(1, 1, status="superseded")
            published_package = _rule_package(1, 2)
            other_project_package = _rule_package(2, 1)
            db.add_all([
                Project(id=1, name="项目一"),
                Project(id=2, name="项目二"),
                Document(id=11, project_id=1, filename="old-p1.pdf", original_name="old-p1.pdf", file_type="pdf"),
                Document(id=21, project_id=2, filename="p2.pdf", original_name="p2.pdf", file_type="pdf"),
                _detail(1, 11, "项目一旧工序"),
                _detail(2, 21, "项目二工序"),
                _snapshot(1, "project-1-old"),
                _snapshot(2, "project-2-current"),
                historical_package,
                published_package,
                other_project_package,
            ])
            await db.commit()

            pdf_content = b"%PDF-1.4\nnew document content\n%%EOF\n"
            uploaded = await documents_router.upload_documents(
                files=[UploadFile(filename="new.pdf", file=BytesIO(pdf_content))],
                project_id=1,
                db=db,
            )

            assert len(uploaded) == 1
            assert (upload_dir / uploaded[0].filename).read_bytes() == pdf_content
            project_one_snapshots = (
                await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 1))
            ).scalars().all()
            project_two_snapshots = (
                await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 2))
            ).scalars().all()
            assert project_one_snapshots == []
            assert len(project_two_snapshots) == 1
            project_one_details = (
                await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 1))
            ).scalars().all()
            project_two_details = (
                await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 2))
            ).scalars().all()
            assert project_one_details == []
            assert [row.operation_name for row in project_two_details] == ["项目二工序"]
            assert await load_published_rule_package(1, db) is None
            assert (await load_published_rule_package(2, db)).id == other_project_package.id
            project_one_packages = (
                await db.execute(
                    select(FinalizedRulePackage)
                    .where(FinalizedRulePackage.project_id == 1)
                    .order_by(FinalizedRulePackage.version.asc())
                )
            ).scalars().all()
            assert [row.id for row in project_one_packages] == [
                historical_package.id,
                published_package.id,
            ]
            assert [row.status for row in project_one_packages] == ["superseded", "superseded"]
            with pytest.raises(HTTPException) as exc_info:
                await generate_route(GenerateRequest(project_id=1), db=db)
            assert exc_info.value.status_code == 409
            assert "尚未导出有效规则包" in str(exc_info.value.detail)

    asyncio.run(run())


def test_document_delete_invalidates_project_cache_without_touching_other_projects(
    route_merge_db,
    tmp_path,
    monkeypatch,
):
    session_factory = route_merge_db
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(route_merge_workspace, "UPLOAD_DIR", upload_dir)
    (upload_dir / "delete-me.pdf").write_bytes(b"old document")

    async def run():
        async with session_factory() as db:
            published_package = _rule_package(1, 1)
            other_project_package = _rule_package(2, 1)
            db.add_all([
                Project(id=1, name="项目一", status="UPLOADED"),
                Project(id=2, name="项目二", status="UPLOADED"),
                Document(id=11, project_id=1, filename="delete-me.pdf", original_name="delete-me.pdf", file_type="pdf"),
                Document(id=12, project_id=1, filename="keep.pdf", original_name="keep.pdf", file_type="pdf"),
                Document(id=21, project_id=2, filename="p2.pdf", original_name="p2.pdf", file_type="pdf"),
                _detail(1, 11, "待删除工序"),
                _detail(1, 12, "项目一保留文档工序"),
                _detail(2, 21, "项目二工序"),
                _snapshot(1, "project-1-old"),
                _snapshot(2, "project-2-current"),
                published_package,
                other_project_package,
            ])
            await db.commit()

            assert await documents_router.delete_document(11, db=db) == {"ok": True}
            assert not (upload_dir / "delete-me.pdf").exists()
            remaining_document_ids = (
                await db.execute(
                    select(Document.id).where(Document.project_id == 1).order_by(Document.id.asc())
                )
            ).scalars().all()
            assert remaining_document_ids == [12]
            assert (
                await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 1))
            ).scalars().all() == []
            assert len((
                await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 2))
            ).scalars().all()) == 1
            assert (
                await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 1))
            ).scalars().all() == []
            project_two_details = (
                await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 2))
            ).scalars().all()
            assert [row.operation_name for row in project_two_details] == ["项目二工序"]
            assert await load_published_rule_package(1, db) is None
            assert published_package.status == "superseded"
            assert (await db.get(FinalizedRulePackage, published_package.id)) is published_package
            assert (await load_published_rule_package(2, db)).id == other_project_package.id

    asyncio.run(run())


def test_changed_document_file_version_forces_detail_and_snapshot_rebuild(
    route_merge_db,
    tmp_path,
    monkeypatch,
):
    session_factory = route_merge_db
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(route_merge_workspace, "UPLOAD_DIR", upload_dir)
    document_path = upload_dir / "route.pdf"
    document_path.write_bytes(b"old route content")

    async def run():
        published_package_id = 0
        async with session_factory() as db:
            published_package = _rule_package(1, 1)
            db.add_all([
                Project(id=1, name="项目一"),
                Document(
                    id=11,
                    project_id=1,
                    filename="route.pdf",
                    original_name="route.pdf",
                    file_type="pdf",
                    file_size=len(b"old route content"),
                ),
                _detail(1, 11, "旧工序"),
                published_package,
            ])
            await db.commit()
            published_package_id = published_package.id

            async def old_details():
                return (
                    await db.execute(
                        select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 1)
                    )
                ).scalars().all()

            async def old_route():
                rows = await old_details()
                return [{"id": 1, "name": rows[0].operation_name, "sequence": 10}]

            old_payload = await ensure_route_merge_snapshot(1, db, old_route, old_details)
            old_signature = str(old_payload["source_signature"])
            assert old_payload["superset_route"][0]["name"] == "旧工序"

        async with session_factory() as db:
            async def unexpected_loader():
                raise AssertionError("unchanged document version should reuse the existing snapshot")

            cached_payload = await ensure_route_merge_snapshot(
                1,
                db,
                unexpected_loader,
                unexpected_loader,
            )
            assert cached_payload["source_signature"] == old_signature
            assert (await load_published_rule_package(1, db)).id == published_package_id

        previous_stat = document_path.stat()
        document_path.write_bytes(b"new route content with changed instructions")
        os.utime(
            document_path,
            ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns + 2_000_000_000),
        )

        async with session_factory() as db:
            async def load_details():
                rows = (
                    await db.execute(
                        select(DocumentOperationDetail)
                        .where(DocumentOperationDetail.project_id == 1)
                        .order_by(DocumentOperationDetail.id.asc())
                    )
                ).scalars().all()
                if rows:
                    return rows
                replacement = _detail(1, 11, "新工序")
                db.add(replacement)
                await db.flush()
                return [replacement]

            async def load_route():
                rows = await load_details()
                return [{"id": 1, "name": rows[0].operation_name, "sequence": 10}]

            new_payload = await ensure_route_merge_snapshot(1, db, load_route, load_details)
            assert new_payload["superset_route"][0]["name"] == "新工序"
            assert new_payload["source_signature"] != old_signature
            details = (
                await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == 1))
            ).scalars().all()
            snapshots = (
                await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == 1))
            ).scalars().all()
            assert [row.operation_name for row in details] == ["新工序"]
            assert len(snapshots) == 1
            assert await load_published_rule_package(1, db) is None
            assert (await db.get(FinalizedRulePackage, published_package_id)).status == "superseded"

    asyncio.run(run())


def test_new_document_signature_creates_new_current_route_version_without_deleting_history(route_merge_db):
    session_factory = route_merge_db

    async def run():
        async with session_factory() as db:
            db.add_all([
                Project(id=1, name="项目一"),
                Document(id=11, project_id=1, filename="route.pdf", original_name="route.pdf", file_type="pdf"),
                RouteMergeSnapshot(
                    project_id=1,
                    source_signature="new-document-signature",
                    superset_route_json="[]",
                    merge_groups_json="[]",
                    merge_suggestions_json="[]",
                    normalized_superset_route_json=json.dumps(
                        [{"id": "new-segment", "normalized_step_name": "新工序", "sequence": 10}],
                        ensure_ascii=False,
                    ),
                    review_state_json="{}",
                ),
            ])
            historical_version = NormalizedRouteVersion(
                project_id=1,
                version=1,
                source_signature="old-document-signature",
                total_docs=1,
                segment_count=1,
                route_json=json.dumps(
                    [{"id": "old-segment", "normalized_step_name": "旧工序", "sequence": 10}],
                    ensure_ascii=False,
                ),
            )
            db.add(historical_version)
            await db.flush()
            historical_review = NormalizedRouteSegmentRuleReview(
                project_id=1,
                route_version_id=historical_version.id,
                segment_id="old-segment",
                decision="accepted",
            )
            db.add(historical_review)
            await db.commit()

            async def no_detail_rows():
                return []

            current_version = await ensure_saved_normalized_route_version(1, db, no_detail_rows)
            assert current_version is not None
            assert current_version.version == 2
            assert current_version.id != historical_version.id
            assert current_version.source_signature == "new-document-signature"
            assert json.loads(current_version.route_json)[0]["normalized_step_name"] == "新工序"

            versions = (
                await db.execute(
                    select(NormalizedRouteVersion)
                    .where(NormalizedRouteVersion.project_id == 1)
                    .order_by(NormalizedRouteVersion.version.asc())
                )
            ).scalars().all()
            reviews = (
                await db.execute(
                    select(NormalizedRouteSegmentRuleReview).where(
                        NormalizedRouteSegmentRuleReview.project_id == 1
                    )
                )
            ).scalars().all()
            assert [row.version for row in versions] == [1, 2]
            assert versions[0].source_signature == "old-document-signature"
            assert [row.route_version_id for row in reviews] == [historical_version.id]

    asyncio.run(run())
