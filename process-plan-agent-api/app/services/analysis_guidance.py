"""Validated, independently versioned project suggestions for subsequent answers.

Defaults and their rendered prompt are reference configuration, never PDF facts
or an instruction to rewrite existing answers, reviewed rules or route results.
"""

from __future__ import annotations

import json
from functools import lru_cache
from copy import deepcopy
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Dict, List, Literal, Optional

import fitz
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import paths
from app.core.compat import run_in_thread
from app.models.models import Document, Project


_DEFAULT_FEATURE_MAPPINGS = MappingProxyType({
    "外圆": ("外圆柱面",), "端面": ("轴端面",),
    "孔/内孔": ("孔", "孔(盲孔)", "孔(通孔)", "内圆柱面"),
    "车槽": ("U形外环槽", "U形内环槽", "外环槽", "内环槽"),
    "铣槽": ("V形环槽", "通槽", "T形截面通槽", "沟槽", "L形端面环槽", "U形直槽"),
    "磨槽": ("U形外环槽", "U形内环槽", "外环槽", "内环槽"),
    "扁位": ("平面",), "型孔": ("型孔",), "螺纹": ("内螺纹", "外螺纹"),
    "螺纹底孔": ("螺纹底孔",), "顶尖孔": ("顶尖孔",), "锥面": ("锥面",),
    "球面": ("球面",), "倒角/孔口倒角": ("倒角", "内倒角", "外倒角", "边倒角"),
    "倒圆/边缘圆角": ("边倒圆", "倒圆", "回转面倒圆"),
})
_DEFAULT_DIRECTIONS = ("A侧", "B侧", "中间", "周边", "所有方位")
_COARSE_RECOMMENDATIONS = (
    ("铣扁", "扁位", ("平面",)),
    ("钻孔", "孔/内孔", ("孔(盲孔)", "孔(通孔)")),
    ("钻铰孔", "孔/内孔", ("孔(通孔)", "内圆柱面")),
    ("铣槽", "铣槽", ("通槽", "沟槽", "U形直槽")),
    ("打孔", "孔/内孔", ("孔(盲孔)", "孔(通孔)")),
    ("割型孔", "型孔", ("型孔",)), ("割扁", "扁位", ("平面",)),
    ("打型孔", "型孔", ("型孔",)),
)


def _nonblank(value: str) -> str:
    value = value.strip()
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("名称不能为空或包含控制字符")
    return value


def _unique(values: List[str]) -> List[str]:
    cleaned = [_nonblank(value) for value in values]
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("候选值不能重复")
    return cleaned


def _named_mapping(values: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {}
    for key, value in values.items():
        key = _nonblank(key)
        if key in cleaned:
            raise ValueError("名称不能重复")
        cleaned[key] = value
    return cleaned


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OperationRecommendation(_StrictModel):
    mode: Literal["mainline", "manual", "condition", "relation"]
    basis: Optional[Literal["feature", "precision", "roughness", "material", "hardness", "requirement"]] = None
    features: Optional[List[str]] = None
    direction: Optional[str] = None
    materials: Optional[List[str]] = None
    it_threshold: Optional[int] = Field(default=None, ge=1, le=18)
    ra_threshold: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    source_operation_name: Optional[str] = None
    source_segment_id: Optional[str] = None

    @field_validator("features", "materials")
    @classmethod
    def validate_choices(cls, value):
        if value is None:
            return value
        if not value:
            raise ValueError("推荐选值不能为空")
        return _unique(value)

    @field_validator("direction", "source_operation_name", "source_segment_id")
    @classmethod
    def validate_name(cls, value):
        return _nonblank(value) if value is not None else value

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "relation":
            if not (self.source_operation_name or self.source_segment_id):
                raise ValueError("关联推荐必须指定来源工序")
        elif self.source_operation_name is not None or self.source_segment_id is not None:
            raise ValueError("仅关联推荐可以指定来源工序")
        if self.mode == "condition":
            required = {"feature": "features", "precision": "it_threshold",
                        "roughness": "ra_threshold", "material": "materials"}
            if self.basis is None:
                raise ValueError("条件推荐必须指定判断依据")
            field = required.get(self.basis)
            if field and getattr(self, field) is None:
                raise ValueError("条件推荐缺少必要选值: %s" % field)
        elif any(getattr(self, field) is not None for field in (
            "basis", "features", "direction", "materials", "it_threshold", "ra_threshold",
        )):
            raise ValueError("当前推荐方式不接受条件选值")
        return self


QUESTION_IDS = frozenset(("guided_mode", "guided_basis", "guided_features", "guided_direction", "guided_it", "guided_ra", "guided_material_scope", "guided_requirement", "guided_hardness_unit", "guided_hardness_min", "guided_hardness_max", "guided_source", "guided_custom"))


class GuidanceQuestionText(_StrictModel):
    prompt: str = Field(min_length=1, max_length=1200)
    option_labels: Dict[str, str] = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value):
        return _nonblank(value)

    @field_validator("option_labels")
    @classmethod
    def validate_labels(cls, value):
        return {_nonblank(key): _nonblank(label) for key, label in value.items()}


