"""PM020-023: exercise the real save/export/revalidation boundary."""
import asyncio
from copy import deepcopy
import json
from datetime import datetime

import pytest
from sqlalchemy import select

from test_template_mapping_exceptions import (exception_client, current, executable_snapshot,
    mapping, operations, save, empty_auxiliary_core_client, replace_template)
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.services.finalized_rule_package_helpers import serialize_finalized_rule_package, compile_publication_snapshot
from app.services.rule_packages.contracts import RulePackageV2


def order():
    return {"drill": ["drill.s2", "drill.s1"], "check": ["check.s1"]}


def test_delete_mapped_step_reload_restore_unmapped_and_keep_order(exception_client):
    client = exception_client
    before = executable_snapshot(client)
    saved = save(client, mappings=[mapping()], step_order_by_process=order())
    assert saved.status_code == 200, saved.text
    deleted = save(client, mappings=[mapping()], hidden_step_keys=["drill.s1"], step_order_by_process=order())
    assert deleted.status_code == 200, deleted.text
    state = current(client)
    assert state["step_mappings"] == []
    assert state["step_order_by_process"] == order()
    assert [step["step_id"] for step in state["mapping_output"][0]["steps"]] == ["drill.s2"]
    restored = save(client, hidden_step_keys=[])
    assert restored.status_code == 200, restored.text
    state = current(client)
    assert [step["step_id"] for step in state["mapping_output"][0]["steps"]] == ["drill.s2", "drill.s1"]
    assert all(step["candidates"] == {} for step in state["mapping_output"][0]["steps"])
    assert executable_snapshot(client) == before


@pytest.mark.parametrize("bad", [
    {},
    {"drill": ["drill.s1", "drill.s1"], "check": ["check.s1"]},
    {"drill": ["drill.s1"], "check": ["check.s1"]},
    {"drill": ["check.s1", "drill.s1"], "check": ["drill.s2"]},
    {"drill": ["unknown", "drill.s1"], "check": ["check.s1"]},
])
def test_invalid_projection_rejected_atomically(exception_client, bad):
    before = current(exception_client)
    response = save(exception_client, step_order_by_process=bad)
    assert response.status_code == 422, response.text
    assert current(exception_client) == before


def test_mapping_export_snapshot_contains_delivery_order_and_revalidates(exception_client):
    client = exception_client
    before = executable_snapshot(client)
    saved = save(client, mappings=[mapping()], step_order_by_process=order(),
                 waived_group_paths=[["A侧", "槽"]])
    assert saved.status_code == 200, saved.text
    revision = client.get("/api/extract/executable-rule-revisions/latest", params={"project_id": client.project_id}).json()
    response = client.post("/api/extract/executable-rule-revisions/{}/export".format(revision["id"]), json={
        "project_id": client.project_id, "expected_workflow_revision": 0,
        "expected_content_hash": revision["content_hash"], "include_template_mapping": True})
    assert response.status_code == 200, response.text
    sources = response.json()["export_sources"]
    assert sources["template_mapping"]["step_order_by_process"] == order()
    delivery = sources["native_snapshot"]["template_mapping_route"]
    assert [step["step_id"] for step in delivery[0]["steps"]] == ["drill.s2", "drill.s1"]
    assert delivery[0]["steps"][1]["candidates"] == {"A侧/孔": ["孔(盲孔)"]}
    assert sources["template_mapping"]["mapping_context"]["route_version_id"] == revision["route_version_id"]
    assert executable_snapshot(client) == before

    async def revalidate():
        async with client.sessions() as db:
            row = await db.get(FinalizedRulePackage, response.json()["id"])
            assert serialize_finalized_rule_package(row).export_error is None
            altered = json.loads(row.export_sources_json)
            altered["template_mapping"]["step_order_by_process"]["drill"] = ["drill.s1", "drill.s2"]
            row.export_sources_json = json.dumps(altered)
            assert serialize_finalized_rule_package(row).export_error
    asyncio.run(revalidate())


