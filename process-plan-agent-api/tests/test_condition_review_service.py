import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.services.rule_packages import condition_review_service as service
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionCandidate,
    RuleConditionProcessOption,
    SaveRuleConditionDraftRequest,
)
from app.services.rule_packages.condition_review_errors import (
    ConditionReviewConflict,
    ConditionReviewValidation,
)
from app.services.rule_packages.condition_review_repository import load_route_and_review
from app.services.rule_packages.condition_review_state import condition_source_hash


def _published_package(project_id: int = 7, version: int = 1) -> FinalizedRulePackage:
    return FinalizedRulePackage(
        project_id=project_id,
        version=version,
        package_name=f"published-{project_id}-{version}",
        schema_version="2.0",
        status="published",
    )


async def _package_status(db, project_id: int = 7) -> str:
    return (await db.execute(
        select(FinalizedRulePackage.status).where(
            FinalizedRulePackage.project_id == project_id,
        )
    )).scalar_one()


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
async def test_save_draft_archives_package_without_committing(db):
    package = _published_package()
    db.add(package)
    await db.commit()
    body = SaveRuleConditionDraftRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text="outer diameter reaches IT8",
    )

    response = await service.save_condition_draft(body, db)

    assert response.review.status == "draft"
    assert await _package_status(db) == "archived"
    await db.rollback()
    assert await _package_status(db) == "published"


@pytest.mark.asyncio
async def test_save_unchanged_draft_keeps_package_published(db):
    body = SaveRuleConditionDraftRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text="outer diameter reaches IT8",
    )
    await service.save_condition_draft(body, db)
    await db.commit()
    db.add(_published_package())
    await db.commit()

    await service.save_condition_draft(body, db)

    assert await _package_status(db) == "published"


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

    db.add(_published_package())
    await db.commit()

    cached = await service.prepare_condition_parse(parse_request, db)
    assert cached.cache_hit is True
    assert cached.cached_response is not None
    assert cached.cached_response.review.candidate is not None
    assert await _package_status(db) == "published"

    changed = await service.prepare_condition_parse(
        parse_request.model_copy(update={"source_text": "outer diameter reaches IT7"}),
        db,
    )
    assert changed.cache_hit is False
    assert await _package_status(db) == "archived"


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
    db.add(_published_package())
    await db.commit()

    with pytest.raises(ConditionReviewValidation) as error:
        await service.confirm_condition_review(confirm_request.model_copy(update={
            "source_hash": condition_source_hash(source_text),
        }), db)

    assert error.value.detail["message"] == "标准因子绑定校验未通过"
    assert await _package_status(db) == "published"


@pytest.mark.asyncio
async def test_confirm_archives_published_package(db, parse_request):
    _, review = await load_route_and_review(7, 1, "process_grind_outer", db)
    source_text = parse_request.source_text.strip()
    source_hash = condition_source_hash(source_text)
    candidate = RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {
            "field": "precision.outer_diameter_it",
            "op": "lte",
            "value": 8,
            "factor_id": "measurement.outer_diameter_it",
        },
        "then": {
            "include_process_ids": ["process_grind_outer"],
            "exclude_process_ids": [],
        },
    })
    review.condition_source_text = source_text
    review.condition_source_hash = source_hash
    review.condition_status = "pending_confirmation"
    review.condition_candidate_json = candidate.model_dump_json()
    db.add(_published_package())
    await db.commit()

    await service.confirm_condition_review(
        ConfirmRuleConditionRequest(
            project_id=7,
            route_id=1,
            segment_id="process_grind_outer",
            source_text=source_text,
            source_hash=source_hash,
            candidate=candidate,
            processes=parse_request.processes,
            confirmed_by="reviewer",
        ),
        db,
    )

    assert await _package_status(db) == "archived"


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


@pytest.mark.asyncio
async def test_migration_keeps_export_process_id_for_segment_route(db):
    route = NormalizedRouteVersion(
        id=2,
        project_id=7,
        version=2,
        route_json='[{"id":"segment-heat","normalized_step_name":"淬火"}]',
    )
    db.add(route)
    await db.commit()

    _, review = await load_route_and_review(7, 2, "segment-heat", db)
    candidate = RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {
            "field": "precision.outer_diameter_it",
            "op": "lte",
            "value": 8,
            "factor_id": "measurement.outer_diameter_it",
        },
        "then": {
            "include_process_ids": ["process_quench"],
            "exclude_process_ids": [],
        },
    })
    review.condition_status = "confirmed"
    review.condition_candidate_json = candidate.model_dump_json()
    review.condition_confirmed_json = candidate.model_dump_json()
    review.condition_issues_json = "[]"
    await db.commit()

    changed = await service.migrate_legacy_standard_factor_reviews(route, db)

    assert changed is True
    await db.refresh(review)
    assert review.condition_status == "confirmed"
    assert "process_quench" in review.condition_confirmed_json
