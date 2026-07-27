"""Effective KmAI factor mapping resolution for builtin, global, and project scopes."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from types import MappingProxyType
from typing import Iterable, Mapping

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import KmaiFactorMapping
from app.services.rule_packages.kmai_mapping_contracts import (
    KmaiFactorCatalogItem,
    KmaiMappingSnapshot,
)


BUILTIN_FACTOR_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    ("F001", "material_grade", "\u6750\u6599\u724c\u53f7", "material", "enum"),
    ("F002", "part_type", "\u96f6\u4ef6\u7c7b\u578b", "part", "enum"),
    ("F003", "has_flat_or_plane", "\u6241\u4f4d/\u5e73\u9762", "feature", "boolean"),
    ("F004", "has_slot_feature", "\u69fd\u7c7b\u7279\u5f81", "feature", "boolean"),
    ("F005", "has_standard_or_aux_hole", "\u666e\u901a\u5b54/\u8f85\u52a9\u5b54", "feature", "boolean"),
    ("F005A", "has_center_through_hole", "\u4e2d\u95f4\u901a\u5b54", "feature", "boolean"),
    ("F006", "has_reamed_or_precision_hole", "\u94f0\u5b54/\u7cbe\u5b54", "feature", "boolean"),
    ("F007", "has_shaped_hole_or_cut_flat", "\u578b\u5b54/\u5272\u6241", "feature", "boolean"),
    ("F008", "has_post_stage_added_hole", "\u540e\u6bb5\u8865\u5145\u5b54", "feature", "boolean"),
    ("F009", "has_hole_finish_machining", "\u5b54\u7cbe\u52a0\u5de5", "precision", "boolean"),
    ("F010", "requires_honing", "\u73e9\u5b54\u8981\u6c42", "precision", "boolean"),
    ("F011", "requires_hole_lapping", "\u7814\u5b54\u8981\u6c42", "precision", "boolean"),
    ("F012", "requires_outer_diameter_grinding", "\u5916\u5706\u78e8\u524a", "precision", "boolean"),
    ("F013", "requires_end_face_grinding", "\u7aef\u9762\u78e8\u524a", "precision", "boolean"),
    ("F014", "requires_slot_grinding", "\u69fd\u78e8\u524a", "precision", "boolean"),
    ("F015", "requires_outer_diameter_lapping", "\u7814\u5916\u5706", "precision", "boolean"),
    ("F016", "uses_center_hole_location", "\u9876\u5c16\u5b54\u5b9a\u4f4d", "precision", "boolean"),
    ("F017", "needs_stress_relief", "\u53bb\u5e94\u529b", "heat_treatment", "boolean"),
    ("F018", "needs_quenching", "\u6dec\u706b", "heat_treatment", "boolean"),
    ("F019", "needs_vacuum_quenching", "\u771f\u7a7a\u6dec\u706b", "heat_treatment", "boolean"),
    ("F020", "has_nitrided_layer", "\u6e17\u6c2e\u5c42", "heat_treatment", "boolean"),
    ("F021", "needs_chromic_acid_anodizing", "\u94ec\u9178\u9633\u6781\u5316", "surface_treatment", "boolean"),
    ("F022", "needs_hard_anodizing", "\u786c\u8d28\u9633\u6781\u5316", "surface_treatment", "boolean"),
    ("F023", "needs_marking", "\u6807\u5370/\u6807\u523b", "inspection_marking", "boolean"),
    ("F024", "needs_crack_inspection", "\u88c2\u7eb9\u68c0\u6d4b", "inspection_marking", "boolean"),
    ("F025", "needs_burn_inspection", "\u70e7\u4f24\u68c0\u67e5", "inspection_marking", "boolean"),
    ("F026", "needs_ndt_inspection", "\u65e0\u635f\u68c0\u6d4b", "inspection_marking", "boolean"),
)


BUILTIN_VALUE_FACTOR_MAP: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        ("cad.features", "\u6241\u4f4d/\u5e73\u9762"): "has_flat_or_plane",
        ("cad.features", "\u69fd\u7c7b\u7279\u5f81"): "has_slot_feature",
        ("cad.features", "\u666e\u901a\u5b54/\u8f85\u52a9\u5b54"): "has_standard_or_aux_hole",
        ("cad.features", "\u94f0\u5b54/\u7cbe\u5b54"): "has_reamed_or_precision_hole",
        ("cad.features", "\u578b\u5b54/\u5272\u6241"): "has_shaped_hole_or_cut_flat",
        ("cad.features", "\u9876\u5c16\u5b54"): "uses_center_hole_location",
    }
)


_SCOPE_PRECEDENCE = {"builtin": 0, "global": 1, "project": 2}
_FACTOR_METADATA = {
    factor_key: (factor_name, factor_category)
    for _, factor_key, factor_name, factor_category, _ in BUILTIN_FACTOR_SPECS
}


def normalize_mapping_value(value: object) -> str:
    """Normalize values before storing or resolving a mapping source pair."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


