import asyncio
import json

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine, get_db
from app.main import app
from app.models.models import Project, ProjectGroupTemplate
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.group_template_xml import parse_group_template_xml
from app.services.project_group_templates import (
    commit_project_group_template,
    get_project_group_template,
    replace_project_group_mappings,
    replace_project_group_step_mappings,
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


def _template_xml_with_two_feature_groups():
    return '''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" />
      <Item type="Group_Template" />
      <Item type="Part" filename="fixture.prt">
        <Item type="Group" id="side-a">
          <Params><param name="名称" value="A侧" /></Params>
          <Item type="Group" id="hole">
            <Params>
              <param name="名称" value="孔" />
              <param name="特征选择" value="孔(盲孔)" />
            </Params>
          </Item>
          <Item type="Group" id="slot">
            <Params>
              <param name="名称" value="槽" />
              <param name="特征选择" value="通槽" />
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


@pytest.fixture
def template_api_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'template-api.db'}")
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with sessions() as db:
            project = Project(name="template-api")
            db.add(project)
            await db.commit()
            return project.id

    project_id = asyncio.run(setup())

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.project_id = project_id
    client.template_sessions = sessions
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


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


def _step_mapping(path=None, *, step_order=1, step_name="钻孔", status="confirmed"):
    return {
        "source_operation_id": 11,
        "source_operation_name": "车削加工（A侧）",
        "source_step_order": step_order,
        "source_step_name": step_name,
        "scope_template_group_path": ["A侧"],
        "template_group_path": ["A侧", "孔"] if path is None else path,
        "candidate_features": ["孔(盲孔)"] if status == "confirmed" else [],
        "match_mode": "any",
        "status": status,
        "confidence": 1.0,
        "source": "user_confirmed",
    }


def test_group_template_preview_confirm_load_and_save_mappings(template_api_client):
    client = template_api_client
    payload = _template_xml()

    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["can_confirm"] is True

    missing = client.get(
        "/api/extract/group-templates/current",
        params={"project_id": client.project_id},
    )
    assert missing.status_code == 404

    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview_body["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    )
    assert created.status_code == 200, created.text
    assert created.json()["template_revision"] == 1
    assert "source_xml" not in created.json()

    saved = client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": 1,
            "mappings": [_mapping()],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["template_revision"] == 2
    assert saved.json()["mappings"][0]["template_group_name"] == "孔"

    current = client.get(
        "/api/extract/group-templates/current",
        params={"project_id": client.project_id},
    )
    assert current.status_code == 200
    assert current.json()["mappings"] == saved.json()["mappings"]
    assert "source_xml" not in current.json()


def test_step_mapping_save_keeps_legacy_operation_aliases_separate(template_api_client):
    client = template_api_client
    payload = _template_xml()
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()

    saved = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": created["template_revision"],
            "mappings": [_step_mapping()],
        },
    )

    assert saved.status_code == 200
    row = saved.json()["step_mappings"][0]
    assert row["source_step_key"] == "op_11_s01"
    assert row["source_step_text_hash"].startswith("sha256:")
    assert row["template_group_key"].startswith("grp_")
    assert row["candidate_features"] == ["孔(盲孔)"]
    assert saved.json()["mappings"] == []


def test_step_mapping_save_keeps_previous_mappings_when_saved_incrementally(template_api_client):
    client = template_api_client
    payload = _template_xml_with_two_feature_groups()
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    )
    assert created.status_code == 200

    operations = [
        {
            "operation_id": 7001,
            "process_id": "final_hole",
            "source_operation_ids": [11],
            "operation_name": "钻孔",
            "process_type": "加工工序",
            "precision": "精加工",
            "steps": [{
                "step_id": "final_hole_s1",
                "step_name": "钻孔",
                "source_operation_id": 11,
                "source_step_order": 1,
                "source_step_name": "钻孔",
            }],
        },
        {
            "operation_id": 7002,
            "process_id": "final_slot",
            "source_operation_ids": [12],
            "operation_name": "铣槽",
            "process_type": "加工工序",
            "precision": "粗加工",
            "steps": [{
                "step_id": "final_slot_s1",
                "step_name": "铣槽",
                "source_operation_id": 12,
                "source_step_order": 1,
                "source_step_name": "铣槽",
            }],
        },
    ]
    first = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": 1,
            "operations": operations,
            "mappings": [_step_mapping()],
        },
    )
    assert first.status_code == 200
    assert len(first.json()["step_mappings"]) == 1

    second_mapping = {
        **_step_mapping(),
        "source_operation_id": 12,
        "source_operation_name": "铣槽",
        "source_step_name": "铣槽",
        "template_group_path": ["A侧", "槽"],
        "candidate_features": ["通槽"],
    }
    second = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": first.json()["template_revision"],
            "operations": operations,
            "mappings": [second_mapping],
        },
    )

    assert second.status_code == 200
    assert {
        tuple(mapping["template_group_path"])
        for mapping in second.json()["step_mappings"]
    } == {("A侧", "孔"), ("A侧", "槽")}
    assert {
        path
        for process in second.json()["mapping_output"]
        for step in process["steps"]
        for path in step["candidates"]
    } == {"A侧/孔", "A侧/槽"}

    replaced = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": second.json()["template_revision"],
            "operations": operations,
            "mappings": [second_mapping],
            "replace_all": True,
        },
    )

    assert replaced.status_code == 200
    assert [
        tuple(mapping["template_group_path"])
        for mapping in replaced.json()["step_mappings"]
    ] == [("A侧", "槽")]


def test_legacy_mapping_incremental_save_keeps_previous_groups(template_api_client):
    client = template_api_client
    payload = _template_xml_with_two_feature_groups()
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    )
    assert created.status_code == 200

    first = client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": 1,
            "mappings": [_mapping()],
        },
    )
    assert first.status_code == 200

    second_mapping = {
        **_mapping(["A侧", "槽"]),
        "source_operation_id": 12,
        "alias": "铣槽（A侧/槽）",
    }
    second = client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": first.json()["template_revision"],
            "mappings": [second_mapping],
        },
    )

    assert second.status_code == 200
    assert {
        tuple(mapping["template_group_path"])
        for mapping in second.json()["mappings"]
    } == {("A侧", "孔"), ("A侧", "槽")}


def test_legacy_mapping_incremental_save_keeps_sibling_groups_for_one_operation(template_api_client):
    client = template_api_client
    payload = _template_xml_with_two_feature_groups()
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    )
    assert created.status_code == 200

    first = client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": 1,
            "mappings": [
                _mapping(),
                {
                    **_mapping(["A侧", "槽"]),
                    "alias": "钻孔（A侧/槽）",
                },
            ],
        },
    )
    assert first.status_code == 200

    second = client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": first.json()["template_revision"],
            "mappings": [{
                **_mapping(),
                "alias": "钻孔（A侧/孔）更新",
            }],
        },
    )

    assert second.status_code == 200
    assert {
        tuple(mapping["template_group_path"])
        for mapping in second.json()["mappings"]
    } == {("A侧", "孔"), ("A侧", "槽")}


def test_step_mapping_save_rejects_parent_targets_and_forged_features(template_api_client):
    client = template_api_client
    payload = _template_xml()
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()

    parent = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": created["template_revision"],
            "mappings": [_step_mapping(["A侧"])],
        },
    )
    forged = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": created["template_revision"],
            "mappings": [{**_step_mapping(), "candidate_features": ["不存在的特征"]}],
        },
    )

    assert parent.status_code == 422
    assert parent.json()["detail"] == "工步正式映射必须指向具有合法特征的叶子分组。"
    assert forged.status_code == 422
    assert forged.json()["detail"] == "候选特征不属于目标叶子分组。"


def test_group_template_confirm_rejects_hash_mismatch_invalid_preview_and_stale_revision(template_api_client):
    client = template_api_client
    payload = _template_xml()

    mismatch = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": "0" * 64,
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    )
    assert mismatch.status_code == 422

    invalid_payload = b"<Kmsoft />"
    invalid_preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("invalid.xml", invalid_payload, "application/xml")},
    )
    assert invalid_preview.status_code == 200
    assert invalid_preview.json()["can_confirm"] is False

    invalid_confirm = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": invalid_preview.json()["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("invalid.xml", invalid_payload, "application/xml")},
    )
    assert invalid_confirm.status_code == 422

    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    )
    assert created.status_code == 200

    stale = client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": 2,
            "mappings": [],
        },
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_template_commit_mapping_and_replacement_revision_transitions(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)
    parsed_a = _parsed("a.xml")
    parsed_b = _parsed("b.xml", child_name="槽", feature="孔(通孔)")

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
async def test_step_mappings_allow_many_targets_and_explicit_not_applicable(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)
    async with sessions() as db:
        await commit_project_group_template(db, project_id, _parsed("a.xml"), expected_revision=0)
        saved = await replace_project_group_step_mappings(
            db,
            project_id,
            [
                _step_mapping(),
                _step_mapping(step_order=2, step_name="检验", status="not_applicable"),
            ],
            expected_revision=1,
        )

    assert [item.status for item in saved.step_mappings] == ["confirmed", "not_applicable"]
    assert saved.step_mappings[1].template_group_path == []


@pytest.mark.asyncio
async def test_step_mapping_save_builds_process_mapping_output(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)
    async with sessions() as db:
        await commit_project_group_template(db, project_id, _parsed("a.xml"), expected_revision=0)
        saved = await replace_project_group_step_mappings(
            db,
            project_id,
            [_step_mapping()],
            expected_revision=1,
            operations=[
                {
                    "operation_id": 11,
                    "operation_name": "车削加工（A侧）",
                    "step_items": ["钻孔", "清洗"],
                    "rule_evidence": ["φ20孔"],
                    "rule_reasons": ["需要形成孔特征"],
                },
                {
                    "operation_id": 12,
                    "operation_name": "调质",
                    "step_items": [],
                    "rule_evidence": ["调质 35HRC"],
                    "rule_reasons": [],
                },
            ],
        )

    assert saved.mapping_output == [
        {
            "process_name": "车削加工（A侧）",
            "process_type": "加工工序",
            "precision": "",
            "steps": [
                {
                    "step_name": "钻孔",
                    "candidates": {"A侧/孔": ["孔(盲孔)"]},
                    "step_id": "op_11_s01",
                },
                {
                    "step_name": "清洗",
                    "candidates": {},
                    "step_id": "op_11_s02",
                },
            ],
            "process_id": "op_11",
        },
        {
            "process_name": "调质",
            "process_type": "辅助工序",
            "precision": "辅助工序",
            "steps": [],
            "process_id": "op_12",
        },
    ]


@pytest.mark.parametrize("invalidate_feature", [False, True])
@pytest.mark.parametrize("duplicate_source", [False, True])
def test_template_replacement_rebuilds_output_from_migrated_mappings(
    template_api_client, invalidate_feature, duplicate_source,
):
    client = template_api_client
    payload = _template_xml()
    preview = client.post("/api/extract/group-templates/preview",
                          files={"file": ("old.xml", payload, "application/xml")}).json()
    created = client.put("/api/extract/group-templates/current", data={
        "project_id": client.project_id,
        "expected_content_hash": preview["content_hash"],
        "expected_template_revision": 0,
    }, files={"file": ("old.xml", payload, "application/xml")})
    assert created.status_code == 200
    operations = [
        {"operation_id": 11, "operation_name": "车削加工（A侧）",
         "step_items": ["清洗", "钻孔"], "rule_evidence": ["孔径20mm"]},
        {"operation_id": 12, "operation_name": "检验", "step_items": ["尺寸检查"]},
    ]
    if duplicate_source:
        operations.insert(0, {"operation_id": 13, "operation_name": "车削加工（A侧）",
                              "step_items": ["清洗", "钻孔"]})
    saved = client.put("/api/extract/group-templates/step-mappings", json={
        "project_id": client.project_id,
        "expected_template_revision": 1,
        "mappings": [_step_mapping(step_order=2)],
        "operations": operations,
    })
    assert saved.status_code == 200
    expected_output = saved.json()["mapping_output"]
    if invalidate_feature:
        expected_output[int(duplicate_source)]["steps"][1].update(candidates={})
        payload = _template_xml(feature="孔(通孔)")
    preview = client.post("/api/extract/group-templates/preview",
                          files={"file": ("new.xml", payload, "application/xml")}).json()
    replacement = client.put("/api/extract/group-templates/current", data={
        "project_id": client.project_id,
        "expected_content_hash": preview["content_hash"],
        "expected_template_revision": 2,
    }, files={"file": ("new.xml", payload, "application/xml")})
    assert replacement.status_code == 200
    assert len(replacement.json()["step_mappings"]) == (0 if invalidate_feature else 1)
    assert replacement.json()["mapping_output"] == expected_output
    current = client.get("/api/extract/group-templates/current", params={"project_id": client.project_id})
    assert current.json()["mapping_output"] == expected_output


@pytest.mark.asyncio
async def test_mapping_path_is_trimmed_and_unicode_normalized_before_lookup(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)
    composed_name = "孔\u00e9"

    async with sessions() as db:
        await commit_project_group_template(
            db,
            project_id,
            _parsed("normalized.xml", child_name=composed_name, feature="孔(通孔)"),
            expected_revision=0,
        )
        mapped = await replace_project_group_mappings(
            db,
            project_id,
            [_mapping([" A侧 ", "孔e\u0301 "])],
            expected_revision=1,
        )

    assert mapped.mappings[0].template_group_path == ["A侧", composed_name]


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
                _parsed("stale.xml", child_name="槽", feature="孔(通孔)"),
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
                    "SELECT original_filename, template_revision, mappings_json, step_mappings_json, mapping_output_json "
                    "FROM project_group_templates WHERE project_id = :project_id"
                ),
                {"project_id": project_id},
            )
        ).one()

    assert row == ("preserved.xml", 1, "[]", "[]", "[]")


@pytest.mark.asyncio
async def test_legacy_template_schema_defaults_ambiguous_saved_route_to_protected_mode(template_store):
    engine, sessions = template_store
    project_id = await _create_project(sessions, name="legacy-template")
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE project_group_templates"))
        await conn.execute(text("""
            CREATE TABLE project_group_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL UNIQUE,
                original_filename VARCHAR(255) NOT NULL,
                source_encoding VARCHAR(32) NOT NULL,
                part_filename VARCHAR(255) NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                feature_dictionary_version VARCHAR(64) NOT NULL,
                source_xml TEXT NOT NULL,
                tree_json TEXT NOT NULL,
                validation_json TEXT NOT NULL DEFAULT '[]',
                mappings_json TEXT NOT NULL DEFAULT '[]',
                mapping_output_json TEXT NOT NULL DEFAULT '[]',
                template_revision INTEGER NOT NULL DEFAULT 1,
                group_count INTEGER NOT NULL DEFAULT 0,
                feature_selection_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            INSERT INTO project_group_templates (
                project_id, original_filename, source_encoding, part_filename,
                content_hash, feature_dictionary_version, source_xml, tree_json,
                mapping_output_json
            ) VALUES (
                :project_id, 'legacy.xml', 'UTF-8', 'legacy.prt', 'hash', 'dict',
                '<Kmsoft />', '[]',
                '[{"process_id":"op_7001","process_name":"历史路线","steps":[]}]'
            )
        """), {"project_id": project_id})
        await ensure_project_schema(conn)

    async with sessions() as db:
        with pytest.raises(HTTPException) as error:
            await replace_project_group_step_mappings(
                db, project_id, [], expected_revision=1, operations=None, replace_all=False,
            )
        assert error.value.status_code == 422
        assert "无法判定" in error.value.detail
        row = await get_project_group_template(db, project_id)
        assert row.template_revision == 1
        assert row.mapping_output_json == '[{"process_id":"op_7001","process_name":"历史路线","steps":[]}]'
        assert row.mapping_output_mode == "unknown"


def _create_template(client):
    payload = _template_xml()
    preview = client.post('/api/extract/group-templates/preview',
                          files={'file': ('template.xml', payload, 'application/xml')}).json()
    result = client.put('/api/extract/group-templates/current', data={
        'project_id': client.project_id,
        'expected_content_hash': preview['content_hash'],
        'expected_template_revision': 0,
    }, files={'file': ('template.xml', payload, 'application/xml')})
    assert result.status_code == 200


def _final_mapping_operations():
    return [
        {'operation_id': 7001, 'process_id': 'final_turning',
         'source_operation_ids': [11, 12], 'operation_name': '精车（合并后）',
         'process_type': '加工工序', 'precision': '精加工',
         'step_items': ['精车内孔', '精车内孔'], 'steps': [
             {'step_id': 'final_hole_a', 'step_name': '精车内孔',
              'source_operation_id': 11, 'source_step_order': 1, 'source_step_name': '钻孔'},
             {'step_id': 'final_hole_b', 'step_name': '精车内孔',
              'source_operation_id': 12, 'source_step_order': 2, 'source_step_name': '铰孔'},
         ]},
        {'operation_id': 7002, 'process_id': 'final_cleaning', 'operation_name': '清洗',
         'process_type': '辅助工序', 'precision': '辅助工序',
         'step_items': ['清洗零件'], 'steps': [
             {'step_id': 'cleaning_step', 'step_name': '清洗零件',
              'source_operation_id': 0, 'source_step_order': 0, 'source_step_name': ''},
         ]},
        {'operation_id': 7003, 'process_id': 'final_cleaning_2', 'operation_name': '清洗',
         'process_type': '辅助工序', 'precision': '辅助工序', 'steps': []},
    ]


def test_final_tree_save_uses_final_nodes_and_actual_source_step_identity(template_api_client):
    client = template_api_client
    _create_template(client)
    second_mapping = dict(_step_mapping(step_order=2, step_name='铰孔'), source_operation_id=12)
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': _final_mapping_operations(),
        'mappings': [_step_mapping(), second_mapping],
    })
    assert result.status_code == 200
    assert result.json()['mapping_output'] == [
        {'process_name': '精车（合并后）', 'process_type': '加工工序', 'precision': '精加工',
         'steps': [
             {'step_name': '精车内孔', 'candidates': {'A侧/孔': ['孔(盲孔)']}, 'step_id': 'final_hole_a'},
             {'step_name': '精车内孔', 'candidates': {'A侧/孔': ['孔(盲孔)']}, 'step_id': 'final_hole_b'},
         ], 'process_id': 'final_turning'},
        {'process_name': '清洗', 'process_type': '辅助工序', 'precision': '辅助工序',
         'steps': [], 'process_id': 'final_cleaning'},
        {'process_name': '清洗', 'process_type': '辅助工序', 'precision': '辅助工序',
         'steps': [], 'process_id': 'final_cleaning_2'},
    ]


def test_final_tree_save_discards_mapping_to_removed_source_step(template_api_client):
    client = template_api_client
    _create_template(client)
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': _final_mapping_operations(),
        'mappings': [_step_mapping(step_order=3, step_name='旧工步')],
    })
    assert result.status_code == 200
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 2
    assert current['step_mappings'] == []
    assert [process['process_id'] for process in current['mapping_output']] == [
        'final_turning', 'final_cleaning', 'final_cleaning_2',
    ]


def test_empty_incremental_step_save_preserves_existing_decisions(template_api_client):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    first = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert first.status_code == 200, first.text
    saved = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 2,
        'operations': operations, 'mappings': [], 'replace_all': False,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()['step_mappings'] == first.json()['step_mappings']
    assert saved.json()['mapping_output'] == first.json()['mapping_output']


def test_incremental_save_cannot_downgrade_a_final_tree_when_operations_are_omitted(template_api_client):
    client = template_api_client
    _create_template(client)
    first = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': _final_mapping_operations(), 'mappings': [_step_mapping()],
    })
    assert first.status_code == 200, first.text
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 2,
        'mappings': [_step_mapping()], 'replace_all': False,
    })
    assert result.status_code == 422, result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 2
    assert current['mapping_output'] == first.json()['mapping_output']
    assert current['step_mappings'] == first.json()['step_mappings']


def test_incremental_save_cannot_downgrade_final_tree_with_legacy_shaped_process_id(template_api_client):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()[:1]
    operations[0]['process_id'] = 'op_7001'
    first = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [], 'replace_all': False,
    })
    assert first.status_code == 200, first.text
    assert [process['process_id'] for process in first.json()['mapping_output']] == ['op_7001']

    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 2,
        'mappings': [], 'replace_all': False,
    })

    assert result.status_code == 422, result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 2
    assert current['mapping_output'] == first.json()['mapping_output']
    assert current['step_mappings'] == first.json()['step_mappings']


def test_incremental_final_tree_save_rejects_partial_operations(template_api_client):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    first = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [],
    })
    assert first.status_code == 200, first.text
    saved_route = first.json()['mapping_output']

    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 2,
        'operations': operations[:1], 'mappings': [], 'replace_all': False,
    })

    assert result.status_code == 422, result.text
    assert '完整最终路线' in result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 2
    assert current['mapping_output'] == saved_route


def test_incremental_save_cannot_upgrade_legacy_snapshot_with_partial_final_route(template_api_client):
    client = template_api_client
    _create_template(client)
    legacy = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'mappings': [_step_mapping()], 'replace_all': True,
    })
    assert legacy.status_code == 200, legacy.text
    saved_route = legacy.json()['mapping_output']

    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 2,
        'operations': _final_mapping_operations()[:1], 'mappings': [], 'replace_all': False,
    })

    assert result.status_code == 422, result.text
    assert '全量替换' in result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 2
    assert current['mapping_output'] == saved_route


def test_empty_incremental_group_save_preserves_existing_decisions(template_api_client):
    client = template_api_client
    _create_template(client)
    first = client.put('/api/extract/group-templates/mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'mappings': [_mapping()],
    })
    assert first.status_code == 200, first.text
    saved = client.put('/api/extract/group-templates/mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 2,
        'mappings': [], 'replace_all': False,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()['mappings'] == first.json()['mappings']


@pytest.mark.parametrize('endpoint', ['current', 'mappings', 'step-mappings'])
def test_template_writes_reject_old_workflow_even_when_template_revision_is_reused(template_api_client, endpoint):
    client = template_api_client
    _create_template(client)

    async def restart_workflow():
        from app.services.project_workflow_lifecycle import invalidate_project_workflow

        async with client.template_sessions() as db:
            project = await db.get(Project, client.project_id)
            await invalidate_project_workflow(db, project, from_step=3)
            await db.commit()

    asyncio.run(restart_workflow())
    payload = _template_xml()
    preview = client.post('/api/extract/group-templates/preview',
                          files={'file': ('new.xml', payload, 'application/xml')}).json()
    fresh = client.put('/api/extract/group-templates/current', data={
        'project_id': client.project_id, 'expected_content_hash': preview['content_hash'],
        'expected_template_revision': 0, 'expected_workflow_revision': 1,
    }, files={'file': ('new.xml', payload, 'application/xml')})
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()['template_revision'] == 1
    if endpoint == 'current':
        result = client.put('/api/extract/group-templates/current', data={
            'project_id': client.project_id, 'expected_content_hash': preview['content_hash'],
            'expected_template_revision': 1, 'expected_workflow_revision': 0,
        }, files={'file': ('obsolete.xml', payload, 'application/xml')})
    else:
        result = client.put(f'/api/extract/group-templates/{endpoint}', json={
            'project_id': client.project_id, 'expected_template_revision': 1,
            'expected_workflow_revision': 0, 'mappings': [_mapping()] if endpoint == 'mappings' else [_step_mapping()],
            **({'operations': _final_mapping_operations()} if endpoint == 'step-mappings' else {}),
        })
    assert result.status_code == 409, result.text
    assert result.json()['detail']['workflow_revision'] == 1
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 1
    assert current['original_filename'] == 'new.xml'
    assert current['mappings'] == [] and current['step_mappings'] == [] and current['mapping_output'] == []


@pytest.mark.parametrize('change', ['remove_step', 'move_step', 'change_source'])
def test_incremental_final_tree_save_discards_decisions_outside_current_targets(template_api_client, change):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    first = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert first.status_code == 200, first.text
    if change == 'remove_step':
        operations[0]['steps'].pop(0)
    elif change == 'move_step':
        moved = operations[0]['steps'].pop(0)
        operations[0]['steps'][0]['source_operation_id'] = 12
        operations.append({
            'operation_id': 7004, 'process_id': 'moved_process', 'operation_name': '粗车',
            'process_type': '加工工序', 'precision': '粗加工', 'steps': [moved],
        })
    else:
        operations[0]['steps'][0]['source_step_name'] = '新的来源工步'
    second_mapping = dict(_step_mapping(step_order=2, step_name='铰孔'), source_operation_id=12)
    saved = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 2,
        'operations': operations, 'mappings': [second_mapping], 'replace_all': False,
    })
    assert saved.status_code == 200, saved.text
    assert [mapping['source_operation_id'] for mapping in saved.json()['step_mappings']] == [12]
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id})
    assert current.json()['step_mappings'] == saved.json()['step_mappings']


def test_final_tree_ids_and_names_survive_template_replacement(template_api_client):
    client = template_api_client
    _create_template(client)
    saved = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': _final_mapping_operations(), 'mappings': [_step_mapping()],
    })
    assert saved.status_code == 200
    expected = [
        {'process_name': '精车（合并后）', 'process_type': '加工工序', 'precision': '精加工',
         'steps': [
             {'step_name': '精车内孔', 'candidates': {}, 'step_id': 'final_hole_a'},
             {'step_name': '精车内孔', 'candidates': {}, 'step_id': 'final_hole_b'},
         ], 'process_id': 'final_turning'},
        {'process_name': '清洗', 'process_type': '辅助工序', 'precision': '辅助工序',
         'steps': [], 'process_id': 'final_cleaning'},
        {'process_name': '清洗', 'process_type': '辅助工序', 'precision': '辅助工序',
         'steps': [], 'process_id': 'final_cleaning_2'},
    ]
    payload = _template_xml(feature='孔(通孔)')
    preview = client.post('/api/extract/group-templates/preview',
                          files={'file': ('new.xml', payload, 'application/xml')}).json()
    replacement = client.put('/api/extract/group-templates/current', data={
        'project_id': client.project_id,
        'expected_content_hash': preview['content_hash'], 'expected_template_revision': 2,
    }, files={'file': ('new.xml', payload, 'application/xml')})
    assert replacement.status_code == 200
    assert replacement.json()['mapping_output'] == expected
    assert replacement.json()['step_mappings'] == []


@pytest.mark.parametrize('identity', ['process', 'step', 'cross_level'])
def test_final_tree_rejects_duplicate_id_before_saving(template_api_client, identity):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    if identity == 'process':
        operations[2]['process_id'] = operations[0]['process_id']
    elif identity == 'step':
        operations[0]['steps'][1]['step_id'] = operations[0]['steps'][0]['step_id']
    else:
        operations[0]['steps'][0]['step_id'] = operations[0]['process_id']
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert result.status_code == 422
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 1


def test_final_tree_one_step_combines_all_explicit_source_mappings(template_api_client):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[0]['steps'] = [{
        'step_id': 'merged_hole', 'step_name': '加工内孔',
        'source_steps': [
            {'source_operation_id': 11, 'source_step_order': 1, 'source_step_name': '钻孔'},
            {'source_operation_id': 12, 'source_step_order': 2, 'source_step_name': '铰孔'},
        ],
    }]
    second_mapping = dict(_step_mapping(step_order=2, step_name='铰孔'), source_operation_id=12)
    saved = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [second_mapping],
    })
    assert saved.status_code == 200
    assert saved.json()['mapping_output'][0]['steps'] == [{
        'step_name': '加工内孔', 'candidates': {'A侧/孔': ['孔(盲孔)']}, 'step_id': 'merged_hole',
    }]


def test_final_tree_unknown_machining_precision_is_not_guessed_from_step_word(template_api_client):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[0]['precision'] = ''
    operations[0]['operation_name'] = '车削加工'
    operations[0]['steps'][0]['step_name'] = '加工精密内孔'
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert result.status_code == 422
    assert '车削加工' in result.json()['detail']
    assert '精度' in result.json()['detail']
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 1
    assert current['mapping_output'] == []


@pytest.mark.parametrize('precision', ['精密', '辅助工序', 'unknown'])
def test_final_tree_rejects_invalid_machining_precision_before_saving(template_api_client, precision):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[0]['precision'] = precision
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert result.status_code == 422
    assert '精车（合并后）' in result.json()['detail']


def test_final_tree_precision_is_preserved_and_auxiliary_precision_is_explicit(template_api_client):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[0]['precision'] = '半精加工'
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert result.status_code == 200
    rows = result.json()['mapping_output']
    assert rows[0]['precision'] == '半精加工'
    assert rows[1]['precision'] == '辅助工序'


@pytest.mark.parametrize('precision', ['精加工', 'unknown'])
def test_final_tree_rejects_invalid_auxiliary_precision_before_mutating_snapshot(template_api_client, precision):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[1]['precision'] = precision
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert result.status_code == 422, result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 1
    assert current['mapping_output'] == []


@pytest.mark.parametrize('identity', ['process_name', 'step_name'])
def test_final_tree_rejects_whitespace_only_names_without_dropping_nodes(template_api_client, identity):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    if identity == 'process_name':
        operations[0]['operation_name'] = '  '
    else:
        operations[0]['steps'][0]['step_name'] = '  '
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert result.status_code == 422, result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 1
    assert current['mapping_output'] == []


def test_user_confirmed_precision_survives_mapping_reload(template_api_client):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[0]['precision'] = '粗加工'
    saved = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [_step_mapping()],
    })
    assert saved.status_code == 200
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id})
    assert current.status_code == 200
    assert current.json()['mapping_output'][0]['precision'] == '粗加工'


def _split_mapping_operations():
    first = _final_mapping_operations()[0]
    first['steps'] = first['steps'][:1]
    second = json.loads(json.dumps(first))
    second.update(operation_id=7004, process_id='split_turning')
    second['steps'][0]['step_id'] = 'split_hole'
    return [first, second]


def test_split_final_nodes_keep_mapping_on_explicit_target_only(template_api_client):
    client = template_api_client
    _create_template(client)
    target = {'process_id': 'final_turning', 'step_id': 'final_hole_a'}
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': _split_mapping_operations(),
        'mappings': [dict(_step_mapping(), final_targets=[target])],
    })
    assert result.status_code == 200, result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['step_mappings'][0]['final_targets'] == [target]
    assert current['mapping_output'][0]['steps'][0]['candidates'] == {'A侧/孔': ['孔(盲孔)']}
    assert current['mapping_output'][1]['steps'][0]['candidates'] == {}


@pytest.mark.parametrize('second_status', ['confirmed', 'not_applicable'])
def test_split_final_nodes_have_independent_deduplication_and_status(template_api_client, second_status):
    client = template_api_client
    _create_template(client)
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': _split_mapping_operations(),
        'mappings': [
            dict(_step_mapping(), final_targets=[{'process_id': 'final_turning', 'step_id': 'final_hole_a'}]),
            dict(_step_mapping(status=second_status),
                 final_targets=[{'process_id': 'split_turning', 'step_id': 'split_hole'}]),
        ],
    })
    assert result.status_code == 200, result.text
    assert len(result.json()['step_mappings']) == 2
    assert result.json()['mapping_output'][1]['steps'][0]['candidates'] == (
        {'A侧/孔': ['孔(盲孔)']} if second_status == 'confirmed' else {}
    )


@pytest.mark.parametrize('explicit_target', [True, False])
@pytest.mark.parametrize('incremental', [True, False])
def test_merged_final_step_rejects_conflicting_status_across_source_aliases(template_api_client, explicit_target, incremental):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[0]['steps'] = [{
        'step_id': 'merged_hole', 'step_name': '加工内孔',
        'source_steps': [
            {'source_operation_id': 11, 'source_step_order': 1, 'source_step_name': '钻孔'},
            {'source_operation_id': 12, 'source_step_order': 2, 'source_step_name': '铰孔'},
        ],
    }]
    mappings = [
        _step_mapping(),
        dict(_step_mapping(step_order=2, step_name='铰孔', status='not_applicable'),
             source_operation_id=12),
    ]
    if explicit_target:
        for mapping in mappings:
            mapping['final_targets'] = [{'process_id': 'final_turning', 'step_id': 'merged_hole'}]
    revision = 1
    if incremental:
        first = client.put('/api/extract/group-templates/step-mappings', json={
            'project_id': client.project_id, 'expected_template_revision': revision,
            'operations': operations, 'mappings': mappings[:1], 'replace_all': False,
        })
        assert first.status_code == 200, first.text
        revision = first.json()['template_revision']
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': revision,
        'operations': operations, 'mappings': mappings[1:] if incremental else mappings, 'replace_all': not incremental,
    })
    assert result.status_code == 422, result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == revision
    assert len(current['step_mappings']) == (1 if incremental else 0)


@pytest.mark.parametrize('target', [
    {'process_id': 'final_turning', 'step_id': 'final_hole_b'},
    {'process_id': 'missing', 'step_id': 'final_hole_a'},
    {'process_id': 'final_cleaning', 'step_id': 'cleaning_step'},
])
def test_explicit_final_target_must_match_mapping_source_and_machining_step(template_api_client, target):
    client = template_api_client
    _create_template(client)
    operations = _final_mapping_operations()
    operations[1]['steps'][0].update(source_operation_id=11, source_step_order=1, source_step_name='钻孔')
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': operations, 'mappings': [dict(_step_mapping(), final_targets=[target])],
    })
    assert result.status_code == 422, result.text
    current = client.get('/api/extract/group-templates/current', params={'project_id': client.project_id}).json()
    assert current['template_revision'] == 1


def test_legacy_source_mapping_does_not_confirm_auxiliary_only_final_node(template_api_client):
    client = template_api_client
    _create_template(client)
    operation = _final_mapping_operations()[1]
    operation['steps'][0].update(source_operation_id=11, source_step_order=1, source_step_name='钻孔')
    result = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': client.project_id, 'expected_template_revision': 1,
        'operations': [operation], 'mappings': [_step_mapping()],
    })
    assert result.status_code == 200, result.text
    assert result.json()['step_mappings'] == []
    assert result.json()['mapping_output'][0]['steps'] == []