class OperationGuidance(_StrictModel):
    feature_group: Optional[str] = None
    recommendation: Optional[OperationRecommendation] = None
    instruction: Optional[str] = None
    questions: Optional[Dict[str, GuidanceQuestionText]] = None
    recommendation_issues: Optional[List[str]] = None
    recommendation_reference_blocked: Optional[bool] = None

    @field_validator("questions")
    @classmethod
    def validate_questions(cls, value):
        if value is not None and not set(value) <= QUESTION_IDS:
            raise ValueError("问题包含未定义的分支")
        return value

    @field_validator("feature_group")
    @classmethod
    def validate_group(cls, value):
        return _nonblank(value) if value is not None else value


class AnalysisGuidanceConfiguration(_StrictModel):
    schema_version: Literal["1.0"]
    revision: int = Field(default=0, ge=0)
    feature_mappings: Dict[str, List[str]]
    directions: List[str] = Field(min_length=1)
    materials: List[str]
    operation_guidance: Dict[str, OperationGuidance]
    guidance: str
    generation_version: Optional[str] = None
    generation_route_id: Optional[int] = None
    generation_operation_ids: Optional[Dict[str, str]] = None

    @field_validator("feature_mappings")
    @classmethod
    def validate_mappings(cls, value):
        result = _named_mapping(value)
        for key, choices in result.items():
            if not choices:
                raise ValueError("特征分组不能为空: %s" % key)
            result[key] = _unique(choices)
        return result

    @field_validator("directions", "materials")
    @classmethod
    def validate_choices(cls, value):
        return _unique(value)

    @field_validator("operation_guidance")
    @classmethod
    def validate_operations(cls, value):
        return _named_mapping(value)

    @model_validator(mode="after")
    def validate_references(self):
        for operation in self.operation_guidance.values():
            group = operation.feature_group
            if group is not None and group not in self.feature_mappings:
                raise ValueError("工序特征分组必须属于当前配置")
            recommendation = operation.recommendation
            if recommendation is None:
                continue
            if recommendation.features is not None:
                if group is None or not set(recommendation.features) <= set(self.feature_mappings[group]):
                    raise ValueError("推荐特征必须属于所选分组")
            if recommendation.direction is not None and recommendation.direction not in self.directions:
                raise ValueError("推荐方位必须属于当前配置")
            if recommendation.materials is not None and not set(recommendation.materials) <= set(self.materials):
                raise ValueError("推荐材料必须属于当前项目材料候选")
        return self


class AnalysisGuidanceUpdate(_StrictModel):
    expected_configuration_revision: int = Field(ge=0)
    configuration: AnalysisGuidanceConfiguration


def validate_guidance_update(body: Dict[str, Any]) -> AnalysisGuidanceUpdate:
    try:
        return AnalysisGuidanceUpdate.model_validate(body)
    except ValidationError as exc:
        # Non-finite JSON numbers must also yield a JSON-safe 422 response.
        raise HTTPException(422, exc.errors(include_input=False, include_context=False, include_url=False)) from exc


