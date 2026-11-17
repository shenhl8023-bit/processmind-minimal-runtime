"""PM007: executable validation precedes optional mapping and immutable export."""

import asyncio
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import (Document, DocumentOperationDetail, FinalizedRulePackage, GeneratedRoute, ProjectGroupTemplate,
                               NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project)
from app.services.rule_packages.contracts import InputSchemaV2
from app.services.rule_packages.input_validation import validate_inputs


@pytest.fixture
def executable_context(tmp_path, monkeypatch, rule_package_v2_payload):
    from app.core.product_profile import get_product_profile
    profile = tmp_path / "full.json"
    profile.write_text(json.dumps({"edition": "full", "template_mapping_enabled": True, "expires_at": None}))
    monkeypatch.setenv("PROCESSMIND_PROFILE_PATH", str(profile))
    get_product_profile.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "executable.db"))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    package = deepcopy(rule_package_v2_payload)
    for i, process in enumerate(sorted(package["route_catalog"]["processes"], key=lambda p: p["default_sequence"])):
        process["source_operation_ids"] = [100 + i]
    segments = [{"id": "segment-" + str(i), "export_process_id": p["process_id"],
                 "normalized_step_name": p["display_name"], "source_operation_ids": [100 + i],
                 "phase": p["phase"],
                 "step_items": [s["name"] for s in p["steps"]],
                 "step_item_details": [{"id": s["step_id"], "text": s["name"], "kind": s["kind"]}
                                       for s in p["steps"]],
                 "doc_coverage": {"hit_docs": 0, "total_docs": 1}}
                for i, p in enumerate(sorted(package["route_catalog"]["processes"], key=lambda p: p["default_sequence"]))]

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(Project(id=12, name="executable", status="ROUTE_SET_READY"))
            db.add(Document(project_id=12, filename="part.pdf", original_name="part.pdf"))
            db.add(NormalizedRouteVersion(id=31, project_id=12, version=1, route_json=json.dumps(segments)))
            db.add_all([NormalizedRouteSegmentRuleReview(project_id=12, route_version_id=31,
                        segment_id=s["id"], decision="accepted") for s in segments])
            await db.commit()
    asyncio.run(setup())

    async def override():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    body = {**package, "project_id": 12, "route_version_id": 31,
            "package_name": package["manifest"]["package_name"], "expected_executable_revision": 0,
            "expected_workflow_revision": 0, "rule_report_md": "# Reviewed executable"}
    yield client, factory, body
    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())
    get_product_profile.cache_clear()


def save(client, body):
    response = client.post("/api/extract/executable-rule-revisions", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def generate(client, revision, **overrides):
    body = {"project_id": 12, "executable_revision_id": revision["id"],
            "factor_values": {"material.grade": "9Cr18", "cad.features": ["槽类特征"], "target_hardness_hrc": 58},
            "input_metadata": {k: {"origin": "manual"} for k in
                               ("material.grade", "cad.features", "target_hardness_hrc")}}
    body.update(overrides)
    return client.post("/api/generate/", json=body)


def export(client, revision, **overrides):
    body = {"project_id": 12, "expected_content_hash": revision["content_hash"],
            "include_template_mapping": False}
    body.update(overrides)
    return client.post("/api/extract/executable-rule-revisions/{}/export".format(revision["id"]), json=body)


def test_save_generate_export_without_template_or_prior_export(executable_context):
    client, factory, body = executable_context
    assert client.get("/api/projects/12/workflow-progress").json()["max_available_step"] == 4
    revision = save(client, body)
    assert revision["revision"] == 1 and revision["generation_ready"]
    assert not revision["has_current_generation"]
    assert client.get("/api/projects/12/workflow-progress").json()["max_available_step"] == 5
    assert export(client, revision).status_code == 409
    generated = generate(client, revision)
    assert generated.status_code == 200, generated.text
    result = generated.json()
    assert result["executable_revision_id"] == revision["id"]
    assert result["executable_content_hash"] == revision["content_hash"]
    assert result["selected_process_ids"] == ["process_prepare", "process_rough_machine", "process_mill_slot", "process_quench"]
    assert client.get("/api/projects/12/workflow-progress").json()["max_available_step"] == 6
    listed = client.get("/api/generate/results?project_id=12")
    assert listed.status_code == 200, listed.text
    assert [r["id"] for r in listed.json()["results"]] == [result["id"]]
    assert listed.json()["results"][0] == result
    published = export(client, revision)
    assert published.status_code == 200, published.text
    assert published.json()["content_hash"] == revision["content_hash"]
    assert published.json()["export_error"] is None
    assert published.json()["export_sources"]["executable_revision_id"] == revision["id"]
    assert save(client, {**body, "expected_executable_revision": 1})["id"] == revision["id"]


def test_compile_cas_and_generation_revision_guards(executable_context):
    client, _, body = executable_context
    revision = save(client, body)
    assert client.post("/api/extract/executable-rule-revisions", json=body).status_code == 409
    assert generate(client, revision, executable_revision_id=999).status_code == 409
    assert generate(client, revision, expected_workflow_revision=5).status_code == 409
    assert export(client, revision, expected_content_hash="wrong").status_code == 409
    assert export(client, revision, project_id=99).status_code in (404, 409)


def test_rule_edit_deletes_results_and_requires_new_validation(executable_context):
    client, factory, body = executable_context
    revision = save(client, body)
    assert generate(client, revision).status_code == 200

    async def edit():
        async with factory() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview).limit(1))).scalar_one()
            row.condition_source_text = "用户修改了工序规则"
            await db.commit()
        async with factory() as db:
            return (await db.execute(select(GeneratedRoute))).scalars().all()
    assert asyncio.run(edit()) == []
    latest = client.get("/api/extract/executable-rule-revisions/latest?project_id=12")
    assert latest.status_code == 200, latest.text
    assert latest.json()["revision"] == 1
    assert latest.json()["generation_ready"] is False
    assert latest.json()["has_current_generation"] is False
    assert generate(client, revision).status_code == 409
    assert export(client, revision).status_code == 409
    assert client.get("/api/projects/12/workflow-progress").json()["max_available_step"] == 4

    assert client.post("/api/extract/executable-rule-revisions", json={**body,
        "expected_executable_revision": latest.json()["revision"]}).status_code == 409
    async def confirm_mainline():
        async with factory() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview).limit(1))).scalar_one()
            row.condition_source_text = "固定为主工序，默认保留"
            row.condition_status = "draft"
            await db.commit()
    asyncio.run(confirm_mainline())
    fresh = save(client, {**body, "expected_executable_revision": latest.json()["revision"]})
    assert fresh["revision"] == 2 and fresh["generation_ready"]
    assert not fresh["has_current_generation"]
    assert export(client, fresh).status_code == 409
    assert generate(client, fresh).status_code == 200
    assert export(client, fresh).status_code == 200


