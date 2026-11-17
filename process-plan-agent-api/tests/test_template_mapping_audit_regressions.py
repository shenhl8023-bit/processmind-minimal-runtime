"""Public template API regressions from audit findings A11 through A15."""

import asyncio
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine, get_db
from app.main import app
from app.models.models import Project
from app.services import template_group_mapping
from app.services.db_schema_maintenance import ensure_project_schema


@pytest.fixture
def template_audit_client(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "templates.db"))
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # These storage/API contract tests submit synthetic legacy and split trees.
    # Core/generation integration is covered without mocks in test_mapping_step_projection.
    async def editor_ready(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.rule_packages.executable_revisions.require_generation", editor_ready)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await ensure_project_schema(connection)
        async with sessions() as db:
            project = Project(name="isolated-template-audit-regression")
            db.add(project)
            await db.flush()
            await db.commit()
            return project.id

    async def override_db():
        async with sessions() as db:
            yield db

    async def no_model(*args, **kwargs):
        pytest.fail("These deterministic template regressions must not call a model")

    monkeypatch.setattr(template_group_mapping, "call_llm", no_model)
    project_id = asyncio.run(setup())
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.project_id = project_id
    try:
        yield client
    finally:
        client.close()
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        asyncio.run(engine.dispose())


def _template_xml(features="孔(盲孔)", *, child="孔", colliding_path=False):
    extra = (
        '<Item type="Group"><Params><param name="名称" value="A侧/孔"/>'
        '<param name="特征选择" value="孔(通孔)"/></Params></Item>'
        if colliding_path else ""
    )
    return (
        '<Kmsoft><Item type="Part_Template"/><Item type="Group_Template"/>'
        '<Item type="Part" filename="fixture.prt"><Item type="Group">'
        '<Params><param name="名称" value="A侧"/></Params><Item type="Group">'
        '<Params><param name="名称" value="{}"/><param name="特征选择" value="{}"/>'
        '</Params></Item></Item>{}</Item></Kmsoft>'
    ).format(child, features, extra).encode("utf-8")


def _confirm(client, payload):
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("fixture.xml", payload, "application/xml")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_confirm"] is True
    confirmed = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": client.project_id,
            "expected_content_hash": preview.json()["content_hash"],
            "expected_template_revision": 0,
        },
        files={"file": ("fixture.xml", payload, "application/xml")},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def _mapping(**changes):
    result = {
        "source_operation_id": 11,
        "source_operation_name": "钻孔（A侧）",
        "source_step_order": 1,
        "source_step_name": "钻孔",
        "template_group_path": ["A侧", "孔"],
        "candidate_features": ["孔(盲孔)"],
        "source": "user_confirmed",
    }
    result.update(changes)
    return result


def _operations(split=False):
    first = {
        "operation_id": 101,
        "operation_name": "钻孔（A侧）",
        "process_id": "final_a",
        "source_operation_ids": [11],
        "process_type": "加工工序",
        "precision": "粗加工",
        "step_items": ["钻孔"],
        "steps": [{
            "step_id": "step_a",
            "step_name": "钻孔",
            "source_operation_id": 11,
            "source_step_order": 1,
            "source_step_name": "钻孔",
        }],
    }
    result = [first]
    if split:
        second = deepcopy(first)
        second.update(operation_id=102, process_id="final_b")
        second["steps"][0]["step_id"] = "step_b"
        result.append(second)
    return result


def _save(client, revision, mappings, *, operations=None, replace_all=True):
    body = {
        "project_id": client.project_id,
        "expected_template_revision": revision,
        "mappings": mappings,
        "replace_all": replace_all,
    }
    if operations is not None:
        body["operations"] = operations
    return client.put("/api/extract/group-templates/step-mappings", json=body)


