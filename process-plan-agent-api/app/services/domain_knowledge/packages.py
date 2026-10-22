"""Immutable activated versions and editable, auditable drafts."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from app.models.models import DomainKnowledgePackageVersion, utcnow
from .contracts import DomainKnowledgePackageDraft, RESOURCE_TYPES
from .registry import validate_package


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def package_draft(row) -> DomainKnowledgePackageDraft:
    return DomainKnowledgePackageDraft.model_validate_json(row.draft_json)


def package_ref(row) -> dict:
    return {'package_id': row.package_id, 'version': row.version, 'content_hash': row.content_hash}


def serialize(row) -> dict:
    draft = package_draft(row)
    return {**package_ref(row), 'status': row.status, 'draft': draft.model_dump(),
            'issues': validate_package(draft, activation=True),
            'audit': json.loads(row.audit_json), 'import_result': json.loads(row.import_json),
            'created_at': row.created_at, 'activated_at': row.activated_at}


async def get_package_version(db, package_id: str, version: int):
    row = await db.scalar(select(DomainKnowledgePackageVersion).where(
        DomainKnowledgePackageVersion.package_id == package_id, DomainKnowledgePackageVersion.version == version))
    if not row: raise HTTPException(404, '知识包版本不存在')
    return row


async def create_package_draft(db, draft: DomainKnowledgePackageDraft, *, new_package=False):
    latest = await db.scalar(select(func.max(DomainKnowledgePackageVersion.version)).where(
        DomainKnowledgePackageVersion.package_id == draft.package_id))
    if new_package and latest: raise HTTPException(409, '知识包已存在，请创建新版本')
    row = DomainKnowledgePackageVersion(package_id=draft.package_id, version=(latest or 0) + 1,
                                        draft_json=canonical_json(draft.model_dump()), content_hash='')
    db.add(row)
    try: await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, '版本发生并发变更，请刷新重试')
    await db.refresh(row)
    return row


async def save_draft(db, row, draft, *, action: str, actor: str = '默认用户'):
    if row.status != 'draft': raise HTTPException(409, '已启用版本不可修改，请创建新版本')
    audit = json.loads(row.audit_json)
    audit.append({'action': action, 'actor': actor, 'at': utcnow().isoformat(),
                  'previous_draft': json.loads(row.draft_json)})
    result = await db.execute(update(DomainKnowledgePackageVersion).where(
        DomainKnowledgePackageVersion.id == row.id,
        DomainKnowledgePackageVersion.status == 'draft',
        DomainKnowledgePackageVersion.draft_json == row.draft_json,
    ).values(draft_json=canonical_json(draft.model_dump()), audit_json=canonical_json(audit)))
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, '草稿已更改，请刷新重试')
    await db.commit()
    await db.refresh(row)
    return row


async def activate_package_version(db, package_id: str, version: int):
    row = await get_package_version(db, package_id, version)
    if row.status != 'draft': return row
    draft = package_draft(row)
    issues = validate_package(draft, activation=True)
    if issues: raise HTTPException(422, detail=issues)
    # Keep rejected drafts in audit; activated runtime only contains accepted records.
    payload = draft.model_dump()
    for kind in RESOURCE_TYPES:
        payload[kind] = [item for item in payload[kind] if item['review_status'] == 'accepted']
    runtime = canonical_json(payload)
    audit = json.loads(row.audit_json) + [{'action': 'activate', 'at': utcnow().isoformat(),
                                         'previous_draft': json.loads(row.draft_json)}]
    result = await db.execute(update(DomainKnowledgePackageVersion).where(
        DomainKnowledgePackageVersion.id == row.id, DomainKnowledgePackageVersion.status == 'draft',
        DomainKnowledgePackageVersion.draft_json == row.draft_json,
    ).values(status='active', draft_json=runtime, content_hash=hashlib.sha256(runtime.encode()).hexdigest(),
             activated_at=utcnow(), audit_json=canonical_json(audit)))
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, '草稿已更改，请重新审核')
    await db.commit()
    await db.refresh(row)
    return row