def test_missing_latest_exposes_zero_cas_counter(executable_context):
    client, _, _ = executable_context
    response = client.get("/api/extract/executable-rule-revisions/latest?project_id=12")
    assert response.status_code == 404
    assert response.json()["detail"]["executable_revision"] == 0


def test_incomplete_analysis_cannot_save_or_bypass_export(executable_context):
    client, factory, body = executable_context
    async def edit():
        async with factory() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview).limit(1))).scalar_one()
            row.decision = "pending"
            await db.commit()
    asyncio.run(edit())
    assert client.post("/api/extract/executable-rule-revisions", json=body).status_code == 409
    assert client.post("/api/extract/finalized-rule-packages", json=body).status_code == 409


def test_reset_finalize_retains_analysis_lock_but_revokes_generation(executable_context):
    client, factory, body = executable_context
    revision = save(client, body)
    assert generate(client, revision).status_code == 200
    response = client.post("/api/extract/workflow/reset", json={"project_id": 12, "from_step": 4})
    assert response.status_code == 200, response.text
    assert response.json()["deleted_rule_reviews"] == 0
    assert export(client, revision, expected_workflow_revision=1).status_code == 409


@pytest.mark.parametrize("leaf,value", [("it", 0), ("it", 19), ("it", 7.5), ("ra", 0), ("ra", -0.8)])
def test_scoped_numeric_domain_validation(leaf, value):
    key = "project_factor.operation_a1b2." + leaf
    schema = InputSchemaV2.model_validate({"fields": [{"key": key, "label": leaf, "type": "number",
        "source": "项目问答配置；同一加工对象；工序=process_grind"}]})
    assert validate_inputs(schema, {key: value})


def test_scoped_reversed_hardness_interval_and_closed_empty_material_rejected():
    prefix = "project_factor.operation_a1b2."
    schema = InputSchemaV2.model_validate({"fields": [
        {"key": prefix + k, "label": k, "type": "number"} for k in ("hardness_min", "hardness_max")]})
    assert validate_inputs(schema, {"project_factor": {"operation_a1b2": {"hardness_min": 60, "hardness_max": 40}}})
    material = InputSchemaV2.model_validate({"fields": [{"key": "project_factor.material_grade", "label": "材料",
        "type": "single_select", "options": [], "allow_custom": False}]})
    assert validate_inputs(material, {"project_factor.material_grade": "invented"})


