"""参数确认问题规格构造器中的材料类问题。"""

from __future__ import annotations

from app.schemas.schemas import ParamConfirmOptionOut
from app.services.param_option_counter import (
    count_attr_values_by_key_tokens as _count_attr_values_by_key_tokens,
    count_attr_values_by_keys as _count_attr_values_by_keys,
)
from app.services.param_question_option_builder import (
    counter_or_fallback_param_options as _counter_or_fallback_param_options,
    finalize_param_question_spec as _finalize_param_question_spec,
    finalize_seeded_param_question_spec as _finalize_seeded_param_question_spec,
    tree_or_default_param_options as _tree_or_default_param_options,
)
from app.services.param_question_tree_config import tree_node_question as _tree_node_question


def _build_material_param_question_spec(
    *,
    category: str,
    step_name: str,
    rows: list[dict[str, str]],
    seeded_options: list[ParamConfirmOptionOut],
) -> tuple[str, str, list[ParamConfirmOptionOut]] | None:
    if category == "material":
        options = _tree_or_default_param_options("coverage", "coverage_material_type", [
            ParamConfirmOptionOut(value="material_basis::class", label="材料大类", count=0),
            ParamConfirmOptionOut(value="material_basis::grade", label="材料牌号", count=0),
            ParamConfirmOptionOut(value="material_basis::heat_state", label="热处理状态", count=0),
            ParamConfirmOptionOut(value="material_basis::mechanical", label="力学性能要求", count=0),
            ParamConfirmOptionOut(value="material_basis::special", label="特殊性能", count=0),
            ParamConfirmOptionOut(value="material_basis::unsure", label="暂时说不清", count=0),
        ])
        return _finalize_seeded_param_question_spec(
            "material_select",
            _tree_node_question("coverage", "coverage_material_type", f"这道工序“{step_name}”的出现，主要是按哪种材料信息区分的？"),
            options,
            seeded_options,
        )

    if category == "material_scope":
        material_counter = _count_attr_values_by_keys(rows, ["零件材质", "材料", "材质"])
        options = _counter_or_fallback_param_options(
            counter=material_counter,
            value_prefix="material::",
            limit=12,
            fallback_options=[
                ParamConfirmOptionOut(value="material::未识别材料1", label="未识别材料1", count=0),
                ParamConfirmOptionOut(value="material::未识别材料2", label="未识别材料2", count=0),
            ],
            seeded_options=seeded_options,
        )
        return _finalize_param_question_spec(
            "material_scope_select",
            _tree_node_question("coverage", "coverage_material_list", f"在当前样本里，哪些材料通常会出现工序“{step_name}”？"),
            options,
        )

    if category == "heat_treatment":
        heat_counter = _count_attr_values_by_key_tokens(rows, ("热处理", "淬火", "处理", "时效", "钝化", "渗氮", "氰化", "正常化"))
        options = _counter_or_fallback_param_options(
            counter=heat_counter,
            value_prefix="heat::",
            seeded_options=seeded_options,
            fallback_options=[
                ParamConfirmOptionOut(value="heat::调质", label="调质", count=0),
                ParamConfirmOptionOut(value="heat::正常化", label="正常化", count=0),
                ParamConfirmOptionOut(value="heat::淬火", label="淬火", count=0),
                ParamConfirmOptionOut(value="heat::渗氮", label="渗氮", count=0),
                ParamConfirmOptionOut(value="heat::时效", label="时效", count=0),
                ParamConfirmOptionOut(value="heat::钝化", label="钝化", count=0),
            ],
        )
        return _finalize_param_question_spec(
            "heat_treatment_select",
            f"先看工序“{step_name}”，如果按热处理或表面处理状态判断，它更接近下面哪一种情况？",
            options,
        )

    return None


__all__ = ["_build_material_param_question_spec"]
