import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.services.db_schema_maintenance import ensure_project_schema


@pytest.fixture
def project_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'projects.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_project_api_exposes_a_single_route_workflow(project_client):
    created = project_client.post("/api/projects/", json={"name": "套筒路线"})

    assert created.status_code == 200, created.text
    project = created.json()
    assert set(project) == {
        "id",
        "name",
        "workflow_revision",
        "status",
        "created_at",
        "updated_at",
    }
    assert project_client.get("/api/projects/profiles").status_code == 405
    assert project_client.patch(
        f"/api/projects/{project['id']}/rule-engine",
        json={"rule_engine": "v1"},
    ).status_code == 404