def test_mapped_export_enriches_only_route_candidates_same_core_bytes(executable_context):
    client, factory, body = executable_context
    for i, p in enumerate(sorted(body["route_catalog"]["processes"], key=lambda p: p["default_sequence"])):
        p["source_operation_ids"] = [100 + i]
    revision = save(client, body)
    assert generate(client, revision).status_code == 200
    plain = export(client, revision).json()
    mapping_output = [{"process_id": p["process_id"], "process_name": p["display_name"],
        "process_type": "加工工序" if p["steps"] else "辅助工序", "precision": "粗加工" if p["steps"] else "辅助工序",
        "steps": [{"step_id": s["step_id"], "step_name": s["name"],
                   "candidates": {"外圆": ["外圆柱面"]} if p["process_id"] == "process_rough_machine" else {}}
                  for s in p["steps"]]} for p in body["route_catalog"]["processes"]]

    async def seed_mapping():
        async with factory() as db:
            db.add(ProjectGroupTemplate(project_id=12, original_filename="fixture.xml", source_encoding="utf-8",
                part_filename="fixture.prt", content_hash="a" * 64, feature_dictionary_version="b" * 64,
                source_xml="<Kmsoft/>", template_revision=1,
                tree_json=json.dumps([{"key": "outer", "name": "外圆", "path": ["外圆"], "children": [], "feature_selections": ["外圆柱面"]}]),
                mappings_json=json.dumps([{"source_operation_id": 101, "alias": "外圆",
                    "template_group_path": ["外圆"], "feature_selections": ["外圆柱面"]}]),
                step_mappings_json="[]", mapping_output_json=json.dumps(mapping_output)))
            await db.commit()
    asyncio.run(seed_mapping())
    mapped_response = export(client, revision, include_template_mapping=True)
    assert mapped_response.status_code == 200, mapped_response.text
    mapped = mapped_response.json()
    snapshot = mapped["export_sources"]["template_mapping"]
    assert snapshot["template_revision"] == 1
    assert snapshot["step_mappings"] == []
    assert snapshot["mapping_output"] == mapping_output
    assert snapshot["hidden_step_keys"] == []
    assert snapshot["waived_group_paths"] == []
    assert mapped["demo_tables"] is None
    assert mapped["content_hash"] == plain["content_hash"] == revision["content_hash"]
    plain_core = plain["export_sources"]["native_snapshot"]["rule_package"]
    mapped_core = mapped["export_sources"]["native_snapshot"]["rule_package"]
    for key in ("factor_dictionary", "input_schema", "route_rules"):
        assert json.dumps(mapped_core[key], ensure_ascii=False) == json.dumps(plain_core[key], ensure_ascii=False)
    assert isinstance(mapped_core["route_catalog"], dict)
    enriched = deepcopy(mapped_core["route_catalog"])
    candidates = [step.pop("candidates") for p in enriched["processes"] for step in p["steps"]]
    assert {"外圆": ["外圆柱面"]} in candidates
    assert enriched == plain_core["route_catalog"]
    assert {p["process_id"] for p in mapped_core["route_catalog"]["processes"]} == {
        p["process_id"] for p in body["route_catalog"]["processes"]}
    assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").json()["has_current_generation"]
    assert len(client.get("/api/generate/results?project_id=12").json()["results"]) == 1
    historical = client.get("/api/extract/finalized-rule-packages/{}?project_id=12".format(plain["id"]))
    assert historical.json()["export_sources"] == plain["export_sources"]


def test_optional_question_rewrite_uses_current_shared_guidance(executable_context, monkeypatch):
    from app.routers import generate as module
    from app.schemas.schemas import ParamCurrentQuestionOut, ParamOperationReviewOut
    client, factory, _ = executable_context
    guidance = client.get("/api/projects/12/analysis-guidance").json()["configuration"]
    guidance["guidance"] = "仅对下一次回答使用项目自定义加工提示XYZ"
    response = client.put("/api/projects/12/analysis-guidance", json={
        "expected_configuration_revision": 0, "configuration": guidance})
    assert response.status_code == 200, response.text
    captured = []
    async def fake_model(system, user, **kwargs):
        captured.append(system)
        return '{"questions": []}'
    monkeypatch.setattr(module, "call_llm", fake_model)
    monkeypatch.setattr(module, "get_prompt_template", lambda name: "{{question_payload_json}}" if name.endswith("user") else "基础提示")
    reviews = [ParamOperationReviewOut(operation_key="grind", stage="精加工", step_name="磨外圆",
        current_question=ParamCurrentQuestionOut(factor_key="it", question_type="single", prompt="实际精度？"))]
    before = reviews[0].model_dump()
    async def invoke():
        async with factory() as db:
            return await module._enhance_param_operation_questions_with_llm(reviews, db=db, project_id=12)
    asyncio.run(invoke())
    assert captured and response.json()["prompt_reference"] in captured[0]
    assert reviews[0].model_dump() == before


@pytest.mark.parametrize("values,code", [
    ({"it": 7.5}, "input_it_invalid"), ({"it": 19}, "input_it_invalid"),
    ({"ra": 0}, "input_ra_invalid"),
    ({"hardness_min": 60, "hardness_max": 40}, "input_hardness_interval_invalid"),
])
def test_generation_rejects_scoped_invalid_values_without_success_record(executable_context, values, code):
    client, factory, body = executable_context
    prefix = "project_factor.operation_ab12."
    body["input_schema"]["fields"].extend([{"key": prefix + key, "label": key, "type": "number",
        "source": "项目问答配置；同一加工对象；工序=process_quench"} for key in values])
    row = save(client, body)
    actual = {"material.grade": "9Cr18", "cad.features": ["槽类特征"], "target_hardness_hrc": 58,
              **{prefix + key: value for key, value in values.items()}}
    response = generate(client, row, factor_values=actual,
        input_metadata={key: {"origin": "manual"} for key in actual})
    assert response.status_code == 422, response.text
    assert code in {item["code"] for item in response.json()["detail"]}
    assert not client.get("/api/generate/results?project_id=12").json()["results"]
    assert export(client, row).status_code == 409


