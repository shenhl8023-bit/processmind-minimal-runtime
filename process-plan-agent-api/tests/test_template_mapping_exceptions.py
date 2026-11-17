"""PM008/009: mapping exceptions persist without changing the validated route."""

import asyncio
from copy import deepcopy
from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.product_profile import get_product_profile
from app.database import Base, configure_sqlite_engine, get_db
from app.main import app
from app.models.models import (Document, DocumentOperationDetail, GeneratedRoute,
                               NormalizedRouteVersion, Project)
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.group_template_xml import parse_group_template_xml
from app.services.project_group_templates import (commit_project_group_template, get_project_group_template,
    replace_project_group_step_mappings)
from app.services.process_tree_builder import build_superset_process_tree
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.executable_revisions import require_generation, save_revision
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.template_mapping_requirements import validate_rule_package_template_mapping


def operations():
    return [{
        "operation_id": 101, "process_id": "drill", "operation_name": "粗钻孔",
        "source_operation_ids": [900001], "process_type": "加工工序", "precision": "粗加工",
        "steps": [{"step_id": "drill.s{}".format(order), "step_name": name,
                   "source_operation_id": 900001, "source_step_order": order,
                   "source_step_name": name} for order, name in enumerate(["钻孔", "扩孔"], 1)],
    }, {
        "operation_id": 102, "process_id": "check", "operation_name": "检验",
        "source_operation_ids": [], "process_type": "辅助工序", "precision": "辅助工序",
        "steps": [{"step_id": "check.s1", "step_name": "检验尺寸"}],
    }]


def template_xml():
    return ("<Kmsoft><Item type='Part_Template'/><Item type='Group_Template'/>"
            "<Item type='Part' filename='test.prt'><Item type='Group'>"
            "<Params><param name='名称' value='A侧'/></Params>"
            "<Item type='Group'><Params><param name='名称' value='孔'/>"
            "<param name='特征选择' value='孔(盲孔)'/></Params></Item>"
            "<Item type='Group'><Params><param name='名称' value='槽'/>"
            "<param name='特征选择' value='通槽'/></Params></Item>"
            "</Item></Item></Kmsoft>").encode("utf-8")


@pytest.fixture
def exception_client(tmp_path, monkeypatch):
    profile = tmp_path / "full.json"
    profile.write_text(json.dumps({"edition": "full", "template_mapping_enabled": True, "expires_at": None}))
    monkeypatch.setenv("PROCESSMIND_PROFILE_PATH", str(profile))
    get_product_profile.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "exceptions.db"))
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with sessions() as db:
            project = Project(name="mapping-exceptions")
            db.add(project)
            await db.flush()
            document = Document(project_id=project.id, filename="fixture.pdf", original_name="fixture.pdf")
            db.add(document)
            await db.flush()
            db.add(DocumentOperationDetail(project_id=project.id, document_id=document.id,
                   pdf_name="fixture.pdf", operation_seq=10, operation_name="钻孔",
                   operation_content="1. 钻孔\n2. 扩孔", source_type="json_route_extract", page_no=1))
            route = NormalizedRouteVersion(project_id=project.id, version=1, route_json=json.dumps([
                {"id": op["process_id"], "normalized_step_name": op["operation_name"],
                 "source_operation_ids": op["source_operation_ids"],
                 "step_item_details": [{"id": step["step_id"], "text": step["step_name"], "kind": "primary"}
                                       for step in op["steps"]],
                 "doc_coverage": {"hit_docs": 1, "total_docs": 1}}
                for op in operations()], ensure_ascii=False))
            db.add(route)
            await db.flush()
            row = await save_revision(db, project, SimpleNamespace(
                expected_executable_revision=0, route_version_id=route.id, package_name="mapping-fixture",
                manifest={"project_id": project.id, "route_version_id": route.id,
                    "package_name": "mapping-fixture", "scope": {"type": "project", "key": str(project.id)}},
                factor_dictionary=None, input_schema={"fields": []}, route_catalog={"processes": [
                    {"process_id": op["process_id"], "display_name": op["operation_name"], "main": True,
                     "default_sequence": order * 100, "source_operation_ids": op["source_operation_ids"],
                     "steps": [{"step_id": step["step_id"], "name": step["step_name"], "kind": "primary"}
                               for step in op["steps"]]} for order, op in enumerate(operations(), 1)]},
                route_rules={"rules": []}, test_cases=[], rule_report_md="# Fixture", created_by="test"))
            package = RulePackageV2.model_validate_json(row.package_json)
            plan = plan_route(package, {})
            db.add(GeneratedRoute(project_id=project.id, executable_revision_id=row.id, input_factors="{}",
                                  result_json=json.dumps({"selected_process_ids": plan.selected_process_ids})))
            await db.commit()
            return project.id

    async def override():
        async with sessions() as db:
            yield db

    project_id = asyncio.run(setup())
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    client.project_id, client.sessions, client.engine = project_id, sessions, engine
    try:
        confirmed = replace_template(client, 0)
        assert confirmed.status_code == 200, confirmed.text
        yield client
    finally:
        client.close()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        asyncio.run(engine.dispose())
        get_product_profile.cache_clear()