@pytest.mark.parametrize("tamper", ["name", "source", "order", "membership"])
def test_core_or_source_forgery_cannot_hide_behind_projection(exception_client, tamper):
    route = operations()
    if tamper == "name": route[0]["steps"][0]["step_name"] = "伪造"
    elif tamper == "source": route[0]["steps"][0]["source_step_order"] = 2
    elif tamper == "order": route[0]["steps"].reverse()
    else: route[0]["source_operation_ids"] = [123]
    response = save(exception_client, operations=route, step_order_by_process=order())
    assert response.status_code == 422, response.text


def test_primary_source_cannot_disagree_with_explicit_source_steps(exception_client):
    route = operations()
    step = route[0]["steps"][0]
    step["source_steps"] = [{key: step[key] for key in
        ("source_operation_id", "source_step_order", "source_step_name")}]
    step["source_step_order"] = 2
    before = current(exception_client)
    response = save(exception_client, operations=route)
    assert response.status_code == 422, response.text
    assert current(exception_client) == before


def test_stale_route_version_rejected_atomically(exception_client):
    before = current(exception_client)
    response = save(exception_client, expected_route_version_id=9999)
    assert response.status_code == 409, response.text
    assert current(exception_client) == before


def test_same_route_template_replacement_keeps_order_and_bound_context(exception_client):
    client = exception_client
    slot = {**mapping(), "template_group_path": ["A侧", "槽"], "candidate_features": ["通槽"]}
    assert save(client, mappings=[mapping(), slot], step_order_by_process=order(),
                hidden_step_keys=["drill.s2"]).status_code == 200
    before = current(client)
    response = replace_template(client, before["template_revision"])
    assert response.status_code == 200, response.text
    state = current(client)
    assert state["hidden_step_keys"] == state["waived_group_paths"] == []
    assert state["step_order_by_process"] == order()
    assert state["mapping_context"] == before["mapping_context"]
    assert [step["step_id"] for step in state["mapping_output"][0]["steps"]] == order()["drill"]
    revision = client.get("/api/extract/executable-rule-revisions/latest", params={"project_id": client.project_id}).json()
    exported = client.post("/api/extract/executable-rule-revisions/{}/export".format(revision["id"]), json={
        "project_id": client.project_id, "expected_workflow_revision": 0,
        "expected_content_hash": revision["content_hash"], "include_template_mapping": True})
    assert exported.status_code == 200, exported.text
    delivered = exported.json()["export_sources"]["native_snapshot"]["template_mapping_catalog"]["processes"][0]["steps"]
    assert [step["step_id"] for step in delivered] == order()["drill"]
    assert delivered[1]["candidates"] == {"A侧/孔": ["孔(盲孔)"], "A侧/槽": ["通槽"]}


def test_frozen_projection_rejects_review_with_unrelated_final_target(exception_client):
    from app.services.project_group_templates import _build_mapping_output, _step_mapping_snapshot
    from app.services.rule_packages.native_publication import compile_native_snapshot, NativePublicationError
    client = exception_client
    assert save(client, mappings=[mapping()], step_order_by_process=order(),
                waived_group_paths=[["A侧", "槽"]]).status_code == 200
    saved = current(client)
    revision = client.get("/api/extract/executable-rule-revisions/latest", params={"project_id": client.project_id}).json()
    package = RulePackageV2.model_validate(revision["package"])
    saved["step_mappings"][0]["final_targets"] = [{"process_id": "drill", "step_id": "drill.s2"}]
    from app.services.template_mapping_projection import project_mapping_route
    canonical = _build_mapping_output(saved["mapping_operations"],
        [_step_mapping_snapshot(value) for value in saved["step_mappings"]])
    saved["mapping_output"] = project_mapping_route(canonical, saved["mapping_operations"], order())
    with pytest.raises(NativePublicationError, match="映射目标"):
        compile_native_snapshot(package, [{"id": "drill"}], 0, template_mapping=saved)


