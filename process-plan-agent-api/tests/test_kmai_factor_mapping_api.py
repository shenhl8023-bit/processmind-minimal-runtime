import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine, get_db
from app.main import app
from app.models.models import (
    FinalizedRulePackage,
    KmaiFactorMapping,
    KmaiFactorMappingEvent,
    KmaiFactorMappingUsage,
    Project,
)
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.kmai_mapping_contracts import KmaiMappingUpdateRequest
from app.services.rule_packages.kmai_mapping_store import update_mapping


@pytest.fixture
def mapping_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mappings.db'}")
    configure_sqlite_engine(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as db:
            db.add_all([Project(id=12, name="one"), Project(id=13, name="two")])
            await db.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    client.mapping_engine = engine
    client.mapping_session_factory = session_factory
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _manual_mapping(source_value="custom feature"):
    return {
        "scope": "project",
        "project_id": 12,
        "source_field": "cad.features",
        "source_value": source_value,
        "mapping_mode": "manual_factor",
        "target_factor_name": "Custom feature",
    }


def _existing_mapping(source_value="custom feature"):
    return {
        "scope": "project",
        "project_id": 12,
        "source_field": "cad.features",
        "source_value": source_value,
        "mapping_mode": "existing_factor",
        "target_factor_key": "has_slot_feature",
    }


def _create_revision_two_mapping(mapping_client, source_value):
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping(source_value),
    )
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]
    updated = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={
            "expected_revision": 1,
            "mapping_mode": "existing_factor",
            "target_factor_key": "requires_honing",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    return updated.json()


def _install_unique_insert_race(mapping_client, source_value):
    escaped_source_value = source_value.replace("'", "''")

    async def install():
        async with mapping_client.mapping_engine.begin() as conn:
            await conn.exec_driver_sql(
                f"""
                CREATE TRIGGER inject_kmai_mapping_unique_race
                BEFORE INSERT ON kmai_factor_mappings
                WHEN NEW.source_value = '{escaped_source_value}'
                     AND NEW.created_by <> '__db_race_winner__'
                BEGIN
                    INSERT INTO kmai_factor_mappings (
                        scope,
                        project_id,
                        source_field,
                        source_value,
                        mapping_mode,
                        target_factor_key,
                        target_factor_name,
                        target_factor_category,
                        status,
                        revision,
                        promoted_from_id,
                        created_by,
                        updated_by
                    ) VALUES (
                        NEW.scope,
                        NEW.project_id,
                        NEW.source_field,
                        NEW.source_value,
                        NEW.mapping_mode,
                        NEW.target_factor_key,
                        NEW.target_factor_name,
                        NEW.target_factor_category,
                        NEW.status,
                        NEW.revision,
                        NEW.promoted_from_id,
                        '__db_race_winner__',
                        '__db_race_winner__'
                    );
                END
                """
            )

    asyncio.run(install())


def _install_usage_before_delete_race(mapping_client, source_value, package_id):
    escaped_source_value = source_value.replace("'", "''")

    async def install():
        async with mapping_client.mapping_engine.begin() as conn:
            await conn.exec_driver_sql(
                f"""
                CREATE TRIGGER inject_kmai_mapping_usage_race
                BEFORE DELETE ON kmai_factor_mappings
                WHEN OLD.source_value = '{escaped_source_value}'
                BEGIN
                    INSERT INTO kmai_factor_mapping_usages (
                        mapping_id,
                        package_id,
                        revision,
                        mapping_snapshot_json
                    ) VALUES (
                        OLD.id,
                        {package_id},
                        OLD.revision,
                        '{{"scope":"project"}}'
                    );
                END
                """
            )

    asyncio.run(install())


def test_catalog_and_manual_mapping_use_server_generated_key(mapping_client):
    catalog = mapping_client.get("/api/kmai-factor-mappings/catalog")

    assert catalog.status_code == 200
    assert any(
        item["factor_key"] == "has_slot_feature"
        and item["value_type"] == "boolean"
        and item["read_only"]
        for item in catalog.json()
    )
    assert next(
        item for item in catalog.json() if item["factor_key"] == "material_grade"
    )["value_type"] == "enum"

    created = mapping_client.post("/api/kmai-factor-mappings", json=_manual_mapping())

    assert created.status_code == 200
    mapping = created.json()
    assert mapping["scope"] == "project"
    assert mapping["mapping_mode"] == "manual_factor"
    assert mapping["target_factor_key"].startswith("processmind_manual_")
    assert mapping["target_factor_key"] != "custom_feature"


def test_create_rejects_enum_existing_factor_for_presence_mapping(mapping_client):
    request = _existing_mapping("enum target on create")
    request["target_factor_key"] = "material_grade"

    created = mapping_client.post("/api/kmai-factor-mappings", json=request)

    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "kmai_mapping_factor_type_incompatible"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    assert not any(item["source_value"] == "enum target on create" for item in listed)


def test_manual_mapping_requires_an_explicit_display_name(mapping_client):
    """Catch a manual mapping that silently inherits an opaque source value as its name."""
    request = _manual_mapping("unlabeled manual feature")
    request.pop("target_factor_name")

    created = mapping_client.post("/api/kmai-factor-mappings", json=request)

    assert created.status_code == 422
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12})
    assert not any(item["source_value"] == "unlabeled manual feature" for item in listed.json())


