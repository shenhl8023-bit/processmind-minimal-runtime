"""Invalidate saved downstream object bindings when their confirmed source changes."""
from typing import Any, Dict, List
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.models import NormalizedRouteSegmentRuleReview


def _trail(raw: str) -> Dict[str, str]:
    try:
        return {item['nodeId']: item['value'] for item in json.loads(raw or '[]') if isinstance(item, dict)}
    except (ValueError, TypeError, KeyError):
        return {}


def _reuse(answers: Dict[str, str]) -> Dict[str, Any]:
    try:
        value = json.loads(answers.get('__object_reuse') or '{}')
        return value if isinstance(value, dict) and value.get('schema_version') == 1 else {}
    except (ValueError, TypeError):
        return {}


def object_signature(raw: str, decision: str):
    answers = _trail(raw)
    if (decision != 'accepted' or answers.get('guided_mode') != 'condition'
            or answers.get('guided_basis') not in ('feature', 'precision', 'roughness')):
        return None
    reuse = _reuse(answers)
    return (answers.get('guided_features', ''), answers.get('guided_direction', ''),
            json.dumps(reuse, ensure_ascii=False, sort_keys=True))


async def validate_object_reuse(db: AsyncSession, route_id: int, segment_id: str,
                              route_items: List[Any], trail: List[Dict[str, str]], draft: Any) -> None:
    """Check inherited facts under the same workflow write lock as their save.

    Local answers can guide the next question before a source rule is complete,
    but an accepted dependent needs a persisted, still-current source. Explicit
    object answers carry no reuse binding and remain independently editable.
    """
    answers = _trail(json.dumps(trail, ensure_ascii=False))
    if '__object_reuse' not in answers:
        return

    def conflict(message):
        raise HTTPException(409, {'code': 'stale_object_reuse', 'message': message})

    order = {str(item.get('id')): index for index, item in enumerate(route_items) if isinstance(item, dict)}
    rows = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
        NormalizedRouteSegmentRuleReview.route_version_id == route_id,
    ).execution_options(populate_existing=True))).scalars().all()
    saved = {row.segment_id: row for row in rows}
    # Repeated references form a DAG, not a tree. Cache only inside this locked
    # save so each source is checked once without retaining stale cross-request facts.
    resolved_objects = {}

    def resolve(key, values):
        if key in resolved_objects:
            return resolved_objects[key]
        if (key not in order or values.get('guided_mode') != 'condition'
                or values.get('guided_basis') not in ('feature', 'precision', 'roughness')):
            conflict('前序加工对象已变化，请重新确认特征和方位。')
        binding = _reuse(values)
        if '__object_reuse' in values and (not binding or not any(binding.get(p) for p in ('features', 'direction'))):
            conflict('加工对象引用无效，请重新确认特征和方位。')
        features = [value for value in values.get('guided_features', '').split('|') if value]
        direction = values.get('guided_direction', '')
        if not features and binding.get('features'):
            features = binding['features'].get('values') if isinstance(binding['features'], dict) else None
        if not direction and binding.get('direction'):
            direction = binding['direction'].get('value') if isinstance(binding['direction'], dict) else None
        if (not isinstance(features, list) or not features
                or any(not isinstance(value, str) or not value for value in features)):
            conflict('引用的加工特征不完整，请重新确认。')
        for part in ('features', 'direction'):
            if part not in binding:
                continue
            item = binding[part]
            if not isinstance(item, dict):
                conflict('加工对象引用无效，请重新确认。')
            inherited = item.get('values' if part == 'features' else 'value')
            expected = features if part == 'features' else direction
            if inherited != expected:
                conflict('当前加工对象与引用内容不一致，请重新确认。')
            sources = item.get('source_segment_ids')
            if (not isinstance(sources, list) or not sources
                    or any(not isinstance(source, str) for source in sources)):
                conflict('加工对象引用缺少有效来源，请重新确认。')
            for source in sources:
                if source not in order or order[source] >= order[key]:
                    conflict('加工对象只能引用当前路线中已确认的前序工序。')
                row = saved.get(source)
                if row is None or row.decision != 'accepted':
                    conflict('请先完成并保存前序加工对象，再采纳当前工序。')
                source_features, source_direction = resolve(source, _trail(row.question_trail_json))
                if not set(features).issubset(source_features) or (part == 'direction' and direction != source_direction):
                    conflict('前序加工对象已变化，请重新确认当前工序的特征和方位。')
        resolved_objects[key] = features, direction
        return features, direction

    features, direction = resolve(segment_id, answers)
    configuration = draft.candidate.configuration if draft and draft.candidate else None
    if configuration is None or configuration.occurrence != 'conditional' or configuration.when is None:
        conflict('引用对象与当前规则不一致，请重新确认。')
    condition = configuration.when.model_dump(exclude_none=True, by_alias=True)
    clauses = condition.get('all', [condition])

    def leaf_matches(node, suffix, op, expected):
        return (isinstance(node, dict) and str(node.get('field', '')).endswith('.' + suffix)
                and node.get('op') == op and node.get('value') == expected)

    if not any(leaf_matches(node, 'features', 'contains_any', features) for node in clauses):
        conflict('规则中的加工特征与引用对象不一致，请重新确认。')
    if direction == '所有方位':
        matches = any(isinstance(node, dict) and len(node.get('any', [])) == 2
                      and all(any(leaf_matches(leaf, 'direction', 'eq', side) for leaf in node['any'])
                              for side in ('A侧', 'B侧')) for node in clauses)
    else:
        matches = bool(direction) and any(leaf_matches(node, 'direction', 'eq', direction) for node in clauses)
    if not matches:
        conflict('规则中的加工方位与引用对象不一致，请重新确认。')


async def invalidate_object_dependents(db: AsyncSession, route_id: int, source_id: str) -> List[str]:
    rows = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
        NormalizedRouteSegmentRuleReview.route_version_id == route_id,
    ).order_by(NormalizedRouteSegmentRuleReview.id))).scalars().all()
    changed = {source_id}
    invalidated = []
    while True:
        found = False
        for row in rows:
            if row.segment_id in changed:
                continue
            binding = _reuse(_trail(row.question_trail_json))
            sources = set()
            for part in ('features', 'direction'):
                value = binding.get(part)
                if isinstance(value, dict):
                    sources.update(item for item in value.get('source_segment_ids', []) if isinstance(item, str))
            if not sources.intersection(changed):
                continue
            changed.add(row.segment_id)
            invalidated.append(row.segment_id)
            found = True
            row.decision = 'pending'
            row.condition_source_text = ''
            row.condition_source_hash = ''
            row.condition_status = 'draft'
            row.condition_candidate_json = None
            row.condition_confirmed_json = None
            row.condition_issues_json = '[]'
            row.condition_confirmed_by = None
            row.condition_confirmed_at = None
            if row.analysis_draft_json:
                draft = json.loads(row.analysis_draft_json)
                draft['status'] = 'incomplete'
                draft['missing'] = ['前序加工对象已变化，请重新采纳推荐或确认当前对象。']
                row.analysis_draft_json = json.dumps(draft, ensure_ascii=False)
        if not found:
            return invalidated
