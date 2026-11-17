"""Basic publication keeps native route/rule semantics without template state."""

import asyncio
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from executable_support import save_generate_export, generate_current
from app.models.models import (
    Document, FinalizedRulePackage, GeneratedRoute, NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion, Project, ProjectGroupTemplate,
)


@pytest.fixture
def native_context(tmp_path, monkeypatch, rule_package_v2_payload):
    from app.core.product_profile import get_product_profile

    profile = tmp_path / "basic.json"
    profile.write_text(json.dumps({
        "edition": "basic-trial", "template_mapping_enabled": False,
        "expires_at": "2026-12-31T00:00:00+08:00",
    }), encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setenv("PROCESSMIND_PROFILE_PATH", str(profile))
        get_product_profile.cache_clear()
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'native.db'}")
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        payload = deepcopy(rule_package_v2_payload)
        for index, process in enumerate(sorted(payload["route_catalog"]["processes"], key=lambda p: p["default_sequence"])):
            process["source_operation_ids"] = [100 + index]
        # Confirmed route identity, order and primary/attached steps are frozen,
        # including machining with no template candidates and an empty-step node.
        segments = [{
            "id": f"segment-{index}", "export_process_id": process["process_id"],
            "normalized_step_name": process["display_name"],
            "step_items": [step["name"] for step in process["steps"]],
            "step_item_details": [{"id": step["step_id"], "text": step["name"], "kind": step["kind"]}
                                  for step in process["steps"]],
            "source_operation_ids": [100 + index],
            "doc_coverage": {"hit_docs": 0, "total_docs": 1},
        } for index, process in enumerate(sorted(payload["route_catalog"]["processes"], key=lambda p: p["default_sequence"]))]

        async def setup():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with factory() as db:
                db.add(Project(id=12, name="basic native", status="ROUTE_SET_READY", workflow_revision=0))
                db.add(Document(project_id=12, filename="part.pdf", original_name="part.pdf", status="parsed"))
                db.add(NormalizedRouteVersion(id=31, project_id=12, version=1, route_json=json.dumps(segments)))
                await db.flush()
                db.add_all([NormalizedRouteSegmentRuleReview(project_id=12, route_version_id=31,
                    segment_id=s["id"], decision="accepted") for s in segments])
                await db.commit()

        asyncio.run(setup())

        async def override_db():
            async with factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        try:
            yield client, factory, payload, segments
        finally:
            client.close()
            app.dependency_overrides.pop(get_db, None)
            asyncio.run(engine.dispose())
    get_product_profile.cache_clear()


def publication_request(payload):
    return {
        "project_id": 12, "route_version_id": 31, "expected_workflow_revision": 0,
        "package_name": payload["manifest"]["package_name"], **payload,
        "rule_report_md": "# Confirmed native route rules",
    }


async def confirm_analysis(factory, segments):
    async with factory() as db:
        db.add_all([NormalizedRouteSegmentRuleReview(
            project_id=12, route_version_id=31, segment_id=segment["id"],
            decision="accepted", question_trail_json="[]",
        ) for segment in segments])
        await db.commit()


