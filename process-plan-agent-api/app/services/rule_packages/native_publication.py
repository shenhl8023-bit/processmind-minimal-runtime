"""Frozen native V2 exports: no template queries, CAD projection, or rule lowering."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from pydantic import ValidationError

from app.core.product_profile import get_product_profile
from app.models.models import FinalizedRulePackage
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash


NATIVE_COMPILER_VERSION = "native-v2/1"


def package_for_product_profile(package: RulePackageV2) -> RulePackageV2:
    """Ignore stale browser-supplied template metadata in the basic edition."""
    if get_product_profile().template_mapping_enabled:
        return package
    native = package.model_copy(deep=True)
    native.manifest.compiled_from.template_ids = []
    for process in native.route_catalog.processes:
        process.template_group_aliases = []
    return native


class NativePublicationError(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.issues = [{"code": "native_snapshot_invalid", "path": "native_snapshot", "message": message}]


def snapshot_hash(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _enrich_route_candidates(catalog: dict, mapping: dict, mother_route: dict | None = None) -> None:
    """Attach saved candidates by stable identity without projecting any rules."""
    nodes = {}

    def visit(tree):
        for node in tree:
            path = node.get("path", [])
            if not node.get("children") and node.get("feature_selections"):
                key = "/".join(path)
                if key in nodes:
                    raise NativePublicationError("模板分组路径不唯一。")
                nodes[key] = set(node["feature_selections"])
            visit(node.get("children", []))

    visit(mapping["tree"])
    hidden = mapping.get("hidden_step_keys", [])
    step_ids = {s["step_id"] for p in catalog["processes"] for s in p["steps"]}
    if mother_route is not None:
        step_ids = {step["step_id"] for process in mother_route.values() for step in process["steps"]}
    if (not isinstance(hidden, list) or any(not isinstance(key, str) for key in hidden)
            or len(hidden) != len(set(hidden)) or not set(hidden).issubset(step_ids)):
        raise NativePublicationError("隐藏工步必须是当前完整母路线中不重复的工步标识。")
    hidden = set(hidden)
    processes = mapping["mapping_output"]
    output = {p.get("process_id"): p for p in processes}
    if len(output) != len(processes) or set(output) != {p["process_id"] for p in catalog["processes"]}:
        raise NativePublicationError("模板映射必须包含完整母路线的全部工序及分支。")
    for process in catalog["processes"]:
        mapped = output[process["process_id"]]
        steps = mapped.get("steps", [])
        # Auxiliary mapping rows deliberately carry no feature bindings. Their
        # core may have no steps; complete source identities stay in mother_route.
        auxiliary = (mother_route[process["process_id"]]["auxiliary"] if mother_route is not None
                     else mapped.get("process_type") == "辅助工序")
        if auxiliary and not steps:
            continue
        by_id = {s.get("step_id"): s for s in steps}
        if len(by_id) != len(steps) or set(by_id) != {s["step_id"] for s in process["steps"]} - hidden:
            raise NativePublicationError("模板映射工步与当前母路线不一致，请重新保存完整工艺树。")
        for step in process["steps"]:
            if step["step_id"] in hidden:
                continue
            candidates = by_id[step["step_id"]].get("candidates", {})
            if not isinstance(candidates, dict):
                raise NativePublicationError("模板候选格式无效。")
            for path, values in candidates.items():
                if (path not in nodes or not isinstance(values, list) or not values
                        or any(not isinstance(value, str) for value in values)
                        or len(values) != len(set(values)) or not set(values).issubset(nodes[path])):
                    raise NativePublicationError("模板候选包含无效分组或特征。")
            step["candidates"] = deepcopy(candidates)


def compile_native_snapshot(package: RulePackageV2, normalized_route: list, workflow_revision: int,
                            *, template_mapping: dict | None = None, mother_route: dict | None = None) -> dict:
    if not isinstance(normalized_route, list) or not normalized_route or any(
        not isinstance(segment, dict) for segment in normalized_route
    ):
        raise NativePublicationError("原生规则包必须关联已保存且非空的标准化路线。")
    normalized_route = deepcopy(normalized_route)
    for segment in normalized_route:
        segment.pop("template_group_aliases", None)
    snapshot = {
        "schema_version": "2.0",
        "normalized_route": normalized_route,
        "rule_package": package.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    if mother_route is not None:
        from app.services.rule_packages.mother_route import MotherRouteError, require_mother_catalog
        try:
            require_mother_catalog(package, mother_route)
        except MotherRouteError as exc:
            raise NativePublicationError(str(exc)) from exc
    if template_mapping is not None and "step_order_by_process" in template_mapping:
        from app.services.template_mapping_projection import (
            MappingProjectionError, project_mapping_route, validate_mapping_attachment,
        )
        try:
            _, delivery = validate_mapping_attachment(package, template_mapping, mother_route)
        except MappingProjectionError as exc:
            raise NativePublicationError(str(exc)) from exc
        snapshot["template_mapping_route"] = delivery
    if template_mapping is not None:
        _enrich_route_candidates(snapshot["rule_package"]["route_catalog"], template_mapping, mother_route)
        if "template_mapping_route" in snapshot:
            delivery_catalog = deepcopy(snapshot["rule_package"]["route_catalog"])
            for process in delivery_catalog["processes"]:
                # Feature-binding rows omit auxiliary instructions. Delivery
                # membership comes from the intact core/mother route instead.
                if mother_route is not None and not process["steps"] and mother_route[process["process_id"]]["auxiliary"]:
                    process["steps"] = [{key: step[key] for key in ("step_id", "name", "kind")}
                                        for step in mother_route[process["process_id"]]["steps"]]
            delivery_catalog["processes"] = project_mapping_route(delivery_catalog["processes"],
                template_mapping["mapping_operations"], template_mapping["step_order_by_process"],
                template_mapping["hidden_step_keys"])
            snapshot["template_mapping_catalog"] = delivery_catalog
    sources = {
        "compiler_version": NATIVE_COMPILER_VERSION,
        "project_id": package.manifest.project_id,
        "route_version_id": package.manifest.route_version_id,
        "workflow_revision": workflow_revision,
        "rule_package_content_hash": rule_package_content_hash(package),
        "route_content_hash": snapshot_hash(normalized_route),
        "native_snapshot_hash": snapshot_hash(snapshot),
        "native_snapshot": snapshot,
    }
    if mother_route is not None:
        sources["mother_route"] = deepcopy(mother_route)
        sources["mother_route_hash"] = snapshot_hash(mother_route)
    if template_mapping is not None:
        sources["template_mapping"] = deepcopy(template_mapping)
        sources["template_mapping_hash"] = snapshot_hash(template_mapping)
        sources["template_revision"] = template_mapping["template_revision"]
        sources["template_content_hash"] = template_mapping["content_hash"]
    return sources


def has_native_snapshot(sources: dict) -> bool:
    return (
        "native_snapshot" in sources or "native_snapshot_hash" in sources
        or str(sources.get("compiler_version", "")).startswith("native-v2/")
    )


def validate_native_snapshot(row: FinalizedRulePackage, sources: dict) -> bool:
    """Verify frozen bytes and package/source bindings without consulting live data."""
    try:
        snapshot = sources.get("native_snapshot")
        if not isinstance(snapshot, dict) or sources.get("compiler_version") != NATIVE_COMPILER_VERSION:
            return False
        package = RulePackageV2.model_validate({
            "manifest": json.loads(row.manifest_json or "{}"),
            "factor_dictionary": json.loads(row.factor_dictionary_json or "{}") or None,
            "input_schema": json.loads(row.input_schema_json or "{}"),
            "route_catalog": json.loads(row.route_catalog_json or "{}"),
            "route_rules": json.loads(row.route_rules_json or "{}"),
            "test_cases": json.loads(row.test_cases_json or "[]"),
        })
        rebuilt = compile_native_snapshot(package, snapshot.get("normalized_route"), sources.get("workflow_revision"),
                                          template_mapping=sources.get("template_mapping"), mother_route=sources.get("mother_route"))
        revision_keys = {"executable_revision_id", "executable_revision", "executable_content_hash"}
        revision_metadata = {key: sources[key] for key in revision_keys if key in sources}
        if revision_metadata and (
            set(revision_metadata) != revision_keys
            or type(revision_metadata["executable_revision_id"]) is not int
            or revision_metadata["executable_revision_id"] < 1
            or type(revision_metadata["executable_revision"]) is not int
            or revision_metadata["executable_revision"] < 1
            or revision_metadata["executable_content_hash"] != row.content_hash
        ):
            return False
        detached_history = row.route_version_id is None and row.status in {"archived", "superseded"}
        return (
            {key: value for key, value in sources.items() if key not in revision_keys} == rebuilt
            and row.project_id == package.manifest.project_id
            and (detached_history or row.route_version_id == package.manifest.route_version_id)
            and row.package_name == package.manifest.package_name
            and row.schema_version == "2.0"
            and row.content_hash == rebuilt["rule_package_content_hash"]
        )
    except (TypeError, ValueError, KeyError, AttributeError, ValidationError):
        return False