def test_scoped_valid_boundaries_and_material_closed_choices(executable_context):
    client, _, body = executable_context
    body["input_schema"]["fields"].extend([
        {"key": "project_factor.operation_a.it", "label": "IT", "type": "number"},
        {"key": "project_factor.operation_a.ra", "label": "Ra", "type": "number"},
        {"key": "project_factor.operation_a.hardness_min", "label": "下限", "type": "number"},
        {"key": "project_factor.operation_a.hardness_max", "label": "上限", "type": "number"},
        {"key": "project_factor.material_grade", "label": "材料", "type": "single_select",
         "options": [{"value": "9Cr18", "label": "9Cr18"}], "allow_custom": False}])
    row = save(client, body)
    values = {"material.grade": "9Cr18", "cad.features": ["槽类特征"], "target_hardness_hrc": 58,
        "project_factor.operation_a.it": 5, "project_factor.operation_a.ra": 0.01,
        "project_factor.operation_a.hardness_min": 40, "project_factor.operation_a.hardness_max": 40,
        "project_factor.material_grade": "fabricated"}
    metadata = {key: {"origin": "manual"} for key in values}
    assert generate(client, row, factor_values=values, input_metadata=metadata).status_code == 422
    values["project_factor.material_grade"] = "9Cr18"
    response = generate(client, row, factor_values=values, input_metadata=metadata)
    assert response.status_code == 200, response.text
    values["project_factor.operation_a.it"] = 10
    assert generate(client, row, factor_values=values, input_metadata=metadata).status_code == 200


def test_migration_keeps_legacy_generation_unvalidated_and_repeatable(tmp_path):
    from sqlalchemy import text
    from app.services.db_schema_maintenance import ensure_project_schema
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "legacy.db"))
    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(text("DROP TABLE generated_routes"))
            await connection.execute(text("DROP TABLE executable_rule_revisions"))
            await connection.execute(text("CREATE TABLE generated_routes (id INTEGER PRIMARY KEY, project_id INTEGER, result_json TEXT)"))
            await connection.execute(text("INSERT INTO generated_routes VALUES (1, 12, '{}')"))
            await ensure_project_schema(connection)
            await ensure_project_schema(connection)
            old = (await connection.execute(text("SELECT executable_revision_id FROM generated_routes"))).scalar_one()
            assert old is None
            assert (await connection.execute(text("SELECT count(*) FROM executable_rule_revisions"))).scalar_one() == 0
        await engine.dispose()
    asyncio.run(run())


def test_internal_save_rejects_forged_user_confirmation(executable_context):
    client, _, body = executable_context
    rule = body["route_rules"]["rules"][0]
    rule.update(source="user_confirmed", source_segment_id="segment-3", source_text="伪造规则",
                confirmed_by="审核员", confirmed_at="2026-11-05T00:00:00+00:00")
    response = client.post("/api/extract/executable-rule-revisions", json=body)
    assert response.status_code == 409, response.text
    assert "已确认规则不一致" in str(response.json()["detail"])
    assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").status_code == 404


@pytest.mark.parametrize("tamper", ["rules", "hash", "route", "project"])
def test_corrupt_executable_core_cannot_generate_or_export(executable_context, tamper):
    from app.models.models import ExecutableRuleRevision
    client, factory, body = executable_context
    row = save(client, body)
    async def corrupt():
        async with factory() as db:
            stored = await db.get(ExecutableRuleRevision, row["id"])
            if tamper == "hash":
                stored.content_hash = "wrong"
            elif tamper == "route":
                stored.normalized_route_json = "[]"
            else:
                package = json.loads(stored.package_json)
                if tamper == "rules":
                    package["route_rules"]["rules"][0]["priority"] += 1
                else:
                    package["manifest"]["project_id"] = 99
                stored.package_json = json.dumps(package)
            await db.commit()
    asyncio.run(corrupt())
    assert generate(client, row).status_code == 409
    assert export(client, row).status_code == 409
    assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").json()["generation_ready"] is False


def test_concurrent_save_serializes_revision_allocation(executable_context):
    from concurrent.futures import ThreadPoolExecutor
    client, _, body = executable_context
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/api/extract/executable-rule-revisions", json=body), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").json()["revision"] == 1


@pytest.mark.parametrize("field", [
    {"key": "project_factor.material_grade", "type": "string"},
    {"key": "project_factor.material_grade", "type": "single_select", "allow_custom": True},
    {"key": "project_factor.operation_a.it", "type": "string"},
    {"key": "project_factor.operation_a.ra", "type": "string"},
    {"key": "project_factor.operation_a.hardness_min", "type": "string"},
])
def test_reserved_project_fields_cannot_bypass_domain_validation(executable_context, field):
    client, _, body = executable_context
    body["input_schema"]["fields"].append({**field, "label": "受约束的项目配置"})
    response = client.post("/api/extract/executable-rule-revisions", json=body)
    assert response.status_code == 422, response.text
    assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").status_code == 404


