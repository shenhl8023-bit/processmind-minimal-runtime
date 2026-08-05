import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages import condition_review_service
from app.services.rule_packages.condition_contracts import RuleConditionCandidate
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_compatibility_runner import compare_kmai_v1
from app.services.rule_packages.kmai_export import builtin_legacy_mapping_snapshot
from app.services.rule_packages.lifecycle import publish_rule_package
from app.services.rule_packages.standard_factors import bind_unambiguous_factor_ids


@pytest.fixture
def lifecycle_client(tmp_path):
    database_path = tmp_path / "lifecycle.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as session:
            session.add(Project(id=12, name="Lifecycle", status="ROUTE_SET_READY"))
            session.add(NormalizedRouteVersion(
                id=31,
                project_id=12,
                version=1,
                route_json=json.dumps([
                    {"id": "process_mill_slot", "normalized_step_name": "铣槽"},
                ], ensure_ascii=False),
            ))
            await session.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.lifecycle_session_factory = session_factory
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _v2_save_payload(package):
    return {
        "project_id": package["manifest"]["project_id"],
        "route_version_id": package["manifest"]["route_version_id"],
        "package_name": package["manifest"]["package_name"],
        "schema_version": "2.0",
        "manifest": package["manifest"],
        "input_schema": package["input_schema"],
        "route_catalog": package["route_catalog"],
        "route_rules": package["route_rules"],
        "test_cases": package["test_cases"],
        "rule_report_md": "# report",
    }


def _compile_payload(package):
    return {
        "project_id": package["manifest"]["project_id"],
        "package_name": package["manifest"]["package_name"],
        "route_version_id": package["manifest"]["route_version_id"],
        "applicability": package["manifest"]["applicability"],
        "fields": package["input_schema"]["fields"],
        "processes": package["route_catalog"]["processes"],
        "rules": package["route_rules"]["rules"],
        "test_cases": package["test_cases"],
    }


def _input_field_from_registry(field):
    return {
        key: field[key]
        for key in (
            "key",
            "label",
            "type",
            "required",
            "source",
            "options",
            "allow_custom",
            "unit",
            "validation",
        )
    }


def _package_with_precision_rule(package, registry_field, when):
    payload = deepcopy(package)
    payload["test_cases"] = []
    payload["input_schema"]["fields"].append(_input_field_from_registry(registry_field))
    slot_rule = next(rule for rule in payload["route_rules"]["rules"] if rule["rule_id"] == "feature.slot.mill")
    slot_rule["when"] = when
    return payload, slot_rule


def _all_json_keys(value):
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _all_json_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _all_json_keys(child)}
    return set()


def _parse_body(source_text):
    return {
        "project_id": 12,
        "route_id": 31,
        "segment_id": "process_mill_slot",
        "source_text": source_text,
        "process_id": "process_mill_slot",
        "process_name": "铣槽",
        "processes": [{"process_id": "process_mill_slot", "display_name": "铣槽"}],
    }


def _confirm_body(source_text, source_hash, candidate):
    return {
        "project_id": 12,
        "route_id": 31,
        "segment_id": "process_mill_slot",
        "source_text": source_text,
        "source_hash": source_hash,
        "candidate": candidate,
        "processes": [{"process_id": "process_mill_slot", "display_name": "铣槽"}],
        "confirmed_by": "验收用户",
    }


def _candidate(value):
    return RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"field": "precision.grades", "op": "contains", "value": value},
        "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
        "preview": f"精度/表面要求集合包含{value}",
        "evidence": value,
    })