def replace_template(client, revision):
    payload = template_xml()
    preview = client.post("/api/extract/group-templates/preview",
                          files={"file": ("fixture.xml", payload, "application/xml")})
    assert preview.status_code == 200, preview.text
    return client.put("/api/extract/group-templates/current", data={
        "project_id": client.project_id, "expected_template_revision": revision,
        "expected_content_hash": preview.json()["content_hash"],
    }, files={"file": ("fixture.xml", payload, "application/xml")})


def current(client):
    result = client.get("/api/extract/group-templates/current", params={"project_id": client.project_id})
    assert result.status_code == 200, result.text
    return result.json()


def save(client, **changes):
    body = {"project_id": client.project_id, "expected_template_revision": current(client)["template_revision"],
            "replace_all": True, "operations": operations(), "mappings": []}
    body.update(changes)
    return client.put("/api/extract/group-templates/step-mappings", json=body)


def mapping():
    return {"source_operation_id": 900001, "source_operation_name": "粗钻孔",
            "source_step_order": 1, "source_step_name": "钻孔", "template_group_path": ["A侧", "孔"],
            "candidate_features": ["孔(盲孔)"],
            "final_targets": [{"process_id": "drill", "step_id": "drill.s1"}]}


@pytest.fixture
def empty_auxiliary_core_client(exception_client):
    """Use real source refs and the frontend's deliberate auxiliary steps=[]."""
    client = exception_client

    async def source_route():
        async with client.sessions() as db:
            document = (await db.execute(select(Document))).scalars().one()
            db.add(DocumentOperationDetail(project_id=client.project_id, document_id=document.id,
                   pdf_name="fixture.pdf", operation_seq=20, operation_name="淬火",
                   operation_content="淬火", page_no=1))
            await db.flush()
            details = (await db.execute(select(DocumentOperationDetail).order_by(
                DocumentOperationDetail.document_id, DocumentOperationDetail.operation_seq,
                DocumentOperationDetail.page_no, DocumentOperationDetail.id))).scalars().all()
            sources = build_superset_process_tree(operations=[], detail_rows=details, sample_count=1)
            route = (await db.execute(select(NormalizedRouteVersion))).scalars().one()
            result, segments = [], []
            for index, (pid, name, phase, family) in enumerate([
                    ("drill", "钻孔", "rough", "hole"),
                    ("check", "淬火", "heat_treatment", "heat")], 1):
                source = next(source for source in sources if source["name"] == name)
                sid = source["id"]
                steps = [{"step_id": "{}.primary.op_{}_s{}".format(pid, sid, order),
                          "step_name": step_name, "kind": "primary", "source_operation_id": sid,
                          "source_step_order": order, "source_step_name": step_name,
                          "source_steps": [{"source_operation_id": sid, "source_step_order": order,
                                            "source_step_name": step_name}]}
                         for order, step_name in enumerate(source["step_items"], 1)]
                result.append({"operation_id": index, "process_id": pid, "operation_name": name,
                    "source_operation_ids": [sid], "process_type": "加工工序" if pid == "drill" else "辅助工序",
                    "precision": "粗加工" if pid == "drill" else "辅助工序", "steps": steps})
                segments.append({"id": pid, "normalized_step_name": name, "sequence": index,
                    "source_operation_ids": [sid], "phase": phase, "step_family": family,
                    "doc_coverage": {"hit_docs": 1, "total_docs": 1}})
            route.route_json = json.dumps(segments, ensure_ascii=False)
            await db.commit()
            return result

    client.real_operations = asyncio.run(source_route())
    old = client.get("/api/extract/executable-rule-revisions/latest",
                     params={"project_id": client.project_id}).json()
    package = deepcopy(old["package"])
    for process, operation in zip(package["route_catalog"]["processes"], client.real_operations):
        process["display_name"] = operation["operation_name"]
        process["source_operation_ids"] = operation["source_operation_ids"]
        process["steps"] = [{"step_id": step["step_id"], "name": step["step_name"], "kind": step["kind"]}
                            for step in operation["steps"]] if operation["process_type"] == "加工工序" else []
    saved = client.post("/api/extract/executable-rule-revisions", json={**package,
        "project_id": client.project_id, "route_version_id": old["route_version_id"],
        "package_name": package["manifest"]["package_name"], "expected_executable_revision": old["revision"],
        "expected_workflow_revision": 0, "rule_report_md": "# Source-backed auxiliary mapping"})
    assert saved.status_code == 200, saved.text
    client.real_revision = saved.json()
    assert client.real_revision["package"]["route_catalog"]["processes"][1]["steps"] == []
    generated = client.post("/api/generate/", json={"project_id": client.project_id,
        "expected_workflow_revision": 0, "executable_revision_id": client.real_revision["id"],
        "factor_values": {}, "input_metadata": {}})
    assert generated.status_code == 200, generated.text
    return client