def default_analysis_guidance(materials: List[str]) -> Dict[str, Any]:
    """Copy the read-only defaults; material recommendations never add candidates."""
    operations = {}
    for name, group, features in _COARSE_RECOMMENDATIONS:
        operations[name] = {
            "feature_group": group,
            "recommendation": {"mode": "condition", "basis": "feature",
                               "features": list(features), "direction": "周边"},
        }
    for name, group in (("磨外圆", "外圆"), ("磨端面", "端面"),
                        ("磨槽", "磨槽"), ("磨孔", "孔/内孔")):
        operations[name] = {
            "feature_group": group,
            "recommendation": {"mode": "condition", "basis": "precision",
                               "features": ["内圆柱面"] if group == "孔/内孔" else list(_DEFAULT_FEATURE_MAPPINGS[group]),
                               "direction": "所有方位", "it_threshold": 7, "ra_threshold": 0.8},
            "instruction": "先确认加工特征和方位；A/B范围仅作可修改推荐。主推荐为IT7及更高精度；仅改选粗糙度分支时使用可编辑的Ra备用阈值。",
        }
    for name, group in (("珩孔", "孔/内孔"), ("研孔", "孔/内孔"), ("研外圆", "外圆")):
        operations[name] = {
            "feature_group": group,
            "recommendation": {"mode": "condition", "basis": "precision", "it_threshold": 6,
                               "features": ["内圆柱面"] if group == "孔/内孔" else list(_DEFAULT_FEATURE_MAPPINGS[group]),
                               "direction": "所有方位"},
            "instruction": "暂定IT6及更高精度；改选粗糙度时需另填阈值。",
        }
    for name, material in (("去应力", "9Cr18"), ("调质", "9Cr18"), ("淬火", "9Cr18"),
                           ("正常化", "4Cr14Ni14W2Mo"), ("渗氮", "4Cr14Ni14W2Mo")):
        operations[name] = {"instruction": "材料推荐只引用当前项目已配置候选；其它分支由工艺师选择。"}
        if material in materials:
            operations[name]["recommendation"] = {
                "mode": "condition", "basis": "material", "materials": [material],
            }
    for name in ("镀铜", "硬质阳极化", "标记", "铬酸阳极化", "研顶尖孔"):
        operations[name] = {"recommendation": {"mode": "manual"}}
    operations["研顶尖孔"]["feature_group"] = "顶尖孔"
    operations["研顶尖孔"]["instruction"] = "定位辅助类，暂按用户倾向推荐人工Bool。"
    operations["除铜"] = {
        "recommendation": {"mode": "relation", "source_operation_name": "镀铜"},
        "instruction": "选择当前路线中明确的镀铜来源节点，保留原路线位置，不要求相邻。",
    }
    for name in ("下料备料", "车削加工（A侧）", "车削加工（B侧）", "包装",
                 "无损检查", "烧伤检查", "去毛刺#1", "去毛刺#2", "去毛刺#3",
                 "清洗#1", "清洗#2", "清洗#3", "检验#1", "检验#2", "检验#3"):
        operations[name] = {"recommendation": {"mode": "mainline"}}
    configuration = AnalysisGuidanceConfiguration(
        schema_version="1.0", revision=0,
        feature_mappings={key: list(values) for key, values in _DEFAULT_FEATURE_MAPPINGS.items()},
        directions=list(_DEFAULT_DIRECTIONS), materials=list(materials),
        operation_guidance=operations,
        guidance="以下为可编辑的项目推荐，不是PDF事实；仅经用户采用后形成后续回答及规则。",
    )
    return configuration.model_dump(exclude_none=True)


# Accept only an explicitly labelled field, never a grade found in body prose.
_MATERIAL_FIELD = re.compile(
    r"^[ \t]*(?:material_grade|材料[ \t]*牌号)[ \t]*[:：|]?[ \t]*\n?"
    r"[ \t]*([A-Za-z0-9][A-Za-z0-9().+/_-]{0,79})[ \t]*(?=$|\|)",
    re.MULTILINE | re.IGNORECASE,
)


def _read_pdf_materials(filenames: List[str]) -> List[str]:
    root = Path(paths.UPLOAD_DIR).resolve()
    sources = []
    for filename in filenames:
        source = (root / filename).resolve()
        if source.parent != root or not source.is_file():
            continue
        try:
            stat = source.stat()
        except OSError:
            continue
        sources.append((str(source), stat.st_size, stat.st_mtime_ns))
    return list(_cached_pdf_materials(tuple(sources)))


@lru_cache(maxsize=128)
def _cached_pdf_materials(sources):
    """Reuse immutable uploaded evidence; changed/replaced PDFs get a new key."""
    materials = []
    for filename, _size, _mtime_ns in sources:
        try:
            with fitz.open(filename) as pdf:
                for page in pdf:
                    for grade in _MATERIAL_FIELD.findall(page.get_text()):
                        if grade not in materials:
                            materials.append(grade)
        except (OSError, RuntimeError, ValueError):
            # An unavailable PDF supplies no material evidence. No parse/cache writes.
            continue
    return tuple(materials)


