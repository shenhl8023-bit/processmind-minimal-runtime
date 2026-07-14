"""
参数确认问题规格构造器。

这里负责把“材料 / 特征 / 精度 / 尺寸 / 毛坯 / 多因素”等分类，
转换成当前问题类型、提示语和选项列表。路由层只保留问答流程编排。
"""

from __future__ import annotations

from app.schemas.schemas import ParamConfirmOptionOut, ParamReviewedFactorOut
from app.services.param_question_option_seed import knowledge_seed_param_options as _knowledge_seed_param_options
from app.services.param_question_spec_builder_common import (
    _factor_review_display_label,
    _factor_review_option,
    _sample_pair_attr_rows,
    _selected_factor_key_from_answer,
    _should_continue_param_operation_questions,
)
from app.services.param_question_spec_builder_feature import _build_feature_param_question_spec
from app.services.param_question_spec_builder_material import _build_material_param_question_spec
from app.services.param_question_spec_builder_misc import _build_misc_param_question_spec
from app.services.param_question_spec_builder_requirement import _build_requirement_size_blank_param_question_spec


def _build_param_question_spec_for_category(
    category: str,
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    sample_pairs: list[dict[str, object]],
) -> tuple[str, str, list[ParamConfirmOptionOut]]:
    rows = _sample_pair_attr_rows(sample_pairs)
    seeded_options = _knowledge_seed_param_options(step_name, category)
    builders = (
        lambda: _build_material_param_question_spec(
            category=category,
            step_name=step_name,
            rows=rows,
            seeded_options=seeded_options,
        ),
        lambda: _build_requirement_size_blank_param_question_spec(
            category=category,
            step_name=step_name,
            rows=rows,
            seeded_options=seeded_options,
        ),
        lambda: _build_feature_param_question_spec(
            category=category,
            step_name=step_name,
            target_factor=target_factor,
            rows=rows,
            seeded_options=seeded_options,
        ),
        lambda: _build_misc_param_question_spec(
            category=category,
            step_name=step_name,
            target_factor=target_factor,
            seeded_options=seeded_options,
        ),
    )
    for build_spec in builders:
        spec = build_spec()
        if spec is not None:
            return spec

    fallback = _build_misc_param_question_spec(
        category="root",
        step_name=step_name,
        target_factor=target_factor,
        seeded_options=seeded_options,
    )
    if fallback is not None:
        return fallback

    raise ValueError(f"Unsupported parameter question category: {category}")


__all__ = [
    "_build_param_question_spec_for_category",
    "_factor_review_display_label",
    "_factor_review_option",
    "_sample_pair_attr_rows",
    "_selected_factor_key_from_answer",
    "_should_continue_param_operation_questions",
]