def executable_snapshot(client):
    async def read():
        async with client.sessions() as db:
            row = await require_generation(db, client.project_id)
            generated = (await db.execute(select(GeneratedRoute).order_by(GeneratedRoute.id))).scalars().all()
            return (row.id, row.package_json, row.content_hash, row.source_hash, row.normalized_route_json,
                    row.validation_json, [(item.id, item.result_json) for item in generated])
    return asyncio.run(read())


def export_auxiliary_mapping(client, hidden, route=None):
    revision = client.real_revision
    return client.post("/api/extract/executable-rule-revisions/{}/export".format(revision["id"]), json={
        "project_id": client.project_id, "expected_workflow_revision": 0,
        "expected_content_hash": revision["content_hash"], "include_template_mapping": True,
        "template_mapping": {"expected_template_revision": current(client)["template_revision"],
            "replace_all": True, "operations": client.real_operations if route is None else route, "mappings": [],
            "hidden_step_keys": hidden, "waived_group_paths": [["A侧", "孔"], ["A侧", "槽"]]}})


def test_real_empty_auxiliary_core_hide_reload_restore_preserves_validation(empty_auxiliary_core_client):
    client = empty_auxiliary_core_client
    before = executable_snapshot(client)
    hidden = client.real_operations[1]["steps"][0]["step_id"]
    saved = save(client, operations=client.real_operations, hidden_step_keys=[hidden],
                 waived_group_paths=[["A侧", "孔"], ["A侧", "槽"]])
    assert saved.status_code == 200, saved.text
    assert current(client)["hidden_step_keys"] == [hidden]
    assert executable_snapshot(client) == before
    restored = save(client, operations=client.real_operations, hidden_step_keys=[])
    assert restored.status_code == 200, restored.text
    assert current(client)["hidden_step_keys"] == []
    assert executable_snapshot(client) == before


def test_real_empty_auxiliary_core_atomic_export_reload_restore(empty_auxiliary_core_client):
    client = empty_auxiliary_core_client
    before = executable_snapshot(client)
    hidden = client.real_operations[1]["steps"][0]["step_id"]
    for keys in ([hidden], []):
        exported = export_auxiliary_mapping(client, keys)
        assert exported.status_code == 200, exported.text
        sources = exported.json()["export_sources"]
        assert sources["template_mapping"]["hidden_step_keys"] == keys
        assert current(client)["hidden_step_keys"] == keys
        assert sources["template_mapping"]["template_revision"] == current(client)["template_revision"]
        exported_core = deepcopy(sources["native_snapshot"]["rule_package"])
        for process in exported_core["route_catalog"]["processes"]:
            for step in process["steps"]:
                assert step.pop("candidates") == {}
        assert exported_core == client.real_revision["package"]
        assert sources["executable_content_hash"] == client.real_revision["content_hash"]
        assert hidden in [step["step_id"] for step in sources["mother_route"]["check"]["steps"]]
        assert sources["native_snapshot"]["rule_package"]["route_catalog"]["processes"][1]["steps"] == []
        assert executable_snapshot(client) == before
        reloaded = client.get("/api/extract/finalized-rule-packages/{}".format(exported.json()["id"]),
                              params={"project_id": client.project_id})
        assert reloaded.status_code == 200, reloaded.text
        assert reloaded.json()["export_sources"]["template_mapping"]["hidden_step_keys"] == keys


@pytest.mark.parametrize("tamper", ["fake_id", "wrong_name", "wrong_order", "wrong_source",
                                   "wrong_process", "machining_as_auxiliary", "wrong_primary_order",
                                   "wrong_source_name", "missing_source", "wrong_membership"])
@pytest.mark.parametrize("action", ["save", "export"])
def test_real_auxiliary_hidden_identity_rejects_forged_source_or_process(empty_auxiliary_core_client, tamper, action):
    client = empty_auxiliary_core_client
    route = deepcopy(client.real_operations)
    step = route[1]["steps"][0]
    if tamper == "fake_id":
        step["step_id"] = "check.fake"
    elif tamper == "wrong_name":
        step["step_name"] = "伪造工步"
    elif tamper == "wrong_order":
        step["source_step_order"] = step["source_steps"][0]["source_step_order"] = 99
    elif tamper == "wrong_source":
        step["source_operation_id"] = step["source_steps"][0]["source_operation_id"] = 999999
    elif tamper == "wrong_process":
        route[1]["process_id"] = "invented_process"
    elif tamper == "machining_as_auxiliary":
        route[0]["process_type"] = "辅助工序"
        route[0]["precision"] = "辅助工序"
        step = route[0]["steps"][0]
        step["step_id"] = "drill.fake"
    elif tamper == "wrong_primary_order":
        step["source_step_order"] = 99
    elif tamper == "wrong_source_name":
        step["source_step_name"] = step["source_steps"][0]["source_step_name"] = "伪造来源工步"
    elif tamper == "missing_source":
        for field in ("source_operation_id", "source_step_order", "source_step_name", "source_steps"):
            step.pop(field)
    elif tamper == "wrong_membership":
        route[1]["source_operation_ids"] = route[0]["source_operation_ids"]
    before = current(client)
    core = executable_snapshot(client)
    response = (save(client, operations=route, hidden_step_keys=[step["step_id"]]) if action == "save"
                else export_auxiliary_mapping(client, [step["step_id"]], route))
    assert response.status_code == 422, response.text
    assert current(client) == before
    assert executable_snapshot(client) == core


def test_real_auxiliary_removed_source_cannot_be_hidden(empty_auxiliary_core_client):
    client = empty_auxiliary_core_client

    async def remove_source():
        async with client.sessions() as db:
            detail = (await db.execute(select(DocumentOperationDetail).where(
                DocumentOperationDetail.operation_name == "淬火"))).scalars().one()
            await db.delete(detail)
            await db.commit()
    asyncio.run(remove_source())
    before = current(client)
    hidden = client.real_operations[1]["steps"][0]["step_id"]
    response = save(client, operations=client.real_operations, hidden_step_keys=[hidden])
    assert response.status_code == 409, response.text
    assert current(client) == before


def test_new_template_defaults_and_save_reload_filter_only_mapping_output(exception_client):
    client = exception_client
    assert current(client)["hidden_step_keys"] == []
    assert current(client)["waived_group_paths"] == []
    source = deepcopy(operations())
    saved = save(client, hidden_step_keys=["drill.s2", "check.s1", "drill.s2"],
                 waived_group_paths=[[" A侧 ", "槽"], ["A侧", "槽"]], mappings=[mapping()])
    assert saved.status_code == 200, saved.text
    loaded = current(client)
    assert loaded == saved.json()
    assert loaded["hidden_step_keys"] == ["drill.s2", "check.s1"]
    assert loaded["waived_group_paths"] == [["A侧", "槽"]]
    assert loaded["template_revision"] == 2
    assert [s["step_id"] for s in loaded["mapping_output"][0]["steps"]] == ["drill.s1"]
    assert len(loaded["step_mappings"]) == 1
    assert operations() == source


def test_omitted_fields_preserve_and_explicit_empty_restores(exception_client):
    client = exception_client
    first = save(client, hidden_step_keys=["drill.s2"], waived_group_paths=[["A侧", "槽"]])
    assert first.status_code == 200, first.text
    kept = save(client)
    assert kept.status_code == 200, kept.text
    assert kept.json()["hidden_step_keys"] == ["drill.s2"]
    assert kept.json()["waived_group_paths"] == [["A侧", "槽"]]
    restored = save(client, hidden_step_keys=[], waived_group_paths=[])
    assert restored.status_code == 200, restored.text
    assert restored.json()["hidden_step_keys"] == []
    assert restored.json()["waived_group_paths"] == []
    assert len(restored.json()["mapping_output"][0]["steps"]) == 2


