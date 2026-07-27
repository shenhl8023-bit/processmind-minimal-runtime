"""Management endpoints for extensible KmAI factor mappings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.rule_packages.kmai_mapping_contracts import (
    KmaiMappingBatchRequest,
    KmaiMappingCreateRequest,
    KmaiMappingPreviewRequest,
    KmaiMappingUpdateRequest,
)
from app.services.rule_packages.kmai_mapping_registry import builtin_factor_catalog
from app.services.rule_packages.kmai_mapping_store import (
    KmaiMappingStoreError,
    create_mapping,
    create_mapping_batch,
    deactivate_or_delete_mapping,
    list_mappings,
    preview_mapping_resolution,
    promote_mapping,
    update_mapping,
)


router = APIRouter(prefix="/api/kmai-factor-mappings", tags=["KmAI factor mappings"])


def _http_error(error: KmaiMappingStoreError) -> HTTPException:
    status_code = 409 if error.code in {
        "kmai_mapping_conflict",
        "kmai_mapping_revision_conflict",
        "kmai_mapping_in_use",
    } else 404 if error.code == "kmai_mapping_not_found" else 422
    return HTTPException(status_code=status_code, detail={"code": error.code, "message": error.message})


async def _commit_or_raise(db: AsyncSession, operation):
    try:
        result = await operation()
        await db.commit()
        return result
    except KmaiMappingStoreError as error:
        await db.rollback()
        raise _http_error(error) from error


@router.get("/catalog")
async def get_catalog():
    return [item.model_dump(mode="json") for item in builtin_factor_catalog()]


@router.get("")
async def get_mappings(
    project_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return [item.model_dump(mode="json") for item in await list_mappings(db, project_id)]


@router.post("")
async def post_mapping(
    body: KmaiMappingCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    mapping = await _commit_or_raise(db, lambda: create_mapping(db, body))
    return mapping.model_dump(mode="json")


@router.post("/batch")
async def post_mapping_batch(
    body: KmaiMappingBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    mappings = await _commit_or_raise(db, lambda: create_mapping_batch(db, body))
    return [item.model_dump(mode="json") for item in mappings]


@router.post("/resolve-preview")
async def resolve_preview(
    body: KmaiMappingPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    return (
        await preview_mapping_resolution(db, body.package, body.package.manifest.project_id)
    ).model_dump(mode="json")


@router.put("/{mapping_id}")
async def put_mapping(
    mapping_id: int,
    body: KmaiMappingUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    mapping = await _commit_or_raise(db, lambda: update_mapping(db, mapping_id, body))
    return mapping.model_dump(mode="json")


@router.post("/{mapping_id}/promote")
async def promote_project_mapping(
    mapping_id: int,
    actor: str = Query(default="默认用户"),
    db: AsyncSession = Depends(get_db),
):
    mapping = await _commit_or_raise(db, lambda: promote_mapping(db, mapping_id, actor))
    return mapping.model_dump(mode="json")


@router.delete("/{mapping_id}")
async def delete_or_deactivate_mapping(
    mapping_id: int,
    delete: bool = Query(default=False),
    actor: str = Query(default="默认用户"),
    db: AsyncSession = Depends(get_db),
):
    result = await _commit_or_raise(
        db,
        lambda: deactivate_or_delete_mapping(db, mapping_id, delete=delete, actor=actor),
    )
    return {"deleted": delete, "mapping": result.model_dump(mode="json") if result is not None else None}
