"""Persistent KmAI factor mapping operations and preview support."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import KmaiFactorMapping, KmaiFactorMappingEvent, KmaiFactorMappingUsage, Project
from app.services.rule_packages.kmai_mapping_contracts import (
    KmaiMappingBatchRequest,
    KmaiMappingCreateRequest,
    KmaiMappingOut,
    KmaiMappingPreviewResponse,
    KmaiMappingSnapshot,
    KmaiMappingUpdateRequest,
)
from app.services.rule_packages.kmai_mapping_registry import (
    builtin_factor_catalog,
    builtin_mapping_snapshots,
    load_effective_mapping_registry,
    manual_factor_key,
    mapping_snapshot_from_row,
    normalize_mapping_value,
)


ALLOWED_MAPPING_FIELDS = {"cad.features", "precision.grades", "special.requirements"}


@dataclass
class KmaiMappingStoreError(Exception):
    code: str
    message: str


def _integrity_error_text(error: IntegrityError) -> str:
    return " ".join(
        str(value)
        for value in (
            error.orig,
            getattr(getattr(error.orig, "diag", None), "constraint_name", None),
        )
        if value is not None
    ).lower()


def _is_mapping_insert_conflict(error: IntegrityError) -> bool:
    message = _integrity_error_text(error)
    unique_conflict = (
        "uq_kmai_factor_mappings_" in message
        or (
            ("unique constraint" in message or "duplicate key" in message)
            and "kmai_factor_mappings" in message
        )
    )
    foreign_key_conflict = "foreign key constraint" in message
    return unique_conflict or foreign_key_conflict


def _is_foreign_key_conflict(error: IntegrityError) -> bool:
    return "foreign key constraint" in _integrity_error_text(error)


async def _flush_mapping_inserts(
    db: AsyncSession,
    mappings: list[KmaiFactorMapping],
    *,
    message: str,
) -> None:
    try:
        await db.flush(mappings)
    except IntegrityError as error:
        if _is_mapping_insert_conflict(error):
            raise KmaiMappingStoreError("kmai_mapping_conflict", message) from error
        raise


def _catalog_by_key() -> dict[str, tuple[str, str]]:
    return {
        item.factor_key: (item.factor_name, item.factor_category)
        for item in builtin_factor_catalog()
    }


def _snapshot_json(snapshot: KmaiMappingSnapshot) -> str:
    return json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _mapping_out(mapping: KmaiFactorMapping, *, overridden: bool = False) -> KmaiMappingOut:
    return KmaiMappingOut(
        **mapping_snapshot_from_row(mapping).model_dump(mode="json"),
        status=mapping.status,
        promoted_from_id=mapping.promoted_from_id,
        created_by=mapping.created_by,
        updated_by=mapping.updated_by,
        overridden=overridden,
    )


async def _duplicate_mapping(
    db: AsyncSession,
    *,
    scope: str,
    project_id: int | None,
    source_field: str,
    source_value: str,
    exclude_id: int | None = None,
) -> KmaiFactorMapping | None:
    statement = select(KmaiFactorMapping).where(
        KmaiFactorMapping.scope == scope,
        KmaiFactorMapping.source_field == source_field,
    )
    if scope == "project":
        statement = statement.where(KmaiFactorMapping.project_id == project_id)
    else:
        statement = statement.where(KmaiFactorMapping.project_id.is_(None))
    for row in (await db.execute(statement)).scalars().all():
        if row.id != exclude_id and normalize_mapping_value(row.source_value) == source_value:
            return row
    return None


def _normalized_create_values(request: KmaiMappingCreateRequest) -> dict[str, object]:
    source_field = normalize_mapping_value(request.source_field)
    source_value = normalize_mapping_value(request.source_value)
    if source_field not in ALLOWED_MAPPING_FIELDS:
        raise KmaiMappingStoreError("kmai_mapping_source_unsupported", "unsupported KmAI mapping source field")
    if not source_value:
        raise KmaiMappingStoreError("kmai_mapping_source_required", "mapping source value is required")
    if request.scope == "global" and request.project_id is not None:
        raise KmaiMappingStoreError("kmai_mapping_scope_invalid", "global mappings cannot have project_id")
    if request.scope == "project" and request.project_id is None:
        raise KmaiMappingStoreError("kmai_mapping_scope_invalid", "project mappings require project_id")

    catalog = _catalog_by_key()
    if request.mapping_mode == "existing_factor":
        factor_key = request.target_factor_key or ""
        if factor_key not in catalog:
            raise KmaiMappingStoreError("kmai_mapping_factor_unknown", "target factor key is not in the builtin catalog")
        factor_name, factor_category = catalog[factor_key]
    else:
        factor_key = manual_factor_key(source_field, source_value)
        factor_name = (request.target_factor_name or "").strip()
        if not factor_name:
            raise KmaiMappingStoreError("kmai_mapping_manual_name_required", "manual mappings require a display name")
        factor_category = (request.target_factor_category or "manual_override").strip() or "manual_override"

    return {
        "scope": request.scope,
        "project_id": request.project_id,
        "source_field": source_field,
        "source_value": source_value,
        "mapping_mode": request.mapping_mode,
        "target_factor_key": factor_key,
        "target_factor_name": factor_name,
        "target_factor_category": factor_category,
        "actor": request.actor,
    }


async def _validate_project_scope(db: AsyncSession, values: dict[str, object]) -> None:
    if values["scope"] != "project":
        return
    project_id = values["project_id"]
    if await db.get(Project, project_id) is None:
        raise KmaiMappingStoreError("kmai_mapping_project_not_found", "project mapping requires an existing project")


async def _add_event(
    db: AsyncSession,
    mapping: KmaiFactorMapping,
    action: str,
    *,
    before: KmaiMappingSnapshot | None = None,
) -> None:
    after = mapping_snapshot_from_row(mapping)
    db.add(
        KmaiFactorMappingEvent(
            mapping_id=mapping.id,
            project_id=mapping.project_id,
            action=action,
            actor=mapping.updated_by,
            before_json=_snapshot_json(before) if before is not None else None,
            after_json=_snapshot_json(after),
        )
    )


async def create_mapping(db: AsyncSession, request: KmaiMappingCreateRequest) -> KmaiMappingOut:
    values = _normalized_create_values(request)
    await _validate_project_scope(db, values)
    duplicate = await _duplicate_mapping(
        db,
        scope=str(values["scope"]),
        project_id=values["project_id"],
        source_field=str(values["source_field"]),
        source_value=str(values["source_value"]),
    )
    if duplicate is not None:
        raise KmaiMappingStoreError("kmai_mapping_conflict", "a mapping already exists for this source pair")

    mapping = KmaiFactorMapping(
        scope=values["scope"],
        project_id=values["project_id"],
        source_field=values["source_field"],
        source_value=values["source_value"],
        mapping_mode=values["mapping_mode"],
        target_factor_key=values["target_factor_key"],
        target_factor_name=values["target_factor_name"],
        target_factor_category=values["target_factor_category"],
        created_by=values["actor"],
        updated_by=values["actor"],
    )
    db.add(mapping)
    await _flush_mapping_inserts(
        db,
        [mapping],
        message="a mapping already exists or its referenced row changed",
    )
    await _add_event(db, mapping, "created")
    return _mapping_out(mapping)


async def create_mapping_batch(db: AsyncSession, request: KmaiMappingBatchRequest) -> list[KmaiMappingOut]:
    values_list = [_normalized_create_values(item) for item in request.mappings]
    for values in values_list:
        await _validate_project_scope(db, values)
    seen: set[tuple[str, int | None, str, str]] = set()
    for values in values_list:
        source_pair = (
            str(values["scope"]),
            values["project_id"],
            str(values["source_field"]),
            str(values["source_value"]),
        )
        if source_pair in seen:
            raise KmaiMappingStoreError("kmai_mapping_conflict", "batch contains duplicate mapping sources")
        seen.add(source_pair)
        duplicate = await _duplicate_mapping(
            db,
            scope=source_pair[0],
            project_id=source_pair[1],
            source_field=source_pair[2],
            source_value=source_pair[3],
        )
        if duplicate is not None:
            raise KmaiMappingStoreError("kmai_mapping_conflict", "a mapping already exists for this source pair")

    rows: list[KmaiFactorMapping] = []
    for values in values_list:
        row = KmaiFactorMapping(
            scope=values["scope"],
            project_id=values["project_id"],
            source_field=values["source_field"],
            source_value=values["source_value"],
            mapping_mode=values["mapping_mode"],
            target_factor_key=values["target_factor_key"],
            target_factor_name=values["target_factor_name"],
            target_factor_category=values["target_factor_category"],
            created_by=values["actor"],
            updated_by=values["actor"],
        )
        db.add(row)
        rows.append(row)
    await _flush_mapping_inserts(
        db,
        rows,
        message="a batch mapping conflicts with current database state",
    )
    for row in rows:
        await _add_event(db, row, "created")
    return [_mapping_out(row) for row in rows]


async def list_mappings(db: AsyncSession, project_id: int | None) -> list[KmaiMappingOut]:
    scopes = [KmaiFactorMapping.scope == "global"]
    if project_id is not None:
        scopes.append(and_(KmaiFactorMapping.scope == "project", KmaiFactorMapping.project_id == project_id))
    rows = (
        await db.execute(
            select(KmaiFactorMapping)
            .where(or_(*scopes))
            .order_by(KmaiFactorMapping.scope, KmaiFactorMapping.id)
        )
    ).scalars().all()
    registry = await load_effective_mapping_registry(db, project_id)
    effective_by_source = {
        (item.source_field, item.source_value): item.mapping_identity
        for item in registry.snapshots
    }
    output: list[KmaiMappingOut] = []
    for builtin in builtin_mapping_snapshots():
        output.append(
            KmaiMappingOut(
                **builtin.model_dump(mode="json"),
                read_only=True,
                overridden=effective_by_source[(builtin.source_field, builtin.source_value)] != builtin.mapping_identity,
            )
        )
    for row in rows:
        snapshot = mapping_snapshot_from_row(row)
        output.append(
            _mapping_out(
                row,
                overridden=effective_by_source.get((snapshot.source_field, snapshot.source_value)) != snapshot.mapping_identity,
            )
        )
    return output


async def update_mapping(
    db: AsyncSession,
    mapping_id: int,
    request: KmaiMappingUpdateRequest,
) -> KmaiMappingOut:
    mapping = await db.get(KmaiFactorMapping, mapping_id)
    if mapping is None:
        raise KmaiMappingStoreError("kmai_mapping_not_found", "mapping does not exist")
    if mapping.revision != request.expected_revision:
        raise KmaiMappingStoreError("kmai_mapping_revision_conflict", "mapping revision is stale")
    if request.mapping_mode is not None and request.mapping_mode != mapping.mapping_mode:
        raise KmaiMappingStoreError("kmai_mapping_mode_invalid", "mapping mode cannot be changed")
    if request.target_factor_key is not None:
        if mapping.mapping_mode == "manual_factor":
            raise KmaiMappingStoreError("kmai_manual_factor_key_immutable", "manual factor keys are generated by the server")
        if request.mapping_mode != "existing_factor":
            raise KmaiMappingStoreError("kmai_mapping_mode_invalid", "target factor key updates require existing_factor mode")
        catalog = _catalog_by_key()
        if request.target_factor_key not in catalog:
            raise KmaiMappingStoreError("kmai_mapping_factor_unknown", "target factor key is not in the builtin catalog")
    if (
        mapping.mapping_mode == "manual_factor"
        and request.target_factor_name is not None
        and not request.target_factor_name.strip()
    ):
        raise KmaiMappingStoreError("kmai_mapping_manual_name_required", "manual mappings require a display name")

    before = mapping_snapshot_from_row(mapping)
    values: dict[str, object] = {
        "updated_by": request.actor,
        "revision": request.expected_revision + 1,
    }
    if request.target_factor_key is not None:
        values["target_factor_key"] = request.target_factor_key
        values["target_factor_name"], values["target_factor_category"] = _catalog_by_key()[request.target_factor_key]
    if request.target_factor_name is not None and mapping.mapping_mode == "manual_factor":
        values["target_factor_name"] = request.target_factor_name.strip()
    if request.target_factor_category is not None and mapping.mapping_mode == "manual_factor":
        values["target_factor_category"] = request.target_factor_category.strip() or "manual_override"
    if request.status is not None:
        values["status"] = request.status
    result = await db.execute(
        update(KmaiFactorMapping)
        .where(
            KmaiFactorMapping.id == mapping_id,
            KmaiFactorMapping.revision == request.expected_revision,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise KmaiMappingStoreError("kmai_mapping_revision_conflict", "mapping revision is stale")
    await db.refresh(mapping)
    await _add_event(db, mapping, "updated", before=before)
    return _mapping_out(mapping)


async def promote_mapping(db: AsyncSession, mapping_id: int, actor: str = "默认用户") -> KmaiMappingOut:
    mapping = await db.get(KmaiFactorMapping, mapping_id)
    if mapping is None:
        raise KmaiMappingStoreError("kmai_mapping_not_found", "mapping does not exist")
    if mapping.scope != "project":
        raise KmaiMappingStoreError("kmai_mapping_promotion_invalid", "only project mappings can be promoted")
    duplicate = await _duplicate_mapping(
        db,
        scope="global",
        project_id=None,
        source_field=mapping.source_field,
        source_value=normalize_mapping_value(mapping.source_value),
    )
    if duplicate is not None:
        raise KmaiMappingStoreError("kmai_mapping_conflict", "global mapping already exists for this source pair")
    promoted = KmaiFactorMapping(
        scope="global",
        source_field=mapping.source_field,
        source_value=normalize_mapping_value(mapping.source_value),
        mapping_mode=mapping.mapping_mode,
        target_factor_key=mapping.target_factor_key,
        target_factor_name=mapping.target_factor_name,
        target_factor_category=mapping.target_factor_category,
        status=mapping.status,
        promoted_from_id=mapping.id,
        created_by=actor,
        updated_by=actor,
    )
    db.add(promoted)
    await _flush_mapping_inserts(
        db,
        [promoted],
        message="global mapping already exists or its source mapping changed",
    )
    await _add_event(db, promoted, "promoted")
    return _mapping_out(promoted)


async def deactivate_or_delete_mapping(
    db: AsyncSession,
    mapping_id: int,
    *,
    delete: bool,
    actor: str = "默认用户",
) -> KmaiMappingOut | None:
    mapping = await db.get(KmaiFactorMapping, mapping_id)
    if mapping is None:
        raise KmaiMappingStoreError("kmai_mapping_not_found", "mapping does not exist")
    if delete:
        usage_count = await db.scalar(
            select(func.count()).select_from(KmaiFactorMappingUsage).where(KmaiFactorMappingUsage.mapping_id == mapping_id)
        )
        if usage_count:
            raise KmaiMappingStoreError("kmai_mapping_in_use", "published package usage prevents mapping deletion")
        before = mapping_snapshot_from_row(mapping)
        event = KmaiFactorMappingEvent(
            mapping_id=mapping.id,
            project_id=mapping.project_id,
            action="deleted",
            actor=actor,
            before_json=_snapshot_json(before),
            after_json=None,
        )
        db.add(event)
        await db.flush([event])
        await db.delete(mapping)
        try:
            await db.flush([mapping])
        except IntegrityError as error:
            if _is_foreign_key_conflict(error):
                raise KmaiMappingStoreError(
                    "kmai_mapping_in_use",
                    "published package usage prevents mapping deletion",
                ) from error
            raise
        return None
    request = KmaiMappingUpdateRequest(expected_revision=mapping.revision, status="inactive", actor=actor)
    return await update_mapping(db, mapping_id, request)


async def record_mapping_usage(
    db: AsyncSession,
    package_id: int,
    snapshots: Iterable[KmaiMappingSnapshot],
) -> None:
    for snapshot in snapshots:
        db.add(
            KmaiFactorMappingUsage(
                mapping_id=snapshot.mapping_id,
                package_id=package_id,
                revision=snapshot.revision,
                mapping_snapshot_json=_snapshot_json(snapshot),
            )
        )


async def list_mapping_usages(db: AsyncSession, mapping_id: int) -> list[KmaiFactorMappingUsage]:
    return (
        await db.execute(
            select(KmaiFactorMappingUsage)
            .where(KmaiFactorMappingUsage.mapping_id == mapping_id)
            .order_by(KmaiFactorMappingUsage.id)
        )
    ).scalars().all()


async def load_registry_for_package(db: AsyncSession, project_id: int | None):
    return await load_effective_mapping_registry(db, project_id)


def _condition_values(node) -> Iterable[tuple[str, str]]:
    if node.field:
        raw_values = node.value if isinstance(node.value, list) else [node.value]
        for value in raw_values:
            if value not in (None, ""):
                yield node.field, normalize_mapping_value(value)
    for child in node.all_conditions or []:
        yield from _condition_values(child)
    for child in node.any_conditions or []:
        yield from _condition_values(child)
    if node.not_condition is not None:
        yield from _condition_values(node.not_condition)


async def preview_mapping_resolution(db: AsyncSession, package, project_id: int | None) -> KmaiMappingPreviewResponse:
    registry = await load_effective_mapping_registry(db, project_id)
    occurrences: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"occurrences": 0, "rule_refs": set()}
    )
    for rule in package.route_rules.rules:
        for source_field, source_value in _condition_values(rule.when):
            if source_field not in {"cad.features", "precision.grades"}:
                continue
            if registry.resolve(source_field, source_value) is not None:
                continue
            bucket = occurrences[(source_field, source_value)]
            bucket["occurrences"] += 1
            bucket["rule_refs"].add(rule.rule_id)

    catalog_keys = [item.factor_key for item in builtin_factor_catalog()]
    issues = [
        {
            "field": source_field,
            "value": source_value,
            "occurrences": details["occurrences"],
            "rule_refs": sorted(details["rule_refs"]),
            "suggested_existing_factors": catalog_keys,
            "can_create_manual_factor": True,
        }
        for (source_field, source_value), details in sorted(occurrences.items())
    ]
    return KmaiMappingPreviewResponse(
        valid=not issues,
        issues=issues,
        mappings=list(registry.snapshots),
    )