@pytest.mark.parametrize("key", ["missing", "op_900001_s01", "drill", "", " drill.s1 "])
def test_unknown_or_noncanonical_hidden_key_rejected_without_mutation(exception_client, key):
    client = exception_client
    before = current(client)
    result = save(client, hidden_step_keys=[key])
    assert result.status_code == 422, result.text
    assert current(client) == before


def test_fabricated_step_in_submitted_operations_is_not_an_authoritative_key(exception_client):
    client = exception_client
    route = operations()
    route[0]["steps"][1]["step_id"] = "invented.s2"
    result = save(client, operations=route, hidden_step_keys=["invented.s2"])
    assert result.status_code == 422, result.text
    assert current(client)["template_revision"] == 1


@pytest.mark.parametrize("replace_all", [True, False])
def test_mapped_step_delete_releases_binding_in_same_or_incremental_save(exception_client, replace_all):
    client = exception_client
    if not replace_all:
        assert save(client, mappings=[mapping()]).status_code == 200
    before = current(client)
    result = save(client, mappings=[mapping()] if replace_all else [],
                  replace_all=replace_all, hidden_step_keys=["drill.s1"])
    assert result.status_code == 200, result.text
    assert current(client)["step_mappings"] == []
    assert current(client)["hidden_step_keys"] == ["drill.s1"]


@pytest.mark.parametrize("path", [["A侧"], ["A侧", "不存在"], [], [""], ["A侧", "槽", "后代"]])
def test_waiver_must_name_an_existing_feature_leaf(exception_client, path):
    client = exception_client
    before = current(client)
    result = save(client, waived_group_paths=[path])
    assert result.status_code == 422, result.text
    assert current(client) == before


def test_waiver_cannot_target_legacy_empty_leaf(exception_client):
    client = exception_client

    async def corrupt_old_fixture():
        async with client.sessions() as db:
            row = await get_project_group_template(db, client.project_id)
            tree = json.loads(row.tree_json)
            tree[0]["children"][1]["feature_selections"] = []
            row.tree_json = json.dumps(tree)
            await db.commit()
    asyncio.run(corrupt_old_fixture())
    assert save(client, waived_group_paths=[["A侧", "槽"]]).status_code == 422


@pytest.mark.parametrize("mapped", [False, True])
def test_valid_mapping_or_explicit_waiver_completes_each_leaf_without_fake_bindings(exception_client, mapped):
    client = exception_client
    waivers = [["A侧", "槽"]] if mapped else [["A侧", "孔"], ["A侧", "槽"]]
    result = save(client, mappings=[mapping()] if mapped else [], waived_group_paths=waivers)
    assert result.status_code == 200, result.text

    async def blockers():
        async with client.sessions() as db:
            revision = await require_generation(db, client.project_id)
            return await validate_rule_package_template_mapping(db, RulePackageV2.model_validate_json(revision.package_json))
    assert asyncio.run(blockers()) == []
    assert len(result.json()["step_mappings"]) == int(mapped)
    if not mapped:
        assert all(not step["candidates"] for step in result.json()["mapping_output"][0]["steps"])
    revoked = save(client, mappings=[mapping()] if mapped else [], waived_group_paths=[])
    assert revoked.status_code == 200, revoked.text
    assert [b.code for b in asyncio.run(blockers())] == ["group_template_mapping_missing"]


def test_waiving_one_leaf_does_not_complete_another(exception_client):
    client = exception_client
    assert save(client, waived_group_paths=[["A侧", "槽"]]).status_code == 200

    async def blockers():
        async with client.sessions() as db:
            row = await require_generation(db, client.project_id)
            return await validate_rule_package_template_mapping(db, RulePackageV2.model_validate_json(row.package_json))
    blockers = asyncio.run(blockers())
    assert len(blockers) == 1
    assert "A侧 / 孔" in blockers[0].message
    assert "A侧 / 槽" not in blockers[0].message