def test_manual_mapping_rejects_client_controlled_category_on_create(mapping_client):
    request = _manual_mapping("spoofed category on create")
    request["target_factor_category"] = "processmind_special_requirement"

    created = mapping_client.post("/api/kmai-factor-mappings", json=request)

    assert created.status_code == 422
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    assert not any(item["source_value"] == "spoofed category on create" for item in listed)


def test_manual_mapping_rejects_client_controlled_category_on_update(mapping_client):
    request = _manual_mapping("spoofed category on update")
    created = mapping_client.post("/api/kmai-factor-mappings", json=request)
    assert created.status_code == 200
    assert created.json()["target_factor_category"] == "manual_override"

    updated = mapping_client.put(
        f"/api/kmai-factor-mappings/{created.json()['mapping_id']}",
        json={
            "expected_revision": 1,
            "mapping_mode": "manual_factor",
            "target_factor_category": "processmind_input",
        },
    )

    assert updated.status_code == 422
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    persisted = next(item for item in listed if item["mapping_id"] == created.json()["mapping_id"])
    assert persisted["target_factor_category"] == "manual_override"
    assert persisted["revision"] == 1


def test_manual_mapping_cannot_be_updated_to_an_empty_display_name(mapping_client):
    created = mapping_client.post("/api/kmai-factor-mappings", json=_manual_mapping())
    assert created.status_code == 200

    updated = mapping_client.put(
        f"/api/kmai-factor-mappings/{created.json()['mapping_id']}",
        json={"expected_revision": 1, "target_factor_name": "   "},
    )

    assert updated.status_code == 422
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    mapping = next(item for item in listed if item["mapping_id"] == created.json()["mapping_id"])
    assert mapping["target_factor_name"] == "Custom feature"


@pytest.mark.parametrize(
    ("create_payload", "update_payload", "persisted_mode"),
    [
        (
            _existing_mapping("existing mode cannot change"),
            {"mapping_mode": "manual_factor", "target_factor_name": "Changed mode"},
            "existing_factor",
        ),
        (
            _manual_mapping("manual mode cannot change"),
            {"mapping_mode": "existing_factor"},
            "manual_factor",
        ),
    ],
)
def test_update_rejects_switching_mapping_mode_without_incrementing_revision(
    mapping_client,
    create_payload,
    update_payload,
    persisted_mode,
):
    created = mapping_client.post("/api/kmai-factor-mappings", json=create_payload)
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]

    updated = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={"expected_revision": 1, **update_payload},
    )

    assert updated.status_code == 422
    assert updated.json()["detail"]["code"] == "kmai_mapping_mode_invalid"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    persisted = next(item for item in listed if item["mapping_id"] == mapping_id)
    assert persisted["mapping_mode"] == persisted_mode
    assert persisted["revision"] == 1


