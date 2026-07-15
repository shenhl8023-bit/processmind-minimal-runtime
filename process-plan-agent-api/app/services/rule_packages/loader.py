"""Database loading boundary for active rule packages."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage


async def load_published_rule_package(project_id: int, db: AsyncSession) -> FinalizedRulePackage | None:
    return (
        await db.execute(
            select(FinalizedRulePackage)
            .where(
                FinalizedRulePackage.project_id == project_id,
                FinalizedRulePackage.status == "published",
            )
            .order_by(FinalizedRulePackage.version.desc(), FinalizedRulePackage.id.desc())
        )
    ).scalar_one_or_none()
