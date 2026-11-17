"""Validate a mapping attachment against the intact core before projecting it."""
from __future__ import annotations

from copy import deepcopy


class MappingProjectionError(ValueError):
    pass


def step_order(operations, requested=None):
    expected = {op["process_id"]: [s["step_id"] for s in op.get("steps", [])] for op in operations}
    if len(expected) != len(operations):
        raise MappingProjectionError("映射工序标识重复。")
    if requested is None:
        return expected
    if not isinstance(requested, dict) or set(requested) != set(expected):
        raise MappingProjectionError("工步顺序必须包含当前完整路线的所有工序。")
    for pid, ids in requested.items():
        if (not isinstance(ids, list) or any(not isinstance(sid, str) for sid in ids)
                or len(ids) != len(set(ids)) or set(ids) != set(expected[pid])):
            raise MappingProjectionError("工步顺序必须是同工序稳定 ID 的完整排列，不能重复、遗漏或跨工序。")
    return deepcopy(requested)


def project_mapping_route(canonical, operations, requested=None, deleted=None):
    ordered = step_order(operations, requested)
    deleted = deleted or []
    known = {sid for ids in ordered.values() for sid in ids}
    if (any(not isinstance(sid, str) for sid in deleted) or len(deleted) != len(set(deleted))
            or not set(deleted).issubset(known)):
        raise MappingProjectionError("删除工步必须属于当前完整路线且不能重复。")
    result = deepcopy(canonical)
    for process in result:
        by_id = {s["step_id"]: s for s in process["steps"]}
        process["steps"] = [by_id[sid] for sid in ordered[process["process_id"]]
                            if sid not in deleted and sid in by_id]
    return result


def require_mapping_core(package, operations, canonical, mother_route=None, source_step_items=None):
    """Names, canonical order and source refs remain authoritative, even if deleted."""
    catalog = package.route_catalog.processes
    if ([op["process_id"] for op in operations] != [p.process_id for p in catalog]
            or [p["process_id"] for p in canonical] != [p.process_id for p in catalog]):
        raise MappingProjectionError("映射工序必须与当前核心的完整工序及顺序一致。")
    for core, op, output in zip(catalog, operations, canonical):
        expected = mother_route.get(core.process_id) if mother_route is not None else None
        if (op["operation_name"] != core.display_name or output["process_name"] != core.display_name
                or op.get("source_operation_ids", []) != core.source_operation_ids):
            raise MappingProjectionError("映射工序名称或来源与当前核心不一致。")
        auxiliary = expected["auxiliary"] if expected is not None else output["process_type"] == "辅助工序"
        if op.get("process_type") != ("辅助工序" if auxiliary else "加工工序"):
            raise MappingProjectionError("映射工序类型与当前母路线不一致。")
        steps = op.get("steps", [])
        authority = expected["steps"] if expected is not None else [s.model_dump() for s in core.steps]
        if ([(s["step_id"], s["step_name"]) for s in steps]
                != [(s["step_id"], s["name"]) for s in authority]):
            raise MappingProjectionError("映射工步身份、名称或规范顺序与当前母路线不一致。")
        for step, authoritative in zip(steps, authority):
            refs = step.get("source_steps") or [step]
            actual = [(ref.get("source_operation_id"), ref.get("source_step_order"), ref.get("source_step_name"))
                      for ref in refs if ref.get("source_operation_id")]
            primary = (step.get("source_operation_id"), step.get("source_step_order"), step.get("source_step_name"))
            if actual and primary != actual[0]:
                raise MappingProjectionError("映射工步的主来源与完整来源引用不一致。")
            frozen = authoritative.get("source_steps")
            if frozen:
                desired = [(r["source_operation_id"], r["source_step_order"], r["source_step_name"]) for r in frozen]
                if actual != desired or primary != desired[0]:
                    raise MappingProjectionError("映射工步的来源身份已变化，请重新加载。")
            elif actual:
                for source_id, order, name in actual:
                    source = (source_step_items or {}).get(str(source_id))
                    if (source_id not in core.source_operation_ids or (source is not None and
                            (not 0 < order <= len(source) or source[order - 1] != name))):
                        raise MappingProjectionError("映射工步的来源序号或文本与当前母路线不一致。")


def validate_mapping_attachment(package, mapping, mother_route=None):
    """Shared by save, both publication formats and frozen snapshot rebuilding."""
    from fastapi import HTTPException
    from app.services.project_group_templates import (
        _build_mapping_output, _step_mapping_snapshot, _final_mapping_targets,
        _path_index, _resolve_step_mapping,
    )
    from app.services.rule_packages.hashing import rule_package_content_hash

    operations = mapping["mapping_operations"]
    reviews = [_step_mapping_snapshot(value) for value in mapping["step_mappings"]]
    try:
        targets = _final_mapping_targets(operations)
        index = _path_index(mapping["tree"])
        for review in reviews:
            ref = (review.source_operation_id, review.source_step_order, review.source_step_name)
            if (not review.final_targets or any(target not in targets.get(ref, []) for target in review.final_targets)):
                raise MappingProjectionError("映射目标不属于该来源工步对应的最终工步。")
            _resolve_step_mapping(review, index)
        canonical = _build_mapping_output(operations, reviews)
    except HTTPException as exc:
        raise MappingProjectionError(str(exc.detail)) from exc
    context = mapping["mapping_context"]
    require_mapping_core(package, operations, canonical, mother_route, context.get("source_step_items"))
    if {key: value for key, value in context.items() if key != "source_step_items"} != {"project_id": package.manifest.project_id,
                   "route_version_id": package.manifest.route_version_id,
                   "core_content_hash": rule_package_content_hash(package),
                   "template_content_hash": mapping["content_hash"]}:
        raise MappingProjectionError("映射附件的路线、规则或模板版本已过期。")
    delivery = project_mapping_route(canonical, operations, mapping["step_order_by_process"], mapping["hidden_step_keys"])
    if delivery != mapping["mapping_output"]:
        raise MappingProjectionError("映射交付表与完整核心及排序、删除附件不一致。")
    deleted = set(mapping["hidden_step_keys"])
    if any(target["step_id"] in deleted for review in reviews for target in review.final_targets):
        raise MappingProjectionError("删除工步仍残留映射关联。")
    return canonical, delivery


def compile_mapping_demo_tables(package, mapping, mother_route=None, *, step_states=None):
    from app.services.project_group_templates import _build_mapping_output, _step_mapping_snapshot
    from app.services.rule_packages.demo_tables import compile_demo_tables

    canonical = _build_mapping_output(mapping["mapping_operations"],
                                     [_step_mapping_snapshot(value) for value in mapping["step_mappings"]])
    # The unchanged compiler checks exact canonical IDs, names, counts and order first.
    compiled = compile_demo_tables(package, canonical, step_states=step_states)
    validate_mapping_attachment(package, mapping, mother_route)
    compiled["full_route_table"] = project_mapping_route(compiled["full_route_table"],
        mapping["mapping_operations"], mapping["step_order_by_process"], mapping["hidden_step_keys"])
    return compiled, canonical
