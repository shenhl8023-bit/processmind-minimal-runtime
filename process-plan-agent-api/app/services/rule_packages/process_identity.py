"""Resolve route-segment identities used by rule packages.

The route editor owns an internal segment id (for example ``segment-heat``),
while the V2/KmAI package may need a stable exported id (for example
``process_quench``).  Keeping that translation in one server-side module
prevents validation and migration from applying different name heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RouteProcessIdentity:
    segment_id: str
    export_process_id: str
    display_name: str


def _value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _display_name(item: Any, segment_id: str) -> str:
    return (
        str(
            _value(item, "normalized_step_name")
            or _value(item, "process_name")
            or _value(item, "name")
            or segment_id
        ).strip()
        or segment_id
    )


def _default_export_process_id(segment_id: str, display_name: str) -> str:
    # Stable ids already present in legacy route snapshots remain authoritative.
    if segment_id.startswith("process_"):
        return segment_id
    # This is the only historical name alias that was emitted by the frontend.
    # It is deliberately kept server-side so every consumer sees the same id.
    if "\u6dec\u706b" in display_name:
        return "process_quench"
    return segment_id


def route_process_identities(route_items: Iterable[Any]) -> list[RouteProcessIdentity]:
    identities: list[RouteProcessIdentity] = []
    for index, item in enumerate(route_items):
        segment_id = str(_value(item, "id") or "").strip()
        if not segment_id:
            segment_id = f"manual-route-{index + 1}"
        display_name = _display_name(item, segment_id)
        explicit_id = str(_value(item, "export_process_id") or "").strip()
        export_process_id = explicit_id or _default_export_process_id(segment_id, display_name)
        if not export_process_id:
            export_process_id = segment_id
        identities.append(RouteProcessIdentity(
            segment_id=segment_id,
            export_process_id=export_process_id,
            display_name=display_name,
        ))
    return identities


def route_process_identity_issues(route_items: Iterable[Any]) -> list[str]:
    identities = route_process_identities(route_items)
    by_export_id: dict[str, list[str]] = {}
    for identity in identities:
        by_export_id.setdefault(identity.export_process_id, []).append(identity.segment_id)
    issues: list[str] = []
    for export_id, segment_ids in sorted(by_export_id.items()):
        unique_segment_ids = list(dict.fromkeys(segment_ids))
        if len(unique_segment_ids) > 1:
            issues.append(
                f"stable process id {export_id} maps to multiple route segments: {', '.join(unique_segment_ids)}"
            )
    return issues


def route_process_reference_map(route_items: Iterable[Any]) -> dict[str, str]:
    identities = route_process_identities(route_items)
    by_export_id: dict[str, list[RouteProcessIdentity]] = {}
    by_segment_id: dict[str, list[RouteProcessIdentity]] = {}
    for identity in identities:
        by_export_id.setdefault(identity.export_process_id, []).append(identity)
        by_segment_id.setdefault(identity.segment_id, []).append(identity)

    references: dict[str, str] = {}
    for segment_id, matches in by_segment_id.items():
        if len(matches) == 1:
            references[segment_id] = matches[0].export_process_id
    for export_id, matches in by_export_id.items():
        if len(matches) == 1:
            references[export_id] = export_id
    return references


def resolve_route_process_reference(reference: str, route_items: Iterable[Any]) -> str:
    text = str(reference or "").strip()
    if not text:
        return text
    return route_process_reference_map(route_items).get(text, text)


def route_export_process_ids(route_items: Iterable[Any]) -> set[str]:
    return {
        identity.export_process_id
        for identity in route_process_identities(route_items)
        if identity.export_process_id
    }


def _route_identity_is_authoritative(route_items: list[Any]) -> bool:
    if not route_items:
        return False
    for item in route_items:
        explicit_id = str(_value(item, "export_process_id") or "").strip()
        segment_id = str(_value(item, "id") or "").strip()
        if explicit_id or segment_id.startswith(("segment-", "split-", "manual-route-")):
            return True
    return False


def package_process_reference_issues(package: Any, route_items: Iterable[Any]) -> list[str]:
    """Return publication blockers for package ids absent from the current route.

    Legacy snapshots whose route catalog already contains stable ``process_*``
    ids are intentionally left alone; newer normalized routes carry explicit
    segment identity metadata and are checked strictly.
    """
    items = list(route_items)
    if not _route_identity_is_authoritative(items):
        return []

    issues = route_process_identity_issues(items)
    allowed_ids = route_export_process_ids(items)
    references: set[str] = set()
    catalog = getattr(package, "route_catalog", None)
    for process in list(getattr(catalog, "processes", []) or []):
        process_id = str(getattr(process, "process_id", "") or "").strip()
        if process_id:
            references.add(process_id)
        constraints = getattr(process, "constraints", None)
        for field_name in ("requires", "must_run_after", "must_run_before", "conflicts_with"):
            references.update(
                str(value).strip()
                for value in list(getattr(constraints, field_name, []) or [])
                if str(value).strip()
            )

    rules = getattr(getattr(package, "route_rules", None), "rules", []) or []
    for rule in rules:
        action = getattr(rule, "then", None)
        for field_name in ("include_process_ids", "exclude_process_ids"):
            references.update(
                str(value).strip()
                for value in list(getattr(action, field_name, []) or [])
                if str(value).strip()
            )
    for relation in list(getattr(getattr(package, "route_rules", None), "process_relations", []) or []):
        references.update(
            str(value).strip()
            for field_name in ("source_process_ids", "target_process_ids")
            for value in list(getattr(relation, field_name, []) or [])
            if str(value).strip()
        )
    for case in list(getattr(package, "test_cases", []) or []):
        expectation = getattr(case, "expect", None)
        references.update(
            str(value).strip()
            for field_name in ("included_process_ids", "excluded_process_ids")
            for value in list(getattr(expectation, field_name, []) or [])
            if str(value).strip()
        )

    issues.extend(
        f"package references route process not present: {process_id}"
        for process_id in sorted(references - allowed_ids)
    )
    return list(dict.fromkeys(issues))


def enrich_route_item_export_process_id(item: Any) -> dict[str, Any]:
    payload = dict(item) if isinstance(item, dict) else {
        key: getattr(item, key)
        for key in ("id", "normalized_step_name", "process_name", "name", "export_process_id")
        if hasattr(item, key)
    }
    identity = route_process_identities([payload])[0]
    payload["export_process_id"] = identity.export_process_id
    return payload


__all__ = [
    "RouteProcessIdentity",
    "enrich_route_item_export_process_id",
    "package_process_reference_issues",
    "resolve_route_process_reference",
    "route_export_process_ids",
    "route_process_identities",
    "route_process_identity_issues",
    "route_process_reference_map",
]
