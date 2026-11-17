"""Project guidance is independently versioned, validated and side-effect free."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import json
import threading
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine, get_db
from app.main import app
from app.models.models import (
    Document, DocumentOperationDetail, FinalizedRulePackage, GeneratedRoute,
    NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project,
)
from app.services.db_schema_maintenance import ensure_project_schema


def test_confirmed_shared_frontend_fixture_matches_backend_defaults():
    from app.services.analysis_guidance import default_analysis_guidance

    fixture = Path(__file__).parent / "fixtures" / "confirmed_project_guidance.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == default_analysis_guidance(["9Cr18", "4Cr14Ni14W2Mo"])


@pytest.fixture
def guidance_client(tmp_path, monkeypatch):
    from app.core import paths

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(paths, "UPLOAD_DIR", uploads)
    # Both languages represent explicit fields, not guesses from operation prose.
    for name, header in [
        ("steel.pdf", "material_grade: 9Cr18"),
        ("steel-copy.pdf", "material_grade: 9Cr18"),
        ("alloy.pdf", "材料牌号：4Cr14Ni14W2Mo"),
        ("other.pdf", "material_grade: 6061"),
        ("no-material.pdf", "Grinding 95Cr18 is mentioned without a material field"),
    ]:
        with fitz.open() as pdf:
            page = pdf.new_page()
            if header.startswith("材料牌号："):
                page.insert_text((50, 50), "材料牌号：", fontname="china-s", fontsize=11)
                page.insert_text((105, 50), header[len("材料牌号："):], fontname="helv", fontsize=11)
            else:
                page.insert_text((50, 50), header, fontname="helv", fontsize=11)
            pdf.save(str(uploads / name))
    (uploads / "legacy.json").write_text('{"material_grade":"INVENTED"}', encoding="utf-8")
    engine = create_async_engine("sqlite+aiosqlite:///%s" % (tmp_path / "guidance.db"))
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add_all([Project(id=9, name="current", workflow_revision=7),
                        Project(id=10, name="other", workflow_revision=3)])
            await db.flush()
            for doc_id, project_id, name, kind in [
                (1, 9, "steel.pdf", "pdf"), (2, 9, "steel-copy.pdf", "PDF"),
                (3, 9, "alloy.pdf", "pdf"), (4, 10, "other.pdf", "pdf"),
                (5, 9, "no-material.pdf", "pdf"), (6, 9, "legacy.json", "json"),
                (7, 9, "missing.pdf", "pdf"),
            ]:
                db.add(Document(id=doc_id, project_id=project_id, filename=name,
                                original_name=name, file_type=kind, status="parsed"))
            db.add(DocumentOperationDetail(project_id=9, document_id=1,
                pdf_name="steel.pdf", operation_name="淬火", operation_content="材料牌号 95Cr18"))
            db.add(NormalizedRouteVersion(id=90, project_id=9, version=1,
                route_json='[{"id":"seg-1","normalized_step_name":"标记"}]',
                analysis_locked_at=datetime(2026, 11, 5)))
            await db.flush()
            db.add(NormalizedRouteSegmentRuleReview(project_id=9, route_version_id=90,
                segment_id="seg-1", decision="accepted", note="saved answer",
                question_trail_json='[{"answer":"manual"}]',
                condition_status="confirmed", condition_source_text="reviewed rule",
                condition_confirmed_json='{"user":"preserved"}'))
            db.add(FinalizedRulePackage(project_id=9, route_version_id=90, version=2,
                package_name="saved package", route_rules_json='{"keep":true}'))
            db.add(GeneratedRoute(project_id=9, result_json='{"saved":"result"}'))
            await db.commit()

    asyncio.run(setup())

    async def override_db():
        async with sessions() as db:
            yield db

    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    # No lifespan startup: only the explicit temporary database is ever written.
    client = TestClient(app)
    try:
        yield client, sessions, engine, uploads
    finally:
        client.close()
        if old is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = old
        asyncio.run(engine.dispose())


def _get(client, project_id=9):
    response = client.get("/api/projects/%s/analysis-guidance" % project_id)
    assert response.status_code == 200, response.text
    return response.json()


def _put(client, configuration, revision=0, project_id=9):
    return client.put("/api/projects/%s/analysis-guidance" % project_id, json={
        "expected_configuration_revision": revision, "configuration": configuration,
    })


def _preserved_rows(sessions):
    async def read():
        async with sessions() as db:
            result = []
            for model in (NormalizedRouteVersion, NormalizedRouteSegmentRuleReview,
                          FinalizedRulePackage, GeneratedRoute):
                result.append((await db.execute(select(model.__table__).order_by(model.id))).all())
            result.append((await db.execute(select(Project.id, Project.workflow_revision)
                                           .order_by(Project.id))).all())
            return result
    return asyncio.run(read())


def test_get_defaults_does_not_persist_or_change_reviewed_artifacts(guidance_client):
    client, sessions, _, _ = guidance_client
    before = _preserved_rows(sessions)
    payload = _get(client)
    assert payload["project_id"] == 9
    config = payload["configuration"]
    assert config["schema_version"] == "1.0"
    assert config["revision"] == 0
    assert config["directions"] == ["A侧", "B侧", "中间", "周边", "所有方位"]
    assert config["materials"] == ["9Cr18", "4Cr14Ni14W2Mo"]
    assert payload["prompt_reference"]
    assert _preserved_rows(sessions) == before

    async def read():
        async with sessions() as db:
            assert (await db.get(Project, 9)).analysis_guidance_json is None
    asyncio.run(read())


def test_default_mappings_keep_full_choices_and_method_specific_slots(guidance_client):
    config = _get(guidance_client[0])["configuration"]
    assert config["feature_mappings"] == {
        "外圆": ["外圆柱面"], "端面": ["轴端面"],
        "孔/内孔": ["孔", "孔(盲孔)", "孔(通孔)", "内圆柱面"],
        "车槽": ["U形外环槽", "U形内环槽", "外环槽", "内环槽"],
        "铣槽": ["V形环槽", "通槽", "T形截面通槽", "沟槽", "L形端面环槽", "U形直槽"],
        "磨槽": ["U形外环槽", "U形内环槽", "外环槽", "内环槽"],
        "扁位": ["平面"], "型孔": ["型孔"], "螺纹": ["内螺纹", "外螺纹"],
        "螺纹底孔": ["螺纹底孔"], "顶尖孔": ["顶尖孔"], "锥面": ["锥面"],
        "球面": ["球面"], "倒角/孔口倒角": ["倒角", "内倒角", "外倒角", "边倒角"],
        "倒圆/边缘圆角": ["边倒圆", "倒圆", "回转面倒圆"],
    }
    operations = config["operation_guidance"]
    for name, features in {
        "铣扁": ["平面"], "钻孔": ["孔(盲孔)", "孔(通孔)"],
        "钻铰孔": ["孔(通孔)", "内圆柱面"], "铣槽": ["通槽", "沟槽", "U形直槽"],
        "打孔": ["孔(盲孔)", "孔(通孔)"], "割型孔": ["型孔"],
        "割扁": ["平面"], "打型孔": ["型孔"],
    }.items():
        rec = operations[name]["recommendation"]
        assert rec == {"mode": "condition", "basis": "feature", "features": features,
                       "direction": "周边"}
        assert set(features) <= set(config["feature_mappings"][operations[name]["feature_group"]])
    assert "挖槽" not in operations


def test_recommendations_keep_approved_modes_thresholds_and_exact_occurrences(guidance_client):
    operations = _get(guidance_client[0])["configuration"]["operation_guidance"]
    for name in ["磨外圆", "磨端面", "磨槽", "磨孔"]:
        assert operations[name]["recommendation"] == {
            "mode": "condition", "basis": "precision", "it_threshold": 7, "ra_threshold": 0.8,
            "features": {"磨外圆": ["外圆柱面"], "磨端面": ["轴端面"], "磨槽": ["U形外环槽", "U形内环槽", "外环槽", "内环槽"], "磨孔": ["内圆柱面"]}[name],
            "direction": "所有方位",
        }
    for name in ["珩孔", "研孔", "研外圆"]:
        assert operations[name]["recommendation"] == {
            "mode": "condition", "basis": "precision", "it_threshold": 6,
            "features": ["外圆柱面"] if name == "研外圆" else ["内圆柱面"], "direction": "所有方位",
        }
        assert "暂定" in operations[name]["instruction"]
    for name in ["去应力", "调质", "淬火"]:
        assert operations[name]["recommendation"] == {
            "mode": "condition", "basis": "material", "materials": ["9Cr18"],
        }
    for name in ["正常化", "渗氮"]:
        assert operations[name]["recommendation"]["materials"] == ["4Cr14Ni14W2Mo"]
    for name in ["镀铜", "硬质阳极化", "标记", "铬酸阳极化", "研顶尖孔"]:
        assert operations[name]["recommendation"] == {"mode": "manual"}
    assert operations["除铜"]["recommendation"] == {
        "mode": "relation", "source_operation_name": "镀铜",
    }
    for name in ["无损检查", "烧伤检查", "去毛刺#2", "去毛刺#3", "清洗#3", "检验#3"]:
        assert operations[name]["recommendation"] == {"mode": "mainline"}
    for name in ["去毛刺", "清洗", "检验", "挖槽", "未知工序"]:
        assert name not in operations


def test_empty_or_other_project_materials_do_not_create_steel_recommendations(guidance_client):
    client, sessions, _, _ = guidance_client
    other = _get(client, 10)["configuration"]
    assert other["materials"] == ["6061"]
    for name in ["去应力", "调质", "淬火", "正常化", "渗氮"]:
        assert "recommendation" not in other["operation_guidance"][name]

    async def create_empty():
        async with sessions() as db:
            db.add(Project(id=11, name="empty"))
            await db.commit()
    asyncio.run(create_empty())
    assert _get(client, 11)["configuration"]["materials"] == []


def test_put_own_revision_survives_reads_and_preserves_all_answer_rule_result_rows(guidance_client):
    client, sessions, _, _ = guidance_client
    before = _preserved_rows(sessions)
    config = _get(client)["configuration"]
    config["guidance"] = "仅供后续作答使用"
    config["materials"].append("user configured alloy")
    first = _put(client, config)
    assert first.status_code == 200, first.text
    assert first.json()["configuration"]["revision"] == 1
    assert first.json()["configuration"]["guidance"] == "仅供后续作答使用"
    assert _get(client) == first.json()
    stale = _put(client, config)
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["configuration_revision"] == 1
    current = first.json()["configuration"]
    current.pop("revision")
    current["guidance"] = "second edit"
    second = _put(client, current, revision=1)
    assert second.status_code == 200, second.text
    assert second.json()["configuration"]["revision"] == 2
    assert _get(client, 10)["configuration"]["revision"] == 0
    assert _get(client, 10)["configuration"]["guidance"] != "second edit"
    assert _preserved_rows(sessions) == before


def test_simultaneous_puts_allow_only_one_writer_for_a_revision(guidance_client):
    client = guidance_client[0]
    config = _get(client)["configuration"]
    barrier = threading.Barrier(2)

    def write(label):
        candidate = deepcopy(config)
        candidate["guidance"] = label
        barrier.wait(timeout=5)
        response = _put(client, candidate)
        return label, response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ["first tab", "second tab"]))
    assert sorted(status for _, status in outcomes) == [200, 409]
    winner = next(label for label, status in outcomes if status == 200)
    saved = _get(client)["configuration"]
    assert saved["revision"] == 1
    assert saved["guidance"] == winner


@pytest.mark.parametrize("path,value", [
    (("feature_mappings", "孔/内孔"), ["孔", "孔"]),
    (("feature_mappings", "孔/内孔"), [" "]),
    (("feature_mappings", "孔/内孔"), "孔"),
    (("directions",), ["周边", " 周边 "]), (("directions",), [""]),
    (("directions",), []), (("materials",), ["9Cr18", "9Cr18"]),
    (("materials",), [" "]), (("unexpected",), True),
    (("schema_version",), "2.0"), (("revision",), -1),
    (("operation_guidance", "钻孔", "unexpected"), "bad"),
    (("operation_guidance", "钻孔", "feature_group"), "unknown group"),
    (("operation_guidance", "钻孔", "recommendation", "features"), ["外圆柱面"]),
    (("operation_guidance", "钻孔", "recommendation", "direction"), "unknown direction"),
    (("operation_guidance", "淬火", "recommendation", "materials"), ["fabricated"]),
    (("operation_guidance", "磨孔", "recommendation", "it_threshold"), 0),
    (("operation_guidance", "磨孔", "recommendation", "it_threshold"), 19),
    (("operation_guidance", "磨孔", "recommendation", "it_threshold"), 7.5),
    (("operation_guidance", "磨孔", "recommendation", "it_threshold"), True),
    (("operation_guidance", "磨孔", "recommendation", "ra_threshold"), 0),
    (("operation_guidance", "磨孔", "recommendation", "ra_threshold"), -0.8),
    (("operation_guidance", "磨孔", "recommendation", "ra_threshold"), "0.8"),
    (("operation_guidance", "磨孔", "recommendation", "mode"), "automatic"),
    (("operation_guidance", "磨孔", "recommendation", "basis"), "protection"),
    (("operation_guidance", "除铜", "recommendation"), {"mode": "relation"}),
    (("operation_guidance", "钻孔", "recommendation"), {"mode": "condition", "basis": "feature"}),
])
def test_invalid_configuration_is_rejected_without_saving(guidance_client, path, value):
    client = guidance_client[0]
    original = _get(client)
    config = deepcopy(original["configuration"])
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    response = _put(client, config)
    assert response.status_code == 422, response.text
    assert _get(client) == original


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_ra_returns_validation_error(guidance_client, number):
    client = guidance_client[0]
    config = _get(client)["configuration"]
    config["operation_guidance"]["磨孔"]["recommendation"]["ra_threshold"] = "RA_SENTINEL"
    body = json.dumps({"expected_configuration_revision": 0, "configuration": config})
    response = client.put("/api/projects/9/analysis-guidance",
        content=body.replace('"RA_SENTINEL"', number), headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text


def test_missing_project_and_invalid_expected_revision_are_rejected(guidance_client):
    client = guidance_client[0]
    assert client.get("/api/projects/999/analysis-guidance").status_code == 404
    config = _get(client)["configuration"]
    assert _put(client, config, project_id=999).status_code == 404
    for revision in [-1, True, "0", 0.5]:
        assert _put(client, config, revision=revision).status_code == 422
    config["revision"] = 4
    assert _put(client, config).status_code == 409


def test_prompt_renders_only_current_config_with_approved_matching_semantics(guidance_client):
    from app.services.analysis_guidance import build_analysis_guidance_prompt

    client = guidance_client[0]
    config = _get(client)["configuration"]
    config["feature_mappings"] = {"custom group": ["custom feature"]}
    config["directions"] = ["custom direction"]
    config["materials"] = ["custom material"]
    config["operation_guidance"] = {"custom operation": {
        "feature_group": "custom group", "instruction": "specific instruction",
        "recommendation": {"mode": "condition", "basis": "feature",
                           "features": ["custom feature"], "direction": "custom direction"},
    }}
    config["guidance"] = "current project note"
    saved = _put(client, config)
    assert saved.status_code == 200, saved.text
    prompt = saved.json()["prompt_reference"]
    assert prompt == build_analysis_guidance_prompt(saved.json()["configuration"])
    for value in ["custom feature", "custom direction", "custom material", "specific instruction",
                  "custom operation", "current project note", "任一", "同一加工对象", "全部满足",
                  "Ra <=", "当前工序", "不自动", "镀铜", "不是PDF事实"]:
        assert value in prompt
    for obsolete in ["孔(盲孔)", "所有方位", "9Cr18", "U形直槽"]:
        assert obsolete not in prompt


def test_old_projects_gain_nullable_guidance_column_idempotently_without_data_rewrites(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///%s" % (tmp_path / "legacy.db"))

    async def run():
        async with engine.begin() as conn:
            await conn.execute(text("""CREATE TABLE projects (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, status TEXT DEFAULT 'CREATED',
                created_at DATETIME, updated_at DATETIME
            )"""))
            await conn.execute(text("INSERT INTO projects(id,name) VALUES(9,'legacy')"))
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
            await ensure_project_schema(conn)
            row = (await conn.execute(text("SELECT name,analysis_guidance_json,workflow_revision FROM projects"))).one()
            assert tuple(row) == ("legacy", None, 0)
            await conn.execute(text("UPDATE projects SET analysis_guidance_json='saved',workflow_revision=7"))
            await ensure_project_schema(conn)
            row = (await conn.execute(text("SELECT analysis_guidance_json,workflow_revision FROM projects"))).one()
            assert tuple(row) == ("saved", 7)
    try:
        asyncio.run(run())
    finally:
        asyncio.run(engine.dispose())