def test_atomic_export_preserves_unhidden_auxiliary_steps_in_native_core(exception_client):
    client = exception_client
    revision = client.get("/api/extract/executable-rule-revisions/latest",
                          params={"project_id": client.project_id}).json()
    result = client.post("/api/extract/executable-rule-revisions/{}/export".format(revision["id"]), json={
        "project_id": client.project_id, "expected_workflow_revision": 0,
        "expected_content_hash": revision["content_hash"], "include_template_mapping": True,
        "template_mapping": {"expected_template_revision": 1, "replace_all": True,
            "operations": operations(), "mappings": [], "hidden_step_keys": ["drill.s2"],
            "waived_group_paths": [["A侧", "孔"], ["A侧", "槽"]]},
    })
    assert result.status_code == 200, result.text
    sources = result.json()["export_sources"]
    assert sources["template_mapping"]["hidden_step_keys"] == ["drill.s2"]
    assert sources["template_mapping"]["waived_group_paths"] == [["A侧", "孔"], ["A侧", "槽"]]
    assert sources["template_mapping"]["template_revision"] == current(client)["template_revision"] == 2
    catalog = sources["native_snapshot"]["rule_package"]["route_catalog"]["processes"]
    assert [[step["step_id"] for step in process["steps"]] for process in catalog] == [
        ["drill.s1", "drill.s2"], ["check.s1"]]


def test_stale_revision_and_workflow_cannot_overwrite_exceptions(exception_client):
    client = exception_client
    assert save(client, hidden_step_keys=["drill.s2"], waived_group_paths=[["A侧", "槽"]]).status_code == 200
    before = current(client)
    for changes in ({"expected_template_revision": 1}, {"expected_workflow_revision": 99}):
        result = save(client, hidden_step_keys=[], waived_group_paths=[], **changes)
        assert result.status_code == 409, result.text
        assert current(client) == before


def test_template_replacement_clears_states_even_with_identical_leaf_paths(exception_client):
    client = exception_client
    saved = save(client, hidden_step_keys=["drill.s2"], waived_group_paths=[["A侧", "槽"]], mappings=[mapping()])
    assert saved.status_code == 200, saved.text
    replaced = replace_template(client, 2)
    assert replaced.status_code == 200, replaced.text
    result = replaced.json()
    assert result["hidden_step_keys"] == []
    assert result["waived_group_paths"] == []
    assert [s["step_id"] for s in result["mapping_output"][0]["steps"]] == ["drill.s1", "drill.s2"]
    assert len(result["step_mappings"]) == 1


def test_mapping_only_changes_preserve_executable_validation_generated_rows_and_source(exception_client):
    client = exception_client

    async def snapshot():
        async with client.sessions() as db:
            row = await require_generation(db, client.project_id)
            routes = (await db.execute(select(NormalizedRouteVersion))).scalars().all()
            generated = (await db.execute(select(GeneratedRoute))).scalars().all()
            return (row.id, row.content_hash, row.source_hash, row.validation_json, row.normalized_route_json,
                    [route.route_json for route in routes], [(r.id, r.result_json) for r in generated])
    before = asyncio.run(snapshot())
    saved = save(client, hidden_step_keys=["drill.s2"], waived_group_paths=[["A侧", "槽"]])
    assert saved.status_code == 200, saved.text
    assert current(client)["hidden_step_keys"] == ["drill.s2"]
    assert asyncio.run(snapshot()) == before


def test_service_does_not_commit_exception_changes(exception_client):
    client = exception_client
    before = current(client)

    async def rolled_back():
        async with client.sessions() as db:
            snapshot = await replace_project_group_step_mappings(db, client.project_id, [], 1,
                operations(), hidden_step_keys=["drill.s2"], waived_group_paths=[["A侧", "槽"]])
            assert asdict(snapshot)["hidden_step_keys"] == ["drill.s2"]
            await db.rollback()
    asyncio.run(rolled_back())
    assert current(client) == before