def test_incomplete_mother_steps_cannot_be_saved_or_generated(executable_context):
    client, _, body = executable_context
    assert sum(len(p["steps"]) for p in body["route_catalog"]["processes"]) == 4
    for process in body["route_catalog"]["processes"]:
        process["steps"] = []
    response = client.post("/api/extract/executable-rule-revisions", json=body)
    assert response.status_code == 422, response.text
    assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").status_code == 404


@pytest.mark.parametrize("change", ["delete", "rename", "reorder", "fake_id", "append", "kind", "source",
                                    "drop_sources", "duplicate_sources", "cross_process", "disguise_auxiliary"])
def test_save_checks_mother_step_identity_text_order_kind_and_sources(executable_context, change):
    client, factory, body = executable_context
    process = next(p for p in body["route_catalog"]["processes"] if p["process_id"] == "process_rough_machine")
    process["steps"].append({"step_id": "rough.finish", "name": "精车", "kind": "primary"})
    async def authoritative_steps():
        async with factory() as db:
            route = await db.get(NormalizedRouteVersion, 31)
            segments = json.loads(route.route_json)
            segment = next(s for s in segments if s["export_process_id"] == process["process_id"])
            segment["step_item_details"].append({"id": "rough.finish", "text": "精车", "kind": "primary"})
            segment["step_items"].append("精车")
            route.route_json = json.dumps(segments)
            await db.commit()
    asyncio.run(authoritative_steps())
    good = save(client, body)
    assert generate(client, good).status_code == 200
    body["expected_executable_revision"] = 1
    if change == "delete": process["steps"] = []
    elif change == "rename": process["steps"][0]["name"] = "伪造工步"
    elif change == "reorder": process["steps"].reverse()
    elif change == "fake_id": process["steps"][0]["step_id"] = "other.primary.op_999_s1"
    elif change == "append": process["steps"].append({"step_id": "injected", "name": "伪造工步", "kind": "primary"})
    elif change == "kind": process["steps"][0]["kind"] = "attached"
    elif change == "source": process["source_operation_ids"] = [999]
    elif change == "drop_sources": process["source_operation_ids"] = []
    elif change == "duplicate_sources": process["source_operation_ids"] *= 2
    elif change == "cross_process": process["steps"] = deepcopy(body["route_catalog"]["processes"][0]["steps"])
    elif change == "disguise_auxiliary":
        process.update(phase="heat_treatment", display_name="清洗", steps=[])
    response = client.post("/api/extract/executable-rule-revisions", json=body)
    assert response.status_code == 422, response.text
    latest = client.get("/api/extract/executable-rule-revisions/latest?project_id=12").json()
    assert latest["id"] == good["id"] and latest["has_current_generation"]
    assert export(client, good).status_code == 200


def test_legal_auxiliary_empty_steps_still_save_generate_and_export(executable_context):
    client, _, body = executable_context
    process = next(p for p in body["route_catalog"]["processes"] if p["process_id"] == "process_quench")
    assert process["steps"]
    process["steps"] = []
    revision = save(client, body)
    assert generate(client, revision).status_code == 200
    assert export(client, revision).status_code == 200


@pytest.fixture
def extracted_mother_context(executable_context):
    client, factory, body = executable_context
    async def setup():
        async with factory() as db:
            document = (await db.execute(select(Document).where(Document.project_id == 12))).scalar_one()
            for index, (name, content) in enumerate([
                ("钻孔", "1. 钻孔（主一）\n2. 铰孔\n3. 钻孔（主二）"),
                ("铣槽", "1. 钻孔\n2. 铣槽"), ("检验", "1. 检验尺寸")], 1):
                db.add(DocumentOperationDetail(project_id=12, document_id=document.id, pdf_name="part.pdf",
                    operation_seq=index * 10, operation_name=name, operation_content=content, page_no=1,
                    source_type="json_route_extract"))
            route = await db.get(NormalizedRouteVersion, 31)
            route.route_json = json.dumps([
                {"id": "segment-0", "export_process_id": "mother", "normalized_step_name": "孔槽加工",
                 "phase": "rough", "step_family": "孔加工类", "source_operation_ids": [900001, 900002]},
                {"id": "segment-1", "export_process_id": "check", "normalized_step_name": "检验",
                 "phase": "inspection", "source_operation_ids": [900003]}])
            await db.commit()
    asyncio.run(setup())
    body.update(factor_dictionary=None, input_schema={"fields": []}, route_rules={"rules": []}, test_cases=[])
    body["route_catalog"] = {"processes": [
        {"process_id": "mother", "display_name": "孔槽加工", "source_operation_ids": [900001, 900002],
         "default_sequence": 10, "main": True, "steps": [
             {"step_id": "mother.primary.op_900001_s1", "name": "钻孔", "kind": "primary"},
             {"step_id": "mother.primary.op_900001_s2", "name": "铰孔", "kind": "primary"},
             {"step_id": "mother.primary.op_900001_s3", "name": "钻孔", "kind": "primary"},
             {"step_id": "mother.primary.op_900002_s2", "name": "铣槽", "kind": "primary"}]},
        {"process_id": "check", "display_name": "检验", "source_operation_ids": [900003],
         "default_sequence": 20, "main": True, "steps": []}]}
    return client, factory, body


