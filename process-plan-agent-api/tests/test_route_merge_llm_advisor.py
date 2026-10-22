import asyncio
import copy
import json

import pytest

from app.services.route_merge import llm_advisor


def candidates():
    return [{
        'id': 'g1', 'review_status': 'pending', 'source_type': 'system_recommendation',
        'normalized_step_name': '车削', 'recommended_target_name': '车削',
        'suggestion_type': 'direct_merge', 'recommendation_reason': '规则理由',
        'source_operation_ids': [1, 2],
        '_source_items': [
            {'id': 1, 'name': '车', 'sequence': 460, 'phase': 'rough', 'matched_detail_rows': []},
            {'id': 2, 'name': '车削', 'sequence': 460, 'phase': 'finish', 'matched_detail_rows': []},
        ],
    }]


def decision(**changes):
    result = {'candidate_id': 'g1', 'action': 'direct_merge', 'target_name': '车加工',
              'reason': '两项证据支持同类加工', 'evidence_ids': ['op:1', 'op:2'], 'confidence': 0.85}
    result.update(changes)
    return result


def run_advice(monkeypatch, response):
    async def fake_call(*args, **kwargs):
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(llm_advisor, 'call_llm', fake_call)
    original = candidates()
    before = copy.deepcopy(original)
    result = asyncio.run(llm_advisor.advise_merge_groups(original))
    assert original == before
    return result


def test_valid_advice_decorates_only_advice_not_route_or_review(monkeypatch):
    groups, status = run_advice(monkeypatch, json.dumps({'decisions': [decision()]}))
    assert status == 'model'
    assert groups[0]['advice_source'] == 'model'
    assert groups[0]['advice_action'] == 'direct_merge'
    assert groups[0]['recommended_target_name'] == '车加工'
    assert groups[0]['normalized_step_name'] == '车削'
    assert groups[0]['review_status'] == 'pending'
    assert groups[0]['advice_evidence_ids'] == ['op:1', 'op:2']


@pytest.mark.parametrize('response', [
    '', 'not json', '[]', '{"decisions": []}',
    json.dumps({'decisions': [decision(candidate_id='unknown')]}),
    json.dumps({'decisions': [decision(), decision()]}),
    json.dumps({'decisions': [decision(evidence_ids=['op:999'])]}),
    json.dumps({'decisions': [decision(evidence_ids=[])]}),
    json.dumps({'decisions': [decision(action='approve')]}),
    json.dumps({'decisions': [decision(target_name='')]}),
    json.dumps({'decisions': [decision(confidence=2)]}),
    TimeoutError('timeout'), RuntimeError('provider down'),
])
def test_invalid_or_unavailable_model_preserves_local_advice(monkeypatch, response):
    groups, status = run_advice(monkeypatch, response)
    assert status == 'fallback'
    assert groups[0]['advice_source'] == 'local_rules'
    assert groups[0]['recommendation_reason'] == '规则理由'
    assert groups[0]['recommended_target_name'] == '车削'


def test_reviewed_and_manually_renamed_groups_are_never_sent(monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail('reviewed groups must not be sent')
    monkeypatch.setattr(llm_advisor, 'call_llm', unexpected)
    groups = copy.deepcopy(candidates() * 2)
    groups[0]['review_status'] = 'merged'
    groups[1]['source_type'] = 'manual_adjusted'
    output, status = asyncio.run(llm_advisor.advise_merge_groups(groups))
    assert output == groups
    assert status == 'not_needed'


def test_request_preserves_distinct_operation_ids_sequence_and_phase(monkeypatch):
    async def capture(system_prompt, user_prompt, **kwargs):
        sent = json.loads(user_prompt)['candidates'][0]
        assert [item['id'] for item in sent['sources']] == [1, 2]
        assert [item['sequence'] for item in sent['sources']] == [460, 460]
        assert [item['phase'] for item in sent['sources']] == ['rough', 'finish']
        assert kwargs['max_retries'] == 0
        assert kwargs['timeout_seconds'] <= 30
        return json.dumps({'decisions': [decision(action='keep_separate') ]})
    monkeypatch.setattr(llm_advisor, 'call_llm', capture)
    groups, _ = asyncio.run(llm_advisor.advise_merge_groups(candidates()))
    assert groups[0]['advice_action'] == 'keep_separate'
    assert groups[0]['suggestion_type'] == 'direct_merge'
    assert groups[0]['review_status'] == 'pending'


def test_candidate_prompt_contract_and_cache_digest():
    from app.services.llm_service import get_prompt_template
    prompt = get_prompt_template(llm_advisor.PROMPT_KEY)
    for token in ['direct_merge', 'absorb_into_parent', 'keep_separate', 'candidate_id',
                  'evidence_ids', 'JSON', '阶段', '独立', '工序号', 'confidence']:
        assert token in prompt
    assert len(llm_advisor.advice_prompt_digest()) == 64


@pytest.mark.parametrize('changes', [
    {'evidence_ids': ['op:1']}, {'evidence_ids': ['op:1', 'op:1', 'op:2']},
    {'action': 'absorb_into_parent'},
])
def test_advice_requires_source_coverage_unique_refs_and_real_parent(monkeypatch, changes):
    groups, status = run_advice(monkeypatch, json.dumps({'decisions': [decision(**changes)]}))
    assert status == 'fallback'


def test_accept_applies_model_target_only_after_review_and_manual_name_wins():
    from app.services.route_merge.review import apply_merge_suggestion_review
    from app.services.route_merge.workspace import build_merge_suggestions_from_groups
    groups = candidates()
    groups[0].update(advice_source='model', advice_action='direct_merge', recommended_target_name='建议名称')
    snapshot = {'merge_groups': groups, 'merge_suggestions': build_merge_suggestions_from_groups(groups)}
    apply_merge_suggestion_review(snapshot, 'suggestion-g1', 'accept', '', {}, [])
    assert snapshot['merge_groups'][0]['normalized_step_name'] == '建议名称'
    apply_merge_suggestion_review(snapshot, 'suggestion-g1', 'rename', '人工名称', {}, [])
    apply_merge_suggestion_review(snapshot, 'suggestion-g1', 'accept', '', {}, [])
    assert snapshot['merge_groups'][0]['normalized_step_name'] == '人工名称'


def test_suggestion_response_preserves_advice_provenance():
    from app.schemas.schemas import MergeSuggestionOut
    from app.services.route_merge.workspace import build_merge_suggestions_from_groups
    groups = candidates()
    groups[0].update(advice_source='model', advice_action='keep_separate', advice_confidence=0.72,
                     advice_evidence_ids=['op:1', 'op:2'])
    output = MergeSuggestionOut.model_validate(build_merge_suggestions_from_groups(groups)[0]).model_dump()
    assert output['advice_source'] == 'model'
    assert output['advice_action'] == 'keep_separate'
    assert output['advice_confidence'] == 0.72
    assert output['advice_evidence_ids'] == ['op:1', 'op:2']
