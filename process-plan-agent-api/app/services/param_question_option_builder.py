"""
参数确认问题选项构造工具。

这里集中放置问题选项拼装、兜底选项、知识种子选项合并等纯函数，
让 generate 路由只负责接口编排和业务流程。
"""
from __future__ import annotations

from collections import Counter

from app.schemas.schemas import ParamConfirmOptionOut
from app.services.param_option_counter import top_counter_options
from app.services.param_question_option_seed import merge_param_options
from app.services.param_question_strategy import prioritized_root_reason_values
from app.services.param_question_tree_config import tree_node_options


def root_reason_option_pool() -> list[ParamConfirmOptionOut]:
    return [
        ParamConfirmOptionOut(value="coverage_reason::material", label="由材质差异导致", count=0),
        ParamConfirmOptionOut(value="coverage_reason::structure", label="由结构或特征差异导致", count=0),
        ParamConfirmOptionOut(value="coverage_reason::size", label="由尺寸或尺度差异导致", count=0),
        ParamConfirmOptionOut(value="coverage_reason::blank", label="由毛坯或来料状态差异导致", count=0),
        ParamConfirmOptionOut(value="coverage_reason::requirement", label="由加工要求差异导致", count=0),
        ParamConfirmOptionOut(value="coverage_reason::multi", label="由多种因素共同决定", count=0),
        ParamConfirmOptionOut(value="coverage_reason::uncertain", label="暂时无法判断", count=0),
    ]


def root_reason_options_for_step(
    step_name: str,
    seeded_options: list[ParamConfirmOptionOut] | None = None,
) -> list[ParamConfirmOptionOut]:
    option_map = {
        option.value: option
        for option in merge_param_options(root_reason_option_pool(), list(seeded_options or []))
    }
    ordered: list[ParamConfirmOptionOut] = []
    used: set[str] = set()
    for value in prioritized_root_reason_values(step_name):
        option = option_map.get(value)
        if option is None or option.value in used:
            continue
        ordered.append(option)
        used.add(option.value)
    ordered.extend([option for option in option_map.values() if option.value not in used])
    return ordered


def with_standard_tail_options(options: list[ParamConfirmOptionOut]) -> list[ParamConfirmOptionOut]:
    seen = {option.value for option in options}
    tail = [
        ParamConfirmOptionOut(value="other", label="其他（请补充）", count=0),
        ParamConfirmOptionOut(value="unsure", label="暂不确定", count=0),
        ParamConfirmOptionOut(value="data_issue", label="样本/数据需核查", count=0),
    ]
    for item in tail:
        if item.value not in seen:
            options.append(item)
    return options


def clone_param_options(options: list[ParamConfirmOptionOut]) -> list[ParamConfirmOptionOut]:
    return [option.model_copy(deep=True) for option in options]


def tree_or_default_param_options(
    branch: str,
    node_id: str,
    default_options: list[ParamConfirmOptionOut],
) -> list[ParamConfirmOptionOut]:
    tree_options = tree_node_options(branch, node_id)
    if tree_options:
        return tree_options
    return clone_param_options(default_options)


def counter_or_fallback_param_options(
    *,
    counter: Counter[str],
    value_prefix: str,
    seeded_options: list[ParamConfirmOptionOut],
    limit: int = 5,
    fallback_options: list[ParamConfirmOptionOut],
    tree_branch: str | None = None,
    tree_node_id: str | None = None,
) -> list[ParamConfirmOptionOut]:
    options = top_counter_options(counter, value_prefix=value_prefix, limit=limit)
    if not options:
        if tree_branch and tree_node_id:
            options = tree_or_default_param_options(tree_branch, tree_node_id, fallback_options)
        else:
            options = clone_param_options(fallback_options)
    return merge_param_options(options, seeded_options)


def finalize_seeded_param_question_spec(
    question_type: str,
    prompt: str,
    options: list[ParamConfirmOptionOut],
    seeded_options: list[ParamConfirmOptionOut],
) -> tuple[str, str, list[ParamConfirmOptionOut]]:
    return finalize_param_question_spec(question_type, prompt, merge_param_options(options, seeded_options))


def finalize_param_question_spec(
    question_type: str,
    prompt: str,
    options: list[ParamConfirmOptionOut],
) -> tuple[str, str, list[ParamConfirmOptionOut]]:
    return question_type, prompt, with_standard_tail_options(options)
