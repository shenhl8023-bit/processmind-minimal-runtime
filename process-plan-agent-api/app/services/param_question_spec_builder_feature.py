"""参数确认问题规格构造器中的结构特征类问题。"""

from __future__ import annotations

from app.schemas.schemas import ParamConfirmOptionOut, ParamReviewedFactorOut
from app.services.param_option_counter import (
    build_feature_detail_options_with_snapshot_fallback as _build_feature_detail_options_with_snapshot_fallback,
    count_category_matches as _count_category_matches,
)
from app.services.param_question_option_builder import (
    counter_or_fallback_param_options as _counter_or_fallback_param_options,
    finalize_param_question_spec as _finalize_param_question_spec,
    finalize_seeded_param_question_spec as _finalize_seeded_param_question_spec,
    tree_or_default_param_options as _tree_or_default_param_options,
)
from app.services.param_question_option_seed import family_scoped_root_options as _family_scoped_root_options
from app.services.param_question_tree_config import tree_node_question as _tree_node_question


def _build_feature_param_question_spec(
    *,
    category: str,
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    rows: list[dict[str, str]],
    seeded_options: list[ParamConfirmOptionOut],
) -> tuple[str, str, list[ParamConfirmOptionOut]] | None:
    if category == "slot_structure":
        options = [
            ParamConfirmOptionOut(value="slot::回转槽类", label="回转槽类", count=0),
            ParamConfirmOptionOut(value="slot::直槽/键槽类", label="直槽/键槽类", count=0),
            ParamConfirmOptionOut(value="slot::凹槽/通槽类", label="凹槽/通槽类", count=0),
            ParamConfirmOptionOut(value="slot::高精度槽/密封槽", label="高精度槽/密封槽", count=0),
        ]
        prompt = f"先看工序“{step_name}”，如果按槽相关结构判断，它更接近下面哪一种情况？"
        if "磨槽" in step_name:
            prompt = f"先看工序“{step_name}”，如果按高精度槽或密封槽需求判断，它更接近下面哪一种情况？"
        return _finalize_seeded_param_question_spec("slot_structure_select", prompt, options, seeded_options)

    if category == "hole_structure":
        options = [
            ParamConfirmOptionOut(value="hole::普通孔类", label="普通孔类", count=0),
            ParamConfirmOptionOut(value="hole::中心孔类", label="中心孔类", count=0),
            ParamConfirmOptionOut(value="hole::阶梯孔/孔台阶类", label="阶梯孔/孔台阶类", count=0),
            ParamConfirmOptionOut(value="hole::小孔/深长孔类", label="小孔/深长孔类", count=0),
        ]
        return _finalize_seeded_param_question_spec(
            "hole_structure_select",
            f"先看工序“{step_name}”，如果按孔相关结构判断，它更接近下面哪一种情况？",
            options,
            seeded_options,
        )

    if category == "hole_detail":
        options = _build_feature_detail_options_with_snapshot_fallback(
            rows=rows,
            target_factor=target_factor,
            include_tokens=("孔", "中心孔", "通孔", "内孔", "堵头", "台阶孔", "深孔"),
            exclude_tokens=("公差", "粗糙度", "圆跳动", "检验"),
            fallback_labels=["通孔", "内孔", "中心孔", "堵头孔"],
            value_prefix="hole_detail::",
            snapshot_include_tokens=("孔", "中心孔", "通孔", "内孔", "堵头", "台阶", "深孔"),
        )
        return _finalize_seeded_param_question_spec(
            "hole_detail_select",
            f"如果继续细化到孔特征，工序“{step_name}”更接近下面哪一种情况？",
            options,
            seeded_options,
        )

    if category == "generic_structure":
        scoped_options = _family_scoped_root_options(step_name, category)
        if scoped_options:
            return _finalize_param_question_spec(
                "generic_structure_select",
                _tree_node_question("coverage", "coverage_structure_type", f"“{step_name}”这个工序存在的条件，主要依赖以下哪类结构或特征差异？"),
                scoped_options,
            )
        structure_mapping = {
            "孔类特征": ("孔", "孔口", "中心孔"),
            "槽类特征": ("槽", "键槽", "通槽", "环槽"),
            "台阶或端面类特征": ("台阶", "端面"),
            "螺纹类特征": ("螺纹",),
            "回转体或非回转体差异": ("回转", "非回转", "外圆"),
            "中空或实心差异": ("中空", "空心", "实心"),
            "薄壁或厚壁差异": ("薄壁", "厚壁"),
            "基准或定位相关特征": ("基准", "定位"),
        }
        structure_counter = _count_category_matches(rows, structure_mapping)
        options = _counter_or_fallback_param_options(
            counter=structure_counter,
            value_prefix="structure::",
            limit=9,
            tree_branch="coverage",
            tree_node_id="coverage_structure_type",
            seeded_options=seeded_options,
            fallback_options=[
                ParamConfirmOptionOut(value="structure::孔类特征", label="孔类特征", count=0),
                ParamConfirmOptionOut(value="structure::槽类特征", label="槽类特征", count=0),
                ParamConfirmOptionOut(value="structure::台阶或端面类特征", label="台阶/端面类特征", count=0),
                ParamConfirmOptionOut(value="structure::螺纹类特征", label="螺纹类特征", count=0),
                ParamConfirmOptionOut(value="structure::回转体或非回转体差异", label="回转体/非回转体差异", count=0),
                ParamConfirmOptionOut(value="structure::中空或实心差异", label="中空/实心差异", count=0),
                ParamConfirmOptionOut(value="structure::薄壁或厚壁差异", label="薄壁/厚壁差异", count=0),
                ParamConfirmOptionOut(value="structure::基准或定位相关特征", label="基准/定位相关特征", count=0),
                ParamConfirmOptionOut(value="structure::其他结构特征", label="其他结构特征", count=0),
            ],
        )
        return _finalize_param_question_spec(
            "generic_structure_select",
            _tree_node_question("coverage", "coverage_structure_type", f"“{step_name}”这个工序存在的条件，主要依赖以下哪类结构或特征差异？"),
            options,
        )

    if category == "structure_need":
        options = _tree_or_default_param_options("coverage", "coverage_structure_need", [
            ParamConfirmOptionOut(value="structure_need::yes", label="是，没有这些特征时通常不会出现", count=0),
            ParamConfirmOptionOut(value="structure_need::partial", label="不完全是，还要结合别的条件", count=0),
            ParamConfirmOptionOut(value="structure_need::unknown", label="当前还不确定", count=0),
        ])
        return _finalize_seeded_param_question_spec(
            "structure_need_select",
            _tree_node_question("coverage", "coverage_structure_need", f"如果没有当前这类结构或特征，工序“{step_name}”通常还会出现吗？"),
            options,
            seeded_options,
        )

    if category == "slot_detail":
        options = _build_feature_detail_options_with_snapshot_fallback(
            rows=rows,
            target_factor=target_factor,
            include_tokens=("槽", "键", "花键", "扁", "环槽", "通槽", "凹槽", "密封"),
            exclude_tokens=("粗糙度", "公差", "圆跳动", "检验"),
            fallback_labels=["键槽", "环槽", "通槽", "凹槽", "密封槽"],
            value_prefix="slot_detail::",
        )
        return _finalize_seeded_param_question_spec(
            "slot_detail_select",
            f"如果继续细化到槽或相关结构，工序“{step_name}”更接近下面哪一种情况？",
            options,
            seeded_options,
        )

    if category == "manufacturability":
        options = [
            ParamConfirmOptionOut(value="mfg::型孔/特殊开口", label="存在型孔/特殊开口", count=0),
            ParamConfirmOptionOut(value="mfg::特殊尖边质量要求", label="需要保证特殊尖边质量", count=0),
            ParamConfirmOptionOut(value="mfg::常规方法难以直接完成", label="常规加工方式难以直接完成", count=0),
        ]
        return _finalize_seeded_param_question_spec(
            "manufacturability_select",
            f"先看工序“{step_name}”，如果按可加工性限制判断，它更接近下面哪一种情况？",
            options,
            seeded_options,
        )

    if category == "stress_risk":
        options = [
            ParamConfirmOptionOut(value="risk::热处理变形风险", label="热处理变形风险", count=0),
            ParamConfirmOptionOut(value="risk::机加应力风险", label="机加应力风险", count=0),
            ParamConfirmOptionOut(value="risk::长径比较大/细长件", label="长径比较大/细长件", count=0),
        ]
        return _finalize_seeded_param_question_spec(
            "stress_risk_select",
            f"先看工序“{step_name}”，如果按变形或应力风险判断，它更接近下面哪一种情况？",
            options,
            seeded_options,
        )

    return None


__all__ = ["_build_feature_param_question_spec"]
