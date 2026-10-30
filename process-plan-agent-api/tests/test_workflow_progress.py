import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    Document,
    FinalizedRulePackage,
    GeneratedRoute,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
    ProjectGroupTemplate,
)
from app.services.workflow_progress import get_workflow_progress


def test_progress_only_unlocks_each_next_step_after_its_saved_milestone(tmp_path):
    database_path = tmp_path / "workflow-progress.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            project = Project(id=51, name="progress", status="GENERATED", workflow_revision=9)
            db.add(project)
            await db.flush()
            db.add(Document(project_id=51, filename="part.pdf", original_name="part.pdf", status="parsed"))
            await db.commit()

            progress = await get_workflow_progress(db, 51)
            assert progress["completed_steps"] == 1
            assert progress["max_available_step"] == 2

            route = NormalizedRouteVersion(
                project_id=51,
                version=1,
                total_docs=1,
                segment_count=1,
                route_json=json.dumps([{
                    "id": "segment-1",
                    "export_process_id": "finish-turn",
                    "normalized_step_name": "精车",
                    "source_operation_ids": [701],
                    "doc_coverage": {"hit_docs": 0, "total_docs": 1},
                }], ensure_ascii=False),
            )
            db.add(route)
            await db.commit()

            progress = await get_workflow_progress(db, 51)
            assert progress["completed_steps"] == 2
            assert progress["max_available_step"] == 3

            db.add(NormalizedRouteSegmentRuleReview(
                project_id=51,
                route_version_id=route.id,
                segment_id="segment-1",
                decision="accepted",
                question_trail_json="[]",
            ))
            await db.commit()
            progress = await get_workflow_progress(db, 51)
            assert progress["completed_steps"] == 3
            assert progress["max_available_step"] == 4

            db.add(ProjectGroupTemplate(
                project_id=51,
                original_filename="template.xml",
                source_encoding="utf-8",
                part_filename="part.prt",
                content_hash="a" * 64,
                feature_dictionary_version="b" * 64,
                source_xml="<Kmsoft />",
                tree_json=json.dumps([{
                    "key": "group-outer",
                    "name": "外圆",
                    "path": ["外圆"],
                    "feature_selections": ["材料"],
                    "children": [],
                }], ensure_ascii=False),
                mappings_json=json.dumps([{
                    "source_operation_id": 701,
                    "template_group_path": ["外圆"],
                    "feature_selections": ["材料"],
                }], ensure_ascii=False),
            ))
            await db.commit()
            progress = await get_workflow_progress(db, 51)
            assert progress["completed_steps"] == 4
            assert progress["max_available_step"] == 5

            db.add(FinalizedRulePackage(
                project_id=51,
                route_version_id=route.id,
                version=1,
                package_name="progress-rules",
                status="published",
            ))
            await db.commit()
            progress = await get_workflow_progress(db, 51)
            assert progress == {
                "project_id": 51,
                "completed_steps": 5,
                "max_available_step": 6,
                "workflow_revision": 9,
            }

            assert (await db.execute(select(ProjectGroupTemplate))).scalars().one()

    try:
        asyncio.run(run())
    finally:
        asyncio.run(engine.dispose())


def test_project_workflow_progress_endpoint_returns_saved_milestones(tmp_path):
    database_path = tmp_path / "workflow-progress-api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("PRAGMA foreign_keys = ON"))
        async with session_factory() as db:
            project = Project(id=61, name="progress-api", status="GENERATED", workflow_revision=7)
            db.add(project)
            await db.flush()
            route = NormalizedRouteVersion(
                project_id=61,
                version=1,
                total_docs=1,
                segment_count=1,
                route_json=json.dumps([{
                    "id": "segment-1",
                    "normalized_step_name": "精车",
                    "source_operation_ids": [701],
                }], ensure_ascii=False),
            )
            db.add(route)
            await db.flush()
            db.add(NormalizedRouteSegmentRuleReview(
                project_id=61,
                route_version_id=route.id,
                segment_id="segment-1",
                decision="accepted",
                question_trail_json="[]",
            ))
            await db.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/projects/61/workflow-progress")
        assert response.status_code == 200
        assert response.json() == {
            "project_id": 61,
            "completed_steps": 3,
            "max_available_step": 4,
            "workflow_revision": 7,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_template_mapping_edit_invalidates_published_package_and_generated_route(tmp_path):
    database_path = tmp_path / "workflow-template-edit.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("PRAGMA foreign_keys = ON"))
        async with session_factory() as db:
            project = Project(id=71, name="template-edit", workflow_revision=9)
            route = NormalizedRouteVersion(
                id=710,
                project_id=71,
                version=1,
                total_docs=1,
                segment_count=1,
                route_json=json.dumps([{
                    "id": "segment-1",
                    "normalized_step_name": "精车",
                    "source_operation_ids": [701],
                    "doc_coverage": {"hit_docs": 0, "total_docs": 1},
                }], ensure_ascii=False),
            )
            template = ProjectGroupTemplate(
                project_id=71,
                original_filename="template.xml",
                source_encoding="utf-8",
                part_filename="part.prt",
                content_hash="a" * 64,
                feature_dictionary_version="b" * 64,
                source_xml="<Kmsoft />",
                tree_json=json.dumps([{
                    "key": "group-outer",
                    "name": "外圆",
                    "path": ["外圆"],
                    "feature_selections": ["材料"],
                    "children": [],
                }], ensure_ascii=False),
                mappings_json=json.dumps([{
                    "source_operation_id": 701,
                    "alias": "外圆",
                    "template_group_path": ["外圆"],
                    "feature_selections": ["材料"],
                }], ensure_ascii=False),
                template_revision=1,
            )
            db.add_all([
                project,
                Document(project_id=71, filename="part.pdf", original_name="part.pdf", status="parsed"),
                route,
                template,
            ])
            await db.flush()
            db.add_all([
                NormalizedRouteSegmentRuleReview(
                    project_id=71,
                    route_version_id=route.id,
                    segment_id="segment-1",
                    decision="accepted",
                    question_trail_json="[]",
                ),
                FinalizedRulePackage(
                    project_id=71,
                    route_version_id=route.id,
                    version=1,
                    package_name="template-edit-rules",
                    status="published",
                ),
                GeneratedRoute(project_id=71, input_factors="{}", result_json="{}"),
            ])
            await db.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            before = client.get("/api/projects/71/workflow-progress")
            assert before.status_code == 200
            assert before.json()["max_available_step"] == 6

            response = client.put("/api/extract/group-templates/mappings", json={
                "project_id": 71,
                "expected_template_revision": 1,
                "expected_workflow_revision": before.json()["workflow_revision"],
                "replace_all": True,
                "mappings": [{
                    "source_operation_id": 701,
                    "alias": "外圆",
                    "template_group_path": ["外圆"],
                }],
            })
            assert response.status_code == 200, response.text

            after = client.get("/api/projects/71/workflow-progress")
            assert after.status_code == 200
            assert after.json()["completed_steps"] == 4
            assert after.json()["max_available_step"] == 5

        async def verify_rows():
            async with session_factory() as db:
                package = (await db.execute(select(FinalizedRulePackage))).scalar_one()
                assert package.status == "superseded"
                assert not (await db.execute(select(GeneratedRoute))).scalars().all()

        asyncio.run(verify_rows())
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())
