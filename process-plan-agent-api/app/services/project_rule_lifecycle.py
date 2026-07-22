"""Keeps published rule assets aligned with their source documents and references."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage, Project


async def invalidate_project_rule_assets(
    db: AsyncSession,
    project: Project,
    *,
    has_documents: bool,
) -> None:
    """Archive the active package whenever source material changes.

    Historical packages remain available in the version list, but cannot silently
    drive a generation based on a superseded document set.
    """
    active_packages = (
        await db.execute(
            select(FinalizedRulePackage).where(
                FinalizedRulePackage.project_id == project.id,
                FinalizedRulePackage.status == "published",
            )
        )
    ).scalars().all()
    for package in active_packages:
        package.status = "archived"

    project.status = "UPLOADED" if has_documents else "CREATED"
