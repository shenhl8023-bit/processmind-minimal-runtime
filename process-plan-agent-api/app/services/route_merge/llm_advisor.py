"""Bounded, advisory-only model review of locally generated merge candidates."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math

from app.services.llm_service import call_llm, get_prompt_template, parse_json_from_llm

logger = logging.getLogger(__name__)
PROMPT_KEY = 'route_merge_candidate_advice'
ACTIONS = {
    'direct_merge': '直接归并',
    'absorb_into_parent': '并入上位工序',
    'keep_separate': '不建议归并',
}
BATCH_SIZE = 12
MAX_PAYLOAD_CHARS = 60000
ADVICE_TIMEOUT_SECONDS = 25


def advice_prompt_digest() -> str:
    return hashlib.sha256(get_prompt_template(PROMPT_KEY).encode('utf-8')).hexdigest()


def _candidate_payload(group: dict) -> tuple[dict, set[str]]:
    sources = []
    evidence_ids = set()
    for item in group.get('_source_items') or []:
        evidence_id = f"op:{item['id']}"
        evidence_ids.add(evidence_id)
        sources.append({
            'evidence_id': evidence_id,
            'id': item['id'], 'name': item.get('name', ''),
            'coverage_label': item.get('coverage_label', ''),
            'sequence': item.get('sequence'), 'phase': item.get('phase', ''),
            'step_family': item.get('step_family', ''),
            'details': [{key: row.get(key) for key in (
                'detail_id', 'document_id', 'pdf_name', 'operation_seq',
                'operation_name', 'operation_content', 'page_no',
                'equipment_types', 'equipment_models',
            )} for row in item.get('matched_detail_rows') or []],
        })
    return {
        'candidate_id': group['id'], 'rule_action': group.get('suggestion_type'),
        'rule_target_name': group.get('recommended_target_name'),
        'parent_segment': group.get('parent_segment', ''), 'sources': sources,
    }, evidence_ids


def _validated_decisions(response: str, evidence_by_candidate: dict[str, set[str]]) -> dict[str, dict]:
    parsed = parse_json_from_llm(response)
    if not isinstance(parsed, dict) or not isinstance(parsed.get('decisions'), list):
        raise ValueError('missing decisions')
    decisions = {}
    for item in parsed['decisions']:
        if not isinstance(item, dict):
            raise ValueError('invalid decision')
        candidate_id = item.get('candidate_id')
        if not isinstance(candidate_id, str) or candidate_id not in evidence_by_candidate or candidate_id in decisions:
            raise ValueError('unknown or duplicate candidate')
        if item.get('action') not in ACTIONS:
            raise ValueError('invalid action')
        for field, limit in [('target_name', 120), ('reason', 2000)]:
            if not isinstance(item.get(field), str) or not item[field].strip() or len(item[field]) > limit:
                raise ValueError(f'invalid {field}')
        refs = item.get('evidence_ids')
        if (not isinstance(refs, list) or not refs or
                any(not isinstance(ref, str) or ref not in evidence_by_candidate[candidate_id] for ref in refs)):
            raise ValueError('unknown or missing evidence')
        if len(refs) != len(set(refs)) or set(refs) != evidence_by_candidate[candidate_id]:
            raise ValueError('duplicate refs or incomplete source coverage')
        confidence = item.get('confidence')
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('invalid confidence')
        decisions[candidate_id] = item
    if set(decisions) != set(evidence_by_candidate):
        raise ValueError('incomplete decisions')
    return decisions


async def advise_merge_groups(groups: list[dict[str, object]]) -> tuple[list[dict[str, object]], str]:
    result = copy.deepcopy(groups)
    pending = [group for group in result
               if group.get('review_status') == 'pending'
               and group.get('source_type') != 'manual_adjusted'
               and len(group.get('source_operation_ids') or []) > 1]
    if not pending:
        return result, 'not_needed'
    for group in pending:
        group['advice_source'] = 'local_rules'
    all_model = True

    async def enrich():
        nonlocal all_model
        for offset in range(0, len(pending), BATCH_SIZE):
            batch = pending[offset:offset + BATCH_SIZE]
            try:
                candidates, evidence = [], {}
                for group in batch:
                    payload, ids = _candidate_payload(group)
                    candidates.append(payload)
                    evidence[str(group['id'])] = ids
                user_prompt = json.dumps({'candidates': candidates}, ensure_ascii=False)
                if len(user_prompt) > MAX_PAYLOAD_CHARS:
                    raise ValueError('candidate evidence exceeds request limit')
                response = await call_llm(
                    get_prompt_template(PROMPT_KEY), user_prompt, temperature=0.1,
                    timeout_seconds=ADVICE_TIMEOUT_SECONDS, max_retries=0,
                )
                decisions = _validated_decisions(response, evidence)
                if any(decisions[str(group['id'])]['action'] == 'absorb_into_parent' and not group.get('parent_segment') for group in batch):
                    raise ValueError('missing parent evidence')
                for group in batch:
                    item = decisions[str(group['id'])]
                    group.update({
                        'advice_source': 'model', 'advice_action': item['action'],
                        'advice_confidence': item['confidence'],
                        'advice_evidence_ids': list(dict.fromkeys(item['evidence_ids'])),
                        'recommendation_label': ACTIONS[item['action']],
                        'recommendation_reason': item['reason'].strip(),
                        'recommended_target_name': item['target_name'].strip(),
                    })
            except Exception as exc:
                all_model = False
                logger.info('Route merge advice fell back to local rules (%s)', type(exc).__name__)

    try:
        await asyncio.wait_for(enrich(), timeout=ADVICE_TIMEOUT_SECONDS)
    except TimeoutError:
        all_model = False
    return result, 'model' if all_model else 'fallback'
