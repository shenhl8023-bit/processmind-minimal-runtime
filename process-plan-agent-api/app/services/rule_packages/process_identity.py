"""Stable exported process identities for normalized route segments."""

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


def _default_export_process_id(segment_id: str, display_name: str) -> str:
    if segment_id.startswith("process_"):
        return segment_id
    if "淬火" in display_name:
        return "process_quench"
    return segment_id


def route_process_identities(route_items: Iterable[Any]) -> list[RouteProcessIdentity]:
    identities: list[RouteProcessIdentity] = []
    for index, item in enumerate(route_items):
        segment_id = str(_value(item, "id") or "").strip() or f"manual-route-{index + 1}"
        display_name = str(
            _value(item, "normalized_step_name")
            or _value(item, "process_name")
            or _value(item, "name")
            or segment_id
        ).strip() or segment_id
        export_process_id = str(_value(item, "export_process_id") or "").strip()
        if not export_process_id:
            export_process_id = _default_export_process_id(segment_id, display_name) or segment_id
        identities.append(RouteProcessIdentity(segment_id, export_process_id, display_name))
    return identities


__all__ = ["RouteProcessIdentity", "route_process_identities"]