def _current(client):
    result = client.get(
        "/api/extract/group-templates/current", params={"project_id": client.project_id},
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize("step, expected", [
    ("加工内倒角", ["内倒角"]),
    ("加工外倒角", ["外倒角"]),
    ("加工边倒角", ["边倒角"]),
    ("加工内倒角及外倒角", ["内倒角", "外倒角"]),
])
def test_explicit_chamfer_qualifiers_exclude_other_generic_alias_matches(
    template_audit_client, step, expected,
):
    client = template_audit_client
    _confirm(client, _template_xml("内倒角,外倒角,边倒角", child="倒角"))
    result = client.post("/api/extract/template-step-mappings/suggest", json={
        "project_id": client.project_id,
        "expected_template_revision": 1,
        "include_llm": False,
        "operations": [{
            "operation_id": 11, "operation_name": "车削（A侧）", "step_items": [step],
        }],
    })
    assert result.status_code == 200, result.text
    suggestion = result.json()["suggestions"][0]
    assert suggestion["source"] == "auto_confirmed"
    assert list(suggestion["recommended_features_by_group"].values()) == [expected]


def test_opposite_chamfer_is_not_automatically_selected_when_it_is_the_only_feature(
    template_audit_client,
):
    client = template_audit_client
    _confirm(client, _template_xml("外倒角", child="倒角"))
    result = client.post("/api/extract/template-step-mappings/suggest", json={
        "project_id": client.project_id, "expected_template_revision": 1, "include_llm": False,
        "operations": [{
            "operation_id": 11, "operation_name": "车削（A侧）", "step_items": ["加工内倒角"],
        }],
    })
    assert result.status_code == 200, result.text
    suggestion = result.json()["suggestions"][0]
    assert suggestion["source"] == "unresolved"
    assert suggestion["recommended_features_by_group"] == {}


@pytest.mark.parametrize("route_mode", ["legacy", "one_final_target", "separate_final_targets"])
def test_colliding_export_paths_are_rejected_without_changing_saved_mapping(
    template_audit_client, route_mode,
):
    client = template_audit_client
    confirmed = _confirm(client, _template_xml(colliding_path=True))
    assert confirmed["tree"][0]["children"][0]["key"] != confirmed["tree"][1]["key"]
    operations = None if route_mode == "legacy" else _operations(
        split=route_mode == "separate_final_targets",
    )
    first_mapping = _mapping()
    second_mapping = _mapping(template_group_path=["A侧/孔"], candidate_features=["孔(通孔)"])
    if route_mode == "separate_final_targets":
        first_mapping["final_targets"] = [{"process_id": "final_a", "step_id": "step_a"}]
        second_mapping["final_targets"] = [{"process_id": "final_b", "step_id": "step_b"}]
    first = _save(client, 1, [first_mapping], operations=operations)
    assert first.status_code == 200, first.text
    before = _current(client)
    assert before["mapping_output"][0]["steps"][0]["candidates"] == {"A侧/孔": ["孔(盲孔)"]}

    result = _save(
        client, before["template_revision"], [first_mapping, second_mapping], operations=operations,
    )
    assert result.status_code == 422, result.text
    assert "路径" in result.json()["detail"] and "冲突" in result.json()["detail"]
    after = _current(client)
    assert after["template_revision"] == before["template_revision"]
    assert after["step_mappings"] == before["step_mappings"]
    assert after["mapping_output"] == before["mapping_output"]


@pytest.mark.parametrize("replace_all", [True, False])
def test_same_batch_group_decisions_preserve_all_selected_features(template_audit_client, replace_all):
    client = template_audit_client
    _confirm(client, _template_xml("孔(盲孔),孔(通孔)"))
    result = _save(client, 1, [
        _mapping(candidate_features=["孔(盲孔)"]),
        _mapping(candidate_features=["孔(通孔)"]),
        _mapping(candidate_features=["孔(盲孔)"]),
    ], operations=_operations(), replace_all=replace_all)
    assert result.status_code == 200, result.text
    saved = _current(client)
    assert len(saved["step_mappings"]) == 1
    assert saved["step_mappings"][0]["candidate_features"] == ["孔(盲孔)", "孔(通孔)"]
    assert saved["mapping_output"][0]["steps"][0]["candidates"] == {
        "A侧/孔": ["孔(盲孔)", "孔(通孔)"],
    }


@pytest.mark.parametrize("with_operations", [False, True])
def test_legacy_server_response_can_be_saved_without_removing_empty_final_targets(
    template_audit_client, with_operations,
):
    client = template_audit_client
    _confirm(client, _template_xml())
    operations = [{"operation_id": 11, "operation_name": "粗钻孔", "step_items": ["钻孔"]}] if with_operations else None
    first = _save(client, 1, [_mapping()], operations=operations)
    assert first.status_code == 200, first.text
    before = _current(client)
    assert before["step_mappings"][0]["final_targets"] == []
    result = _save(client, before["template_revision"], before["step_mappings"], operations=operations)
    assert result.status_code == 200, result.text
    after = _current(client)
    assert after["step_mappings"] == before["step_mappings"]
    assert after["mapping_output"] == before["mapping_output"]


def test_empty_explicit_final_targets_remain_invalid_for_a_final_tree(template_audit_client):
    client = template_audit_client
    _confirm(client, _template_xml())
    result = _save(client, 1, [_mapping(final_targets=[])], operations=_operations())
    assert result.status_code == 422, result.text
    current = _current(client)
    assert current["template_revision"] == 1
    assert current["step_mappings"] == []


@pytest.mark.parametrize("initial_status", ["confirmed", "not_applicable"])
def test_incremental_status_change_on_one_inferred_target_preserves_the_other(
    template_audit_client, initial_status,
):
    client = template_audit_client
    _confirm(client, _template_xml())
    initial = _mapping(status=initial_status)
    if initial_status == "not_applicable":
        initial.update(template_group_path=[], candidate_features=[])
    first = _save(client, 1, [initial], operations=_operations(split=True))
    assert first.status_code == 200, first.text
    before = first.json()
    assert before["step_mappings"][0]["final_targets"] == [
        {"process_id": "final_a", "step_id": "step_a"},
        {"process_id": "final_b", "step_id": "step_b"},
    ]
    new_status = "not_applicable" if initial_status == "confirmed" else "confirmed"
    change = _mapping(status=new_status, final_targets=[{"process_id": "final_a", "step_id": "step_a"}])
    if new_status == "not_applicable":
        change.update(template_group_path=[], candidate_features=[])
    result = _save(
        client, before["template_revision"], [change], operations=_operations(split=True), replace_all=False,
    )
    assert result.status_code == 200, result.text
    current = _current(client)
    statuses_by_target = {
        (target["process_id"], target["step_id"]): mapping["status"]
        for mapping in current["step_mappings"] for target in mapping["final_targets"]
    }
    assert statuses_by_target == {
        ("final_a", "step_a"): new_status,
        ("final_b", "step_b"): initial_status,
    }
    for process in current["mapping_output"]:
        expected_status = new_status if process["process_id"] == "final_a" else initial_status
        assert process["steps"][0]["candidates"] == (
            {"A侧/孔": ["孔(盲孔)"]} if expected_status == "confirmed" else {}
        )


def test_incremental_feature_addition_only_changes_the_selected_split_target(template_audit_client):
    client = template_audit_client
    _confirm(client, _template_xml("孔(盲孔),孔(通孔)"))
    first = _save(client, 1, [_mapping()], operations=_operations(split=True))
    assert first.status_code == 200, first.text
    result = _save(client, first.json()["template_revision"], [_mapping(
        candidate_features=["孔(通孔)"], final_targets=[{"process_id": "final_a", "step_id": "step_a"}],
    )], operations=_operations(split=True), replace_all=False)
    assert result.status_code == 200, result.text
    saved = _current(client)
    features_by_target = {
        (target["process_id"], target["step_id"]): mapping["candidate_features"]
        for mapping in saved["step_mappings"] for target in mapping["final_targets"]
    }
    assert features_by_target == {
        ("final_a", "step_a"): ["孔(盲孔)", "孔(通孔)"],
        ("final_b", "step_b"): ["孔(盲孔)"],
    }
    assert saved["mapping_output"][0]["steps"][0]["candidates"] == {"A侧/孔": ["孔(盲孔)", "孔(通孔)"]}
    assert saved["mapping_output"][1]["steps"][0]["candidates"] == {"A侧/孔": ["孔(盲孔)"]}