@pytest.mark.parametrize("change", ["none", "delete", "rename", "reorder", "source_position", "source_id",
                                    "drop_source", "append", "kind"])
def test_saved_route_without_inline_steps_reconstructs_authoritative_extracted_steps(extracted_mother_context, change):
    client, _, body = extracted_mother_context
    process = body["route_catalog"]["processes"][0]
    if change == "delete": process["steps"] = []
    elif change == "rename": process["steps"][0]["name"] = "伪造钻孔"
    elif change == "reorder": process["steps"].reverse()
    elif change == "source_position": process["steps"][0]["step_id"] = "mother.primary.op_900002_s1"
    elif change == "source_id": process["source_operation_ids"] = [900003]
    elif change == "drop_source": process["source_operation_ids"] = [900001]
    elif change == "append": process["steps"].append({"step_id": "fabricated", "name": "伪造", "kind": "primary"})
    elif change == "kind": process["steps"][0]["kind"] = "attached"
    response = client.post("/api/extract/executable-rule-revisions", json=body)
    if change != "none":
        assert response.status_code == 422, response.text
        assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").status_code == 404
        return
    assert response.status_code == 200, response.text
    row = response.json()
    generated = generate(client, row, factor_values={}, input_metadata={})
    assert generated.status_code == 200, generated.text
    assert generated.json()["steps"][0]["process_steps"] == ["钻孔", "铰孔", "钻孔", "铣槽"]
    assert export(client, row).status_code == 200


def test_historic_incomplete_core_with_recomputed_hash_is_not_current(extracted_mother_context):
    from app.models.models import ExecutableRuleRevision
    from app.services.rule_packages.contracts import RulePackageV2
    from app.services.rule_packages.hashing import rule_package_content_hash
    client, factory, body = extracted_mother_context
    revision = save(client, body)
    assert generate(client, revision, factor_values={}, input_metadata={}).status_code == 200
    async def corrupt_legacy_core():
        async with factory() as db:
            stored = await db.get(ExecutableRuleRevision, revision["id"])
            package = RulePackageV2.model_validate_json(stored.package_json)
            package.route_catalog.processes[0].steps = []
            stored.package_json = package.model_dump_json(by_alias=True, exclude_none=True)
            stored.content_hash = rule_package_content_hash(package)
            await db.commit()
            return stored.content_hash
    bad_hash = asyncio.run(corrupt_legacy_core())
    latest = client.get("/api/extract/executable-rule-revisions/latest?project_id=12").json()
    assert latest["generation_ready"] is False
    assert generate(client, revision, factor_values={}, input_metadata={}).status_code == 409
    assert export(client, revision, expected_content_hash=bad_hash).status_code == 409


def test_mother_steps_preserve_repeats_attached_offsets_and_all_sources():
    from app.services.rule_packages.mother_route import build_mother_route
    mother = build_mother_route([
        {"id": "cut", "normalized_step_name": "孔加工", "source_operation_ids": [12, 11]},
        {"id": "cut_again", "normalized_step_name": "孔加工", "source_operation_ids": [11]},
    ], [
        {"id": 11, "step_items": ["钻孔（第一处）", "", "钻孔（第二处）"],
         "attached_step_items": ["倒角（第一处）", "倒角（第二处）"]},
        {"id": 12, "step_items": ["钻孔"], "attached_step_items": ["倒角", "去毛刺"]},
    ])
    assert [(s["step_id"], s["name"], s["kind"]) for s in mother["cut"]["steps"]] == [
        ("cut.primary.op_11_s1", "钻孔", "primary"),
        ("cut.primary.op_11_s3", "钻孔", "primary"),
        ("cut.attached.op_11_s4", "倒角", "attached"),
        ("cut.attached.op_11_s5", "倒角", "attached"),
        ("cut.attached.op_12_s3", "去毛刺", "attached"),
    ]
    assert mother["cut"]["steps"][2]["source_steps"] == [
        {"source_operation_id": 11, "source_step_order": 4, "source_step_name": "倒角（第一处）"},
        {"source_operation_id": 12, "source_step_order": 2, "source_step_name": "倒角"},
    ]
    assert [s["step_id"] for s in mother["cut_again"]["steps"]] == [
        "cut_again.primary.op_11_s1", "cut_again.primary.op_11_s3",
        "cut_again.attached.op_11_s4", "cut_again.attached.op_11_s5",
    ]


def test_saved_source_order_defines_step_identity_without_overriding_current_text(extracted_mother_context):
    from app.models.models import RouteMergeSnapshot
    client, factory, body = extracted_mother_context
    async def save_source_order():
        async with factory() as db:
            db.add(RouteMergeSnapshot(project_id=12, superset_route_json=json.dumps([
                {"id": 900002, "step_items": ["不能替代提取文本"]}, {"id": 900001}, {"id": 900003}])))
            await db.commit()
    asyncio.run(save_source_order())
    body["route_catalog"]["processes"][0]["steps"] = [
        {"step_id": "mother.primary.op_900002_s1", "name": "钻孔", "kind": "primary"},
        {"step_id": "mother.primary.op_900002_s2", "name": "铣槽", "kind": "primary"},
        {"step_id": "mother.primary.op_900001_s2", "name": "铰孔", "kind": "primary"},
        {"step_id": "mother.primary.op_900001_s3", "name": "钻孔", "kind": "primary"},
    ]
    revision = save(client, body)
    generated = generate(client, revision, factor_values={}, input_metadata={})
    assert generated.status_code == 200, generated.text
    assert generated.json()["steps"][0]["process_steps"] == ["钻孔", "铣槽", "铰孔", "钻孔"]