def test_existing_target_key_update_still_requires_existing_factor_mode(mapping_client):
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping("target key edit contract"),
    )
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]

    missing_mode = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={"expected_revision": 1, "target_factor_key": "requires_honing"},
    )
    assert missing_mode.status_code == 422

    updated = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={
            "expected_revision": 1,
            "mapping_mode": "existing_factor",
            "target_factor_key": "requires_honing",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["target_factor_key"] == "requires_honing"
    assert updated.json()["revision"] == 2


def test_update_rejects_enum_existing_factor_without_incrementing_revision(mapping_client):
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping("enum target on update"),
    )
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]

    updated = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={
            "expected_revision": 1,
            "mapping_mode": "existing_factor",
            "target_factor_key": "part_type",
        },
    )

    assert updated.status_code == 422
    assert updated.json()["detail"]["code"] == "kmai_mapping_factor_type_incompatible"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    persisted = next(item for item in listed if item["mapping_id"] == mapping_id)
    assert persisted["target_factor_key"] == "has_slot_feature"
    assert persisted["revision"] == 1


def test_project_mapping_rejects_an_unknown_project(mapping_client):
    request = _existing_mapping("unknown project feature")
    request["project_id"] = 999

    created = mapping_client.post("/api/kmai-factor-mappings", json=request)

    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "kmai_mapping_project_not_found"


def test_batch_is_atomic_and_list_exposes_effective_precedence(mapping_client):
    batch = mapping_client.post(
        "/api/kmai-factor-mappings/batch",
        json={"mappings": [_existing_mapping("duplicate"), _existing_mapping("duplicate")]},
    )

    assert batch.status_code == 409
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12})
    assert listed.status_code == 200
    assert not any(item["source_value"] == "duplicate" for item in listed.json())

    global_mapping = mapping_client.post(
        "/api/kmai-factor-mappings",
        json={
            "scope": "global",
            "source_field": "cad.features",
            "source_value": "\u69fd\u7c7b\u7279\u5f81",
            "mapping_mode": "existing_factor",
            "target_factor_key": "has_slot_feature",
        },
    )
    assert global_mapping.status_code == 200
    project_mapping = mapping_client.post("/api/kmai-factor-mappings", json=_existing_mapping("\u69fd\u7c7b\u7279\u5f81"))
    assert project_mapping.status_code == 200

    effective = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    global_item = next(item for item in effective if item["mapping_id"] == global_mapping.json()["mapping_id"])
    project_item = next(item for item in effective if item["mapping_id"] == project_mapping.json()["mapping_id"])
    builtin_item = next(
        item
        for item in effective
        if item["scope"] == "builtin" and item["source_value"] == "\u69fd\u7c7b\u7279\u5f81"
    )
    assert global_item["overridden"] is True
    assert project_item["overridden"] is False
    assert builtin_item["overridden"] is True


def test_create_maps_database_unique_race_to_conflict(mapping_client):
    source_value = "create unique race"
    _install_unique_insert_race(mapping_client, source_value)

    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping(source_value),
    )

    assert created.status_code == 409
    assert created.json()["detail"]["code"] == "kmai_mapping_conflict"


def test_batch_maps_database_unique_race_to_conflict_and_rolls_back(mapping_client):
    source_value = "batch unique race"
    _install_unique_insert_race(mapping_client, source_value)

    created = mapping_client.post(
        "/api/kmai-factor-mappings/batch",
        json={
            "mappings": [
                _existing_mapping("batch item before race"),
                _existing_mapping(source_value),
            ]
        },
    )

    assert created.status_code == 409
    assert created.json()["detail"]["code"] == "kmai_mapping_conflict"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    assert not any(item["source_value"] == "batch item before race" for item in listed)
    assert not any(item["source_value"] == source_value for item in listed)


