import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteVersion, Project
from app.services.rule_packages.condition_review_errors import ConditionReviewNotFound
from app.services.rule_packages.condition_review_repository import load_route_and_review


@pytest_asyncio.fixture
async def db_with_route():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    db = factory()
    db.add_all(
        [
            Project(id=7, name="condition review"),
            NormalizedRouteVersion(
                id=1,
                project_id=7,
                version=1,
                route_json='[{"id":"process_mark"}]',
            ),
        ]
    )
    await db.commit()
    try:
        yield db
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_repository_creates_one_review_for_a_route_segment(db_with_route):
    route, review = await load_route_and_review(7, 1, "process_mark", db_with_route)

    assert route.id == 1
    assert review.segment_id == "process_mark"
    assert review.condition_status == "draft"

    _, same_review = await load_route_and_review(7, 1, "process_mark", db_with_route)
    assert same_review.id == review.id


@pytest.mark.asyncio
async def test_repository_uses_domain_not_found_error_for_unknown_segment(db_with_route):
    with pytest.raises(ConditionReviewNotFound) as error:
        await load_route_and_review(7, 1, "process_missing", db_with_route)

    assert error.value.detail == "当前工序不属于该保存路线版本。"
