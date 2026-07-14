"""参数确认问题规格构造器中的兜底与多因素类问题。"""

from __future__ import annotations

from app.schemas.schemas import ParamConfirmOptionOut, ParamReviewedFactorOut
from app.services.param_question_option_builder import (
    finalize_param_question_spec as _finalize_param_question_spec,
    finalize_seeded_param_question_spec as _finalize_seeded_param_question_spec,
    root_reason_options_for_step as _root_reason_options_for_step,
    tree_or_default_param_options as _tree_or_default_param_options,
)
from app.services.param_question_tree_config import (
    tree_node_options as _tree_node_options,
    tree_node_question as _tree_node_question,
)


def _build_misc_param_question_spec(
    *,
    category: str,
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    seeded_options: list[ParamConfirmOptionOut],
) -> tuple[str, str, list[ParamConfirmOptionOut]] | None:
    if category == "multi_factor":
        options = _tree_or_default_param_options("coverage", "coverage_multi_pair", [
            ParamConfirmOptionOut(value="multi::材质+结构", label="材质 + 结构", count=0),
            ParamConfirmOptionOut(value="multi::材质+尺寸", label="材质 + 尺寸", count=0),
            ParamConfirmOptionOut(value="multi::材质+要求", label="材质 + 加工要求", count=0),
            ParamConfirmOptionOut(value="multi::结构+尺寸", label="结构 + 尺寸", count=0),
            ParamConfirmOptionOut(value="multi::结构+要求", label="结构 + 加工要求", count=0),
            ParamConfirmOptionOut(value="multi::尺寸+要求", label="尺寸 + 加工要求", count=0),
            ParamConfirmOptionOut(value="multi::毛坯+结构", label="毛坯 + 结构", count=0),
            ParamConfirmOptionOut(value="multi::毛坯+尺寸", label="毛坯 + 尺寸", count=0),
        ])
        return _finalize_seeded_param_question_spec(
            "multi_factor_select",
            _tree_node_question("coverage", "coverage_multi_pair", f"工序“{step_name}”如果不是由单一因素决定，当前最主要的两个因素更接近哪一组？"),
            options,
            seeded_options,
        )

    if category == "multi_primary":
        pair_text = str(target_factor.expected_value or "").strip()
        parts = [part.strip() for part in pair_text.split("+") if part.strip()]
        first_label = parts[0] if len(parts) >= 1 else "前一个因素"
        second_label = parts[1] if len(parts) >= 2 else "后一个因素"
        options = _tree_node_options("coverage", "coverage_multi_primary")
        if not options:
            options = [
                ParamConfirmOptionOut(value="multi_primary::first", label=f"{first_label}更像主因素", count=0),
                ParamConfirmOptionOut(value="multi_primary::second", label=f"{second_label}更像主因素", count=0),
                ParamConfirmOptionOut(value="multi_primary::both", label="两个因素缺一不可", count=0),
                ParamConfirmOptionOut(value="multi_primary::unknown", label="当前还不能确定", count=0),
            ]
        return _finalize_seeded_param_question_spec(
            "multi_primary_select",
            _tree_node_question("coverage", "coverage_multi_primary", f"在当前这组联合因素里，工序“{step_name}”更接近由哪个因素主导？"),
            options,
            seeded_options,
        )

    if category == "uncertain":
        options = _tree_or_default_param_options("coverage", "coverage_uncertain_missing", [
            ParamConfirmOptionOut(value="missing::material", label="材质信息缺失", count=0),
            ParamConfirmOptionOut(value="missing::size", label="尺寸信息缺失", count=0),
            ParamConfirmOptionOut(value="missing::structure", label="结构信息缺失", count=0),
            ParamConfirmOptionOut(value="missing::blank", label="毛坯信息缺失", count=0),
            ParamConfirmOptionOut(value="missing::requirement", label="图纸/要求信息缺失", count=0),
            ParamConfirmOptionOut(value="missing::sample_count", label="样本数量不足", count=0),
            ParamConfirmOptionOut(value="missing::sample_bias", label="样本分布不均", count=0),
        ])
        return _finalize_seeded_param_question_spec(
            "missing_info_select",
            _tree_node_question("coverage", "coverage_uncertain_missing", f"对于工序“{step_name}”，当前最缺少哪一类信息？"),
            options,
            seeded_options,
        )

    if category == "root":
        options = _root_reason_options_for_step(step_name, seeded_options)
        return _finalize_param_question_spec(
            "generic_reason_select",
            _tree_node_question("coverage", "coverage_reason_root", f"想先确认一下：工序“{step_name}”存在的条件主要依赖以下哪类因素？"),
            options,
        )

    return None


__all__ = ["_build_misc_param_question_spec"]