def test_update_promotion_and_preview_report_real_mapping_behavior(mapping_client, rule_package_v2_payload):
    created = mapping_client.post("/api/kmai-factor-mappings", json=_existing_mapping("promotable"))
    assert created.status_code == 200
    mapping = created.json()

    stale = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping['mapping_id']}",
        json={"expected_revision": 2, "status": "inactive"},
    )
    assert stale.status_code == 409

    updated = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping['mapping_id']}",
        json={"expected_revision": 1, "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2

    promoted = mapping_client.post(
        f"/api/kmai-factor-mappings/{mapping['mapping_id']}/promote",
        params={"expected_revision": 2},
    )
    assert promoted.status_code == 200
    assert promoted.json()["scope"] == "global"
    assert promoted.json()["promoted_from_id"] == mapping["mapping_id"]

    payload = deepcopy(rule_package_v2_payload)
    payload["route_rules"]["rules"].append(
        {
            "rule_id": "unknown-feature",
            "priority": 1,
            "enabled": True,
            "source": "user_confirmed",
            "when": {"field": "cad.features", "op": "contains", "value": "unmapped custom feature"},
            "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
        }
    )
    preview = mapping_client.post(
        "/api/kmai-factor-mappings/resolve-preview",
        json={"project_id": 12, "package": payload},
    )
    assert preview.status_code == 200
    issue = next(item for item in preview.json()["issues"] if item["value"] == "unmapped custom feature")
    assert issue["field"] == "cad.features"
    assert issue["occurrences"] == 1
    assert issue["rule_refs"] == ["unknown-feature"]
    assert issue["can_create_manual_factor"] is True


@pytest.mark.parametrize(
    ("method", "suffix", "params"),
    [
        ("post", "/promote", {}),
        ("delete", "", {}),
        ("delete", "", {"delete": "true"}),
    ],
)
def test_promote_deactivate_and_delete_require_expected_revision(
    mapping_client,
    method,
    suffix,
    params,
):
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping(f"required revision {method} {suffix} {params}"),
    )
    assert created.status_code == 200

    response = getattr(mapping_client, method)(
        f"/api/kmai-factor-mappings/{created.json()['mapping_id']}{suffix}",
        params=params,
    )

    assert response.status_code == 422


def test_stale_revision_cannot_promote_newer_mapping(mapping_client):
    mapping = _create_revision_two_mapping(mapping_client, "stale promotion")

    promoted = mapping_client.post(
        f"/api/kmai-factor-mappings/{mapping['mapping_id']}/promote",
        params={"expected_revision": 1},
    )

    assert promoted.status_code == 409
    assert promoted.json()["detail"]["code"] == "kmai_mapping_revision_conflict"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    assert not any(
        item["scope"] == "global" and item["source_value"] == "stale promotion"
        for item in listed
    )


def test_stale_revision_cannot_deactivate_newer_mapping(mapping_client):
    mapping = _create_revision_two_mapping(mapping_client, "stale deactivation")

    deactivated = mapping_client.delete(
        f"/api/kmai-factor-mappings/{mapping['mapping_id']}",
        params={"expected_revision": 1},
    )

    assert deactivated.status_code == 409
    assert deactivated.json()["detail"]["code"] == "kmai_mapping_revision_conflict"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    persisted = next(item for item in listed if item["mapping_id"] == mapping["mapping_id"])
    assert persisted["status"] == "active"
    assert persisted["revision"] == 2


def test_stale_revision_cannot_hard_delete_newer_mapping(mapping_client):
    mapping = _create_revision_two_mapping(mapping_client, "stale deletion")

    deleted = mapping_client.delete(
        f"/api/kmai-factor-mappings/{mapping['mapping_id']}",
        params={"delete": "true", "expected_revision": 1},
    )

    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "kmai_mapping_revision_conflict"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    persisted = next(item for item in listed if item["mapping_id"] == mapping["mapping_id"])
    assert persisted["revision"] == 2


