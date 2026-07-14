"""
route_rules_runtime 的轻量 warning 与恢复辅助。
"""

from __future__ import annotations

from typing import Any

from app.services.harness_validators import harness_warning_factor_name, looks_like_equipment_name


def recover_equipment_promoted_to_operation(route_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recovered: list[dict[str, Any]] = []
    removed_names: list[str] = []
    for item in route_items:
        name = str(item.get("name") or item.get("operation_name") or "").strip()
        if looks_like_equipment_name(name):
            removed_names.append(name)
            continue
        recovered.append(item)

    if not removed_names or not recovered:
        return recovered

    warnings = list(recovered[0].get("harness_recovery_warnings") or [])
    target = " / ".join(removed_names[:4])
    if len(removed_names) > 4:
        target += " / ..."
    warnings.append({
        "code": "EQUIPMENT_OPERATION_REMOVED",
        "message": "设备、机床或工位名称被误作为顶层工序，已自动从路线中移除。",
        "target": target,
        "suggested_action": "请在路线归并审核中确认这些名称仅作为设备证据使用。",
    })
    recovered[0] = {
        **recovered[0],
        "harness_recovery_warnings": warnings,
    }
    return recovered


def harness_warning_factor_from_payload(warning: dict[str, Any]) -> dict[str, str] | None:
    code = str(warning.get("code") or "").strip()
    if not code:
        return None
    message = str(warning.get("message") or "").strip()
    target = str(warning.get("target") or "").strip()
    suggested_action = str(warning.get("suggested_action") or "").strip()
    evidence_parts = [
        part
        for part in (
            message,
            f"对象：{target}" if target else "",
            f"建议：{suggested_action}" if suggested_action else "",
        )
        if part
    ]
    return {
        "name": harness_warning_factor_name(code),
        "evidence": "；".join(evidence_parts),
        "strength": "WEAK",
    }


def merge_harness_warning_factors(
    factors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(factors or [])
    seen = {str(item.get("name") or "").strip() for item in merged if isinstance(item, dict)}
    for warning in warnings or []:
        factor = harness_warning_factor_from_payload(warning) if isinstance(warning, dict) else None
        if not factor or factor["name"] in seen:
            continue
        merged.append(factor)
        seen.add(factor["name"])
    return merged


__all__ = [
    "harness_warning_factor_from_payload",
    "merge_harness_warning_factors",
    "recover_equipment_promoted_to_operation",
]
