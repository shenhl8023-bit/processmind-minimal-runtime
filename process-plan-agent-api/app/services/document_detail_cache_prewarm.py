"""Background prewarm for document operation-detail cache.

This service intentionally reuses the same cache builder that the route-merge
workspace uses on demand. Upload can start it opportunistically so Step 2 has a
better chance of reading parsed document details from cache instead of building
them while the user is waiting.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.models import Document, DocumentOperationDetail
from app.services.route_rules_document_details_runtime import (
    ensure_document_operation_details,
    extract_document_operation_details,
)
from app.services.route_rules_parsing import (
    _detail_row_normalized_names,
    _normalize_operation_name,
)


logger = logging.getLogger(__name__)

DOCUMENT_DETAIL_CACHE_PREWARM_JOBS: dict[int, asyncio.Task] = {}


def cancel_document_detail_cache_prewarm(project_id: int) -> bool:
    """Cancel an in-flight prewarm task for a project before document changes."""
    normalized_project_id = int(project_id or 0)
    if normalized_project_id <= 0:
        return False
    active = DOCUMENT_DETAIL_CACHE_PREWARM_JOBS.pop(normalized_project_id, None)
    if active is None or active.done():
        return False
    active.cancel()
    return True


async def _extract_document_operation_details(
    db: AsyncSession,
    project_id: int,
    docs: list[Document] | None = None,
) -> list[DocumentOperationDetail]:
    return await extract_document_operation_details(
        db,
        project_id,
        docs=docs,
        detail_row_normalized_names=_detail_row_normalized_names,
        normalize_operation_name=_normalize_operation_name,
    )


async def run_document_detail_cache_prewarm(project_id: int) -> list[DocumentOperationDetail]:
    """Build missing document operation-detail cache rows for one project."""
    async with async_session() as db:
        try:
            rows = await ensure_document_operation_details(
                db,
                int(project_id),
                extract_document_operation_details_fn=_extract_document_operation_details,
            )
            await db.commit()
            return rows
        except Exception:
            await db.rollback()
            raise


async def _run_and_cleanup(project_id: int) -> None:
    try:
        await run_document_detail_cache_prewarm(project_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Document detail cache prewarm failed for project %s", project_id, exc_info=True)
    finally:
        current = DOCUMENT_DETAIL_CACHE_PREWARM_JOBS.get(int(project_id))
        if current is asyncio.current_task():
            DOCUMENT_DETAIL_CACHE_PREWARM_JOBS.pop(int(project_id), None)


def start_document_detail_cache_prewarm(project_id: int) -> bool:
    """Start a best-effort cache prewarm task unless one is already running."""
    normalized_project_id = int(project_id or 0)
    if normalized_project_id <= 0:
        return False

    active = DOCUMENT_DETAIL_CACHE_PREWARM_JOBS.get(normalized_project_id)
    if active is not None and not active.done():
        return False

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug(
            "Skipped document detail cache prewarm for project %s because no event loop is running",
            normalized_project_id,
        )
        return False

    DOCUMENT_DETAIL_CACHE_PREWARM_JOBS[normalized_project_id] = loop.create_task(
        _run_and_cleanup(normalized_project_id)
    )
    return True


__all__ = [
    "DOCUMENT_DETAIL_CACHE_PREWARM_JOBS",
    "cancel_document_detail_cache_prewarm",
    "run_document_detail_cache_prewarm",
    "start_document_detail_cache_prewarm",
]