def test_changed_extracted_step_invalidates_saved_executable(extracted_mother_context):
    client, factory, body = extracted_mother_context
    revision = save(client, body)
    assert generate(client, revision, factor_values={}, input_metadata={}).status_code == 200
    async def change_current_source():
        async with factory() as db:
            detail = (await db.execute(select(DocumentOperationDetail).where(
                DocumentOperationDetail.project_id == 12, DocumentOperationDetail.operation_name == "铣槽"))).scalar_one()
            detail.operation_content = "1. 钻孔\n2. 铣键槽"
            await db.commit()
    asyncio.run(change_current_source())
    latest = client.get("/api/extract/executable-rule-revisions/latest?project_id=12").json()
    assert latest["generation_ready"] is False
    assert generate(client, revision, factor_values={}, input_metadata={}).status_code == 409
    assert export(client, revision).status_code == 409


def test_other_project_operation_cannot_satisfy_mother_source(extracted_mother_context):
    from app.models.models import Operation
    client, factory, body = extracted_mother_context
    async def other_project_source():
        async with factory() as db:
            db.add(Project(id=13, name="other"))
            await db.flush()
            db.add(Operation(id=123, project_id=13, name="钻孔"))
            route = await db.get(NormalizedRouteVersion, 31)
            segments = json.loads(route.route_json)
            segments[0]["source_operation_ids"] = [123]
            route.route_json = json.dumps(segments)
            await db.commit()
    asyncio.run(other_project_source())
    body["route_catalog"]["processes"][0]["source_operation_ids"] = [123]
    response = client.post("/api/extract/executable-rule-revisions", json=body)
    assert response.status_code == 422, response.text
    assert client.get("/api/extract/executable-rule-revisions/latest?project_id=12").status_code == 404


def test_mapped_export_binds_hidden_auxiliary_to_frozen_authoritative_steps(extracted_mother_context):
    client, factory, body = extracted_mother_context
    revision = save(client, body)
    assert generate(client, revision, factor_values={}, input_metadata={}).status_code == 200
    hidden = "check.primary.op_900003_s1"
    output = [{"process_id": process["process_id"], "process_name": process["display_name"],
        "process_type": "加工工序" if process["process_id"] == "mother" else "辅助工序",
        "precision": "粗加工" if process["process_id"] == "mother" else "辅助工序",
        "steps": [{"step_id": step["step_id"], "step_name": step["name"], "candidates": {}}
                  for step in process["steps"]]} for process in body["route_catalog"]["processes"]]
    async def seed():
        async with factory() as db:
            db.add(ProjectGroupTemplate(project_id=12, original_filename="fixture.xml", source_encoding="utf-8",
                part_filename="fixture.prt", content_hash="a" * 64, feature_dictionary_version="b" * 64,
                source_xml="<Kmsoft/>", template_revision=1, mappings_json="[]", step_mappings_json="[]",
                tree_json=json.dumps([{"key": "hole", "name": "孔", "path": ["孔"],
                    "children": [], "feature_selections": ["孔(盲孔)"]}]),
                mapping_output_json=json.dumps(output), hidden_step_keys_json=json.dumps([hidden]),
                waived_group_paths_json=json.dumps([["孔"]])))
            await db.commit()
    asyncio.run(seed())
    response = export(client, revision, include_template_mapping=True)
    assert response.status_code == 200, response.text
    sources = response.json()["export_sources"]
    assert sources["mother_route"]["check"]["steps"][0]["step_id"] == hidden
    assert sources["native_snapshot"]["rule_package"]["route_catalog"]["processes"][1]["steps"] == []
    assert sources["template_mapping"]["hidden_step_keys"] == [hidden]
    async def forge():
        async with factory() as db:
            template = (await db.execute(select(ProjectGroupTemplate))).scalar_one()
            template.hidden_step_keys_json = '["check.primary.op_999999_s1"]'
            await db.commit()
    asyncio.run(forge())
    assert export(client, revision, include_template_mapping=True).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("waivers,ready", [
    ([["A", "孔"]], True), ([[" A ", "孔"]], True),
    ([], False), ([["A"]], False), ([["不存在"]], False),
    ([["A", "孔"], ["A", "孔"]], False), (["A/孔"], False),
])
async def test_template_completeness_accepts_only_valid_current_leaf_waivers(monkeypatch, waivers, ready):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.rule_packages import template_mapping_requirements as module
    template = SimpleNamespace(tree=[{"path": ["A"], "children": [
        {"path": ["A", "孔"], "children": [], "feature_selections": ["孔"]}]}],
        mappings=[], step_mappings=[], mapping_output=[], waived_group_paths=waivers)
    package = SimpleNamespace(manifest=SimpleNamespace(project_id=1), route_catalog=SimpleNamespace(processes=[]))
    monkeypatch.setattr(module, "get_project_group_template", AsyncMock(return_value=object()))
    monkeypatch.setattr(module, "serialize_project_group_template", lambda _: template)
    assert (not await module.validate_rule_package_template_mapping(None, package)) is ready


