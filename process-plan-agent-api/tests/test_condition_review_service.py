import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteVersion, Project
from app.services.rule_packages import condition_review_service as service
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_review_errors import (
    ConditionReviewConflict,
    ConditionReviewValidation,
)
from app.services.rule_packages.condition_review_repository import load_route_and_review
from app.services.rule_packages.condition_review_state import condition_source_hash


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    session.add_all(
        [
            Project(id=7, name="condition review"),
            NormalizedRouteVersion(
                id=1,
                project_id=7,
                version=1,
                route_json='[{"id":"process_grind_outer","normalized_step_name":"grind outer"}]',
            ),
        ]
    )
    await session.commit()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.fixture
def parse_request():
    return ParseRuleConditionRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text="outer diameter reaches IT8",
        process_id="process_grind_outer",
        process_name="grind outer",
        processes=[
            RuleConditionProcessOption(
                process_id="process_grind_outer",
                display_name="grind outer",
            )
        ],
    )


@pytest.fixture
def confirm_request(parse_request):
    return ConfirmRuleConditionRequest(
        project_id=parse_request.project_id,
        route_id=parse_request.route_id,
        expected_workflow_revision=parse_request.expected_workflow_revision,
        segment_id=parse_request.segment_id,
        source_text=parse_request.source_text,
        source_hash=condition_source_hash("changed condition"),
        candidate=RuleConditionCandidate.model_validate(
            {
                "kind": "condition",
                "when": {
                    "field": "precision.outer_diameter_it",
                    "op": "lte",
                    "value": 8,
                },
                "then": {
                    "include_process_ids": ["process_grind_outer"],
                    "exclude_process_ids": [],
                },
            }
        ),
        processes=parse_request.processes,
    )


@pytest.mark.asyncio
async def test_prepare_parse_returns_cached_response_without_reparsing(
    db,
    parse_request,
    monkeypatch,
):
    async def fake_config():
        return {"model": "test-model"}

    monkeypatch.setattr(service, "get_llm_config", fake_config)
    first = await service.prepare_condition_parse(parse_request, db)
    assert first.cache_hit is False
    candidate = RuleConditionCandidate.model_validate(
        {
            "kind": "condition",
            "when": {
                "field": "precision.outer_diameter_it",
                "op": "lte",
                "value": 8,
            },
            "then": {
                "include_process_ids": ["process_grind_outer"],
                "exclude_process_ids": [],
            },
        }
    )
    await service.complete_condition_parse(parse_request, first, (candidate, 0.9, []), db)
    await db.commit()

    cached = await service.prepare_condition_parse(parse_request, db)
    assert cached.cache_hit is True
    assert cached.cached_response is not None
    assert cached.cached_response.review.candidate is not None


@pytest.mark.asyncio
async def test_confirm_uses_domain_conflict_when_source_hash_changed(db, confirm_request):
    with pytest.raises(ConditionReviewConflict, match="条件文字"):
        await service.confirm_condition_review(confirm_request, db)


@pytest.mark.asyncio
async def test_confirm_uses_domain_validation_for_unbound_factor(db, confirm_request):
    _, review = await load_route_and_review(
        confirm_request.project_id,
        confirm_request.route_id,
        confirm_request.segment_id,
        db,
    )
    source_text = confirm_request.source_text.strip()
    review.condition_source_text = source_text
    review.condition_source_hash = condition_source_hash(source_text)
    review.condition_status = "pending_confirmation"
    await db.commit()

    with pytest.raises(ConditionReviewValidation) as error:
        await service.confirm_condition_review(confirm_request.model_copy(update={
            "source_hash": condition_source_hash(source_text),
        }), db)

    assert error.value.detail["message"] == "标准因子绑定校验未通过"


@pytest.mark.asyncio
async def test_complete_parse_refreshes_review_before_stale_write_check(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'stale-review.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def fake_config():
        return {"model": "test-model"}

    monkeypatch.setattr(service, "get_llm_config", fake_config)
    request = ParseRuleConditionRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text="outer diameter reaches IT8",
        process_id="process_grind_outer",
        process_name="grind outer",
        processes=[
            RuleConditionProcessOption(
                process_id="process_grind_outer",
                display_name="grind outer",
            )
        ],
    )
    candidate = RuleConditionCandidate.model_validate(
        {
            "kind": "condition",
            "when": {
                "field": "precision.outer_diameter_it",
                "op": "lte",
                "value": 8,
            },
            "then": {
                "include_process_ids": ["process_grind_outer"],
                "exclude_process_ids": [],
            },
        }
    )

    async with factory() as first:
        first.add_all(
            [
                Project(id=7, name="condition review"),
                NormalizedRouteVersion(
                    id=1,
                    project_id=7,
                    version=1,
                    route_json='[{"id":"process_grind_outer"}]',
                ),
            ]
        )
        await first.commit()
        preparation = await service.prepare_condition_parse(request, first)
        await first.commit()

        async with factory() as second:
            _, newer_review = await load_route_and_review(7, 1, "process_grind_outer", second)
            newer_review.condition_source_text = "newer condition"
            newer_review.condition_source_hash = condition_source_hash("newer condition")
            newer_review.condition_status = "draft"
            await second.commit()

        response = await service.complete_condition_parse(
            request,
            preparation,
            (candidate, 0.9, [], 5),
            first,
        )
        assert response.review.source_text == "newer condition"
        assert response.review.status == "draft"
        assert response.review.candidate is None

    await engine.dispose()
