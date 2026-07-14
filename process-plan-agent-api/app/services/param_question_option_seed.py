"""
参数问答选项种子工具。

这里集中处理知识切片补充选项和选项去重合并，避免 generate.py
同时承担 API、问答构造和知识辅助选项三类职责。
"""
from __future__ import annotations

import json
import os

from app.core.paths import ROUTE_RULE_KNOWLEDGE_DIR
from app.schemas.schemas import ParamConfirmOptionOut
from app.services.param_question_strategy import param_operation_family


KNOWLEDGE_SLICE_FILE = "07_高精度配合回转件通用基础知识_切片.json"
KNOWLEDGE_SLICE_CACHE: list[dict[str, object]] = []


def merge_param_options(primary: list[ParamConfirmOptionOut], seeded: list[ParamConfirmOptionOut]) -> list[ParamConfirmOptionOut]:
    merged: list[ParamConfirmOptionOut] = []
    seen: set[str] = set()
    for option in [*primary, *seeded]:
        if option.value in seen:
            continue
        seen.add(option.value)
        merged.append(option)
    return merged


def is_outer_profile_step(step_name: str) -> bool:
    text = (step_name or "").strip()
    return "车外形" in text or text == "外形"


def load_param_knowledge_slice_chunks() -> list[dict[str, object]]:
    global KNOWLEDGE_SLICE_CACHE
    if KNOWLEDGE_SLICE_CACHE:
        return list(KNOWLEDGE_SLICE_CACHE)
    filepath = os.path.join(ROUTE_RULE_KNOWLEDGE_DIR, KNOWLEDGE_SLICE_FILE)
    if not os.path.isfile(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []
    chunks = payload.get("chunks") if isinstance(payload, dict) else None
    if not isinstance(chunks, list):
        return []
    KNOWLEDGE_SLICE_CACHE = [item for item in chunks if isinstance(item, dict)]
    return list(KNOWLEDGE_SLICE_CACHE)


def param_knowledge_chunk_ids(step_name: str, category: str) -> set[str]:
    family = param_operation_family(step_name)
    tags_map: dict[tuple[str, str], tuple[str, ...]] = {
        ("heat", "material"): ("材料", "热处理", "工艺分化"),
        ("heat", "heat_treatment"): ("材料", "热处理", "工艺分化"),
        ("heat", "precision"): ("精度", "定尺寸"),
        ("hole", "hole_structure"): ("孔结构", "通孔", "盲孔", "台阶孔", "可达性"),
        ("hole", "hole_detail"): ("孔结构", "通孔", "盲孔", "台阶孔", "可达性"),
        ("hole", "precision"): ("内孔", "镗孔", "铰孔", "磨孔", "珩孔", "定尺寸"),
        ("finish", "precision"): ("外圆", "磨削", "研磨", "定尺寸"),
        ("finish", "generic_structure"): ("外圆", "主线工艺"),
        ("outer_surface", "precision"): ("外圆", "磨削", "研磨", "定尺寸"),
        ("outer_surface", "generic_structure"): ("外圆", "主线工艺"),
    }
    wanted_tags = tags_map.get((family, category)) or ()
    if not wanted_tags:
        return set()
    chunk_ids: set[str] = set()
    for chunk in load_param_knowledge_slice_chunks():
        tags = [str(tag).strip() for tag in chunk.get("tags", []) if str(tag).strip()]
        haystack = " ".join([str(chunk.get("title") or ""), str(chunk.get("text") or ""), *tags])
        if any(tag in haystack for tag in wanted_tags):
            chunk_ids.add(str(chunk.get("chunk_id") or "").strip())
    return chunk_ids


def knowledge_seed_param_options(step_name: str, category: str) -> list[ParamConfirmOptionOut]:
    family = param_operation_family(step_name)
    chunk_ids = param_knowledge_chunk_ids(step_name, category)

    if family == "hole" and category in {"hole_structure", "hole_detail"}:
        options = [
            ParamConfirmOptionOut(value="hole_detail::通孔", label="通孔", count=0),
            ParamConfirmOptionOut(value="hole_detail::盲孔", label="盲孔", count=0),
            ParamConfirmOptionOut(value="hole_detail::中心孔", label="中心孔", count=0),
            ParamConfirmOptionOut(value="hole_detail::阶梯孔/孔台阶", label="阶梯孔/孔台阶", count=0),
        ]
        if "gprk-07" in chunk_ids:
            options.extend([
                ParamConfirmOptionOut(value="hole_detail::深孔/长孔", label="深孔/长孔", count=0),
                ParamConfirmOptionOut(value="hole_detail::可达性受限孔", label="可达性受限孔", count=0),
            ])
        return options

    if family == "hole" and category == "precision":
        return [
            ParamConfirmOptionOut(value="precision::孔径尺寸精度要求高", label="孔径尺寸精度要求高", count=0),
            ParamConfirmOptionOut(value="precision::孔圆度/圆柱度/位置精度要求高", label="孔圆度/圆柱度/位置精度要求高", count=0),
            ParamConfirmOptionOut(value="precision::孔表面质量要求高", label="孔表面质量要求高", count=0),
            ParamConfirmOptionOut(value="precision::关键配合孔定尺寸", label="关键配合孔定尺寸", count=0),
        ]

    if family in {"finish", "outer_surface"} and category == "precision":
        return [
            ParamConfirmOptionOut(value="precision::外圆尺寸精度要求高", label="外圆尺寸精度要求高", count=0),
            ParamConfirmOptionOut(value="precision::圆度/圆柱度/跳动要求高", label="圆度/圆柱度/跳动要求高", count=0),
            ParamConfirmOptionOut(value="precision::关键配合外圆定尺寸", label="关键配合外圆定尺寸", count=0),
            ParamConfirmOptionOut(value="precision::最终光整或研磨要求", label="最终光整或研磨要求", count=0),
        ]

    if family == "end_face" and category == "generic_structure":
        return [
            ParamConfirmOptionOut(value="structure::端面基准类", label="端面基准类", count=0),
            ParamConfirmOptionOut(value="structure::台阶端面类", label="台阶端面类", count=0),
            ParamConfirmOptionOut(value="structure::贴合端面类", label="贴合端面类", count=0),
            ParamConfirmOptionOut(value="structure::孔口端面类", label="孔口端面类", count=0),
        ]

    if family == "chamfer" and category == "generic_structure":
        return [
            ParamConfirmOptionOut(value="structure::外圆边缘类", label="外圆边缘类", count=0),
            ParamConfirmOptionOut(value="structure::孔口倒角类", label="孔口倒角类", count=0),
            ParamConfirmOptionOut(value="structure::锐边保护类", label="锐边保护类", count=0),
            ParamConfirmOptionOut(value="structure::装配导入类", label="装配导入类", count=0),
        ]

    if family == "outer_surface" and category == "generic_structure":
        if is_outer_profile_step(step_name):
            return [
                ParamConfirmOptionOut(value="structure::外圆类", label="外圆主形面类", count=0),
                ParamConfirmOptionOut(value="structure::回转轮廓类", label="锥面/圆弧/过渡回转面类", count=0),
                ParamConfirmOptionOut(value="structure::局部外形轮廓类", label="局部外形轮廓类", count=0),
            ]
        return [
            ParamConfirmOptionOut(value="structure::外圆类", label="外圆类", count=0),
            ParamConfirmOptionOut(value="structure::台阶外形类", label="台阶外形类", count=0),
            ParamConfirmOptionOut(value="structure::关键配合外圆类", label="关键配合外圆类", count=0),
            ParamConfirmOptionOut(value="structure::基准外圆类", label="基准外圆类", count=0),
        ]

    if family == "heat" and category == "heat_treatment":
        return [
            ParamConfirmOptionOut(value="heat::预处理链分化", label="预处理链分化", count=0),
            ParamConfirmOptionOut(value="heat::终热处理链分化", label="终热处理链分化", count=0),
            ParamConfirmOptionOut(value="heat::热后还需补充精整", label="热后还需补充精整", count=0),
        ]

    return []


FAMILY_SCOPED_OPTION_RULES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "generic_structure": {
        "hole": [
            ("structure::孔类特征", "孔类特征"),
            ("structure::孔口/沉孔/台阶孔类特征", "孔口/沉孔/台阶孔类特征"),
            ("structure::螺纹孔相关特征", "螺纹孔相关特征"),
            ("structure::基准或定位相关特征", "基准/定位相关特征"),
            ("structure::其他结构特征", "其他结构特征"),
        ],
        "slot": [
            ("structure::槽类特征", "槽类特征"),
            ("structure::键槽/扁位类特征", "键槽/扁位类特征"),
            ("structure::环槽/退刀槽类特征", "环槽/退刀槽类特征"),
            ("structure::基准或定位相关特征", "基准/定位相关特征"),
            ("structure::其他结构特征", "其他结构特征"),
        ],
        "heat": [
            ("structure::中空或实心差异", "中空/实心差异"),
            ("structure::薄壁或厚壁差异", "薄壁/厚壁差异"),
            ("structure::回转体或非回转体差异", "回转体/非回转体差异"),
            ("structure::基准或定位相关特征", "基准/定位相关特征"),
            ("structure::其他结构特征", "其他结构特征"),
        ],
        "finish": [
            ("structure::台阶或端面类特征", "台阶/端面类特征"),
            ("structure::回转体或非回转体差异", "回转体/非回转体差异"),
            ("structure::基准或定位相关特征", "基准/定位相关特征"),
            ("structure::中空或实心差异", "中空/实心差异"),
            ("structure::其他结构特征", "其他结构特征"),
        ],
    },
    "size": {
        "end_face": [
            ("size::端面直径", "端面直径"),
            ("size::长度", "长度"),
            ("size::台阶高度/端面距", "台阶高度/端面距"),
            ("size::总体尺寸", "总体尺寸"),
            ("size::其他尺寸", "其他尺寸"),
        ],
        "outer_surface": [
            ("size::直径", "直径"),
            ("size::长度", "长度"),
            ("size::长径比", "长径比"),
            ("size::台阶差/轮廓尺寸", "台阶差/轮廓尺寸"),
            ("size::总体尺寸", "总体尺寸"),
        ],
        "finish": [
            ("size::直径", "直径"),
            ("size::长度", "长度"),
            ("size::长径比", "长径比"),
            ("size::台阶差/轮廓尺寸", "台阶差/轮廓尺寸"),
            ("size::总体尺寸", "总体尺寸"),
        ],
        "hole": [
            ("size::孔径", "孔径"),
            ("size::孔深/长度", "孔深/长度"),
            ("size::壁厚", "壁厚"),
            ("size::孔距/分布尺寸", "孔距/分布尺寸"),
            ("size::总体尺寸", "总体尺寸"),
        ],
        "slot": [
            ("size::槽宽", "槽宽"),
            ("size::槽深", "槽深"),
            ("size::槽长", "槽长"),
            ("size::壁厚", "壁厚"),
            ("size::总体尺寸", "总体尺寸"),
        ],
        "heat": [
            ("size::最大截面", "最大截面"),
            ("size::壁厚", "壁厚"),
            ("size::长径比", "长径比"),
            ("size::总体尺寸", "总体尺寸"),
        ],
    },
    "blank": {
        "end_face": [
            ("blank::棒料", "棒料"),
            ("blank::管料", "管料"),
            ("blank::锻件", "锻件"),
            ("blank::铸件", "铸件"),
            ("blank::采购成品料", "采购成品料"),
            ("blank::其他来料状态", "其他来料状态"),
        ],
        "outer_surface": [
            ("blank::棒料", "棒料"),
            ("blank::管料", "管料"),
            ("blank::锻件", "锻件"),
            ("blank::铸件", "铸件"),
            ("blank::采购成品料", "采购成品料"),
            ("blank::其他来料状态", "其他来料状态"),
        ],
        "finish": [
            ("blank::棒料", "棒料"),
            ("blank::管料", "管料"),
            ("blank::锻件", "锻件"),
            ("blank::铸件", "铸件"),
            ("blank::采购成品料", "采购成品料"),
            ("blank::其他来料状态", "其他来料状态"),
        ],
        "hole": [
            ("blank::棒料", "棒料"),
            ("blank::管料", "管料"),
            ("blank::锻件", "锻件"),
            ("blank::铸件", "铸件"),
            ("blank::采购成品料", "采购成品料"),
            ("blank::其他来料状态", "其他来料状态"),
        ],
        "slot": [
            ("blank::棒料", "棒料"),
            ("blank::管料", "管料"),
            ("blank::锻件", "锻件"),
            ("blank::铸件", "铸件"),
            ("blank::采购成品料", "采购成品料"),
            ("blank::其他来料状态", "其他来料状态"),
        ],
        "chamfer": [
            ("blank::棒料", "棒料"),
            ("blank::管料", "管料"),
            ("blank::锻件", "锻件"),
            ("blank::铸件", "铸件"),
            ("blank::采购成品料", "采购成品料"),
            ("blank::其他来料状态", "其他来料状态"),
        ],
        "heat": [
            ("blank::锻件", "锻件"),
            ("blank::棒料", "棒料"),
            ("blank::管料", "管料"),
            ("blank::铸件", "铸件"),
            ("blank::已热处理来料", "已热处理来料"),
            ("blank::其他来料状态", "其他来料状态"),
        ],
    },
    "requirement": {
        "end_face": [
            ("requirement::尺寸精度", "尺寸精度要求"),
            ("requirement::形位公差", "形位公差要求"),
            ("requirement::粗糙度", "粗糙度要求"),
            ("requirement::表面质量", "表面质量要求"),
            ("requirement::装配配合", "装配配合要求"),
            ("requirement::other", "其他要求"),
        ],
        "outer_surface": [
            ("requirement::尺寸精度", "尺寸精度要求"),
            ("requirement::形位公差", "形位公差要求"),
            ("requirement::粗糙度", "粗糙度要求"),
            ("requirement::表面质量", "表面质量要求"),
            ("requirement::装配配合", "装配配合要求"),
            ("requirement::other", "其他要求"),
        ],
        "finish": [
            ("requirement::尺寸精度", "尺寸精度要求"),
            ("requirement::形位公差", "形位公差要求"),
            ("requirement::粗糙度", "粗糙度要求"),
            ("requirement::表面质量", "表面质量要求"),
            ("requirement::装配配合", "装配配合要求"),
            ("requirement::other", "其他要求"),
        ],
        "hole": [
            ("requirement::孔径尺寸精度", "孔径尺寸精度要求"),
            ("requirement::位置/同轴等形位", "位置/同轴等形位要求"),
            ("requirement::孔表面质量", "孔表面质量要求"),
            ("requirement::装配配合", "装配配合要求"),
            ("requirement::检测试验", "检测/试验要求"),
            ("requirement::other", "其他要求"),
        ],
        "slot": [
            ("requirement::槽宽尺寸精度", "槽宽尺寸精度要求"),
            ("requirement::位置/对称", "位置/对称要求"),
            ("requirement::粗糙度", "粗糙度要求"),
            ("requirement::装配配合", "装配配合要求"),
            ("requirement::检测试验", "检测/试验要求"),
            ("requirement::other", "其他要求"),
        ],
        "heat": [
            ("requirement::热处理后性能", "热处理后性能要求"),
            ("requirement::尺寸稳定性", "尺寸稳定性要求"),
            ("requirement::变形控制", "变形控制要求"),
            ("requirement::检测试验", "检测/试验要求"),
            ("requirement::other", "其他要求"),
        ],
    },
}


def fixed_param_options(rows: list[tuple[str, str]]) -> list[ParamConfirmOptionOut]:
    return [ParamConfirmOptionOut(value=value, label=label, count=0) for value, label in rows]


def family_scoped_root_options(step_name: str, category: str) -> list[ParamConfirmOptionOut]:
    family = param_operation_family(step_name)

    if category == "generic_structure":
        seeded = knowledge_seed_param_options(step_name, category)
        if seeded:
            return merge_param_options(
                list(seeded),
                [ParamConfirmOptionOut(value="structure::其他结构特征", label="其他结构特征", count=0)],
            )
    rows = FAMILY_SCOPED_OPTION_RULES.get(category, {}).get(family)
    if rows:
        return fixed_param_options(rows)
    return []