def test_status_transitions_have_explicit_audit_actions_and_state(mapping_client):
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping("audited status transition"),
    )
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]

    deactivated = mapping_client.delete(
        f"/api/kmai-factor-mappings/{mapping_id}",
        params={"expected_revision": 1, "actor": "deactivator"},
    )
    assert deactivated.status_code == 200
    reactivated = mapping_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={"expected_revision": 2, "status": "active", "actor": "reactivator"},
    )
    assert reactivated.status_code == 200

    async def load_events():
        async with mapping_client.mapping_session_factory() as db:
            return (
                await db.execute(
                    select(KmaiFactorMappingEvent)
                    .where(KmaiFactorMappingEvent.mapping_id == mapping_id)
                    .order_by(KmaiFactorMappingEvent.id)
                )
            ).scalars().all()

    events = asyncio.run(load_events())
    assert [event.action for event in events] == ["created", "deactivated", "reactivated"]
    deactivated_before = json.loads(events[1].before_json)
    deactivated_after = json.loads(events[1].after_json)
    reactivated_before = json.loads(events[2].before_json)
    reactivated_after = json.loads(events[2].after_json)
    assert (deactivated_before["status"], deactivated_after["status"]) == ("active", "inactive")
    assert (reactivated_before["status"], reactivated_after["status"]) == ("inactive", "active")
    assert deactivated_after["promoted_from_id"] is None


def test_promotion_audit_retains_source_id_after_source_mapping_is_deleted(mapping_client):
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping("audited promotion provenance"),
    )
    assert created.status_code == 200
    source_id = created.json()["mapping_id"]
    promoted = mapping_client.post(
        f"/api/kmai-factor-mappings/{source_id}/promote",
        params={"expected_revision": 1, "actor": "promoter"},
    )
    assert promoted.status_code == 200
    promoted_id = promoted.json()["mapping_id"]

    deleted = mapping_client.delete(
        f"/api/kmai-factor-mappings/{source_id}",
        params={"delete": "true", "expected_revision": 1, "actor": "deleter"},
    )
    assert deleted.status_code == 200

    async def load_state_and_event():
        async with mapping_client.mapping_session_factory() as db:
            mapping = await db.get(KmaiFactorMapping, promoted_id)
            event = (
                await db.execute(
                    select(KmaiFactorMappingEvent).where(
                        KmaiFactorMappingEvent.mapping_id == promoted_id,
                        KmaiFactorMappingEvent.action == "promoted",
                    )
                )
            ).scalar_one()
            return mapping, event

    promoted_mapping, event = asyncio.run(load_state_and_event())
    assert promoted_mapping is not None
    assert promoted_mapping.promoted_from_id is None
    after = json.loads(event.after_json)
    assert after["status"] == "active"
    assert after["promoted_from_id"] == source_id


def test_same_expected_revision_updates_are_atomic_and_only_winner_is_audited(mapping_client):
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping("atomic revision"),
    )
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]
    default_override = app.dependency_overrides[get_db]

    async def stale_after_winner_get_db():
        async with mapping_client.mapping_session_factory() as stale_db:
            stale_mapping = await stale_db.get(KmaiFactorMapping, mapping_id)
            assert stale_mapping is not None
            assert stale_mapping.revision == 1
            async with mapping_client.mapping_session_factory() as winner_db:
                await update_mapping(
                    winner_db,
                    mapping_id,
                    KmaiMappingUpdateRequest(
                        expected_revision=1,
                        mapping_mode="existing_factor",
                        target_factor_key="requires_honing",
                        actor="revision winner",
                    ),
                )
                await winner_db.commit()
            yield stale_db

    app.dependency_overrides[get_db] = stale_after_winner_get_db
    try:
        contender = mapping_client.put(
            f"/api/kmai-factor-mappings/{mapping_id}",
            json={
                "expected_revision": 1,
                "status": "inactive",
                "actor": "revision contender",
            },
        )
    finally:
        app.dependency_overrides[get_db] = default_override

    assert contender.status_code == 409
    assert contender.json()["detail"]["code"] == "kmai_mapping_revision_conflict"

    async def load_persisted_state():
        async with mapping_client.mapping_session_factory() as db:
            mapping = await db.get(KmaiFactorMapping, mapping_id)
            events = (
                await db.execute(
                    select(KmaiFactorMappingEvent)
                    .where(
                        KmaiFactorMappingEvent.mapping_id == mapping_id,
                        KmaiFactorMappingEvent.action == "updated",
                    )
                    .order_by(KmaiFactorMappingEvent.id)
                )
            ).scalars().all()
            return mapping, events

    mapping, events = asyncio.run(load_persisted_state())
    assert mapping is not None
    assert mapping.status == "active"
    assert mapping.target_factor_key == "requires_honing"
    assert mapping.revision == 2
    assert len(events) == 1
    assert json.loads(events[0].before_json)["revision"] == 1
    assert json.loads(events[0].before_json)["target_factor_key"] == "has_slot_feature"
    assert json.loads(events[0].after_json)["revision"] == 2
    assert json.loads(events[0].after_json)["target_factor_key"] == "requires_honing"


