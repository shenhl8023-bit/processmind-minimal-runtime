import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion
from app.services.analysis_drafts import AnalysisRuleDraft
from app.services.route_analysis import save_segment_rule_review_record


@pytest.mark.asyncio
async def test_pending_analysis_draft_is_saved_and_serialized():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add(NormalizedRouteVersion(
            id=3,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind","normalized_step_name":"磨削"}]',
        ))
        await session.commit()

        draft = AnalysisRuleDraft(
            scope="仅适用于有内孔的零件",
            object="内孔",
            condition_text="有内孔时安排磨削",
            missing=["请确认内孔尺寸条件"],
            status="incomplete",
        )
        result = await save_segment_rule_review_record(
            project_id=7,
            route_id=3,
            segment_id="process_grind",
            decision="pending",
            note="",
            summary_lines=["本工序需进一步确认"],
            question_trail=[],
            analysis_draft=draft,
            db=session,
        )

        row = (await session.execute(select(NormalizedRouteSegmentRuleReview))).scalars().one()
        assert result.rule_review is not None
        assert result.rule_review.analysis_draft.scope == "仅适用于有内孔的零件"
        assert json.loads(row.analysis_draft_json)["missing"] == ["请确认内孔尺寸条件"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_analysis_draft_must_be_complete_and_confirmed():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add(NormalizedRouteVersion(
            id=3,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind","normalized_step_name":"磨削"}]',
        ))
        await session.commit()
        draft = AnalysisRuleDraft(
            scope="全部零件",
            object="外圆",
            condition_text="高精度时安排磨削",
            missing=["请确认精度阈值"],
            status="confirmed",
        )
        with pytest.raises(HTTPException) as exc_info:
            await save_segment_rule_review_record(
                project_id=7,
                route_id=3,
                segment_id="process_grind",
                decision="accepted",
                note="",
                summary_lines=[],
                question_trail=[],
                analysis_draft=draft,
                db=session,
            )
        assert "请确认精度阈值" in exc_info.value.detail

    await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_trail_without_draft_derives_structured_draft():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add(NormalizedRouteVersion(
            id=5,
            project_id=9,
            version=1,
            route_json='[{"id":"process_grind","normalized_step_name":"磨削"}]',
        ))
        await session.commit()
        result = await save_segment_rule_review_record(
            project_id=9,
            route_id=5,
            segment_id="process_grind",
            decision="accepted",
            note="零件带内孔时保留钻孔工序",
            summary_lines=[],
            question_trail=[
                {"nodeId": "rule_reason_root", "value": "all", "label": "所有样本都需要该工序"},
                {"nodeId": "structure_scene_type", "value": "hole", "label": "带内孔结构"},
            ],
            analysis_draft=None,
            db=session,
        )
        draft = result.rule_review.analysis_draft
        assert draft is not None
        assert draft.scope
        assert draft.object
        assert draft.condition_text
        assert draft.status == "confirmed"

    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_pending_without_draft_still_clears_review():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add(NormalizedRouteVersion(
            id=3,
            project_id=7,
            version=1,
            route_json='[{"id":"process_grind","normalized_step_name":"磨削"}]',
        ))
        await session.commit()
        session.add(NormalizedRouteSegmentRuleReview(
            project_id=7,
            route_version_id=3,
            segment_id="process_grind",
            decision="accepted",
            summary_json="[]",
            question_trail_json="[]",
        ))
        await session.commit()

        await save_segment_rule_review_record(
            project_id=7,
            route_id=3,
            segment_id="process_grind",
            decision="pending",
            note="",
            summary_lines=[],
            question_trail=[],
            db=session,
        )
        assert (await session.execute(select(NormalizedRouteSegmentRuleReview))).scalars().all() == []

    await engine.dispose()
