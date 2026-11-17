"""Stable exported process identities for normalized route segments."""

from __future__ import annotations

from collections import Counter
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
    fixed_identities: list[bool] = []
    for index, item in enumerate(route_items):
        segment_id = str(_value(item, "id") or "").strip() or f"manual-route-{index + 1}"
        display_name = str(
            _value(item, "normalized_step_name")
            or _value(item, "process_name")
            or _value(item, "name")
            or segment_id
        ).strip() or segment_id
        export_process_id = str(_value(item, "export_process_id") or "").strip()
        fixed_identities.append(bool(export_process_id) or segment_id.startswith("process_"))
        if not export_process_id:
            export_process_id = _default_export_process_id(segment_id, display_name) or segment_id
        identities.append(RouteProcessIdentity(segment_id, export_process_id, display_name))

    export_counts = Counter(item.export_process_id for item in identities)
    segment_counts = Counter(item.segment_id for item in identities)
    reserved_ids = set(export_counts) | set(segment_counts)
    resolved: list[RouteProcessIdentity] = []
    for identity, fixed in zip(identities, fixed_identities):
        process_id = identity.export_process_id
        # A duplicated segment ID has no stable node identity to recover;
        # leave it invalid for the existing authoritative route validation.
        if not fixed and segment_counts[identity.segment_id] == 1 and (
            export_counts[process_id] > 1
            or (process_id != identity.segment_id and process_id in segment_counts)
        ):
            # Legacy name aliases are valid only when they identify one node.
            # Resolve collisions from the stable segment ID before persisting;
            # occurrence numbers would move rules/factors on a route reorder.
            process_id = identity.segment_id
            if process_id in export_counts:
                suffix = 2
                while "{}__{}".format(identity.segment_id, suffix) in reserved_ids:
                    suffix += 1
                process_id = "{}__{}".format(identity.segment_id, suffix)
            reserved_ids.add(process_id)
        resolved.append(RouteProcessIdentity(identity.segment_id, process_id, identity.display_name))
    return resolved


__all__ = ["RouteProcessIdentity", "route_process_identities"]
