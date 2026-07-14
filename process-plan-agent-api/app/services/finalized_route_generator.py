"""
第5步：基于第4步定稿规则包生成工序工步树。

这个模块只负责解释 finalized rule package，不处理 HTTP、数据库持久化、
旧版 Operation/Faktor 兜底规则。这样路由层可以保持轻量。
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

from app.models.models import FinalizedRulePackage
from app.schemas.schemas import RouteStep


FactorParser = Callable[[str], dict | None]
FactorMatcher = Callable[[str, dict[str, object], str], tuple[bool, str]]
BoolParser = Callable[[object], bool]
FloatParser = Callable[[object], float | None]
QualityGateCollapser = Callable[[list[RouteStep]], list[RouteStep]]


NON_EXECUTABLE_TRIGGER_FACTORS = {
    "conditional=true",
    "structure_variation=true",
    "heat_chain=true",
    "naming_variant=true",
    "外圆结构要求",
    "台阶外形要求",
    "外圆基准要求",
    "外圆配合要求",
    "回转轮廓要求",
    "外形轮廓要求",
    "端面基准要求",
    "端面贴合要求",
    "孔口端面要求",
    "端面配合要求",
    "锐边去除要求",
    "孔口倒角要求",
    "装配导入要求",
    "孔结构类型",
    "中心孔定位要求",
    "孔复合要求",
    "深长孔要求",
    "孔可达性限制",
    "孔尺寸精度要求",
    "孔形位精度要求",
    "孔表面质量要求",
    "孔配合要求",
    "配对加工要求",
    "分组配套要求",
    "尺寸公差高",
    "形位精度要求",
    "最终光整要求",
    "装配配合要求",
    "热处理链分化",
    "热后精整要求",
    "性能与耐磨要求",
    "尺寸稳定性要求",
}


def _json_dict(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_text_list(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,，;；、\n]+", text) if part.strip()]


def _normalized_text(value: object) -> str:
    return str(value or "").strip().lower()


def _text_matches(expected: object, actual_values: list[str]) -> bool:
    expected_text = _normalized_text(expected)
    if not expected_text:
        return False
    for actual in actual_values:
        actual_text = _normalized_text(actual)
        if actual_text == expected_text or expected_text in actual_text or actual_text in expected_text:
            return True
    return False


def _extract_catalog_process_steps(segment: dict[str, object]) -> list[str]:
    steps: list[str] = []
    for field_name in ("primary_steps", "attached_steps"):
        raw_steps = segment.get(field_name)
        if not isinstance(raw_steps, list):
            continue
        for item in raw_steps:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = str(
                    item.get("step_name")
                    or item.get("name")
                    or item.get("content")
                    or item.get("description")
                    or ""
                ).strip()
            else:
                text = str(item or "").strip()
            if text and text not in steps:
                steps.append(text)
    return steps


def _extract_min_roughness_from_precision(precision_values: list[str]) -> float | None:
    matched_values: list[float] = []
    for item in precision_values:
        matched = re.search(r"Ra\s*([0-9]+(?:\.[0-9]+)?)", str(item or ""), flags=re.IGNORECASE)
        if not matched:
            continue
        try:
            matched_values.append(float(matched.group(1)))
        except ValueError:
            continue
    return min(matched_values) if matched_values else None


def _high_precision_signal(precision_values: list[str]) -> bool:
    text = " ".join(precision_values)
    if re.search(r"\bIT[0-7]\b", text, re.IGNORECASE):
        return True
    if re.search(r"\b[Hh][0-7]\b", text):
        return True
    if re.search(r"Ra\s*0\.[0-8]\b", text, re.IGNORECASE):
        return True
    return any(token in text for token in ("圆度", "圆柱度", "同轴度", "跳动", "位置度", "精密", "高精度"))


def _feature_family_hits(features: list[str]) -> set[str]:
    text = " ".join(features)
    hits: set[str] = set()
    if any(token in text for token in ("孔", "铰孔", "精孔", "顶尖孔")):
        hits.add("hole")
    if any(token in text for token in ("外圆", "圆柱")):
        hits.add("outer")
    if any(token in text for token in ("端面", "平端面")):
        hits.add("face")
    if any(token in text for token in ("槽", "键", "花键")):
        hits.add("slot")
    if any(token in text for token in ("扁", "平面")):
        hits.add("flat")
    return hits


def _extract_rule_package_inputs(
    inputs: dict[str, object],
    *,
    to_bool: BoolParser,
    to_float: FloatParser,
) -> dict[str, object]:
    material_grade = (
        inputs.get("material_grade")
        or inputs.get("material")
        or inputs.get("材料牌号")
        or inputs.get("材料")
        or ""
    )
    cad_features = _as_text_list(
        inputs.get("cad_features")
        or inputs.get("features")
        or inputs.get("feature_types")
        or inputs.get("特征")
    )
    if to_bool(inputs.get("has_hole")) and not any("孔" in item for item in cad_features):
        cad_features.append("普通孔/辅助孔")
    if to_bool(inputs.get("has_spline")) and not any(("槽" in item or "键" in item or "扁" in item) for item in cad_features):
        cad_features.append("槽类特征")

    precision_grades = _as_text_list(
        inputs.get("precision_grades")
        or inputs.get("precision")
        or inputs.get("加工精度等级")
    )
    roughness = to_float(inputs.get("roughness"))
    if roughness is not None:
        precision_grades.append(f"Ra{roughness:g}")

    requirements = _as_text_list(
        inputs.get("requirements")
        or inputs.get("requirement")
        or inputs.get("special_requirements")
        or inputs.get("special_requirement")
        or inputs.get("surface_requirements")
        or inputs.get("技术要求")
        or inputs.get("特殊要求")
    )
    return {
        "material_grade": str(material_grade or "").strip(),
        "cad_features": cad_features,
        "precision_grades": precision_grades,
        "requirements": requirements,
    }


def _build_runtime_inputs_for_process_rules(
    inputs: dict[str, object],
    *,
    to_bool: BoolParser,
    to_float: FloatParser,
) -> dict[str, object]:
    package_inputs = _extract_rule_package_inputs(inputs, to_bool=to_bool, to_float=to_float)
    cad_features = list(package_inputs.get("cad_features") or [])
    precision_grades = list(package_inputs.get("precision_grades") or [])
    requirements = list(package_inputs.get("requirements") or [])
    requirement_text = " ".join(requirements)
    derived_roughness = _extract_min_roughness_from_precision(precision_grades)
    return {
        **inputs,
        "material": str(package_inputs.get("material_grade") or "").strip(),
        "material_grade": str(package_inputs.get("material_grade") or "").strip(),
        "cad_features": cad_features,
        "precision_grades": precision_grades,
        "requirements": requirements,
        "has_hole": any("孔" in item for item in cad_features),
        "has_spline": any(("槽" in item or "键" in item or "扁" in item) for item in cad_features),
        "roughness": derived_roughness if derived_roughness is not None else inputs.get("roughness"),
        "need_trace": any(token in requirement_text for token in ("标记", "标印", "追溯")),
        "need_mt": any(token in requirement_text for token in ("磁粉", "磁粉检查")),
        "need_burn_check": any(token in requirement_text for token in ("烧伤", "烧伤检查")),
    }


def _match_process_trigger_rule(
    rule: dict[str, object],
    runtime_inputs: dict[str, object],
    *,
    parse_factor_condition: FactorParser,
    matches_factor_condition: FactorMatcher,
) -> tuple[bool, list[str]]:
    factor_values = _as_text_list(rule.get("internal_factors"))
    executable_factors: list[str] = []
    for factor in factor_values:
        if not factor or factor in NON_EXECUTABLE_TRIGGER_FACTORS:
            continue
        parsed = parse_factor_condition(factor)
        if not parsed or parsed.get("operator") == "raw":
            continue
        executable_factors.append(factor)

    if not executable_factors:
        return False, []

    reasons: list[str] = []
    for factor_name in executable_factors:
        matched, reason = matches_factor_condition(factor_name, runtime_inputs, str(rule.get("process_name") or ""))
        if not matched:
            return False, []
        if reason:
            reasons.append(reason)
    return True, reasons


def _process_ids_for_names(process_names: list[str], catalog_segments: list[dict[str, object]]) -> set[str]:
    selected: set[str] = set()
    for process_name in process_names:
        for segment in catalog_segments:
            catalog_name = str(segment.get("process_name") or "").strip()
            if _text_matches(process_name, [catalog_name]):
                process_id = str(segment.get("process_id") or "").strip()
                if process_id:
                    selected.add(process_id)
    return selected


def _match_material_rule(rule: dict[str, object], package_inputs: dict[str, object]) -> bool:
    when = rule.get("when")
    if not isinstance(when, dict):
        return False
    material = str(package_inputs.get("material_grade") or "").strip()
    requirements = list(package_inputs.get("requirements") or [])
    features = list(package_inputs.get("cad_features") or [])
    precision = list(package_inputs.get("precision_grades") or [])
    context_values = [material, *requirements, *features, *precision]

    for key, expected in when.items():
        if key == "material_grade":
            if not _text_matches(expected, [material]):
                return False
        elif not _text_matches(expected, context_values):
            return False
    return True


def _match_feature_rule(rule: dict[str, object], package_inputs: dict[str, object]) -> bool:
    when = rule.get("when")
    if not isinstance(when, dict):
        return False
    features = list(package_inputs.get("cad_features") or [])
    expected = when.get("cad_feature") or when.get("feature")
    return _text_matches(expected, features)


def _match_precision_rule(rule: dict[str, object], package_inputs: dict[str, object], process_names: list[str]) -> bool:
    when = rule.get("when")
    if not isinstance(when, dict):
        return False
    precision_values = list(package_inputs.get("precision_grades") or [])
    expected = when.get("precision_requirement") or when.get("precision_grade")
    if _text_matches(expected, precision_values):
        return True
    if not _high_precision_signal(precision_values):
        return False

    feature_hits = _feature_family_hits(list(package_inputs.get("cad_features") or []))
    target_text = " ".join([str(expected or ""), *process_names])
    if any(token in target_text for token in ("孔", "珩孔", "研孔")):
        return "hole" in feature_hits
    if any(token in target_text for token in ("外圆", "研外圆")):
        return "outer" in feature_hits
    if "端面" in target_text:
        return "face" in feature_hits
    if "槽" in target_text:
        return "slot" in feature_hits
    return False


def _match_special_requirement_rule(rule: dict[str, object], package_inputs: dict[str, object]) -> bool:
    when = rule.get("when")
    if not isinstance(when, dict):
        return False
    requirements = list(package_inputs.get("requirements") or [])
    expected = when.get("special_requirement") or when.get("requirement")
    return _text_matches(expected, requirements)


def generate_steps_from_finalized_rule_package(
    package: FinalizedRulePackage,
    inputs: dict[str, object],
    *,
    collapse_quality_gates: QualityGateCollapser,
    parse_factor_condition: FactorParser,
    matches_factor_condition: FactorMatcher,
    to_bool: BoolParser,
    to_float: FloatParser,
) -> tuple[list[RouteStep], str] | None:
    route_catalog = _json_dict(package.route_catalog_json)
    route_rules = _json_dict(package.route_rules_json)
    catalog_segments = route_catalog.get("segments")
    if not isinstance(catalog_segments, list) or not catalog_segments:
        return None

    normalized_segments = [
        segment for segment in catalog_segments
        if isinstance(segment, dict) and str(segment.get("process_id") or "").strip()
    ]
    if not normalized_segments:
        return None

    package_inputs = _extract_rule_package_inputs(inputs, to_bool=to_bool, to_float=to_float)
    runtime_inputs = _build_runtime_inputs_for_process_rules(inputs, to_bool=to_bool, to_float=to_float)
    selected_process_ids: set[str] = set()
    selected_reasons: dict[str, str] = {}

    for segment in normalized_segments:
        process_id = str(segment.get("process_id") or "").strip()
        if bool(segment.get("main")):
            selected_process_ids.add(process_id)
            selected_reasons.setdefault(process_id, "主线工序")

    process_trigger_rules = route_rules.get("process_trigger_rules")
    if isinstance(process_trigger_rules, list):
        for rule in process_trigger_rules:
            if not isinstance(rule, dict):
                continue
            process_id = str(rule.get("process_id") or "").strip()
            if not process_id or bool(rule.get("main")):
                continue
            matched, reasons = _match_process_trigger_rule(
                rule,
                runtime_inputs,
                parse_factor_condition=parse_factor_condition,
                matches_factor_condition=matches_factor_condition,
            )
            if not matched:
                continue
            selected_process_ids.add(process_id)
            selected_reasons.setdefault(
                process_id,
                "；".join(reasons) if reasons else str(rule.get("condition_text") or "").strip() or "定稿规则命中",
            )

    material_rules = route_rules.get("material_rules")
    if isinstance(material_rules, list):
        for rule in material_rules:
            if not isinstance(rule, dict) or not _match_material_rule(rule, package_inputs):
                continue
            targets = _as_text_list(rule.get("then"))
            for process_id in _process_ids_for_names(targets, normalized_segments):
                selected_process_ids.add(process_id)
                selected_reasons.setdefault(process_id, "材料规则命中")

    feature_rules = route_rules.get("feature_rules")
    if isinstance(feature_rules, list):
        for rule in feature_rules:
            if not isinstance(rule, dict) or not _match_feature_rule(rule, package_inputs):
                continue
            targets = _as_text_list(rule.get("then"))
            for process_id in _process_ids_for_names(targets, normalized_segments):
                selected_process_ids.add(process_id)
                selected_reasons.setdefault(process_id, "CAD特征规则命中")

    precision_rules = route_rules.get("precision_rules")
    if isinstance(precision_rules, list):
        for rule in precision_rules:
            if not isinstance(rule, dict):
                continue
            targets = _as_text_list(rule.get("then"))
            if not _match_precision_rule(rule, package_inputs, targets):
                continue
            for process_id in _process_ids_for_names(targets, normalized_segments):
                selected_process_ids.add(process_id)
                selected_reasons.setdefault(process_id, "加工精度规则命中")

    special_requirement_rules = route_rules.get("special_requirement_rules")
    if isinstance(special_requirement_rules, list):
        for rule in special_requirement_rules:
            if not isinstance(rule, dict) or not _match_special_requirement_rule(rule, package_inputs):
                continue
            targets = _as_text_list(rule.get("then"))
            for process_id in _process_ids_for_names(targets, normalized_segments):
                selected_process_ids.add(process_id)
                selected_reasons.setdefault(process_id, "特殊要求规则命中")

    steps: list[RouteStep] = []
    for segment in sorted(normalized_segments, key=lambda item: (int(item.get("sequence") or 0), str(item.get("process_id") or ""))):
        process_id = str(segment.get("process_id") or "").strip()
        if process_id not in selected_process_ids:
            continue
        steps.append(
            RouteStep(
                process_id=process_id,
                sequence=int(segment.get("sequence") or 0) or None,
                name=str(segment.get("process_name") or "").strip(),
                op_type="MAIN" if bool(segment.get("main")) else "BRANCH",
                reason=selected_reasons.get(process_id, "规则包命中"),
                process_steps=_extract_catalog_process_steps(segment),
            )
        )

    if not steps:
        return None
    return (
        collapse_quality_gates(steps),
        f"已基于第4步规则包 V{package.version} 生成路线",
    )