def test_native_hidden_steps_omit_only_mapping_bindings(rule_package_v2_payload):
    from app.services.rule_packages.contracts import RulePackageV2
    from app.services.rule_packages.native_publication import compile_native_snapshot, NativePublicationError
    package = RulePackageV2.model_validate(rule_package_v2_payload)
    hidden = next(s.step_id for p in package.route_catalog.processes for s in p.steps)
    mapping = {"template_revision": 2, "content_hash": "a" * 64, "tree": [],
        "hidden_step_keys": [hidden], "waived_group_paths": [],
        "mapping_output": [{"process_id": p.process_id, "steps": [
            {"step_id": s.step_id, "candidates": {}} for s in p.steps if s.step_id != hidden]}
            for p in package.route_catalog.processes]}
    plain = compile_native_snapshot(package, [{"id": "mother"}], 0)
    mapped = compile_native_snapshot(package, [{"id": "mother"}], 0, template_mapping=mapping)
    core = mapped["native_snapshot"]["rule_package"]
    for p in core["route_catalog"]["processes"]:
        for s in p["steps"]:
            assert s.pop("candidates", {}) == {}
    assert core == plain["native_snapshot"]["rule_package"]
    for invalid in ([], [hidden, hidden], ["nonexistent"]):
        with pytest.raises(NativePublicationError):
            compile_native_snapshot(package, [{"id": "mother"}], 0,
                template_mapping={**mapping, "hidden_step_keys": invalid})


@pytest.mark.parametrize("omit_branch", [False, True])
def test_atomic_export_freezes_saved_exceptions_or_rolls_back(executable_context, omit_branch):
    client, factory, body = executable_context
    revision = save(client, body)
    assert generate(client, revision).status_code == 200
    plain = export(client, revision).json()
    operations = [{"operation_id": i, "process_id": p["process_id"],
        "operation_name": p["display_name"], "source_operation_ids": p.get("source_operation_ids", []),
        "process_type": "辅助工序" if plain["export_sources"]["mother_route"][p["process_id"]]["auxiliary"] else "加工工序",
        "precision": "辅助工序" if plain["export_sources"]["mother_route"][p["process_id"]]["auxiliary"] else "粗加工",
        "steps": [{"step_id": s["step_id"], "step_name": s["name"]} for s in p["steps"]]}
        for i, p in enumerate(body["route_catalog"]["processes"], 1)]
    hidden = next(s["step_id"] for p in operations for s in p["steps"])
    async def seed():
        async with factory() as db:
            db.add(ProjectGroupTemplate(project_id=12, original_filename="fixture.xml", source_encoding="utf-8",
                part_filename="fixture.prt", content_hash="a" * 64, feature_dictionary_version="b" * 64,
                source_xml="<Kmsoft/>", template_revision=1,
                tree_json=json.dumps([{"key": "outer", "name": "外圆", "path": ["外圆"], "children": [], "feature_selections": ["外圆柱面"]}]),
                mappings_json="[]", step_mappings_json="[]", mapping_output_json="[]"))
            await db.commit()
    asyncio.run(seed())
    response = export(client, revision, include_template_mapping=True, template_mapping={
        "expected_template_revision": 1, "replace_all": True, "mappings": [],
        "operations": operations[:-1] if omit_branch else operations,
        "hidden_step_keys": [hidden], "waived_group_paths": [["外圆"]]})
    stored = client.get("/api/extract/group-templates/current?project_id=12").json()
    if omit_branch:
        assert response.status_code == 422, response.text
        assert stored["template_revision"] == 1
        assert stored["hidden_step_keys"] == stored["waived_group_paths"] == stored["mapping_output"] == []
        old = client.get("/api/extract/finalized-rule-packages/{}?project_id=12".format(plain["id"])).json()
        assert old["status"] == "published"
    else:
        assert response.status_code == 200, response.text
        mapped = response.json()
        snapshot = mapped["export_sources"]["template_mapping"]
        for key in ("template_revision", "step_mappings", "mapping_output", "hidden_step_keys", "waived_group_paths"):
            assert snapshot[key] == stored[key]
        assert snapshot["template_revision"] == 2
        assert snapshot["hidden_step_keys"] == [hidden]
        assert snapshot["waived_group_paths"] == [["外圆"]]
        assert all(s["step_id"] != hidden for p in snapshot["mapping_output"] for s in p["steps"])
        core = mapped["export_sources"]["native_snapshot"]["rule_package"]
        for p in core["route_catalog"]["processes"]:
            for s in p["steps"]:
                assert s.pop("candidates", {}) == {}
        assert core == plain["export_sources"]["native_snapshot"]["rule_package"]
    assert len(client.get("/api/generate/results?project_id=12").json()["results"]) == 1