async def _project_default_configuration(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    filenames = (await db.execute(select(Document.filename).where(
        Document.project_id == project_id, func.lower(Document.file_type) == "pdf",
    ).order_by(Document.id))).scalars().all()
    materials = await run_in_thread(_read_pdf_materials, list(filenames))
    return default_analysis_guidance(materials)


def _saved_configuration(raw: str) -> Dict[str, Any]:
    try:
        return AnalysisGuidanceConfiguration.model_validate_json(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(409, {"code": "analysis_guidance_invalid",
            "message": "已保存的项目分析配置无效，未覆盖原配置。"}) from exc


def build_analysis_guidance_prompt(configuration: Dict[str, Any]) -> str:
    """Render current validated choices, suggestions and instruction text for review."""
    current = AnalysisGuidanceConfiguration.model_validate(configuration).model_dump(exclude_none=True)
    semantics = (
        "项目分析配置参考：这是可编辑的推荐，不是PDF事实，候选不证明零件具有该特征。\n"
        "只使用下列当前配置的特征分组、候选、方位、材料及逐工序指导，不猜测未知工序的推荐。\n"
        "粗加工先选特征，再单选方位：特征多选任一命中（OR），特征与方位全部满足（AND），"
        "且必须属于同一加工对象，不允许跨对象拼接。\n"
        "尺寸精度按IT等级序号 <= 阈值；粗糙度按实际要求 Ra <= 配置阈值。"
        "备用Ra不同时附加到IT主分支，不把阈值填作实际零件值。\n"
        "明确要求仅检查当前工序、当前部位自身的要求，不借用其它工序要求。"
        "不自动因保护要求触发镀铜；人工Bool由用户选择，关联仅跟随明确来源并保持原位置。\n"
        "带#次数的工序键仅适用对应出现次数，不能扩散到同名其它节点。"
        "配置变更只供后续作答，不改写已保存回答、已审核规则、定稿包或生成结果。\n"
    )
    if "所有方位" in current["directions"]:
        semantics += "当前候选中的所有方位只表示A侧或B侧任一侧满足，不包含中间或周边；精加工也先确认特征、单选方位，再设置IT/Ra阈值。\n"
    return semantics + json.dumps(current, ensure_ascii=False, indent=2, allow_nan=False)


def complete_object_recommendations(configuration: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Fill old threshold-only suggestions from a valid same-operation reference.

    This is a response projection, never an edit to saved answers/rules. Indexed
    occurrences and incompatible/custom domains must not borrow factory values.
    Runtime confirmed-object reuse still takes precedence when answers are built.
    """
    result = deepcopy(configuration)
    for name, operation in result.get('operation_guidance', {}).items():
        recommendation = operation.get('recommendation') or {}
        reference = defaults.get('operation_guidance', {}).get(name) or {}
        fallback = reference.get('recommendation') or {}
        group = operation.get('feature_group')
        if (operation.get('recommendation_reference_blocked') or
                group != reference.get('feature_group') or
                recommendation.get('mode') != 'condition' or
                recommendation.get('basis') not in {'precision', 'roughness'} or
                fallback.get('mode') != 'condition'):
            continue
        features = fallback.get('features')
        if (not recommendation.get('features') and features and
                set(features) <= set(result.get('feature_mappings', {}).get(group, []))):
            recommendation['features'] = deepcopy(features)
        if (not recommendation.get('direction') and recommendation.get('features') == features and
                fallback.get('direction') in result.get('directions', [])):
            recommendation['direction'] = fallback['direction']
    return result


def _response(project_id: int, configuration: Dict[str, Any]) -> Dict[str, Any]:
    configuration = complete_object_recommendations(configuration, default_analysis_guidance(configuration.get('materials', [])))
    return {"project_id": project_id, "configuration": configuration,
            "prompt_reference": build_analysis_guidance_prompt(configuration)}


async def get_analysis_guidance(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    project = (await db.execute(select(Project).where(Project.id == project_id)
                              .execution_options(populate_existing=True))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "任务不存在")
    configuration = (_saved_configuration(project.analysis_guidance_json)
                     if project.analysis_guidance_json is not None
                     else await _project_default_configuration(db, project_id))
    return _response(project_id, configuration)


async def save_analysis_guidance(
    db: AsyncSession, project_id: int, body: AnalysisGuidanceUpdate,
) -> Dict[str, Any]:
    """Lock before reading the revision, then CAS JSON without workflow invalidation."""
    try:
        locked = (await db.execute(text(
            "UPDATE projects SET analysis_guidance_json = analysis_guidance_json "
            "WHERE id = :project_id RETURNING analysis_guidance_json"
        ), {"project_id": project_id})).first()
        if locked is None:
            raise HTTPException(404, "任务不存在")
        previous = locked[0]
        revision = _saved_configuration(previous)["revision"] if previous is not None else 0
        expected = body.expected_configuration_revision
        supplied = body.configuration
        if expected != revision or ("revision" in supplied.model_fields_set and supplied.revision != revision):
            raise HTTPException(409, {"code": "analysis_guidance_revision_conflict",
                "message": "项目分析配置已更新，请刷新后重试。", "configuration_revision": revision})
        configuration = supplied.model_dump(exclude_none=True)
        configuration["revision"] = revision + 1
        serialized = json.dumps(configuration, ensure_ascii=False, allow_nan=False)
        updated = (await db.execute(text(
            "UPDATE projects SET analysis_guidance_json = :configuration "
            "WHERE id = :project_id AND (analysis_guidance_json = :previous "
            "OR (analysis_guidance_json IS NULL AND :previous IS NULL)) RETURNING id"
        ), {"project_id": project_id, "configuration": serialized, "previous": previous})).first()
        if updated is None:
            raise HTTPException(409, {"code": "analysis_guidance_revision_conflict",
                "message": "项目分析配置已更新，请刷新后重试。", "configuration_revision": revision})
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _response(project_id, configuration)
