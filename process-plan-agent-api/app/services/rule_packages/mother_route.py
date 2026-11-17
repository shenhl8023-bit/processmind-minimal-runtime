"""Server-owned final step identities shared by execution and mapping checks."""

from __future__ import annotations

import json
import re

from sqlalchemy import select

from app.models.models import DocumentOperationDetail, Operation, RouteMergeSnapshot
from app.services.process_tree_builder import build_superset_process_tree
from app.services.process_knowledge import is_material_preparation_name


class MotherRouteError(ValueError):
    pass


def _step_name(value):
    # Same display normalization as finalRouteSteps/normalizeOperationName.
    return re.sub(r"（.*?）", "", str(value or "").strip()).strip()


def _auxiliary(segment, steps):
    if is_material_preparation_name(segment.get("normalized_step_name") or ""):
        return True
    phase = str(segment.get("phase") or "")
    family = str(segment.get("step_family") or "")
    if phase in {"auxiliary", "inspection", "heat_treatment", "surface_treatment", "surface_or_heat_treatment"}:
        return True
    if family in {"heat", "surface", "inspection", "release"}:
        return True
    if family in {"shape", "hole", "feature", "finish", "孔加工类", "特征加工类", "车削类", "车削/成形类"}:
        return False
    names = str(segment.get("normalized_step_name") or "") + " ".join(step["name"] for step in steps)
    return re.search(r"车|铣|钻|镗|铰|攻丝|磨|研|珩|切槽|挖槽|倒角|倒圆|成形|割型|打型|打孔|割扁|刻线|电火花|线切割|平端面", names) is None


def _source_ids(segment):
    values = segment.get("source_operation_ids") or []
    if (not isinstance(values, list) or any(type(value) is not int or value <= 0 for value in values)
            or len(values) != len(set(values))):
        raise MotherRouteError("母路线来源工序标识无效，请返回路线归并核对。")
    return list(values)


def build_mother_route(segments, sources):
    """Mirror finalRouteSteps using persisted source data, never request steps."""
    result = {}
    source_ids = {source["id"] for source in sources}
    for segment in segments:
        process_id = str(segment.get("export_process_id") or segment.get("id") or "").strip()
        if not process_id or process_id in result:
            raise MotherRouteError("母路线工序标识缺失或重复。")
        ids = _source_ids(segment)
        steps = []
        if "step_item_details" in segment:
            # Some saved/legacy routes carry a server-owned explicit snapshot.
            for detail in segment["step_item_details"]:
                identity = detail.get("id") or detail.get("step_id")
                text = detail.get("text") or detail.get("name")
                kind = detail.get("kind", "primary")
                if not identity or not text or kind not in {"primary", "attached"}:
                    raise MotherRouteError("母路线工步快照不完整。")
                steps.append({"step_id": identity, "name": text, "kind": kind})
        else:
            if not set(ids).issubset(source_ids):
                raise MotherRouteError("母路线来源工序已缺失，请返回路线归并核对最新来源。")
            selected = [source for source in sources if source["id"] in ids]
            for kind, key in (("primary", "step_items"), ("attached", "attached_step_items")):
                merged = {}
                for source in selected:
                    occurrences = {}
                    for index, raw in enumerate(source.get(key) or []):
                        name = _step_name(raw)
                        if not name:
                            continue
                        occurrences[name] = occurrences.get(name, 0) + 1
                        occurrence = (name, occurrences[name])
                        order = index + 1 + (len(source.get("step_items") or []) if kind == "attached" else 0)
                        ref = {"source_operation_id": source["id"], "source_step_order": order,
                               "source_step_name": str(raw).strip()}
                        if occurrence in merged:
                            merged[occurrence]["source_steps"].append(ref)
                            continue
                        step = {"step_id": "{}.{}.op_{}_s{}".format(process_id, kind, source["id"], order),
                                "name": name, "kind": kind, "source_steps": [ref]}
                        merged[occurrence] = step
                        steps.append(step)
        if len({step["step_id"] for step in steps}) != len(steps):
            raise MotherRouteError("母路线工步标识重复。")
        result[process_id] = {"source_operation_ids": ids, "steps": steps, "auxiliary": _auxiliary(segment, steps)}
    return result


async def load_mother_route(db, project_id, segments):
    """Read already-extracted project rows without PDF parsing or model calls."""
    details = (await db.execute(select(DocumentOperationDetail).where(
        DocumentOperationDetail.project_id == project_id).order_by(
        DocumentOperationDetail.document_id, DocumentOperationDetail.operation_seq,
        DocumentOperationDetail.page_no, DocumentOperationDetail.id))).scalars().all()
    if details:
        sources = build_superset_process_tree(operations=[], detail_rows=details, sample_count=0)
    else:
        operations = (await db.execute(select(Operation).where(Operation.project_id == project_id)
                                      .order_by(Operation.sequence, Operation.id))).scalars().all()
        sources = [{"id": row.id, "step_items": [], "attached_step_items": []} for row in operations]
    # A saved merge workspace freezes the source order chosen in step two.
    # Its contents cannot replace current extracted text or invent source IDs.
    snapshot = (await db.execute(select(RouteMergeSnapshot).where(
        RouteMergeSnapshot.project_id == project_id).order_by(
        RouteMergeSnapshot.updated_at.desc(), RouteMergeSnapshot.id.desc()))).scalars().first()
    if snapshot:
        try:
            frozen_sources = json.loads(snapshot.superset_route_json or "[]")
            order = {source["id"]: i for i, source in enumerate(frozen_sources)}
            sources.sort(key=lambda source: order.get(source["id"], len(order)))
        except (ValueError, TypeError, KeyError):
            raise MotherRouteError("已保存的母路线来源顺序无效，请返回路线归并重新保存。")
    return build_mother_route(segments, sources)


def require_mother_catalog(package, mother_route):
    """Allow empty auxiliary instructions; machining must retain exact steps."""
    processes = sorted(package.route_catalog.processes, key=lambda process: process.default_sequence)
    if [process.process_id for process in processes] != list(mother_route):
        raise MotherRouteError("可执行规则必须包含当前完整母路线的全部工序及顺序。")
    for process in processes:
        expected = mother_route[process.process_id]
        if process.source_operation_ids != expected["source_operation_ids"]:
            raise MotherRouteError("工序 {} 的来源工序与已保存母路线不一致。".format(process.process_id))
        actual = [step.model_dump() for step in process.steps]
        steps = [{key: step[key] for key in ("step_id", "name", "kind")} for step in expected["steps"]]
        if actual != steps and not (expected["auxiliary"] and not actual):
            raise MotherRouteError("工序 {} 的工步身份、文本、顺序或来源与完整母路线不一致。".format(process.process_id))