def test_legacy_source_keys_hide_restore_without_requiring_new_client_fields(exception_client):
    client = exception_client

    async def check():
        async with client.sessions() as db:
            project = Project(name="legacy-mapping-client")
            db.add(project)
            await db.flush()
            await commit_project_group_template(db, project.id,
                parse_group_template_xml("fixture.xml", template_xml()), 0)
            legacy_mapping = {key: value for key, value in mapping().items() if key != "final_targets"}
            route = [{"operation_id": 900001, "operation_name": "粗钻孔", "step_items": ["钻孔", "扩孔"]}]
            saved = await replace_project_group_step_mappings(db, project.id, [legacy_mapping], 1, route,
                hidden_step_keys=["op_900001_s02"], waived_group_paths=[["A侧", "槽"]])
            assert [s["step_id"] for s in saved.mapping_output[0]["steps"]] == ["op_900001_s01"]
            # A legacy client omits both the full operations and new fields.
            kept = await replace_project_group_step_mappings(db, project.id, [legacy_mapping], 2)
            assert kept.hidden_step_keys == ["op_900001_s02"]
            assert kept.waived_group_paths == [["A侧", "槽"]]
            restored = await replace_project_group_step_mappings(db, project.id, [legacy_mapping], 3,
                hidden_step_keys=[], waived_group_paths=[])
            assert [s["step_id"] for s in restored.mapping_output[0]["steps"]] == ["op_900001_s01", "op_900001_s02"]
            assert restored.mapping_output[0]["steps"][0]["candidates"] == {"A侧/孔": ["孔(盲孔)"]}
    asyncio.run(check())


def test_split_final_targets_can_hide_unmapped_sibling_of_same_source_step(exception_client):
    client = exception_client

    async def check():
        async with client.sessions() as db:
            project = Project(name="split-final-mapping")
            db.add(project)
            await db.flush()
            await commit_project_group_template(db, project.id,
                parse_group_template_xml("fixture.xml", template_xml()), 0)
            route = operations()[:1]
            route[0]["steps"] = route[0]["steps"][:1]
            sibling = deepcopy(route[0])
            sibling.update(operation_id=202, process_id="drill.branch")
            sibling["steps"][0]["step_id"] = "drill.branch.s1"
            route.append(sibling)
            saved = await replace_project_group_step_mappings(db, project.id, [mapping()], 1, route,
                hidden_step_keys=["drill.branch.s1"])
            assert saved.hidden_step_keys == ["drill.branch.s1"]
            assert saved.mapping_output[0]["steps"][0]["candidates"] == {"A侧/孔": ["孔(盲孔)"]}
            assert saved.mapping_output[1]["steps"] == []
            assert saved.step_mappings[0].final_targets == [{"process_id": "drill", "step_id": "drill.s1"}]
    asyncio.run(check())


def test_populated_legacy_schema_migrates_empty_exception_defaults_idempotently(exception_client):
    client = exception_client

    async def migrate():
        async with client.engine.begin() as conn:
            # Recreate only this owned table with the pre-PM008/009 ORM shape.
            await conn.execute(text("DROP TABLE project_group_templates"))
            await conn.execute(text("""CREATE TABLE project_group_templates (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL UNIQUE,
                original_filename TEXT, source_encoding TEXT, part_filename TEXT,
                content_hash TEXT, feature_dictionary_version TEXT, source_xml TEXT, tree_json TEXT,
                validation_json TEXT DEFAULT '[]', mappings_json TEXT DEFAULT '[]',
                step_mappings_json TEXT DEFAULT '[]', mapping_output_json TEXT DEFAULT '[]',
                mapping_output_mode TEXT DEFAULT 'legacy', template_revision INTEGER DEFAULT 7,
                group_count INTEGER DEFAULT 0, feature_selection_count INTEGER DEFAULT 0,
                created_at DATETIME, updated_at DATETIME)"""))
            await conn.execute(text("""INSERT INTO project_group_templates
                (project_id, original_filename, source_xml, tree_json, mappings_json)
                VALUES (:project_id, 'legacy.xml', '<Kmsoft/>', '[]', '[{"alias":"retain"}]')"""),
                {"project_id": client.project_id})
            await ensure_project_schema(conn)
            await ensure_project_schema(conn)
            fields = (await conn.execute(text("PRAGMA table_info(project_group_templates)"))).fetchall()
            assert {"hidden_step_keys_json", "waived_group_paths_json", "mapping_operations_json",
                    "step_order_by_process_json", "mapping_context_json"}.issubset(
                {field[1] for field in fields})
            row = (await conn.execute(text("SELECT original_filename, source_xml, mappings_json, template_revision, "
                "hidden_step_keys_json, waived_group_paths_json, mapping_operations_json, "
                "step_order_by_process_json, mapping_context_json FROM project_group_templates"))).one()
            assert row == ("legacy.xml", "<Kmsoft/>", '[{"alias":"retain"}]', 7, "[]", "[]", "[]", "{}", "{}")
    asyncio.run(migrate())