def test_basic_unlocks_internal_finalize_only_after_analysis(native_context):
    client, factory, _, segments = native_context
    async def unreview():
        async with factory() as db:
            for review in (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalars():
                review.decision = "pending"
            await db.commit()
    asyncio.run(unreview())
    before = client.get("/api/projects/12/workflow-progress").json()
    assert (before["completed_steps"], before["max_available_step"]) == (2, 3)
    asyncio.run(confirm_analysis(factory, segments))
    after = client.get("/api/projects/12/workflow-progress").json()
    assert (after["completed_steps"], after["max_available_step"]) == (3, 4)


def test_basic_precheck_and_publication_need_no_templates(native_context):
    client, factory, payload, segments = native_context
    asyncio.run(confirm_analysis(factory, segments))
    body = publication_request(payload)
    precheck = client.post("/api/extract/finalized-rule-packages/precheck", json=body)
    assert precheck.status_code == 200, precheck.text
    assert precheck.json()["ok"], precheck.text
    assert not {"template_mapping", "demo_tables"}.intersection(
        item["code"] for item in precheck.json()["checklist"]
    )
    published = save_generate_export(client, json=body)
    assert published.status_code == 200, published.text
    data = published.json()
    assert data["demo_tables"] is None
    assert data["export_error"] is None
    assert data["export_sources"]["compiler_version"] == "native-v2/1"
    snapshot = data["export_sources"]["native_snapshot"]
    assert snapshot["normalized_route"] == segments
    assert [p["process_id"] for p in snapshot["rule_package"]["route_catalog"]["processes"]] == [
        "process_prepare", "process_rough_machine", "process_quench", "process_mill_slot", "process_nitriding",
    ]
    assert snapshot["rule_package"]["route_rules"]["rules"][0]["when"] == payload["route_rules"]["rules"][0]["when"]
    assert snapshot["rule_package"]["route_catalog"]["processes"][1]["steps"] == [
        {"step_id": "rough.turn", "name": "粗车", "kind": "primary"},
    ]
    progress = client.get("/api/projects/12/workflow-progress").json()
    assert (progress["completed_steps"], progress["max_available_step"]) == (5, 5)
    for url in ("/api/extract/finalized-rule-packages/latest?project_id=12",
                f"/api/extract/finalized-rule-packages/{data['id']}?project_id=12"):
        downloaded = client.get(url)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.json()["export_sources"] == data["export_sources"]
        assert downloaded.json()["export_error"] is None


async def save_unrelated_mapping(factory):
    async with factory() as db:
        db.add(ProjectGroupTemplate(
            project_id=12, original_filename="old.xml", source_encoding="utf-8", part_filename="old.prt",
            content_hash="a" * 64, feature_dictionary_version="b" * 64,
            source_xml="<invalid historical template />", tree_json="[]", mappings_json="[]",
            mapping_output_json=json.dumps([{"process_id": "unrelated", "steps": []}]),
        ))
        await db.commit()


def generate(client):
    return generate_current(client, json={
        "project_id": 12,
        "factor_values": {"material": {"grade": "9Cr18"}, "cad": {"features": ["槽类特征"]},
                          "target_hardness_hrc": 58},
        "input_metadata": {"material.grade": {"origin": "manual"}, "cad.features": {"origin": "manual"},
                           "target_hardness_hrc": {"origin": "manual", "unit": "HRC"}},
    })


def test_native_generation_and_download_ignore_historical_template(native_context):
    client, factory, payload, segments = native_context
    published = save_generate_export(client, json=publication_request(payload))
    assert published.status_code == 200, published.text
    frozen = published.json()["export_sources"]
    asyncio.run(save_unrelated_mapping(factory))
    response = generate(client)
    assert response.status_code == 200, response.text
    assert response.json()["selected_process_ids"] == [
        "process_prepare", "process_rough_machine", "process_mill_slot", "process_quench",
    ]
    output = json.loads(response.json()["output_json_text"])
    # This existing field is specifically typed as a CAD mapping table. Native
    # routes live in the published snapshot; generation exposes V2 process_steps.
    assert output["full_route_structure"] == []
    assert response.json()["full_route_structure"] == []
    assert next(step for step in response.json()["steps"] if step["process_id"] == "process_rough_machine")["process_steps"] == ["粗车"]
    downloaded = client.get("/api/extract/finalized-rule-packages/latest?project_id=12").json()
    assert downloaded["export_sources"] == frozen
    assert downloaded["export_error"] is None


def test_native_publication_with_historical_mapping_equals_unmapped_publication(native_context):
    client, factory, payload, _ = native_context
    plain = save_generate_export(client, json=publication_request(payload))
    assert plain.status_code == 200, plain.text
    asyncio.run(save_unrelated_mapping(factory))
    mapped = save_generate_export(client, json=publication_request(payload))
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["export_sources"] == plain.json()["export_sources"]
    assert mapped.json()["content_hash"] == plain.json()["content_hash"]


def test_basic_discards_template_metadata_from_stale_publication_request(native_context):
    client, _, payload, _ = native_context
    plain = save_generate_export(client, json=publication_request(payload))
    assert plain.status_code == 200, plain.text
    payload["manifest"]["compiled_from"]["template_ids"] = [987]
    payload["route_catalog"]["processes"][0]["template_group_aliases"] = [{
        "source_operation_id": 100, "alias": "old-feature", "template_group_id": "old-template",
        "template_group_path": ["old-group"], "feature_selections": ["old-feature"],
    }]
    response = save_generate_export(client, json=publication_request(payload))
    assert response.status_code == 200, response.text
    assert response.json()["content_hash"] == plain.json()["content_hash"]
    assert response.json()["export_sources"] == plain.json()["export_sources"]
    generated = generate(client)
    assert generated.status_code == 200, generated.text
    assert all(not step["template_group_aliases"] for step in generated.json()["steps"])


def test_native_archived_download_uses_frozen_route_even_in_full_profile(native_context, tmp_path, monkeypatch):
    from app.core.product_profile import get_product_profile

    client, factory, payload, segments = native_context
    published = save_generate_export(client, json=publication_request(payload))
    assert published.status_code == 200, published.text
    frozen = published.json()["export_sources"]

    async def change_current_route():
        async with factory() as db:
            row = (await db.execute(select(FinalizedRulePackage))).scalar_one()
            row.status = "archived"
            row.route_version_id = None
            current = await db.get(NormalizedRouteVersion, 31)
            current.route_json = "[]"
            await db.commit()

    asyncio.run(change_current_route())
    full = tmp_path / "full.json"
    full.write_text(json.dumps({"edition": "full", "template_mapping_enabled": True, "expires_at": None}))
    with monkeypatch.context() as patch:
        patch.setenv("PROCESSMIND_PROFILE_PATH", str(full))
        get_product_profile.cache_clear()
        downloaded = client.get(f"/api/extract/finalized-rule-packages/{published.json()['id']}?project_id=12")
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.json()["export_error"] is None
    assert downloaded.json()["export_sources"] == frozen
    assert downloaded.json()["export_sources"]["native_snapshot"]["normalized_route"] == segments


def test_full_native_export_is_independent_of_legacy_mapping_precheck(native_context, tmp_path, monkeypatch):
    from app.core.product_profile import get_product_profile

    client, _, payload, _ = native_context
    profile = tmp_path / "full.json"
    profile.write_text(json.dumps({"edition": "full", "template_mapping_enabled": True, "expires_at": None}))
    with monkeypatch.context() as patch:
        patch.setenv("PROCESSMIND_PROFILE_PATH", str(profile))
        get_product_profile.cache_clear()
        precheck = client.post("/api/extract/finalized-rule-packages/precheck", json=publication_request(payload))
        published = save_generate_export(client, json=publication_request(payload))
    assert precheck.status_code == 200, precheck.text
    assert not precheck.json()["ok"]
    assert "group_template_missing" in {item["code"] for item in precheck.json()["blockers"]}
    assert published.status_code == 200, published.text
    assert published.json()["export_sources"]["compiler_version"] == "native-v2/1"


def test_basic_keeps_manual_rule_confirmation_gate(native_context):
    client, _, payload, _ = native_context
    payload["route_rules"]["rules"][0].update({
        "source": "user_confirmed", "source_segment_id": "segment-2",
        "source_text": "unconfirmed instruction", "confirmed_by": "tester", "confirmed_at": "2026-10-30T00:00:00Z",
    })
    precheck = client.post("/api/extract/finalized-rule-packages/precheck", json=publication_request(payload))
    assert precheck.status_code == 200, precheck.text
    assert not precheck.json()["ok"]
    assert "user_rule_sources_unconfirmed" in {item["code"] for item in precheck.json()["blockers"]}
    published = save_generate_export(client, json=publication_request(payload))
    assert published.status_code == 409, published.text


@pytest.mark.parametrize("companion", ["missing", "disabled", "wrong_priority", "valid"])
def test_manual_bool_publication_requires_active_false_companion(native_context, companion):
    from app.services.rule_packages.condition_reviews import _manual_process_field_key

    client, factory, payload, segments = native_context
    process_id = "process_quench"
    segment_id = next(segment["id"] for segment in segments if segment["export_process_id"] == process_id)
    key = _manual_process_field_key(process_id)
    field = {
        "key": key, "label": "是否淬火", "type": "boolean", "required": False,
        "source": "用户直接设定", "allow_custom": False,
    }
    candidate = {
        "kind": "condition", "when": {"field": key, "op": "eq", "value": True},
        "then": {"include_process_ids": [process_id], "exclude_process_ids": []},
        "field_definitions": [{**field, "category": "项目", "operators": ["eq"]}],
    }
    confirmed = client.post("/api/extract/finalized-rule-packages/rule-conditions/manual", json={
        "project_id": 12, "route_id": 31, "segment_id": segment_id,
        "process_id": process_id, "source_text": "由用户选择是否纳入淬火",
        "candidate": candidate,
        "processes": [{"process_id": p["process_id"], "display_name": p["display_name"], "main": p["main"]}
                      for p in payload["route_catalog"]["processes"]],
    })
    assert confirmed.status_code == 200, confirmed.text
    review = confirmed.json()["review"]
    audit = {
        "priority": 2000, "source": "user_confirmed", "source_segment_id": segment_id,
        "source_text": review["source_text"], "confirmed_by": review["confirmed_by"],
        "confirmed_at": review["confirmed_at"],
    }
    payload["input_schema"]["fields"].append(field)
    payload["route_rules"]["rules"].append({
        **audit, "rule_id": "manual.quench.true", "when": candidate["when"], "then": candidate["then"],
    })
    payload["test_cases"][0]["input"][key] = True
    if companion != "missing":
        payload["route_rules"]["rules"].append({
            **audit, "rule_id": "manual.quench.false",
            "priority": 1999 if companion == "wrong_priority" else 2000,
            "enabled": companion != "disabled",
            "when": {"field": key, "op": "eq", "value": False},
            "then": {"include_process_ids": [], "exclude_process_ids": [process_id]},
        })
        if companion != "disabled":
            # The original material rule still includes quench at priority 100.
            case = deepcopy(payload["test_cases"][0])
            case["case_id"] = "manual-quench-false"
            case["input"][key] = False
            case["expect"] = {"included_process_ids": ["process_prepare", "process_mill_slot"],
                              "excluded_process_ids": [process_id]}
            payload["test_cases"].append(case)

    body = publication_request(payload)
    checked = client.post("/api/extract/finalized-rule-packages/precheck", json=body)
    assert checked.status_code == 200, checked.text
    assert checked.json()["ok"] is (companion == "valid"), checked.text
    published = save_generate_export(client, json=body)
    if companion != "valid":
        blocker = next(item for item in checked.json()["blockers"] if item["code"] == "user_rule_sources_unconfirmed")
        assert blocker["segment_ids"] == [segment_id]
        assert published.status_code == 409, published.text

        async def package_ids():
            async with factory() as db:
                return (await db.execute(select(FinalizedRulePackage.id))).scalars().all()

        assert asyncio.run(package_ids()) == []
        return

    assert published.status_code == 200, published.text
    case = payload["test_cases"][-1]
    generated = generate_current(client, json={
        "project_id": 12, "factor_values": case["input"],
        "input_metadata": {"material.grade": {"origin": "manual"}, "cad.features": {"origin": "manual"},
                           "target_hardness_hrc": {"origin": "manual", "unit": "HRC"}, key: {"origin": "manual"}},
    })
    assert generated.status_code == 200, generated.text
    assert generated.json()["selected_process_ids"] == ["process_prepare", "process_mill_slot"]


def test_basic_draft_compilation_and_simulation_drop_template_aliases(native_context):
    client, _, payload, _ = native_context
    payload["route_catalog"]["processes"][0]["template_group_aliases"] = [{
        "source_operation_id": 100, "alias": "old-feature", "template_group_id": "old-template",
    }]
    compiled = client.post("/api/extract/finalized-rule-packages/compile", json={
        "project_id": 12, "package_name": "shaft_rules", "route_version_id": 31,
        "fields": payload["input_schema"]["fields"], "processes": payload["route_catalog"]["processes"],
        "rules": payload["route_rules"]["rules"], "test_cases": payload["test_cases"],
    })
    assert compiled.status_code == 200, compiled.text
    assert all(not p["template_group_aliases"] for p in compiled.json()["package"]["route_catalog"]["processes"])
    simulated = client.post("/api/extract/finalized-rule-packages/simulate", json={
        "package": payload, "inputs": payload["test_cases"][0]["input"],
    })
    assert simulated.status_code == 200, simulated.text
    assert all(not step["template_group_aliases"] for step in simulated.json()["plan"]["steps"])


def test_native_snapshot_ignores_saved_route_template_aliases(native_context):
    client, factory, payload, _ = native_context
    plain = save_generate_export(client, json=publication_request(payload))
    assert plain.status_code == 200, plain.text

    async def add_old_aliases():
        async with factory() as db:
            route = await db.get(NormalizedRouteVersion, 31)
            segments = json.loads(route.route_json)
            segments[0]["template_group_aliases"] = [{
                "source_operation_id": 100, "alias": "stale", "template_group_id": "unrelated",
            }]
            route.route_json = json.dumps(segments)
            await db.commit()

    asyncio.run(add_old_aliases())
    with_aliases = save_generate_export(client, json=publication_request(payload))
    assert with_aliases.status_code == 200, with_aliases.text
    assert with_aliases.json()["export_sources"] == plain.json()["export_sources"]


def test_missing_export_sources_do_not_change_independent_executable_generation(native_context, tmp_path, monkeypatch):
    from app.core.product_profile import get_product_profile

    client, factory, payload, _ = native_context
    published = save_generate_export(client, json=publication_request(payload))
    assert published.status_code == 200, published.text

    async def remove_sources():
        async with factory() as db:
            row = (await db.execute(select(FinalizedRulePackage))).scalar_one()
            row.export_sources_json = None
            await db.commit()

    asyncio.run(remove_sources())
    full = tmp_path / "full.json"
    full.write_text(json.dumps({"edition": "full", "template_mapping_enabled": True, "expires_at": None}))
    with monkeypatch.context() as patch:
        patch.setenv("PROCESSMIND_PROFILE_PATH", str(full))
        get_product_profile.cache_clear()
        response = generate(client)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("tamper", ["native_route", "native_rules", "snapshot_hash", "route_hash",
                                   "project_binding", "compiler", "stored_rules", "missing_snapshot"])
def test_native_export_corruption_blocks_download_but_keeps_independent_core(native_context, tamper):
    client, factory, payload, _ = native_context
    published = save_generate_export(client, json=publication_request(payload))
    assert published.status_code == 200, published.text

    async def corrupt():
        async with factory() as db:
            row = (await db.execute(select(FinalizedRulePackage))).scalar_one()
            sources = json.loads(row.export_sources_json)
            if tamper == "native_route":
                sources["native_snapshot"]["normalized_route"][0]["normalized_step_name"] = "tampered"
            elif tamper == "native_rules":
                sources["native_snapshot"]["rule_package"]["route_rules"]["rules"] = []
            elif tamper == "snapshot_hash":
                sources["native_snapshot_hash"] = "0" * 64
            elif tamper == "route_hash":
                sources["route_content_hash"] = "0" * 64
            elif tamper == "project_binding":
                sources["project_id"] = 999
            elif tamper == "compiler":
                sources["compiler_version"] = "native-v2/unknown"
            elif tamper == "missing_snapshot":
                sources.pop("native_snapshot")
            else:
                rules = json.loads(row.route_rules_json)
                rules["rules"][0]["priority"] = 9876
                row.route_rules_json = json.dumps(rules)
            row.export_sources_json = json.dumps(sources)
            await db.commit()

    asyncio.run(corrupt())
    downloaded = client.get("/api/extract/finalized-rule-packages/latest?project_id=12")
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.json()["export_error"]
    assert "native_snapshot" not in downloaded.json()["export_sources"]
    response = generate(client)
    assert response.status_code == 200, response.text

    async def persisted_count():
        async with factory() as db:
            return len((await db.execute(select(GeneratedRoute))).scalars().all())
    assert asyncio.run(persisted_count()) == 2