def test_promotion_rejects_an_existing_global_mapping(mapping_client):
    source_value = "already global"
    global_mapping = mapping_client.post(
        "/api/kmai-factor-mappings",
        json={
            "scope": "global",
            "source_field": "cad.features",
            "source_value": source_value,
            "mapping_mode": "existing_factor",
            "target_factor_key": "has_slot_feature",
        },
    )
    assert global_mapping.status_code == 200
    project_mapping = mapping_client.post("/api/kmai-factor-mappings", json=_existing_mapping(source_value))
    assert project_mapping.status_code == 200

    promoted = mapping_client.post(
        f"/api/kmai-factor-mappings/{project_mapping.json()['mapping_id']}/promote",
        params={"expected_revision": 1},
    )

    assert promoted.status_code == 409
    assert promoted.json()["detail"]["code"] == "kmai_mapping_conflict"


def test_promotion_maps_database_unique_race_to_conflict(mapping_client):
    source_value = "promotion unique race"
    project_mapping = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping(source_value),
    )
    assert project_mapping.status_code == 200
    _install_unique_insert_race(mapping_client, source_value)

    promoted = mapping_client.post(
        f"/api/kmai-factor-mappings/{project_mapping.json()['mapping_id']}/promote",
        params={"expected_revision": 1},
    )

    assert promoted.status_code == 409
    assert promoted.json()["detail"]["code"] == "kmai_mapping_conflict"


def test_preview_uses_the_project_embedded_in_the_v2_package(mapping_client, rule_package_v2_payload):
    source_value = "package scoped feature"
    created = mapping_client.post("/api/kmai-factor-mappings", json=_existing_mapping(source_value))
    assert created.status_code == 200
    package = deepcopy(rule_package_v2_payload)
    package["route_rules"]["rules"].append(
        {
            "rule_id": "package-scope",
            "priority": 1,
            "enabled": True,
            "source": "user_confirmed",
            "when": {"field": "cad.features", "op": "contains", "value": source_value},
            "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
        }
    )

    preview = mapping_client.post(
        "/api/kmai-factor-mappings/resolve-preview",
        json={"project_id": 13, "package": package},
    )

    assert preview.status_code == 200
    assert not any(item["value"] == source_value for item in preview.json()["issues"])


def test_preview_leaves_unpersisted_special_requirements_to_the_exporter(mapping_client, rule_package_v2_payload):
    package = deepcopy(rule_package_v2_payload)
    package["route_rules"]["rules"].append(
        {
            "rule_id": "automatic-special-factor",
            "priority": 1,
            "enabled": True,
            "source": "user_confirmed",
            "when": {"field": "special.requirements", "op": "contains", "value": "custom inspection"},
            "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
        }
    )

    preview = mapping_client.post(
        "/api/kmai-factor-mappings/resolve-preview",
        json={"project_id": 12, "package": package},
    )

    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert preview.json()["issues"] == []


