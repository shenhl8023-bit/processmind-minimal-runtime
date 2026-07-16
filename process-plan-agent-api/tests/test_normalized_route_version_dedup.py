import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteVersion, Project
from app.services.route_analysis import (
    canonical_normalized_route_json,
    normalized_route_content_hash,
    save_normalized_route_version,
)


def _sample_route(name: str = "车外圆") -> list[dict]:
    return [
        {
            "id": "seg-1",
            "normalized_step_name": name,
            "sequence": 1,
            "source_operation_ids": [1, 2],
        }
    ]


def test_route_content_hash_is_key_order_independent():
    a = [{"b": 1, "a": 2}, {"z": True}]
    b = [{"a": 2, "b": 1}, {"z": True}]
    assert canonical_normalized_route_json(a) == canonical_normalized_route_json(b)
    assert normalized_route_content_hash(a) == normalized_route_content_hash(b)
    assert len(normalized_route_content_hash(a)) == 64


def test_route_content_hash_changes_when_content_changes():
    assert normalized_route_content_hash(_sample_route("车外圆")) != normalized_route_content_hash(
        _sample_route("磨外圆")
    )


@pytest.fixture
def route_version_db(tmp_path):
    database_path = tmp_path / "route_versions.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(Project(id=1, name="路线版本去重测试"))
            await session.commit()

    asyncio.run(setup())
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())


def test_identical_content_reuses_version_without_bump(route_version_db):
    session_factory = route_version_db
    route = _sample_route()

    async def run():
        async with session_factory() as db:
            first = await save_normalized_route_version(
                project_id=1,
                db=db,
                source_signature="sig-a",
                total_docs=3,
                normalized_route=route,
            )
            assert first.version == 1
            first_id = first.id

            second = await save_normalized_route_version(
                project_id=1,
                db=db,
                source_signature="sig-a",
                total_docs=3,
                normalized_route=route,
            )
            assert second.id == first_id
            assert second.version == 1

            # Key order only differs — still same content.
            reordered = [
                {
                    "sequence": 1,
                    "source_operation_ids": [1, 2],
                    "normalized_step_name": "车外圆",
                    "id": "seg-1",
                }
            ]
            third = await save_normalized_route_version(
                project_id=1,
                db=db,
                source_signature="sig-b",  # metadata may refresh; version stays
                total_docs=5,
                normalized_route=reordered,
            )
            assert third.id == first_id
            assert third.version == 1
            assert third.source_signature == "sig-b"
            assert third.total_docs == 5

            rows = (
                await db.execute(
                    select(NormalizedRouteVersion).where(NormalizedRouteVersion.project_id == 1)
                )
            ).scalars().all()
            assert len(rows) == 1

    asyncio.run(run())


def test_changed_content_bumps_version(route_version_db):
    session_factory = route_version_db

    async def run():
        async with session_factory() as db:
            first = await save_normalized_route_version(
                project_id=1,
                db=db,
                source_signature="sig-a",
                total_docs=3,
                normalized_route=_sample_route("车外圆"),
            )
            second = await save_normalized_route_version(
                project_id=1,
                db=db,
                source_signature="sig-a",
                total_docs=3,
                normalized_route=_sample_route("磨外圆"),
            )
            assert first.version == 1
            assert second.version == 2
            assert second.id != first.id

            rows = (
                await db.execute(
                    select(NormalizedRouteVersion).where(NormalizedRouteVersion.project_id == 1)
                )
            ).scalars().all()
            assert len(rows) == 2

    asyncio.run(run())