@pytest.mark.parametrize("deleted", [[], ["drill.s1"]])
def test_legacy_tables_compile_intact_core_then_apply_order_and_deletion(empty_auxiliary_core_client, deleted):
    client = empty_auxiliary_core_client
    ops = client.real_operations
    ids = [step["step_id"] for step in ops[0]["steps"]]
    ordered = {op["process_id"]: [s["step_id"] for s in op["steps"]] for op in ops}
    ordered["drill"] = list(reversed(ids))
    deleted = ids[:1] if deleted else []
    bindings = [{**mapping(), "source_operation_id": step["source_operation_id"],
                 "source_step_order": step["source_step_order"], "source_step_name": step["source_step_name"],
                 "final_targets": [{"process_id": "drill", "step_id": step["step_id"]}]} for step in ops[0]["steps"]]
    response = save(client, operations=ops, mappings=bindings, hidden_step_keys=deleted,
                    step_order_by_process=ordered, waived_group_paths=[["A侧", "槽"]])
    assert response.status_code == 200, response.text

    async def compile_and_check():
        async with client.sessions() as db:
            from app.services.rule_packages.executable_revisions import require_generation
            row = await require_generation(db, client.project_id)
            package = RulePackageV2.model_validate_json(row.package_json)
            tables, sources = await compile_publication_snapshot(package, await db.get(Project, client.project_id), db)
            delivered_ids = [step["step_id"] for step in tables["full_route_table"][0]["steps"]]
            assert delivered_ids == [sid for sid in ordered["drill"] if sid not in deleted]
            assert all(step["candidates"] == {"A侧/孔": ["孔(盲孔)"]} for step in tables["full_route_table"][0]["steps"])
            assert [step["step_id"] for step in sources["source_full_route_table"][0]["steps"]] == ids
            payload = package.model_dump(mode="json", by_alias=True, exclude_none=True)
            export = FinalizedRulePackage(id=99, created_at=datetime.now(), project_id=client.project_id, route_version_id=row.route_version_id,
                version=1, package_name=package.manifest.package_name, schema_version="2.0", status="published",
                **{key + "_json": json.dumps(payload[key]) for key in ("manifest", "factor_dictionary", "input_schema", "route_catalog", "route_rules", "test_cases")},
                content_hash=row.content_hash, demo_tables_json=json.dumps(tables), export_sources_json=json.dumps(sources))
            assert serialize_finalized_rule_package(export).export_error is None
            altered = deepcopy(sources)
            altered["mapping_projection"]["step_order_by_process"]["drill"] = [ids[0], ids[0]]
            export.export_sources_json = json.dumps(altered)
            assert serialize_finalized_rule_package(export).export_error
    asyncio.run(compile_and_check())


@pytest.fixture
def auxiliary_delivery_context(exception_client):
    """A real saved mother route with three auxiliary instructions, including an attachment."""
    client = exception_client
    ops = operations()
    ops[1]["steps"] = [
        {"step_id": "check.s1", "step_name": "检验尺寸", "kind": "primary"},
        {"step_id": "check.s2", "step_name": "检验外观", "kind": "primary"},
        {"step_id": "check.s3", "step_name": "记录结果", "kind": "attached"},
    ]

    async def update_mother():
        async with client.sessions() as db:
            route = (await db.execute(select(NormalizedRouteVersion))).scalars().one()
            segments = json.loads(route.route_json)
            segments[1]["step_item_details"] = [
                {"id": step["step_id"], "text": step["step_name"], "kind": step["kind"]}
                for step in ops[1]["steps"]
            ]
            route.route_json = json.dumps(segments, ensure_ascii=False)
            await db.commit()

    asyncio.run(update_mother())
    previous = client.get("/api/extract/executable-rule-revisions/latest",
                          params={"project_id": client.project_id}).json()
    return client, ops, previous