def test_confirmed_standard_factor_journey_compiles_and_saves_without_mappings(
    lifecycle_client,
    rule_package_v2_payload,
    monkeypatch,
):
    """Breaks if fourth-step confirmation no longer drives fixed-factor publish output."""
    async def parse_hole_finish(*args, **kwargs):
        return _candidate("孔精加工"), 0.99, []

    monkeypatch.setattr(condition_review_service, "parse_rule_condition", parse_hole_finish)
    registry = lifecycle_client.get("/api/extract/finalized-rule-packages/condition-fields")
    assert registry.status_code == 200
    registry_body = registry.json()
    selected_factor = next(
        factor for factor in registry_body["factors"]
        if factor["factor_id"] == "precision.hole_finish"
    )
    precision_field = next(
        field for field in registry_body["fields"]
        if field["key"] == selected_factor["source_field"]
    )

    source_text = "当存在孔精加工要求时，纳入铣槽工序"
    parsed = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/parse",
        json=_parse_body(source_text),
    )
    assert parsed.status_code == 200
    candidate = parsed.json()["review"]["candidate"]
    candidate["when"]["factor_id"] = selected_factor["factor_id"]

    confirmed = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/confirm",
        json=_confirm_body(source_text, parsed.json()["review"]["source_hash"], candidate),
    )
    assert confirmed.status_code == 200
    confirmed_review = confirmed.json()["review"]
    assert confirmed_review["status"] == "confirmed"
    assert confirmed_review["confirmed"]["when"]["factor_id"] == "precision.hole_finish"

    payload, rule = _package_with_precision_rule(
        rule_package_v2_payload,
        precision_field,
        confirmed_review["confirmed"]["when"],
    )
    rule.update({
        "source": "user_confirmed",
        "source_segment_id": "process_mill_slot",
        "source_text": source_text,
        "confirmed_by": confirmed_review["confirmed_by"],
        "confirmed_at": confirmed_review["confirmed_at"],
        "then": confirmed_review["confirmed"]["then"],
    })

    compiled = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compile",
        json=_compile_payload(payload),
    )
    assert compiled.status_code == 200
    compiled_rule = next(
        item for item in compiled.json()["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        if item["rule_id"] == "feature.slot.mill"
    )
    assert compiled_rule["when"]["all"][0]["factor_key"] == "has_hole_finish_machining"

    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(compiled.json()["package"]),
    )
    assert saved.status_code == 200
    saved_report = saved.json()["validation_report"]
    assert saved_report["kmai_compatibility"] == {"factor_catalog_version": "2026.11"}
    assert not {
        "mapping_identity",
        "mapping_scope",
        "mapping_revision",
        "mapping_signature",
        "mapping_snapshot",
    } & _all_json_keys(saved_report)

    async def retired_mapping_tables():
        async with lifecycle_client.lifecycle_session_factory() as db:
            rows = (await db.execute(text(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'kmai_factor_mapping%'"
            ))).scalars().all()
            return rows

    assert asyncio.run(retired_mapping_tables()) == []


def test_unknown_custom_factor_cannot_be_confirmed_compiled_or_saved(
    lifecycle_client,
    rule_package_v2_payload,
    monkeypatch,
):
    """Breaks if an unknown standard value can bypass any fourth-step boundary."""
    async def parse_unknown(*args, **kwargs):
        candidate = _candidate("自定义精加工")
        bound, issues = bind_unambiguous_factor_ids(candidate.when)
        return (
            candidate.model_copy(update={"when": bound}),
            0.99,
            [issue.message for issue in issues],
        )

    monkeypatch.setattr(condition_review_service, "parse_rule_condition", parse_unknown)
    registry = lifecycle_client.get("/api/extract/finalized-rule-packages/condition-fields").json()
    precision_field = next(field for field in registry["fields"] if field["key"] == "precision.grades")
    source_text = "precision.grades contains 自定义精加工"

    parsed = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/parse",
        json=_parse_body(source_text),
    )
    assert parsed.status_code == 200
    parsed_review = parsed.json()["review"]
    assert parsed_review["status"] == "pending_confirmation"
    assert parsed_review["candidate"]["when"].get("factor_id") is None
    assert parsed_review["issues"]

    refused = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/confirm",
        json=_confirm_body(source_text, parsed_review["source_hash"], parsed_review["candidate"]),
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["issues"][0]["code"] == "factor_unbound"

    payload, _ = _package_with_precision_rule(
        rule_package_v2_payload,
        precision_field,
        parsed_review["candidate"]["when"],
    )
    compiled = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compile",
        json=_compile_payload(payload),
    )
    assert compiled.status_code == 422
    assert compiled.json()["detail"]["issues"][0]["code"] == "factor_unbound"

    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(payload),
    )
    assert saved.status_code == 422
    assert saved.json()["detail"]["issues"][0]["code"] == "factor_unbound"