def manual_factor_key(source_field: str, source_value: str) -> str:
    normalized_field = normalize_mapping_value(source_field)
    normalized_value = normalize_mapping_value(source_value)
    digest = hashlib.sha256(f"{normalized_field}\0{normalized_value}".encode("utf-8")).hexdigest()[:12]
    return f"processmind_manual_{digest}"


def _source_key(source_field: str, source_value: str) -> tuple[str, str]:
    return normalize_mapping_value(source_field), normalize_mapping_value(source_value)


def builtin_factor_catalog() -> tuple[KmaiFactorCatalogItem, ...]:
    return tuple(
        KmaiFactorCatalogItem(
            factor_key=factor_key,
            factor_name=factor_name,
            factor_category=factor_category,
            source_mode="builtin",
            read_only=True,
        )
        for _, factor_key, factor_name, factor_category, _ in BUILTIN_FACTOR_SPECS
    )


def builtin_mapping_snapshots() -> tuple[KmaiMappingSnapshot, ...]:
    snapshots: list[KmaiMappingSnapshot] = []
    for (source_field, source_value), target_factor_key in BUILTIN_VALUE_FACTOR_MAP.items():
        target_factor_name, target_factor_category = _FACTOR_METADATA[target_factor_key]
        normalized_field, normalized_value = _source_key(source_field, source_value)
        snapshots.append(
            KmaiMappingSnapshot(
                mapping_identity=f"builtin:{normalized_field}:{normalized_value}",
                scope="builtin",
                source_field=normalized_field,
                source_value=normalized_value,
                mapping_mode="existing_factor",
                target_factor_key=target_factor_key,
                target_factor_name=target_factor_name,
                target_factor_category=target_factor_category,
            )
        )
    return tuple(snapshots)


def mapping_snapshot_from_row(mapping: KmaiFactorMapping) -> KmaiMappingSnapshot:
    normalized_field, normalized_value = _source_key(mapping.source_field, mapping.source_value)
    return KmaiMappingSnapshot(
        mapping_id=mapping.id,
        mapping_identity=f"{mapping.scope}:{mapping.id}",
        revision=mapping.revision,
        scope=mapping.scope,
        project_id=mapping.project_id,
        source_field=normalized_field,
        source_value=normalized_value,
        mapping_mode=mapping.mapping_mode,
        target_factor_key=mapping.target_factor_key,
        target_factor_name=mapping.target_factor_name,
        target_factor_category=mapping.target_factor_category,
    )


class KmaiMappingRegistry:
    """A deterministic, precedence-aware view of currently effective mappings."""

    def __init__(self, snapshots: Iterable[KmaiMappingSnapshot]):
        by_source: dict[tuple[str, str], KmaiMappingSnapshot] = {}
        for snapshot in sorted(
            snapshots,
            key=lambda item: _SCOPE_PRECEDENCE[item.scope],
        ):
            by_source[_source_key(snapshot.source_field, snapshot.source_value)] = snapshot
        self._by_source = by_source
        self._snapshots = tuple(
            sorted(
                by_source.values(),
                key=lambda item: (item.source_field, item.source_value, item.mapping_identity),
            )
        )

    @property
    def snapshots(self) -> tuple[KmaiMappingSnapshot, ...]:
        return self._snapshots

    @property
    def signature(self) -> str:
        payload = [snapshot.model_dump(mode="json") for snapshot in self._snapshots]
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def resolve(self, source_field: str, source_value: str) -> KmaiMappingSnapshot | None:
        return self._by_source.get(_source_key(source_field, source_value))


def builtin_mapping_registry() -> KmaiMappingRegistry:
    return KmaiMappingRegistry(builtin_mapping_snapshots())


async def load_effective_mapping_registry(
    db: AsyncSession,
    project_id: int | None,
) -> KmaiMappingRegistry:
    scopes = [KmaiFactorMapping.scope == "global"]
    if project_id is not None:
        scopes.append(
            and_(
                KmaiFactorMapping.scope == "project",
                KmaiFactorMapping.project_id == project_id,
            )
        )
    result = await db.execute(
        select(KmaiFactorMapping)
        .where(KmaiFactorMapping.status == "active", or_(*scopes))
        .order_by(KmaiFactorMapping.id)
    )
    persisted_snapshots = [mapping_snapshot_from_row(mapping) for mapping in result.scalars().all()]
    return KmaiMappingRegistry((*builtin_mapping_snapshots(), *persisted_snapshots))