@pytest.mark.parametrize("empty_core", [False, True], ids=["core-instructions", "empty-auxiliary-core"])
@pytest.mark.parametrize("auxiliary_order,deleted,expected", [
    (["check.s1", "check.s2", "check.s3"], [], [
        {"step_id": "check.s1", "name": "检验尺寸", "kind": "primary"},
        {"step_id": "check.s2", "name": "检验外观", "kind": "primary"},
        {"step_id": "check.s3", "name": "记录结果", "kind": "attached"},
    ]),
    (["check.s3", "check.s1", "check.s2"], [], [
        {"step_id": "check.s3", "name": "记录结果", "kind": "attached"},
        {"step_id": "check.s1", "name": "检验尺寸", "kind": "primary"},
        {"step_id": "check.s2", "name": "检验外观", "kind": "primary"},
    ]),
    (["check.s3", "check.s1", "check.s2"], ["check.s1"], [
        {"step_id": "check.s3", "name": "记录结果", "kind": "attached"},
        {"step_id": "check.s2", "name": "检验外观", "kind": "primary"},
    ]),
    (["check.s3", "check.s1", "check.s2"], ["check.s1", "check.s2", "check.s3"], []),
], ids=["unchanged", "reordered", "partially-deleted", "all-deleted"])
def test_native_auxiliary_delivery_download_and_snapshot_revalidation(
        auxiliary_delivery_context, empty_core, auxiliary_order, deleted, expected):
    """Feature bindings may be empty; only explicit deletions remove delivery instructions."""
    from app.services.rule_packages.native_publication import snapshot_hash, validate_native_snapshot

    client, ops, previous = auxiliary_delivery_context
    package = deepcopy(previous["package"])
    core_steps = [] if empty_core else [
        {"step_id": "check.s1", "name": "检验尺寸", "kind": "primary"},
        {"step_id": "check.s2", "name": "检验外观", "kind": "primary"},
        {"step_id": "check.s3", "name": "记录结果", "kind": "attached"},
    ]
    package["route_catalog"]["processes"][1]["steps"] = core_steps
    revision = client.post("/api/extract/executable-rule-revisions", json={**package,
        "project_id": client.project_id, "route_version_id": previous["route_version_id"],
        "package_name": package["manifest"]["package_name"], "expected_executable_revision": previous["revision"],
        "expected_workflow_revision": 0, "rule_report_md": "# Auxiliary delivery regression"})
    assert revision.status_code == 200, revision.text
    revision = revision.json()
    generated = client.post("/api/generate/", json={"project_id": client.project_id,
        "expected_workflow_revision": 0, "executable_revision_id": revision["id"],
        "factor_values": {}, "input_metadata": {}})
    assert generated.status_code == 200, generated.text
    before = executable_snapshot(client)
    ordered = {"drill": ["drill.s1", "drill.s2"], "check": auxiliary_order}
    saved = save(client, operations=ops, step_order_by_process=ordered, hidden_step_keys=deleted,
                 waived_group_paths=[["A侧", "孔"], ["A侧", "槽"]])
    assert saved.status_code == 200, saved.text
    # Auxiliary rows contain no feature bindings, independently of their instructions.
    assert saved.json()["mapping_output"][1]["steps"] == []
    exported = client.post("/api/extract/executable-rule-revisions/{}/export".format(revision["id"]), json={
        "project_id": client.project_id, "expected_workflow_revision": 0,
        "expected_content_hash": revision["content_hash"], "include_template_mapping": True})
    assert exported.status_code == 200, exported.text
    exported = exported.json()
    frozen = exported["export_sources"]
    assert frozen["native_snapshot"]["rule_package"]["route_catalog"]["processes"][1]["steps"] == core_steps
    assert [step["step_id"] for step in frozen["mother_route"]["check"]["steps"]] == [
        "check.s1", "check.s2", "check.s3"]

    for endpoint in ("latest", str(exported["id"])):
        downloaded = client.get("/api/extract/finalized-rule-packages/" + endpoint,
                                params={"project_id": client.project_id})
        assert downloaded.status_code == 200, downloaded.text
        downloaded = downloaded.json()
        assert downloaded["export_error"] is None
        assert downloaded["export_sources"] == frozen
        # This frozen catalog is consumed by nativeRulePackageFiles/full_route_table.json.
        assert downloaded["export_sources"]["native_snapshot"]["template_mapping_catalog"]["processes"][1]["steps"] == expected

    async def revalidate():
        async with client.sessions() as db:
            row = await db.get(FinalizedRulePackage, exported["id"])
            assert validate_native_snapshot(row, frozen)
            altered = deepcopy(frozen)
            altered["native_snapshot"]["template_mapping_catalog"]["processes"][1]["steps"] = [
                {"step_id": "invented", "name": "伪造辅助工步", "kind": "primary"}]
            altered["native_snapshot_hash"] = snapshot_hash(altered["native_snapshot"])
            assert not validate_native_snapshot(row, altered)
    asyncio.run(revalidate())
    assert executable_snapshot(client) == before
