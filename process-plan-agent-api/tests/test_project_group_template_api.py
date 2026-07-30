import asyncio
import json

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import Project, ProjectGroupTemplate
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.group_template_xml import parse_group_template_xml
from app.services.project_group_templates import (
    commit_project_group_template,
    get_project_group_template,
    replace_project_group_mappings,
    serialize_project_group_template,
)


def _template_xml(*, child_name="孔", feature="孔(盲孔)", source_id="child-1"):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" />
      <Item type="Group_Template" />
      <Item type="Part" filename="fixture.prt">
        <Item type="Group" id="side-a">
          <Params><param name="名称" value="A侧" /></Params>
          <Item type="Group" id="{source_id}">
            <Params>
              <param name="名称" value="{child_name}" />
              <param name="特征选择" value="{feature}" />
            </Params>
          </Item>
        </Item>
      </Item>
    </Kmsoft>'''.encode("utf-8")


def _parsed(filename, **kwargs):
    parsed = parse_group_template_xml(filename, _template_xml(**kwargs))
    assert parsed.can_confirm is True
    return parsed


@pytest_asyncio.fixture
async def template_store(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'templates.db'}")
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_project_schema(conn)
    try:
        yield engine, sessions
    finally:
        await engine.dispose()


async def _create_project(sessions, name="project"):
    async with sessions() as db:
        project = Project(name=name)
        db.add(project)
        await db.commit()
        return project.id


def _mapping(path=None):
    return {
        "source_operation_id": 11,
        "alias": "钻孔（A侧/孔）",
        "template_group_path": path or ["A侧", "孔"],
        "template_group_key": "client-key-must-not-survive",
        "template_group_id": "xml-uuid-must-not-survive",
        "template_group_name": "client-name-must-not-survive",
        "feature_selections": ["client-feature-must-not-survive"],
    }


@pytest.mark.asyncio
async def test_template_commit_mapping_and_replacement_revision_transitions(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)
    parsed_a = _parsed("a.xml")
    parsed_b = _parsed("b.xml", child_name="槽", feature="")

    async with sessions() as db:
        saved = await commit_project_group_template(db, project_id, parsed_a, expected_revision=0)
        assert saved.template_revision == 1

        mapped = await replace_project_group_mappings(
            db,
            project_id,
            [_mapping()],
            expected_revision=1,
        )
        assert mapped.template_revision == 2
        assert mapped.mappings[0].template_group_key.startswith("grp_")
        assert mapped.mappings[0].template_group_id == mapped.mappings[0].template_group_key
        assert mapped.mappings[0].template_group_name == "孔"
        assert mapped.mappings[0].feature_selections == ["孔(盲孔)"]

        replaced = await commit_project_group_template(db, project_id, parsed_b, expected_revision=2)
        assert replaced.template_revision == 3
        assert replaced.kept_source_operation_ids == []
        assert replaced.invalidated[0].source_operation_id == 11
        await db.commit()

    async with sessions() as db:
        stored = await get_project_group_template(db, project_id)
        snapshot = serialize_project_group_template(stored)
        assert snapshot.original_filename == "b.xml"
        assert snapshot.mappings == []


@pytest.mark.asyncio
async def test_replacement_preserves_only_an_exact_path_and_refreshes_server_metadata(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)

    async with sessions() as db:
        await commit_project_group_template(db, project_id, _parsed("a.xml"), expected_revision=0)
        await replace_project_group_mappings(db, project_id, [_mapping()], expected_revision=1)
        replacement = await commit_project_group_template(
            db,
            project_id,
            _parsed("same-path.xml", feature="孔(通孔)", source_id="new-xml-id"),
            expected_revision=2,
        )

        assert replacement.template_revision == 3
        assert replacement.kept_source_operation_ids == [11]
        assert replacement.invalidated == []
        assert replacement.mappings[0].template_group_id == replacement.mappings[0].template_group_key
        assert replacement.mappings[0].feature_selections == ["孔(通孔)"]
        await db.commit()


@pytest.mark.asyncio
async def test_stale_or_invalid_replacement_returns_http_error_without_changing_row(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)

    async with sessions() as db:
        saved = await commit_project_group_template(db, project_id, _parsed("original.xml"), expected_revision=0)
        await db.commit()

        with pytest.raises(HTTPException) as stale:
            await commit_project_group_template(
                db,
                project_id,
                _parsed("stale.xml", child_name="槽", feature=""),
                expected_revision=0,
            )
        assert stale.value.status_code == 409
        assert stale.value.detail == "分组模板已在其他页面更新，请重新加载。"

        with pytest.raises(HTTPException) as invalid_path:
            await replace_project_group_mappings(
                db,
                project_id,
                [_mapping(["A侧", "不存在"])],
                expected_revision=saved.template_revision,
            )
        assert invalid_path.value.status_code == 422

        stored = await get_project_group_template(db, project_id)
        assert stored.original_filename == "original.xml"
        assert stored.template_revision == 1
        assert json.loads(stored.mappings_json) == []


@pytest.mark.asyncio
async def test_first_create_requires_revision_zero_and_competing_create_has_one_winner(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)
    parsed = _parsed("first.xml")

    async with sessions() as db:
        with pytest.raises(HTTPException) as wrong_revision:
            await commit_project_group_template(db, project_id, parsed, expected_revision=1)
        assert wrong_revision.value.status_code == 409

    ready = asyncio.Event()
    arrived = 0

    async def contender():
        nonlocal arrived
        async with sessions() as db:
            arrived += 1
            if arrived == 2:
                ready.set()
            await ready.wait()
            result = await commit_project_group_template(db, project_id, parsed, expected_revision=0)
            await db.commit()
            return result.template_revision

    results = await asyncio.gather(contender(), contender(), return_exceptions=True)
    assert sorted((type(result) for result in results), key=lambda item: item.__name__) == [
        HTTPException,
        int,
    ]
    assert next(result for result in results if isinstance(result, int)) == 1
    conflict = next(result for result in results if isinstance(result, HTTPException))
    assert conflict.status_code == 409

    async with sessions() as db:
        rows = (await db.execute(select(ProjectGroupTemplate))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_service_does_not_commit_and_project_delete_cascades_template(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)

    async with sessions() as db:
        await commit_project_group_template(db, project_id, _parsed("rollback.xml"), expected_revision=0)
        await db.rollback()

    async with sessions() as db:
        assert await get_project_group_template(db, project_id) is None
        await commit_project_group_template(db, project_id, _parsed("cascade.xml"), expected_revision=0)
        await db.commit()
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.commit()
        assert (await db.execute(select(ProjectGroupTemplate))).scalars().all() == []


@pytest.mark.asyncio
async def test_schema_maintenance_is_idempotent_and_preserves_existing_template(template_store):
    engine, sessions = template_store
    project_id = await _create_project(sessions)
    async with sessions() as db:
        await commit_project_group_template(db, project_id, _parsed("preserved.xml"), expected_revision=0)
        await db.commit()

    async with engine.begin() as conn:
        await ensure_project_schema(conn)
        await ensure_project_schema(conn)
        row = (
            await conn.execute(
                text(
                    "SELECT original_filename, template_revision, mappings_json "
                    "FROM project_group_templates WHERE project_id = :project_id"
                ),
                {"project_id": project_id},
            )
        ).one()

    assert row == ("preserved.xml", 1, "[]")
