import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import Project
from app.services.db_schema_maintenance import ensure_project_schema


@pytest.fixture
def knowledge_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as session:
            session.add(Project(id=1, name="测试项目", status="CREATED"))
            await session.commit()

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


def test_evidence_snapshot_is_idempotent(knowledge_client):
    payload = {
        "project_id": 1,
        "query": "硬度",
        "content": "真空淬火后硬度不低于56 HRC",
        "item_id": "chunk-1",
        "document_name": "JRT148-06-01.pdf",
        "page_no": 23,
        "identity": "jrt148:v1:p23",
    }

    first = knowledge_client.post("/api/knowledge/evidence", json=payload)
    second = knowledge_client.post("/api/knowledge/evidence", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    listed = knowledge_client.get("/api/knowledge/evidence", params={"project_id": 1})
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_evidence_snapshot_keeps_route_and_segment_context(knowledge_client):
    payload = {
        "project_id": 1,
        "route_version_id": 11,
        "segment_id": "op-40",
        "query": "硬度",
        "content": "真空淬火后硬度不低于56 HRC",
        "item_id": "chunk-context",
    }

    response = knowledge_client.post("/api/knowledge/evidence", json=payload)

    assert response.status_code == 200
    assert response.json()["route_version_id"] == 11
    assert response.json()["segment_id"] == "op-40"