def test_preview_aggregates_repeated_unmapped_values_across_rules(mapping_client, rule_package_v2_payload):
    package = deepcopy(rule_package_v2_payload)
    for rule_id in ("unmapped-one", "unmapped-two"):
        package["route_rules"]["rules"].append(
            {
                "rule_id": rule_id,
                "priority": 1,
                "enabled": True,
                "source": "user_confirmed",
                "when": {"field": "precision.grades", "op": "contains", "value": "unmapped tolerance"},
                "then": {"include_process_ids": ["process_mill_slot"], "exclude_process_ids": []},
            }
        )

    preview = mapping_client.post(
        "/api/kmai-factor-mappings/resolve-preview",
        json={"project_id": 12, "package": package},
    )

    assert preview.status_code == 200
    issue = next(item for item in preview.json()["issues"] if item["value"] == "unmapped tolerance")
    assert issue["occurrences"] == 2
    assert issue["rule_refs"] == ["unmapped-one", "unmapped-two"]


def test_list_reports_reference_count_for_mapping_usage(mapping_client):
    created = mapping_client.post("/api/kmai-factor-mappings", json=_existing_mapping("listed reference"))
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]

    async def add_usage():
        async with mapping_client.mapping_session_factory() as db:
            package = FinalizedRulePackage(
                project_id=12,
                version=1,
                package_name="listed usage",
                schema_version="2.0",
                status="published",
            )
            db.add(package)
            await db.flush()
            db.add(
                KmaiFactorMappingUsage(
                    mapping_id=mapping_id,
                    package_id=package.id,
                    revision=1,
                    mapping_snapshot_json='{"scope": "project"}',
                )
            )
            await db.commit()

    asyncio.run(add_usage())

    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12})

    assert listed.status_code == 200
    referenced = next(item for item in listed.json() if item["mapping_id"] == mapping_id)
    assert referenced["reference_count"] == 1
    assert all(item["reference_count"] == 0 for item in listed.json() if item["scope"] == "builtin")


def test_mapping_referenced_by_package_cannot_be_deleted_but_can_be_deactivated(mapping_client):
    created = mapping_client.post("/api/kmai-factor-mappings", json=_existing_mapping("referenced"))
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]

    async def add_usage():
        async with mapping_client.mapping_session_factory() as db:
            package = FinalizedRulePackage(
                project_id=12,
                version=1,
                package_name="published",
                schema_version="2.0",
                status="published",
            )
            db.add(package)
            await db.flush()
            db.add(
                KmaiFactorMappingUsage(
                    mapping_id=mapping_id,
                    package_id=package.id,
                    revision=1,
                    mapping_snapshot_json='{"scope": "project"}',
                )
            )
            await db.commit()

    asyncio.run(add_usage())

    delete = mapping_client.delete(
        f"/api/kmai-factor-mappings/{mapping_id}",
        params={"delete": "true", "expected_revision": 1},
    )
    assert delete.status_code == 409
    assert delete.json()["detail"]["code"] == "kmai_mapping_in_use"

    deactivated = mapping_client.delete(
        f"/api/kmai-factor-mappings/{mapping_id}",
        params={"expected_revision": 1},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["mapping"]["status"] == "inactive"


def test_delete_maps_usage_created_after_precheck_to_mapping_in_use(mapping_client):
    source_value = "delete usage race"
    created = mapping_client.post(
        "/api/kmai-factor-mappings",
        json=_existing_mapping(source_value),
    )
    assert created.status_code == 200
    mapping_id = created.json()["mapping_id"]

    async def add_package():
        async with mapping_client.mapping_session_factory() as db:
            package = FinalizedRulePackage(
                project_id=12,
                version=1,
                package_name="race package",
                schema_version="2.0",
                status="draft",
            )
            db.add(package)
            await db.commit()
            return package.id

    package_id = asyncio.run(add_package())
    _install_usage_before_delete_race(mapping_client, source_value, package_id)

    deleted = mapping_client.delete(
        f"/api/kmai-factor-mappings/{mapping_id}",
        params={"delete": "true", "expected_revision": 1},
    )

    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "kmai_mapping_in_use"
    listed = mapping_client.get("/api/kmai-factor-mappings", params={"project_id": 12}).json()
    assert any(item["mapping_id"] == mapping_id for item in listed)
