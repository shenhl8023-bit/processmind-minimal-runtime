"""Semantic validation in addition to the structural Pydantic contract."""
import hashlib
import re
from .contracts import DomainKnowledgePackageDraft, RESOURCE_TYPES


def source_blocks(content: str) -> list[dict]:
    path, blocks, start, buffer = [], [], None, []
    def flush():
        if buffer and start is not None:
            blocks.append({'heading_path': list(path), 'start_line': start,
                           'end_line': start + len(buffer) - 1, 'text': '\n'.join(buffer)})
    for line_no, line in enumerate(content.splitlines(), 1):
        heading = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
        if heading:
            flush()
            buffer, start = [], None
            level = len(heading.group(1))
            path = path[:level - 1] + [heading.group(2)]
        elif line.strip() or buffer:
            if start is None: start = line_no
            buffer.append(line)
    flush()
    return blocks


def validate_package(draft: DomainKnowledgePackageDraft, *, activation: bool = False) -> list[str]:
    issues, ids = [], set()
    sources = {source.id: source for source in draft.sources}
    if len(sources) != len(draft.sources): issues.append('来源 ID 重复')
    for source in draft.sources:
        if hashlib.sha256(source.content.encode('utf-8')).hexdigest() != source.content_hash:
            issues.append(f'{source.filename}: 来源哈希不匹配')
    concepts = {item.id for item in draft.concepts if item.review_status != 'rejected'}
    accepted = 0
    for kind in RESOURCE_TYPES:
        for item in getattr(draft, kind):
            if item.id in ids: issues.append(f'{item.id}: 条目 ID 重复')
            ids.add(item.id)
            if item.review_status == 'rejected': continue
            if activation and item.review_status != 'accepted': issues.append(f'{item.id}: 尚未审核')
            if item.review_status == 'accepted': accepted += 1
            if draft.part_family_scope and (not item.applicability.part_families or
                    not set(item.applicability.part_families).issubset(draft.part_family_scope)):
                issues.append(f'{item.id}: 条目适用范围超出包范围')
            for ref in item.source_refs:
                source = sources.get(ref.source_id)
                blocks = source_blocks(source.content) if source else []
                if not any(b['heading_path'] == ref.heading_path and
                           b['start_line'] <= ref.start_line <= ref.end_line <= b['end_line'] for b in blocks):
                    issues.append(f'{item.id}: 来源定位无效')
                if source and source.verification_status == 'obsolete':
                    issues.append(f'{item.id}: 来源已过期')
            for key in ('source_concept_id', 'target_concept_id'):
                target = getattr(item, key, None)
                if target and target not in concepts: issues.append(f'{item.id}: 未知概念 {target}')
            for target in getattr(item, 'concept_ids', []):
                if target not in concepts: issues.append(f'{item.id}: 未知概念 {target}')
    if activation and not accepted: issues.append('至少需要一个已审核条目')
    return issues
