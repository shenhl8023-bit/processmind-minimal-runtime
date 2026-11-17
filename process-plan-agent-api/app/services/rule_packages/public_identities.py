"""Append-only project ID allocation under the same database write transaction."""
from typing import Dict, Iterable

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.public_rule_package_identity import PublicRulePackageIdentity


PREFIXES = {'processes': 'P', 'steps': 'S', 'factors': 'F'}


async def allocate_public_identities(db: AsyncSession, project_id: int,
                                     identities: Dict[str, Iterable[str]]) -> dict:
    """Caller owns commit/rollback. Deleted objects remain reserved until project deletion.

    A no-op project UPDATE serializes allocators across browsers/processes, also
    on SQLite, without bumping workflow revision, updated_at or executable hashes.
    The table is registered by the router import before init_db/create_all; this
    adds it idempotently to an existing installation without altering V2 tables.
    """
    locked = await db.execute(text(
        'UPDATE projects SET workflow_revision = workflow_revision WHERE id = :project_id'),
        {'project_id': project_id})
    if locked.rowcount != 1:
        raise HTTPException(404, '任务不存在，不能分配对外编号。')
    existing = (await db.execute(select(PublicRulePackageIdentity).where(
        PublicRulePackageIdentity.project_id == project_id))).scalars().all()
    result = {kind: {} for kind in PREFIXES}
    next_ordinal = {kind: 1 for kind in PREFIXES}
    for row in existing:
        result[row.kind][row.native_id] = '{}{:03d}'.format(PREFIXES[row.kind], row.ordinal)
        next_ordinal[row.kind] = max(next_ordinal[row.kind], row.ordinal + 1)
    if set(identities) != set(PREFIXES):
        raise ValueError('identity kinds must be processes, steps and factors')
    for kind, prefix in PREFIXES.items():
        values = list(identities[kind])
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError('native identity must be a nonempty string')
        for native_id in sorted(set(values)):
            if native_id in result[kind]:
                continue
            ordinal = next_ordinal[kind]
            db.add(PublicRulePackageIdentity(project_id=project_id, kind=kind,
                                           native_id=native_id, ordinal=ordinal))
            result[kind][native_id] = '{}{:03d}'.format(prefix, ordinal)
            next_ordinal[kind] += 1
    await db.flush()
    return result
