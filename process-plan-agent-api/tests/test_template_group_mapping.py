import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import Project
from app.schemas.schemas import (
    TemplateGroupMappingOperationIn,
    TemplateGroupMappingSuggestRequest,
    TemplateStepMappingSuggestRequest,
)
from app.services import template_group_mapping
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.group_template_xml import parse_group_template_xml
from app.services.project_group_templates import commit_project_group_template


def _template_xml():
    return '''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" /><Item type="Group_Template" />
      <Item type="Part" filename="fixture.prt">
        <Item type="Group"><Params><param name="名称" value="A侧" /></Params>
          <Item type="Group"><Params><param name="名称" value="端面" /><param name="特征选择" value="轴端面" /></Params></Item>
          <Item type="Group"><Params><param name="名称" value="外圆" /><param name="特征选择" value="外圆柱面" /></Params></Item>
          <Item type="Group"><Params><param name="名称" value="孔" /><param name="特征选择" value="孔(盲孔)" /></Params></Item>
        </Item>
        <Item type="Group"><Params><param name="名称" value="B侧" /></Params>
          <Item type="Group"><Params><param name="名称" value="孔" /><param name="特征选择" value="孔(盲孔)" /></Params></Item>
        </Item>
        <Item type="Group"><Params><param name="名称" value="壳体" /></Params>
          <Item type="Group"><Params><param name="名称" value="内腔" /></Params>
            <Item type="Group"><Params><param name="名称" value="盲孔" /><param name="特征选择" value="孔(盲孔)" /></Params></Item>
          </Item>
        </Item>
      </Item>
    </Kmsoft>'''.encode("utf-8")


def _request(name="打孔", step_items=None):
    return TemplateGroupMappingSuggestRequest(
        project_id=7,
        operations=[TemplateGroupMappingOperationIn(
            operation_id=360,
            operation_name=name,
            step_items=step_items or [],
            rule_evidence=["孔"],
            rule_reasons=["加工特征明确。"],
        )],
    )


def _node_key(tree, path):
    pending = list(tree)
    while pending:
        node = pending.pop(0)
        if node["path"] == path:
            return node["key"]
        pending.extend(node.get("children", []))
    raise AssertionError(f"missing path: {path}")


