"""Allocate external IDs only from an exact immutable validated Native V2 export."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import FinalizedRulePackage
from app.services.rule_packages.native_publication import validate_native_snapshot
from app.services.rule_packages.public_identities import allocate_public_identities


router = APIRouter(prefix='/api/extract/public-rule-package-identities', tags=['规则包对外编号'])


class PublicIdentityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    finalized_rule_package_id: int = Field(gt=0)
    expected_content_hash: str = Field(min_length=1)


@router.post('')
async def allocate_export_identities(body: PublicIdentityRequest, db: AsyncSession = Depends(get_db)):
    try:
        row = await db.get(FinalizedRulePackage, body.finalized_rule_package_id)
        if row is None:
            raise HTTPException(404, '规则包不存在，请重新导出。')
        if row.content_hash != body.expected_content_hash:
            raise HTTPException(409, '规则包内容与编号请求不一致，请刷新后重新导出。')
        try:
            sources = json.loads(row.export_sources_json or '{}')
        except (ValueError, TypeError) as exc:
            raise HTTPException(409, '规则包冻结快照损坏，请重新验证导出。') from exc
        if not validate_native_snapshot(row, sources):
            raise HTTPException(409, '规则包冻结快照校验失败，不能分配对外编号；请重新验证导出。')
        snapshot = sources['native_snapshot']
        package = snapshot['rule_package']
        catalog = package['route_catalog']['processes']
        process_ids = {process['process_id'] for process in catalog}
        # Reserve complete source steps too, so hide/restore and optional mapping
        # never replace another object's external ID.
        step_ids = {step['step_id'] for process in catalog for step in process['steps']}
        for pid, process in sources.get('mother_route', {}).items():
            if pid in process_ids:
                step_ids.update(step['step_id'] for step in process['steps'])
        registry = await allocate_public_identities(db, row.project_id, {
            'processes': process_ids, 'steps': step_ids,
            'factors': {field['key'] for field in package['input_schema']['fields']},
        })
        result = {'finalized_rule_package_id': row.id, 'project_id': row.project_id,
                  'content_hash': row.content_hash, 'registry': registry}
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise
