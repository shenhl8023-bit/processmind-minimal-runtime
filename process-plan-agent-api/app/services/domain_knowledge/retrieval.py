"""Scoped exact concept/alias lookup; no embedding service required."""
from .packages import package_draft, package_ref
from .contracts import RESOURCE_TYPES


def scope_matches(scope, part_family=None, material=None, stage=None):
    return all(not allowed or actual in allowed for allowed, actual in (
        (scope.part_families, part_family), (scope.materials, material), (scope.stages, stage)))


def applicable_resources(package_version, part_family=None, material=None, stage=None):
    if not package_version or package_version.status != 'active': return []
    draft = package_draft(package_version)
    if draft.part_family_scope and part_family not in draft.part_family_scope: return []
    return [(kind, item) for kind in RESOURCE_TYPES for item in getattr(draft, kind)
            if item.review_status == 'accepted' and scope_matches(item.applicability, part_family, material, stage)]


def evidence(package_version, kind, resource):
    draft = package_draft(package_version)
    sources = {item.id: item for item in draft.sources}
    return {'resource_id': resource.id, 'resource_type': kind, 'name': resource.name,
            'package': package_ref(package_version), 'applicability': resource.applicability.model_dump(),
            'source_refs': [{**ref.model_dump(), 'filename': sources[ref.source_id].filename,
                             'content_hash': sources[ref.source_id].content_hash,
                             'excerpt': '\n'.join(sources[ref.source_id].content.splitlines()[ref.start_line-1:ref.end_line])}
                            for ref in resource.source_refs]}


def retrieve_route_knowledge(package_version, operation_names, part_family=None, material=None, stage=None):
    resources = applicable_resources(package_version, part_family, material, stage)
    names = {str(name).strip().casefold() for name in operation_names}
    matched = {item.id for kind, item in resources if kind == 'concepts' and
               names.intersection({item.name.casefold(), *(name.casefold() for name in item.aliases)})}
    result = []
    for kind, item in resources:
        relevant = kind == 'concepts' and item.id in matched
        if kind == 'relations': relevant = item.source_concept_id in matched and item.target_concept_id in matched
        if kind == 'route_templates': relevant = bool(matched.intersection(item.concept_ids))
        if relevant: result.append(evidence(package_version, kind, item))
    return result


def enrich_merge_groups(groups, raw_operations, detail_rows, package_version, part_family=None, material=None, stage=None):
    from app.services.route_merge.group_builder import _build_group_payload_from_members, build_source_group_from_operation
    resources = applicable_resources(package_version, part_family, material, stage)
    concepts = {item.id: item for kind, item in resources if kind == 'concepts'}
    def matches(group, concept):
        names = {concept.name.casefold(), *(name.casefold() for name in concept.aliases)}
        return bool(names.intersection(str(name).strip().casefold() for name in group.get('source_nodes', [])))
    for kind, relation in resources:
        if kind != 'relations' or relation.condition is not None: continue
        left, right = concepts.get(relation.source_concept_id), concepts.get(relation.target_concept_id)
        if not left or not right: continue
        members = [group for group in groups if matches(group, left) or matches(group, right)]
        if not any(matches(g, left) for g in members) or not any(matches(g, right) for g in members): continue
        if relation.relation_type == 'keep_separate':
            ids = {id(g) for g in members}
            replacement = []
            op_map = {op['id']: op for op in raw_operations}
            for group in members:
                for op_id in group.get('source_operation_ids', []):
                    if op_id in op_map: replacement.append(build_source_group_from_operation(op_map[op_id], detail_rows))
            groups = [g for g in groups if id(g) not in ids] + replacement
        elif relation.relation_type in {'synonym', 'absorb_into'} and len(members) >= 2:
            merged = _build_group_payload_from_members(
                group_id=f'domain-{relation.id}', group_key=f'domain:{relation.id}', normalized_step_name=right.name,
                members=members, detail_rows=detail_rows, review_status='pending',
                suggestion_type='direct_merge' if relation.relation_type == 'synonym' else 'absorb_into_parent',
                recommendation_label='领域知识归并建议', recommendation_reason=relation.name,
                manual_review_required=True, reason_codes=['domain_knowledge'],
            )
            ids = {id(g) for g in members}
            groups = [g for g in groups if id(g) not in ids] + [merged]
    for group in groups:
        group['domain_evidence'] = retrieve_route_knowledge(package_version, group.get('source_nodes', []), part_family, material, stage)
    return groups
