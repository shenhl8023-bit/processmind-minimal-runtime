"""Read-only workflow completion checks used by step navigation."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Document,
    FinalizedRulePackage,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
    ProjectGroupTemplate,
    DocumentOperationDetail,
)
from app.services.process_tree_builder import build_superset_process_tree


def _load_list(value: Optional[str]) -> List[object]:
    try:
        payload = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return payload if isinstance(payload, list) else []


def _path_key(path: object) -> Tuple[str, ...]:
    if not isinstance(path, list):
        return ()
    return tuple(unicodedata.normalize("NFC", str(part)).strip() for part in path)


def _route_items(route: NormalizedRouteVersion) -> List[Dict[str, object]]:
    return [item for item in _load_list(route.route_json) if isinstance(item, dict)]


def _needs_merge_name_review(segment: dict[str, object]) -> bool:
    name = str(segment.get("normalized_step_name") or "")
    parts = {part.strip() for part in re.split(r"[／/]", name) if part.strip()}
    return len(parts) >= 2


def _has_merge_name_answer(review: NormalizedRouteSegmentRuleReview | None) -> bool:
    if review is None:
        return False
    trail = _load_list(review.question_trail_json)
    return any(
        isinstance(item, dict) and str(item.get("nodeId") or "") == "merge_name_root"
        for item in trail
    )


def _segment_has_rule_decision(
    segment: dict[str, object],
    review: NormalizedRouteSegmentRuleReview | None,
) -> bool:
    if _needs_merge_name_review(segment) and not _has_merge_name_answer(review):
        return False
    return review is not None and str(review.decision or "").lower() in {"accepted", "rejected"}


def _segment_is_default_complete(segment: dict[str, object]) -> bool:
    if _needs_merge_name_review(segment):
        return False
    coverage = segment.get("doc_coverage")
    if not isinstance(coverage, dict):
        return False
    try:
        hit_docs = int(coverage.get("hit_docs") or 0)
        total_docs = int(coverage.get("total_docs") or 0)
    except (TypeError, ValueError):
        return False
    return total_docs > 0 and hit_docs >= total_docs


async def _analysis_is_complete(
    db: AsyncSession,
    route: NormalizedRouteVersion,
    segments: List[Dict[str, object]],
) -> bool:
    if not segments:
        return False
    rows = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview)
            .where(NormalizedRouteSegmentRuleReview.route_version_id == route.id)
            .order_by(
                NormalizedRouteSegmentRuleReview.updated_at.desc(),
                NormalizedRouteSegmentRuleReview.id.desc(),
            )
        )
    ).scalars().all()
    reviews: Dict[str, NormalizedRouteSegmentRuleReview] = {}
    for row in rows:
        reviews.setdefault(str(row.segment_id or ""), row)
    return all(
        _segment_has_rule_decision(segment, reviews.get(str(segment.get("id") or "")))
        or _segment_is_default_complete(segment)
        for segment in segments
    )


async def _template_mappings_are_complete(
    db: AsyncSession,
    template: ProjectGroupTemplate,
    segments: List[Dict[str, object]],
) -> bool:
    tree = _load_list(template.tree_json)
    feature_groups: Dict[Tuple[str, ...], Set[str]] = {}

    def visit(nodes: List[object]) -> None:
        for raw in nodes:
            if not isinstance(raw, dict):
                continue
            children = raw.get("children")
            children = children if isinstance(children, list) else []
            features = raw.get("feature_selections")
            features = {str(item) for item in features if str(item)} if isinstance(features, list) else set()
            if not children and features:
                feature_groups[_path_key(raw.get("path"))] = features
            visit(children)

    visit(tree)
    if not feature_groups:
        return False

    source_operation_ids = {
        int(value)
        for segment in segments
        for value in segment.get("source_operation_ids", [])
        if str(value).isdigit() and int(value) > 0
    }
    current_process_ids = {
        str(segment.get("export_process_id") or segment.get("id") or "").strip()
        for segment in segments
        if str(segment.get("export_process_id") or segment.get("id") or "").strip()
    }
    current_process_sources = {
        str(segment.get("export_process_id") or segment.get("id") or "").strip(): {
            int(value)
            for value in segment.get("source_operation_ids", [])
            if str(value).isdigit() and int(value) > 0
        }
        for segment in segments
        if str(segment.get("export_process_id") or segment.get("id") or "").strip()
    }
    mapped_paths: Set[Tuple[str, ...]] = set()

    for mapping in _load_list(template.mappings_json):
        if not isinstance(mapping, dict):
            continue
        path = _path_key(mapping.get("template_group_path"))
        allowed_features = feature_groups.get(path)
        features = mapping.get("feature_selections")
        features = {str(item) for item in features} if isinstance(features, list) else set()
        try:
            operation_id = int(mapping.get("source_operation_id") or 0)
        except (TypeError, ValueError):
            continue
        if operation_id in source_operation_ids and allowed_features and features.intersection(allowed_features):
            mapped_paths.add(path)

    source_steps = {}
    step_mappings = _load_list(template.step_mappings_json)
    if step_mappings:
        details = (
            await db.execute(
                select(DocumentOperationDetail)
                .where(DocumentOperationDetail.project_id == template.project_id)
                .order_by(
                    DocumentOperationDetail.document_id.asc(),
                    DocumentOperationDetail.operation_seq.asc(),
                    DocumentOperationDetail.page_no.asc(),
                    DocumentOperationDetail.id.asc(),
                )
            )
        ).scalars().all()
        source_processes = build_superset_process_tree(operations=[], detail_rows=details, sample_count=0)
        source_steps = {
            int(source["id"]): list(source.get("step_items") or []) + list(source.get("attached_step_items") or [])
            for source in source_processes
        }
    mapping_output = _load_list(template.mapping_output_json)
    output_steps = {
        (str(process.get("process_id") or ""), str(step.get("step_id") or "")): step
        for process in mapping_output
        if isinstance(process, dict) and process.get("process_type") != "辅助工序"
        for step in (process.get("steps") or [])
        if isinstance(step, dict)
    }

    for mapping in step_mappings:
        if not isinstance(mapping, dict) or str(mapping.get("status") or "") != "confirmed":
            continue
        path = _path_key(mapping.get("template_group_path"))
        allowed_features = feature_groups.get(path)
        features = mapping.get("candidate_features")
        features = {str(item) for item in features if str(item)} if isinstance(features, list) else set()
        try:
            operation_id = int(mapping.get("source_operation_id") or 0)
        except (TypeError, ValueError):
            continue
        source_operation_steps = source_steps.get(operation_id, [])
        try:
            step_order = int(mapping.get("source_step_order") or 0)
        except (TypeError, ValueError):
            continue
        source_step_name = str(mapping.get("source_step_name") or "").strip()
        if (
            step_order < 1
            or step_order > len(source_operation_steps)
            or unicodedata.normalize("NFC", str(source_operation_steps[step_order - 1])).strip()
            != unicodedata.normalize("NFC", source_step_name)
        ):
            continue
        targets = mapping.get("final_targets")
        target_is_current = operation_id in source_operation_ids
        if isinstance(targets, list) and targets:
            target_is_current = False
            for target in targets:
                if not isinstance(target, dict):
                    continue
                process_id = str(target.get("process_id") or "").strip()
                step_id = str(target.get("step_id") or "").strip()
                step = output_steps.get((process_id, step_id))
                if (
                    process_id not in current_process_ids
                    or operation_id not in current_process_sources.get(process_id, set())
                    or step is None
                    or not features.issubset(
                        set((step.get("candidates") or {}).get("/".join(path), []))
                    )
                ):
                    continue
                target_is_current = True
                break
        if (
            operation_id in source_operation_ids
            and allowed_features
            and features
            and features.issubset(allowed_features)
            and target_is_current
        ):
            mapped_paths.add(path)

    return bool(mapped_paths) and set(feature_groups).issubset(mapped_paths)


async def get_workflow_progress(db: AsyncSession, project_id: int) -> Optional[Dict[str, int]]:
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        return None

    completed_steps = 0
    documents = (
        await db.execute(select(Document.id).where(Document.project_id == project_id).limit(1))
    ).first()
    if documents:
        completed_steps = 1

    route = (
        await db.execute(
            select(NormalizedRouteVersion)
            .where(NormalizedRouteVersion.project_id == project_id)
            .order_by(NormalizedRouteVersion.version.desc(), NormalizedRouteVersion.id.desc())
        )
    ).scalars().first()
    segments = _route_items(route) if route else []
    if segments:
        completed_steps = 2
        if await _analysis_is_complete(db, route, segments):
            completed_steps = 3
            template = (
                await db.execute(
                    select(ProjectGroupTemplate).where(ProjectGroupTemplate.project_id == project_id)
                )
            ).scalar_one_or_none()
            if template is not None and await _template_mappings_are_complete(db, template, segments):
                completed_steps = 4
                published_package = (
                    await db.execute(
                        select(FinalizedRulePackage.id)
                        .where(
                            FinalizedRulePackage.project_id == project_id,
                            FinalizedRulePackage.route_version_id == route.id,
                            FinalizedRulePackage.status == "published",
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if published_package is not None:
                    completed_steps = 5

    return {
        "project_id": project_id,
        "completed_steps": completed_steps,
        "max_available_step": min(6, completed_steps + 1),
        "workflow_revision": int(project.workflow_revision or 0),
    }