def test_confirm_endpoint_preserves_source_changed_conflict(lifecycle_client):
    source_text = "当外圆尺寸精度达到 IT8 时，纳入铣槽工序"
    parsed = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/parse",
        json=_parse_body(source_text),
    )
    assert parsed.status_code == 200

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/confirm",
        json=_confirm_body("新的条件文字", parsed.json()["review"]["source_hash"], parsed.json()["review"]["candidate"]),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "条件文字已经发生变化，请重新解析后再确认。"


def test_manual_endpoint_rejects_spoofed_target(lifecycle_client):
    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/manual",
        json={
            "project_id": 12,
            "route_id": 31,
            "segment_id": "process_mill_slot",
            "source_text": "用户决定是否纳入铣槽工序",
            "process_id": "process_mill_slot",
            "candidate": _candidate("孔精加工").model_dump(mode="json"),
            "processes": [{"process_id": "process_mill_slot", "display_name": "铣槽"}],
        },
    )

    assert response.status_code == 422
    assert "人工 Bool" in response.json()["detail"]


def test_new_package_persists_catalog_version(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))

    assert saved.status_code == 200
    body = saved.json()
    assert body["validation_report"]["kmai_compatibility"] == {"factor_catalog_version": "2026.11"}


def test_compile_and_save_use_immutable_standard_factor(lifecycle_client, rule_package_v2_payload):
    compiled = lifecycle_client.post("/api/extract/finalized-rule-packages/compile", json=_compile_payload(rule_package_v2_payload))
    assert compiled.status_code == 200
    compiled_slot = next(
        rule for rule in compiled.json()["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        if rule["rule_id"] == "feature.slot.mill"
    )
    assert compiled_slot["when"]["all"][0]["factor_key"] == "has_slot_feature"

    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))
    assert saved.status_code == 200
    saved_slot = next(
        rule for rule in saved.json()["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        if rule["rule_id"] == "feature.slot.mill"
    )
    assert saved_slot["when"]["all"][0]["factor_key"] == "has_slot_feature"


def _set_historical_rule(lifecycle_client, package_id, *, snapshot, source_value="\u69fd\u7c7b\u7279\u5f81"):
    async def update():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = (await db.execute(select(FinalizedRulePackage).where(FinalizedRulePackage.id == package_id))).scalar_one()
            rules = json.loads(row.route_rules_json)
            slot = next(rule for rule in rules["rules"] if rule["rule_id"] == "feature.slot.mill")
            slot["when"].pop("factor_id", None)
            slot["when"]["value"] = source_value
            row.route_rules_json = json.dumps(rules, ensure_ascii=True)
            compatibility = {"mapping_snapshot": snapshot} if snapshot is not None else {}
            row.validation_report_json = json.dumps({"kmai_compatibility": compatibility})
            await db.commit()

    asyncio.run(update())


def test_historical_compatibility_uses_snapshot_embedded_in_package(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))
    assert saved.status_code == 200
    snapshot = [{
        "mapping_identity": "project:7",
        "revision": 3,
        "scope": "project",
        "project_id": 12,
        "source_field": "cad.features",
        "source_value": "\u69fd\u7c7b\u7279\u5f81",
        "mapping_mode": "existing_factor",
        "target_factor_key": "requires_honing",
        "target_factor_name": "Honing",
        "target_factor_category": "precision",
    }]
    _set_historical_rule(lifecycle_client, saved.json()["id"], snapshot=snapshot)

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={"project_id": 12, "inputs": {"material": {"grade": "9Cr18"}, "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]}, "target_hardness_hrc": 58}},
    )

    assert response.status_code == 200
    assert response.json()["manual_factors"]["requires_honing"] is True
    assert response.json()["manual_factors"]["has_flat_or_plane"] is False


def test_snapshotless_historical_package_uses_only_fixed_legacy_builtins(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))
    assert saved.status_code == 200
    _set_historical_rule(lifecycle_client, saved.json()["id"], snapshot=None)

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={"project_id": 12, "inputs": {"material": {"grade": "9Cr18"}, "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]}, "target_hardness_hrc": 58}},
    )
    assert response.status_code == 200
    assert response.json()["manual_factors"]["has_slot_feature"] is True

    _set_historical_rule(lifecycle_client, saved.json()["id"], snapshot=None, source_value="unknown old value")
    async def legacy_package():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = (await db.execute(select(FinalizedRulePackage).where(FinalizedRulePackage.id == saved.json()["id"]))).scalar_one()
            return RulePackageV2.model_validate({
                "manifest": json.loads(row.manifest_json),
                "input_schema": json.loads(row.input_schema_json),
                "route_catalog": json.loads(row.route_catalog_json),
                "route_rules": json.loads(row.route_rules_json),
                "test_cases": json.loads(row.test_cases_json),
            })

    blocked = compare_kmai_v1(
        asyncio.run(legacy_package()),
        {"material": {"grade": "9Cr18"}, "cad": {"features": ["unknown old value"]}, "target_hardness_hrc": 58},
        legacy_mapping_snapshot=builtin_legacy_mapping_snapshot(),
    )
    assert [issue["code"] for issue in blocked["errors"]] == ["standard_factor_unbound"]


def test_migration_backfills_legacy_version_status_and_hash(tmp_path):
    database_path = tmp_path / "legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def run_migration():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("DROP TABLE finalized_rule_packages"))
            await conn.execute(text("""
                CREATE TABLE finalized_rule_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL, route_version_id INTEGER,
                    version INTEGER NOT NULL, package_name VARCHAR(255) NOT NULL,
                    input_schema_json TEXT, route_catalog_json TEXT, route_rules_json TEXT,
                    rule_report_md TEXT, validation_report_json TEXT, created_by VARCHAR(100), created_at DATETIME
                )
            """))
            await conn.execute(text("""
                INSERT INTO finalized_rule_packages
                    (project_id, version, package_name, input_schema_json, route_catalog_json, route_rules_json, rule_report_md, created_by, created_at)
                VALUES (1, 1, 'rules-v1', '{}', '{}', '{}', '# v1', 'user', CURRENT_TIMESTAMP),
                       (1, 2, 'rules-v2', '{}', '{}', '{}', '# v2', 'user', CURRENT_TIMESTAMP)
            """))
            await ensure_project_schema(conn)
            rows = (await conn.execute(text("""
                SELECT version, status, schema_version, content_hash
                FROM finalized_rule_packages ORDER BY version
            """))).mappings().all()
        await engine.dispose()
        return rows

    rows = asyncio.run(run_migration())

    assert [row["status"] for row in rows] == ["superseded", "published"]
    assert [row["schema_version"] for row in rows] == ["1.0", "1.0"]
    assert all(len(row["content_hash"]) == 64 for row in rows)


def test_publish_helper_does_not_commit_before_caller(lifecycle_client, rule_package_v2_payload):
    async def exercise():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = FinalizedRulePackage(
                project_id=12,
                route_version_id=31,
                version=1,
                package_name="transactional",
                schema_version="2.0",
                status="draft",
                manifest_json=json.dumps(rule_package_v2_payload["manifest"]),
                input_schema_json=json.dumps(rule_package_v2_payload["input_schema"]),
                route_catalog_json=json.dumps(rule_package_v2_payload["route_catalog"]),
                route_rules_json=json.dumps(rule_package_v2_payload["route_rules"]),
                test_cases_json=json.dumps(rule_package_v2_payload["test_cases"]),
                rule_report_md="# report",
                validation_report_json="{}",
                content_hash="x" * 64,
                created_by="tester",
            )
            db.add(row)
            await db.flush()
            await publish_rule_package(row, db, actor="tester")
            await db.rollback()
        async with lifecycle_client.lifecycle_session_factory() as db:
            return (await db.execute(select(FinalizedRulePackage))).scalars().all()

    assert asyncio.run(exercise()) == []
