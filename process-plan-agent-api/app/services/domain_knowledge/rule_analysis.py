"""Domain proposals use project sample facts; neither source substitutes for the other."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.models import KnowledgeRuleSuggestion, NormalizedRouteVersion, DocumentOperationDetail
from .binding import project_binding
from .packages import package_ref, canonical_json
from .retrieval import applicable_resources, evidence


def current_context(project, package):
    return {**package_ref(package), 'part_family': project.domain_part_family or '',
            'material': project.domain_material or '', 'stage': project.domain_stage or ''} if package else None


async def route_context(db, project_id, route_id, segment_id):
    project, package = await project_binding(db, project_id)
    route = await db.get(NormalizedRouteVersion, route_id)
    if not route or route.project_id != project_id: raise HTTPException(404, '路线版本不存在')
    segment = next((item for item in json.loads(route.route_json or '[]') if str(item.get('id')) == segment_id), None)
    if not segment: raise HTTPException(404, '当前工序不属于该保存路线版本')
    if json.loads(route.knowledge_package_json or 'null') != current_context(project, package):
        raise HTTPException(409, '领域知识选择已更改，请重新核对并保存第二步路线')
    ids = [int(item['detail_id']) for item in segment.get('matched_detail_rows', []) if item.get('detail_id')]
    details = (await db.scalars(select(DocumentOperationDetail).where(
        DocumentOperationDetail.project_id == project_id, DocumentOperationDetail.id.in_(ids)))).all() if ids else []
    return project, package, route, segment, details


def build_domain_rule_candidates(package_version, route_segment, sample_evidence, *, part_family=None, material=None, stage=None):
    if not sample_evidence: return []
    resources = applicable_resources(package_version, part_family, material, stage)
    names = {str(route_segment.get('normalized_step_name') or '').casefold(),
             *(str(name).casefold() for name in route_segment.get('source_nodes', []))}
    concepts = {item.id for kind, item in resources if kind == 'concepts' and names.intersection(
        {item.name.casefold(), *(alias.casefold() for alias in item.aliases)})}
    factors = [item.field.model_dump() for kind, item in resources if kind == 'factors']
    candidates = []
    for kind, rule in resources:
        if kind != 'rule_candidates' or rule.target_concept_id not in concepts: continue
        candidates.append({'resource_id': rule.id, 'title': rule.name,
            'suggestion_text': f'{rule.explanation}\n条件结构：{canonical_json(rule.condition.model_dump(by_alias=True, exclude_none=True))}\n结论：{rule.conclusion} 当前工序。',
            'candidate': {'kind': 'condition', 'when': rule.condition.model_dump(by_alias=True, exclude_none=True),
                'then': {'include_process_ids': [route_segment.get('export_process_id') or route_segment['id']] if rule.conclusion == 'include' else [],
                         'exclude_process_ids': [route_segment.get('export_process_id') or route_segment['id']] if rule.conclusion == 'exclude' else [], 'reason': rule.explanation},
                'confidence': rule.confidence, 'uncertainty': rule.uncertainty, 'factors': factors},
            'domain_evidence_refs': [evidence(package_version, kind, rule)],
            'sample_detail_ids': [item.id for item in sample_evidence]})
    return candidates


async def generate_domain_suggestions(db, project_id, route_version_id, segment_id):
    project, package, route, segment, details = await route_context(db, project_id, route_version_id, segment_id)
    from app.services.knowledge.suggestions import serialize_suggestion
    if not package: return {'suggestions': [], 'issues': ['项目未选择领域知识包'], 'knowledge_package': None}
    candidates = build_domain_rule_candidates(package, segment, details, part_family=project.domain_part_family,
                                                material=project.domain_material, stage=project.domain_stage)
    result = []
    for candidate in candidates:
        ref = canonical_json(package_ref(package))
        domain_refs = canonical_json(candidate['domain_evidence_refs'])
        existing = await db.scalar(select(KnowledgeRuleSuggestion).where(
            KnowledgeRuleSuggestion.project_id == project_id, KnowledgeRuleSuggestion.route_version_id == route_version_id,
            KnowledgeRuleSuggestion.segment_id == segment_id, KnowledgeRuleSuggestion.domain_package_ref_json == ref,
            KnowledgeRuleSuggestion.domain_evidence_refs_json == domain_refs).order_by(KnowledgeRuleSuggestion.id.desc()))
        if existing: result.append(serialize_suggestion(existing)); continue
        row = KnowledgeRuleSuggestion(project_id=project_id, route_version_id=route_version_id, segment_id=segment_id,
            title=candidate['title'], suggestion_text=candidate['suggestion_text'], candidate_json=canonical_json(candidate['candidate']),
            evidence_ids_json='[]', sample_detail_ids_json=canonical_json(candidate['sample_detail_ids']),
            domain_package_ref_json=ref, domain_evidence_refs_json=domain_refs, status='draft', created_by='领域知识包', updated_by='领域知识包')
        db.add(row); await db.flush()
        result.append(serialize_suggestion(row))
    await db.commit()
    domain = [evidence(package, kind, item) for kind, item in applicable_resources(package, project.domain_part_family,
                 project.domain_material, project.domain_stage) if kind == 'factors']
    return {'suggestions': result, 'knowledge_package': package_ref(package), 'factor_evidence': domain,
            'issues': [] if candidates else ['未找到适用的规则候选，或当前路线工序缺少可追溯样本明细']}


async def validate_domain_suggestion(db, row):
    project, package, route, segment, details = await route_context(db, row.project_id, row.route_version_id, row.segment_id)
    if not package or json.loads(row.domain_package_ref_json or 'null') != package_ref(package):
        raise HTTPException(409, '领域建议所用知识包版本已过期')
    ids = json.loads(row.sample_detail_ids_json or '[]')
    if not ids or not set(ids).issubset({item.id for item in details}):
        raise HTTPException(422, '领域建议缺少当前工序的样本事实依据')
    eligible = {item.id: evidence(package, kind, item) for kind, item in applicable_resources(package,
        project.domain_part_family, project.domain_material, project.domain_stage) if kind == 'rule_candidates'}
    refs = json.loads(row.domain_evidence_refs_json or '[]')
    if not refs or any(eligible.get(ref.get('resource_id')) != ref for ref in refs):
        raise HTTPException(422, '领域依据未审核、范围不匹配或引用已更改')


async def rule_package_route_ref(db, project_id, route_id, *, require_exists=True):
    if route_id is None: return None
    route = await db.get(NormalizedRouteVersion, route_id)
    if not route:
        if require_exists: raise HTTPException(422, '规则包路线版本不属于当前项目')
        return None
    if route.project_id != project_id: raise HTTPException(422, '规则包路线版本不属于当前项目')
    context = json.loads(route.knowledge_package_json or 'null')
    return {key: context[key] for key in ('package_id', 'version', 'content_hash')} if context else None


async def validate_rule_package_provenance(db, package):
    from .packages import get_package_version
    expected = await rule_package_route_ref(db, package.manifest.project_id, package.manifest.route_version_id)
    actual = package.manifest.domain_knowledge_package
    if (actual.model_dump() if actual else None) != expected:
        raise HTTPException(409, '规则包的领域知识版本与路线快照不一致，请重新编译')
    if expected:
        row = await get_package_version(db, expected['package_id'], expected['version'])
        if row.status != 'active' or row.content_hash != expected['content_hash']:
            raise HTTPException(409, '规则包使用的领域知识版本未启用或哈希不一致')
