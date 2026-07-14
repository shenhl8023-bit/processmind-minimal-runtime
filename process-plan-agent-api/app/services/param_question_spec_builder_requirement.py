"""参数确认问题规格构造器中的要求/尺寸/毛坯类问题。"""

from __future__ import annotations

from app.schemas.schemas import ParamConfirmOptionOut
from app.services.param_option_counter import (
    count_attr_values_by_key_tokens as _count_attr_values_by_key_tokens,
    count_category_matches as _count_category_matches,
    count_positive_attr_labels as _count_positive_attr_labels,
)
from app.services.param_question_option_builder import (
    counter_or_fallback_param_options as _counter_or_fallback_param_options,
    finalize_param_question_spec as _finalize_param_question_spec,
    finalize_seeded_param_question_spec as _finalize_seeded_param_question_spec,
    tree_or_default_param_options as _tree_or_default_param_options,
)
from app.services.param_question_option_seed import family_scoped_root_options as _family_scoped_root_options
from app.services.param_question_tree_config import tree_node_question as _tree_node_question


def _build_requirement_size_blank_param_question_spec(
    *,
    category: str,
    step_name: str,
    rows: list[dict[str, str]],
    seeded_options: list[ParamConfirmOptionOut],
) -> tuple[str, str, list[ParamConfirmOptionOut]] | None:
    if category == "precision":
        scoped_options = _family_scoped_root_options(step_name, category)
        if scoped_options:
            return _finalize_param_question_spec(
                "precision_select",
                f"工序“{step_name}”更接近由哪一类加工要求差异触发？",
                scoped_options,
            )
        precision_counter = _count_positive_attr_labels(rows, ("配套", "粗糙度", "公差", "跳动", "圆柱度", "同轴度"))
        options = _counter_or_fallback_param_options(
            counter=precision_counter,
            value_prefix="precision::",
            seeded_options=seeded_options,
            fallback_options=[
                ParamConfirmOptionOut(value="precision::配套外圆要求", label="配套外圆要求", count=0),
                ParamConfirmOptionOut(value="precision::配套内孔要求", label="配套内孔要求", count=0),
                ParamConfirmOptionOut(value="precision::更高表面质量要求", label="更高表面质量要求", count=0),
                ParamConfirmOptionOut(value="precision::更高尺寸精度要求", label="更高尺寸精度要求", count=0),
                ParamConfirmOptionOut(value="precision::更高形位精度要求", label="更高形位精度要求", count=0),
            ],
        )
        return _finalize_param_question_spec(
            "precision_select",
            f"工序“{step_name}”更接近由哪一类加工要求差异触发？",
            options,
        )

    if category == "size":
        scoped_options = _family_scoped_root_options(step_name, category)
        if scoped_options:
            return _finalize_param_question_spec(
                "size_select",
                _tree_node_question("coverage", "coverage_size_type", f"工序“{step_name}”主要是由哪一种尺寸或尺度边界在起作用？"),
                scoped_options,
            )
        size_mapping = {
            "直径": ("直径", "外圆", "内径"),
            "长度": ("长度", "总长"),
            "壁厚": ("壁厚", "薄壁", "厚壁"),
            "孔径": ("孔径", "孔直径"),
            "最大截面": ("截面",),
            "长径比": ("长径比", "细长"),
            "总体尺寸": ("外形尺寸", "总体尺寸"),
        }
        size_counter = _count_category_matches(rows, size_mapping)
        options = _counter_or_fallback_param_options(
            counter=size_counter,
            value_prefix="size::",
            limit=7,
            tree_branch="coverage",
            tree_node_id="coverage_size_type",
            seeded_options=seeded_options,
            fallback_options=[
                ParamConfirmOptionOut(value="size::直径", label="直径", count=0),
                ParamConfirmOptionOut(value="size::长度", label="长度", count=0),
                ParamConfirmOptionOut(value="size::壁厚", label="壁厚", count=0),
                ParamConfirmOptionOut(value="size::孔径", label="孔径", count=0),
                ParamConfirmOptionOut(value="size::最大截面", label="最大截面", count=0),
                ParamConfirmOptionOut(value="size::长径比", label="长径比", count=0),
                ParamConfirmOptionOut(value="size::总体尺寸", label="总体尺寸", count=0),
            ],
        )
        return _finalize_param_question_spec(
            "size_select",
            _tree_node_question("coverage", "coverage_size_type", f"工序“{step_name}”主要是由哪一种尺寸或尺度边界在起作用？"),
            options,
        )

    if category == "size_boundary":
        options = _tree_or_default_param_options("coverage", "coverage_size_boundary", [
            ParamConfirmOptionOut(value="size_boundary::clear", label="有明确分界", count=0),
            ParamConfirmOptionOut(value="size_boundary::trend", label="只有大致趋势", count=0),
            ParamConfirmOptionOut(value="size_boundary::unknown", label="还没有总结出来", count=0),
        ])
        return _finalize_seeded_param_question_spec(
            "size_boundary_select",
            _tree_node_question("coverage", "coverage_size_boundary", f"围绕工序“{step_name}”当前这类尺寸边界，是否已经能总结出一个大致分界？"),
            options,
            seeded_options,
        )

    if category == "blank":
        scoped_options = _family_scoped_root_options(step_name, category)
        if scoped_options:
            return _finalize_param_question_spec(
                "blank_select",
                _tree_node_question("coverage", "coverage_blank_type", f"工序“{step_name}”是否主要由毛坯或来料状态差异决定？如果是，更接近哪一种？"),
                scoped_options,
            )
        blank_counter = _count_attr_values_by_key_tokens(rows, ("毛坯", "来料", "棒料", "锻件", "铸件", "管料", "板料"))
        options = _counter_or_fallback_param_options(
            counter=blank_counter,
            value_prefix="blank::",
            limit=10,
            tree_branch="coverage",
            tree_node_id="coverage_blank_type",
            seeded_options=seeded_options,
            fallback_options=[
                ParamConfirmOptionOut(value="blank::棒料", label="棒料", count=0),
                ParamConfirmOptionOut(value="blank::管料", label="管料", count=0),
                ParamConfirmOptionOut(value="blank::板料", label="板料", count=0),
                ParamConfirmOptionOut(value="blank::锻件", label="锻件", count=0),
                ParamConfirmOptionOut(value="blank::铸件", label="铸件", count=0),
                ParamConfirmOptionOut(value="blank::采购成品料", label="采购成品料", count=0),
            ],
        )
        return _finalize_param_question_spec(
            "blank_select",
            _tree_node_question("coverage", "coverage_blank_type", f"工序“{step_name}”是否主要由毛坯或来料状态差异决定？如果是，更接近哪一种？"),
            options,
        )

    if category == "blank_need":
        options = _tree_or_default_param_options("coverage", "coverage_blank_need", [
            ParamConfirmOptionOut(value="blank_need::yes", label="这种状态下通常需要", count=0),
            ParamConfirmOptionOut(value="blank_need::partial", label="不完全是，还要看别的条件", count=0),
            ParamConfirmOptionOut(value="blank_need::unknown", label="当前还不确定", count=0),
        ])
        return _finalize_seeded_param_question_spec(
            "blank_need_select",
            _tree_node_question("coverage", "coverage_blank_need", f"在当前这类毛坯或来料状态下，工序“{step_name}”是否通常需要保留？"),
            options,
            seeded_options,
        )

    if category == "requirement":
        scoped_options = _family_scoped_root_options(step_name, category)
        if scoped_options:
            return _finalize_param_question_spec(
                "requirement_select",
                _tree_node_question("coverage", "coverage_requirement_type", f"工序“{step_name}”更接近由哪一类要求差异触发？"),
                scoped_options,
            )
        requirement_mapping = {
            "尺寸精度": ("尺寸精度", "尺寸公差", "定尺寸"),
            "形位公差": ("形位", "同轴度", "圆柱度", "跳动", "位置度"),
            "粗糙度": ("粗糙度",),
            "表面质量": ("表面质量", "表面完整性"),
            "热处理后性能": ("硬度", "强度", "热处理后", "组织"),
            "装配配合": ("配合", "装配"),
            "检测试验": ("检验", "检测", "试验"),
        }
        requirement_counter = _count_category_matches(rows, requirement_mapping, positive_only=False)
        options = _counter_or_fallback_param_options(
            counter=requirement_counter,
            value_prefix="requirement::",
            limit=7,
            tree_branch="coverage",
            tree_node_id="coverage_requirement_type",
            seeded_options=seeded_options,
            fallback_options=[
                ParamConfirmOptionOut(value="requirement::尺寸精度", label="尺寸精度要求", count=0),
                ParamConfirmOptionOut(value="requirement::形位公差", label="形位公差要求", count=0),
                ParamConfirmOptionOut(value="requirement::粗糙度", label="粗糙度要求", count=0),
                ParamConfirmOptionOut(value="requirement::表面质量", label="表面质量要求", count=0),
                ParamConfirmOptionOut(value="requirement::热处理后性能", label="热处理后性能要求", count=0),
                ParamConfirmOptionOut(value="requirement::装配配合", label="装配配合要求", count=0),
                ParamConfirmOptionOut(value="requirement::检测试验", label="检测/试验要求", count=0),
            ],
        )
        return _finalize_param_question_spec(
            "requirement_select",
            _tree_node_question("coverage", "coverage_requirement_type", f"工序“{step_name}”更接近由哪一类要求差异触发？"),
            options,
        )

    if category == "requirement_need":
        options = _tree_or_default_param_options("coverage", "coverage_requirement_need", [
            ParamConfirmOptionOut(value="requirement_need::yes", label="只有要求更高的样本才会增加", count=0),
            ParamConfirmOptionOut(value="requirement_need::partial", label="不完全是，还要结合别的条件", count=0),
            ParamConfirmOptionOut(value="requirement_need::unknown", label="当前还不确定", count=0),
        ])
        return _finalize_seeded_param_question_spec(
            "requirement_need_select",
            _tree_node_question("coverage", "coverage_requirement_need", f"工序“{step_name}”是否主要出现在要求更高的样本里？"),
            options,
            seeded_options,
        )

    return None


__all__ = ["_build_requirement_size_blank_param_question_spec"]