@pytest_asyncio.fixture
async def mapping_store(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mapping.db'}")
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_project_schema(conn)
    parsed = parse_group_template_xml("fixture.xml", _template_xml())
    async with sessions() as db:
        project = Project(id=7, name="mapping")
        db.add(project)
        await db.flush()
        await commit_project_group_template(db, 7, parsed, expected_revision=0)
        await db.commit()
    try:
        yield sessions, parsed.tree
    finally:
        await engine.dispose()


def test_builds_candidates_from_arbitrary_confirmed_template_names():
    parsed = parse_group_template_xml("fixture.xml", _template_xml())
    operation = TemplateGroupMappingOperationIn(
        operation_id=1,
        operation_name="钻内腔盲孔",
        step_items=[],
    )

    candidates = template_group_mapping.build_template_candidates(operation, parsed.tree)

    assert [candidate.path for candidate in candidates] == [["壳体", "内腔", "盲孔"]]


def test_compound_side_operation_keeps_every_evidenced_feature_candidate():
    parsed = parse_group_template_xml("fixture.xml", _template_xml())
    operation = TemplateGroupMappingOperationIn(
        operation_id=1,
        operation_name="车削加工（A侧）",
        step_items=["平端面", "车外圆", "钻孔"],
    )

    candidates = template_group_mapping.build_template_candidates(operation, parsed.tree)

    assert [candidate.path for candidate in candidates] == [
        ["A侧", "端面"],
        ["A侧", "外圆"],
        ["A侧", "孔"],
    ]


def test_builds_candidates_for_each_step_without_returning_parent_groups():
    parsed = parse_group_template_xml("fixture.xml", _template_xml())
    operation = TemplateGroupMappingOperationIn(
        operation_id=1,
        operation_name="车削加工（A侧）",
        step_items=["平端面", "车外圆", "钻孔"],
    )

    prepared = template_group_mapping.prepare_step_candidates(operation, parsed.tree)

    assert [item.step_key for item, _ in prepared] == ["op_1_s01", "op_1_s02", "op_1_s03"]
    assert [[candidate.path for candidate in candidates] for _, candidates in prepared] == [
        [["A侧", "端面"]],
        [["A侧", "外圆"]],
        [["A侧", "孔"]],
    ]


@pytest.mark.asyncio
async def test_step_suggestions_reject_groups_outside_each_step_candidates(mapping_store, monkeypatch):
    sessions, _ = mapping_store

    async def choose_outside_candidate(*args, **kwargs):
        return json.dumps({"suggestions": [{
            "step_key": "op_360_s01",
            "group_ids": ["not-allowed"],
            "confidence": 0.99,
            "evidence": ["钻孔"],
            "reason": "invalid",
        }]})

    monkeypatch.setattr(template_group_mapping, "call_llm", choose_outside_candidate)
    async with sessions() as db:
        result = await template_group_mapping.resolve_template_step_mappings(
            db,
            TemplateStepMappingSuggestRequest(
                project_id=7,
                expected_template_revision=1,
                operations=[TemplateGroupMappingOperationIn(
                    operation_id=360,
                    operation_name="加工",
                    step_items=["钻孔"],
                )],
            ),
        )

    suggestion = result.suggestions[0]
    assert suggestion.step_key == "op_360_s01"
    assert suggestion.recommended_group_ids == []
    assert suggestion.source == "unresolved"
    assert "候选范围" in "".join(suggestion.warnings)


@pytest.mark.asyncio
async def test_step_model_failure_preserves_candidates_for_every_step(mapping_store, monkeypatch):
    sessions, _ = mapping_store

    async def unavailable(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(template_group_mapping, "call_llm", unavailable)
    async with sessions() as db:
        result = await template_group_mapping.resolve_template_step_mappings(
            db,
            TemplateStepMappingSuggestRequest(
                project_id=7,
                expected_template_revision=1,
                operations=[TemplateGroupMappingOperationIn(
                    operation_id=360,
                    operation_name="加工",
                    step_items=["钻孔", "车外圆"],
                )],
            ),
        )

    assert [item.step_key for item in result.suggestions] == ["op_360_s01", "op_360_s02"]
    assert all(item.candidates for item in result.suggestions)
    assert result.model_used is False


@pytest.mark.asyncio
async def test_accepts_only_high_confidence_model_choice_from_server_candidates(mapping_store, monkeypatch):
    sessions, tree = mapping_store
    a_hole_key = _node_key(tree, ["A侧", "孔"])

    async def valid_llm(*args, **kwargs):
        return json.dumps({"suggestions": [{
            "operation_id": 360,
            "group_id": a_hole_key,
            "confidence": 0.93,
            "evidence": ["在A侧钻安装孔"],
            "reason": "工步明确说明在A侧加工孔。",
        }]}, ensure_ascii=False)

    monkeypatch.setattr(template_group_mapping, "call_llm", valid_llm)
    async with sessions() as db:
        result = await template_group_mapping.resolve_template_group_mappings(
            db,
            _request(step_items=["在A侧钻安装孔"]),
        )

    assert result.model_used is True
    assert result.suggestions[0].group_id == a_hole_key
    assert result.suggestions[0].source == "llm"
    assert result.suggestions[0].evidence == ["在A侧钻安装孔"]


@pytest.mark.asyncio
async def test_rejects_unknown_or_low_confidence_model_group(mapping_store, monkeypatch):
    sessions, _ = mapping_store

    async def invalid_llm(*args, **kwargs):
        return '{"suggestions":[{"operation_id":360,"group_id":"invented","confidence":0.99}]}'

    monkeypatch.setattr(template_group_mapping, "call_llm", invalid_llm)
    async with sessions() as db:
        unknown = await template_group_mapping.resolve_template_group_mappings(db, _request())
    assert unknown.suggestions[0].group_id is None

    async def low_llm(*args, **kwargs):
        payload = json.loads(args[1])
        return json.dumps({"suggestions": [{
            "operation_id": 360,
            "group_id": payload["operations"][0]["candidates"][0]["group_id"],
            "confidence": 0.89,
        }]})

    monkeypatch.setattr(template_group_mapping, "call_llm", low_llm)
    async with sessions() as db:
        low = await template_group_mapping.resolve_template_group_mappings(db, _request())
    assert low.suggestions[0].group_id is None
    assert low.suggestions[0].confidence == 0.89


@pytest.mark.asyncio
async def test_high_confidence_model_cannot_choose_for_compound_candidates(mapping_store, monkeypatch):
    sessions, _ = mapping_store

    async def overconfident_llm(*args, **kwargs):
        payload = json.loads(args[1])
        return json.dumps({"suggestions": [{
            "operation_id": 360,
            "group_id": payload["operations"][0]["candidates"][0]["group_id"],
            "confidence": 0.99,
            "reason": "选择其中一个。",
        }]})

    monkeypatch.setattr(template_group_mapping, "call_llm", overconfident_llm)
    request = _request(
        name="车削加工（A侧）",
        step_items=["平端面", "车外圆", "钻孔"],
    )
    async with sessions() as db:
        result = await template_group_mapping.resolve_template_group_mappings(db, request)

    assert len(result.suggestions[0].candidate_group_ids) == 3
    assert result.suggestions[0].group_id is None
    assert any("多个候选" in warning for warning in result.suggestions[0].warnings)


@pytest.mark.asyncio
async def test_model_failure_preserves_server_candidates(mapping_store, monkeypatch):
    sessions, tree = mapping_store

    async def unavailable(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(template_group_mapping, "call_llm", unavailable)
    async with sessions() as db:
        result = await template_group_mapping.resolve_template_group_mappings(db, _request())

    assert result.model_used is False
    assert result.suggestions[0].group_id is None
    assert set(result.suggestions[0].candidate_group_ids) == {
        _node_key(tree, ["A侧", "孔"]),
        _node_key(tree, ["B侧", "孔"]),
        _node_key(tree, ["壳体", "内腔", "盲孔"]),
    }


@pytest.mark.asyncio
async def test_model_mapping_uses_a_short_single_attempt_timeout(mapping_store, monkeypatch):
    sessions, _ = mapping_store
    request_options = {}

    async def capture_options(*args, **kwargs):
        request_options.update(kwargs)
        return ""

    monkeypatch.setattr(template_group_mapping, "call_llm", capture_options)
    async with sessions() as db:
        await template_group_mapping.resolve_template_group_mappings(db, _request())

    assert request_options["timeout_seconds"] == 12.0
    assert request_options["max_retries"] == 0


@pytest.mark.asyncio
async def test_missing_confirmed_template_returns_manual_mapping_warning(mapping_store):
    sessions, _ = mapping_store
    async with sessions() as db:
        db.add(Project(id=8, name="without-template"))
        await db.commit()
        request = _request()
        request.project_id = 8
        result = await template_group_mapping.resolve_template_group_mappings(db, request)

    assert result.suggestions[0].candidate_group_ids == []
    assert any("尚未确认分组模板" in warning for warning in result.warnings)
