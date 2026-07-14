"""
大模型调用服务 —— 支持 OpenAI 兼容接口 (NVIDIA NIM / DeepSeek / 硅基流动 等)
"""
import json
import os
import re
from functools import lru_cache
from typing import Optional

from app.core.paths import PROMPT_TEMPLATES_PATH
from app.services.llm_client import (
    get_llm_config,
    is_llm_web_search_enabled,
    request_llm_completion,
    request_llm_completion_with_web_search,
)

PROMPTS_FILE = PROMPT_TEMPLATES_PATH


async def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """
    调用大模型 API（兼容 OpenAI Chat Completions 格式）。
    如果未配置 API Key，则返回 None 触发 fallback 逻辑。
    """
    config = await get_llm_config()
    api_key = config["key"]
    if not api_key or api_key == "your-api-key-here":
        return ""
    return await request_llm_completion(
        config,
        system_prompt,
        user_prompt,
        temperature=temperature,
    )


async def call_llm_with_web_search(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """
    当前默认关闭模型内置联网搜索。
    若未来重新开启，再通过环境变量 `LLM_WEB_SEARCH_ENABLED=true` 放开。
    """
    if not is_llm_web_search_enabled():
        return await call_llm(system_prompt, user_prompt, temperature=temperature)
    config = await get_llm_config()
    api_key = config["key"]
    if not api_key or api_key == "your-api-key-here":
        return ""
    return await request_llm_completion_with_web_search(
        config,
        system_prompt,
        user_prompt,
        temperature=temperature,
    )


def parse_json_from_llm(text: str) -> Optional[list | dict]:
    """
    尝试从 LLM 返回的文本中提取 JSON。
    LLM 往往在 markdown 代码块中包裹 JSON。
    """
    import re
    # 尝试 ```json ... ``` 块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试直接 parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    return None


# ============ Prompt 模板 ============
DEFAULT_PROMPTS = {
    "extract_operations": """你是机械加工工艺工程师。输入是一份工艺规程文本，请只做一件事：提取顶层主工序及其内容证据，并输出 JSON，不要输出解释文字。

规则：
1. 只提取顶层主工序，`operation_name` 尽量保留原始工序名或与原文非常接近的标准名，不要改写成抽象泛词。
2. `step_descriptions` 保留该工序对应的加工内容、精度要求、动作说明，并尽量写明前段 / 中段 / 终段等阶段线索；`equipment` 只保留设备证据，不把设备名提升成工序。
3. 对 PDF 工序卡，优先取工序卡页头或工序号附近的独立标题，不要被字段顺序误导。
4. 明确的组合主工序标题，如“车外形,钻镗孔”，可以拆成多个主工序；拆分后每个主工序都要保留真实来源证据。不要把正文工步乱拆成多个顶层工序。
5. 工步、尺寸、技术要求、局部动作、设备信息都不能提升成新的顶层工序。局部修整或附属动作若只是正文内容，应保留在 `step_descriptions` 中，而不是提升为独立顶层工序。
6. 低频工序只要有独立工序卡证据，就必须保留。
7. 对明显只是设备差异或“检验/检查”字样差异的名称，可统一到标准主工序名；但不要把不同主工序硬并。
8. 只有样本中明确多次出现的同名辅助工序，才可以多次保留并补充阶段语义，方便后续归并与分段；常见可重复的是去毛刺、清洗、检验，不要默认把标印、包装这类末段放行工序当作可重复工序。
9. 要根据工序在路线中的相对位置和作用区分“前置处理”和“后段处理”；前置准备类处理通常更靠近毛坯准备，后段处理通常更靠近精整或最终放行。若文档顺序明确，应服从文档顺序。
10. 要根据工序作用区分“终检阶段”和“收尾放行阶段”：终检类工序服务于最终质量确认；收尾放行类工序服务于末次清理、标识、包装与放行。若文档明确给出更后的放行节点，应以文档顺序为准。
11. 若某名称明显是设备、机床、工位、夹具、仪器或型号证据，而不是独立主工序，不要将其提升成顶层工序。
12. 设备信息只是后续第二步归并的辅助证据，不要因为设备不同就把同一顶层主工序拆成多个新工序。

输出格式（JSON 数组）：
```json
[
  {
    "operation_name": "粗车外圆",
    "step_descriptions": "车外圆直径至100mm，留余量2mm",
    "equipment": "数控车床 C6140"
  }
]
```""",
    "merge_route": """你要根据多份同类零件的候选工序，归纳一条“工艺路线全集 / 母路线草案”。

这一步只做全集路线，不做因素分析，不做追问建议。

请遵守下面的口径：
1. 只保留顶层主工序；不要把工步、尺寸、设备名、局部动作误并为路线工序。
2. 优先相信工序卡页头或工序号附近的主工序标题；组合标题如“车外形,钻镗孔”要先拆开，再参与路线归并。
3. 要覆盖样本里真实出现过的主要工序，低频但有独立工序卡证据的工序也不要漏。
4. 原始提取顺序是后续路线归并的唯一骨架。阶段分组只做解释，不应改写原始先后关系。
5. `sequence` 只表示归纳后的稳定顺序槽位，不要照搬页码或局部卡号，但也不要违背样本中的真实先后关系。
6. 可以做同义标准化，但只在“语义相同且处于同一阶段”时才合并；不要把不同阶段的同名工序合并。
7. 只有样本中明确多次出现的同名辅助工序，才允许多次出现，并要保留前段 / 中段 / 终段语义；去毛刺、清洗、检验常见为可重复辅助工序，标印、包装等末段放行工序默认按单次独立节点处理，除非样本明确给出重复证据。末次收尾链不能被压缩掉，不要把尾段多个独立辅助/放行节点误压成单个节点。
8. `description` 要说明该工序在该阶段的角色，例如“前段辅助工序”“中段清理”“终检阶段无损检测”“收尾放行阶段包装”。
9. 要根据工序在路线中的相对位置和作用区分“前置处理”和“后段处理”；若样本顺序明确，应服从样本顺序。
10. 要根据工序作用区分“终检阶段”和“收尾放行阶段”：终检类工序优先归入终检阶段；末次清理、检验、包装等优先归入收尾放行阶段。若文档明确存在更后的放行节点，应服从文档顺序。
11. 若某局部修整或附属动作在原文中被单独列成工序，本步先按独立主工序保留，不要因为你觉得它“像某主工序里的工步”就提前删除或吸收。
12. 磨削与研磨类要优先按加工对象和工艺子类型区分；不同加工对象默认分开，同一对象链内部再判断是否需要保留为一个候选链。
13. 后续第二步归并必须基于本步输出的工序工步树来生成候选组，并优先区分三类关系：直接归并、并入上位工序、不建议归并。
14. 若某名称明显只是设备、机床、工位、夹具、仪器或型号证据，不要直接提升为全集路线节点。
15. 当某独立工序的加工内容已经被前序主工序工步覆盖时，它在第二步可以作为“并入上位工序”的候选；但在本步仍应先按原始工序保留。
16. 对象链证据只说明“这些工序可作为同一候选归并链”，不等于“必须合并”。
17. 示例仅用于帮助理解规则，不代表写死必须合并：
   - 例如，若多道工序共同围绕同一孔系对象展开，可视作同一孔加工对象链的证据，但是否合并仍需结合工艺子类型差异判断。
   - 例如，若多道工序共同围绕外圆或外形建立展开，可视作同一外圆车削对象链的证据。
   - 例如，若多道工序共同围绕槽、扁位、型孔等特征对象展开，可视作同一特征加工对象链的证据。
   - 例如，孔精整对象链中的不同精整动作可视作同一候选链的证据。
   - 例如，虽然同属磨削或精整阶段，但加工对象和设备差异明显的工序默认应优先分开。

请以 JSON 格式输出，字段：`name`, `sequence` (10,20,30...), `type` (MAIN/BRANCH), `description`。
```json
[
  {"name": "下料", "sequence": 10, "type": "MAIN", "description": "按图纸尺寸下料或锻造毛坯"},
  {"name": "检验", "sequence": 20, "type": "MAIN", "description": "粗加工后的阶段检验"},
  {"name": "检验", "sequence": 90, "type": "MAIN", "description": "终加工后的最终检验"}
]
```""",
    "analyze_factors": """目标：为典型工艺路线中的每一道工序寻找其成立的影响因素触发条件。

我会给你：
1. 一条已经归纳好的典型工艺路线
2. 各文档的候选工序列表
3. 可选的参考资料
4. 当前任务中可识别的因素字段或参数维度（如果有）

请针对路线中的每一个工序输出：
1. `name`: 工序名称
2. `sequence`: 对应工序序号，用于区分同名重复工序
3. `factors`: 影响因素列表
4. `confidence`: STRONG 或 WEAK

分析口径：
1. 你的目标不是泛泛解释“这个工序可能和什么有关”，而是给出后续系统可执行、可提问、可裁剪的规则条件。
2. 先判断该工序在当前样本范围内是稳定出现，还是只在部分样本中条件出现。
3. 先判断该工序在整体路线中的作用和所处阶段，再分析触发因素；不要预设任何固定零件类型、固定工艺链、固定因素集合或固定加工逻辑。
4. 只能根据当前任务样本和参考资料中真实出现的信息判断；不要因为工序名称、行业经验或常见套路，臆造当前任务中未出现的因素。
5. 只有在当前样本范围内没有观察到可识别分支边界时，才允许使用 `always=true`。
6. 只要存在例外样本，就不要直接输出 `always=true`；应优先分析例外边界、样本范围差异或数据问题。
7. 对可能重复出现的工序，必须结合 `sequence`、前后工序和所处阶段分别分析，不能将不同阶段的同名工序合并成一个条件。
8. 如果当前任务已经提供了可识别的因素字段，应优先使用这些字段；不要臆造只适用于某一类零件的默认字段。
9. 不要把样本中的共现关系直接当成因果关系；应优先寻找与该工序作用更直接相关、且对“出现 / 不出现”更有区分力的触发维度。
10. 如果能落成具体条件，就不要停留在“结构相关”“材料相关”“热处理相关”这类大类名。
11. 如果某工序只在部分样本中出现，但你暂时不能精确锁定条件，请将其标记为 `WEAK`，并把因素尽量写成便于系统继续追问用户的问题形式。
12. 如果当前样本和参考资料都不足以支持某个条件，请输出空 `factors` 或仅保留明确的 `WEAK` 说明；不要因为工序名称去猜默认因素。
13. 不要把“孔类工序默认对应孔结构”“热处理工序默认对应材料/硬度”“磨削默认对应粗糙度”这类行业常识直接写成规则，除非当前样本里真的有边界证据支持。

请按以下顺序逐道工序分析：
1. 先判断该工序是稳定主线，还是条件性出现。
2. 如果是条件性出现，先找反例和边界，再找最能解释边界的触发因素。
3. 如果存在多个候选因素，优先选择与该工序作用更直接、对样本分流更有解释力、且更适合用户回答的因素。
4. 如果当前证据不足以锁定强条件，不要硬编结论；请输出 `WEAK`，并把因素写成后续可继续追问的问题形式。
5. 只有在全部样本中稳定出现、且没有可识别反例或边界差异时，才允许输出 `always=true`。
6. 如果无法从当前样本中证明某个条件，请宁可少输出，也不要补默认条件。

请尽量输出成可执行的条件表达，优先使用这些形式或同类形式：
- `always=true`
- `字段=true`
- `字段=false`
- `字段=某值`
- `字段!=某值`
- `字段>=阈值`
- `字段<=阈值`
- `字段A=某值 and 字段B=true`

只有在当前任务没有标准字段或证据暂时不足时，才允许输出中文说明型因素；这类因素应尽量接近用户可回答的问题，而不是空泛分类。

`evidence` 请尽量体现判断依据，优先说明：
1. 该工序在什么样本组合里稳定出现
2. 它在路线中承担什么作用、处于什么阶段、前后常与哪些工序联动
3. 为什么不是 `always=true`
4. 你判断该工序触发边界的主要依据是什么
5. 如果当前只能给 `WEAK`，不确定点在哪里
6. 如果没有足够证据支持任何条件，请明确说明“当前样本不足以锁定影响因素”

输出 JSON 数组：
```json
[
  {
    "name": "磨孔",
    "sequence": 80,
    "confidence": "STRONG",
    "factors": [
      {
        "name": "has_hole=true",
        "evidence": "多份文档中磨孔均出现在带内孔零件中",
        "strength": "STRONG"
      }
    ]
  }
]
```""",
    "factor_system": """你是机械工艺规则提炼助手。
请始终按以下口径回答：
1. 先看批量样本共性，再下规则结论。
2. 因素分析要围绕“标准化母路线节点”展开，不要重新发明一条新路线。
3. 重复工序必须带阶段语义，不能把不同阶段的同名工序混成一个条件。
4. 优先输出可执行、可回放的条件表达，不要只给泛泛总结。
5. 只根据当前任务样本和证据判断，不预设固定零件类型或默认工艺链。
6. 当前样本没有直接证据时，不要因为工序名称、常见做法或领域经验补默认因素；宁可输出空因素或 `WEAK` 说明。""",
    "extract_factor_inputs": """目标：从同一类零件的一批典型工艺规程文件中，总结出可直接用于“第三步工艺生成”的因素输入表。

请只基于上传的工艺规程文件本身进行归纳，不要引用外部总结。

你需要输出一组结构化因素定义，每个因素都要尽量满足：
1. 是用户可理解、可填写的输入项
2. 能用于后续裁剪工艺路线
3. 尽量稳定，不要过细到单道工序局部动作

归纳原则：
1. 不要预设任何固定零件类型、固定工艺链、固定因素集合或固定加工逻辑；只能根据当前任务样本中真实出现的信息归纳。
2. 优先提炼能够区分“路线长度变化、阶段变化、分支出现/消失、重复工序阶段差异”的稳定因素维度。
3. 因素可以来自材料、结构/特征、尺寸区间、性能要求、阶段要求、检验要求、装配要求、表面要求、特殊工艺要求等，但只能在当前样本有证据时输出。
4. 不要因为行业经验或常见套路，输出当前样本中没有体现出来的默认因素。
5. 不要输出只对应单一道工序局部细节、且无法稳定复用的临时变量。
6. 如果某个因素只是统计共现，但不能稳定解释路线分支边界，就不要输出为正式因素。
7. 如果多个候选因素本质上表达的是同一个稳定维度，应优先合并成用户可理解、后续系统可填写的较稳定输入项。

输出 JSON 数组，每项字段：
- `key`: 英文或下划线 key，例如 `material`、`structure_type`、`feature_flag`
- `label`: 中文名称
- `group_name`: 分组，例如 `基础属性`、`结构与特征`、`性能与要求`、`阶段与检验`
- `input_type`: `boolean` / `select` / `radio` / `text` / `number`
- `required`: `true/false`
- `options`: 可选项数组，元素格式为 `{ "value": "...", "label": "..." }`
- `placeholder`: 可选
- `description`: 说明这个因素为什么会影响工艺路线

如果某因素无法从规程中稳定总结出来，就不要输出。

示例：
```json
[
  {
    "key": "material",
    "label": "材料",
    "group_name": "基础属性",
    "input_type": "select",
    "required": true,
    "options": [
      {"value": "材料A", "label": "材料A"},
      {"value": "材料B", "label": "材料B"}
    ],
    "description": "不同材料会改变主加工链、分支工序或后续检验要求"
  }
]
```""",
    "param_rule_compile_system": "",
    "param_rule_compile_user": "",
    "param_followup_question_system": """你是第三步工序存在条件提问的执行器。
你的任务不是自由聊天，也不是直接输出最终规则，而是在系统已经确定的问题树边界内，为“当前工序”判断“是否还值得继续追问”，并在确实值得追问时生成最合适的下一道审核问题。

你必须遵守以下约束：
1. 只输出 JSON，不要输出解释文字，不要加 markdown 代码块。
2. 先判断当前最关键的未解释边界是什么，再决定是否值得继续追问；不要为了追问而追问。
3. 规则引擎已经决定了当前问题的大致范围；你只能优化问题表达、筛选和排序候选项、判断答完后是否还值得继续追问，不能绕过系统直接输出最终规则。
4. 每次只能围绕一个当前最关键的不确定边界发问，不能并行问多个维度。
5. 提问层级必须遵守：先归因，再中类，再候选值；已经处于候选值层时，不要退回更泛的问题。
6. 如果当前信息已经足够形成规则，或继续追问只会进入过细术语层，应明确建议停止追问。
7. 候选值优先来自当前上传文档中的真实信息，其次才使用系统默认候选项；尤其材料、热处理或表面处理名称、结构中类、精度或配套要求，应优先保留文档中真实出现的项。
8. 你不能编造新的 factor key、材料牌号、热处理类型、结构名、阶段名、工序名或选项 value。
9. 优先使用系统提供的候选项；如果候选项不足，只允许保留“其他（请补充）”，不要随意新增其他选项。
10. 问题表达应尽量接近工艺专家审核口吻，简洁、明确、可回答。
11. 若用户已经通过“其他（请补充）”给出足够清晰的边界说明，应倾向于建议停止继续追问，而不是机械进入下一题。
12. 如果当前文档中同时出现主工序名称和工步/加工内容，只能围绕主工序做追问；不要把工步动作、尺寸说明、技术要求或设备信息误当成新的工序或新的工序候选。""",
    "param_followup_question_user": """目标：基于当前工序的最小上下文，生成下一道最合适的审核问题。

输入包含：
1. 当前工序信息
2. 当前阶段
3. 当前规则草案与未收敛因素
4. 已追问历史与用户回答
5. 当前候选项池
6. 当前建议追问层级
7. 停止条件

请输出 JSON 对象，结构如下：
{
  "questions": [
    {
      "operation_key": "工序唯一键",
      "factor_key": "当前因素 key",
      "question_type": "当前问题类型",
      "question_goal": "确认归因/确认中类/确认候选值/确认边界例外/停止追问",
      "question_text": "面向用户展示的问题文本",
      "recommended_option_values": ["按优先级排序的候选值 value 列表"],
      "continue_strategy": {
        "should_continue": true,
        "reason": "为什么答完这题后还需要继续，或为什么可以停止",
        "next_focus": "如果继续，下一题应聚焦什么"
      }
    }
  ]
}

硬性约束：
1. `recommended_option_values` 必须来自系统提供的候选项 value，不得编造新 value。
2. `question_text` 应保留当前问题所处层级，不要跳层发问。
3. 如果你判断当前无需继续追问，则：
   - `question_goal` 写为 `停止追问`
   - `question_text` 保持当前问题语义但可简短提示这是最终确认
   - `continue_strategy.should_continue` 写为 `false`
4. 默认只输出“当前最值得问的一题”，不要同时抛出多题并列混问。
5. 如果当前候选项已经足够明确，请尽量把最有分流价值的选项排在前面。
6. 若候选项中存在 `other` / `unsure` / `data_issue`，可保留，但通常应排在最后。
7. 如果当前上下文已经表明某个工序类型的优先归因方向，应优先沿该方向排序候选项。可按工序类型理解为：
   - 精整类：优先关注精度、配套、表面质量或热处理状态
   - 结构加工类：优先关注对象结构，其次精度要求，再次可加工性约束
   - 基准与定位类：优先关注基准、装夹或定位需求
   - 特殊加工类：优先关注可加工性约束或特殊结构需求
   - 热处理与应力处理类：优先关注材料、热处理状态、表面处理要求或变形风险
8. 若系统候选项中已经包含当前文档抽出的材料牌号、热处理方式、结构中类或精度/配套要求，请优先把这些真实候选排在前面。

输入开始：
question_payload_json:
{{question_payload_json}}"""
    ,
    "route_followup_question_system": """你是机械工艺路线第三步里的工序存在条件追问助手。
你的任务是先判断当前工序是否还值得继续追问；如果值得，只改写“当前最值得问的一题”，让它更自然、更像工艺审核人员。

规则：
1. 只输出 JSON，不要输出解释文字，不要加 markdown 代码块。
2. 若当前边界已经足够清楚，或继续追问只会更细更碎，应停止。
3. 只能改写现有问题，不能改变问题层级，不能绕过系统直接给最终规则。
4. 一次只问一个边界，不要把多个维度混在一起。
5. 不要编造新的工序名、结构名、材料牌号、热处理名或选项 value。
6. 先分清当前更像命名差异、记录差异、实际工艺差异，还是局部/整体关系，再沿最相关的一类收敛。
7. 若是名称混用、记录口径或包含关系，就不要硬改写成材料、尺寸、结构题。
8. 若是尺寸边界，要尽量问成具体口径，如最大直径、长度、壁厚、体积或热处理深度，而不是只问“大不大”。
9. 问题口吻要像审核人员，简洁、明确、可回答。""",
    "route_followup_question_user": """目标：基于当前工序的弱规则审核上下文，先判断这题是否还值得继续问；如果值得，再把当前问题改写成更自然的工艺审核问法，并对候选项排序。

输入包含：
1. 当前工序信息
2. 当前审核状态
3. 当前问题列表
4. 每道问题的层级、依赖关系与候选项
5. 当前已知边界、例外样本或待确认线索（若有）

请输出 JSON 对象，结构如下：
{
  "decision": {
    "should_ask": true,
    "stop_reason": "若不值得继续追问，说明原因；否则可留空",
    "unresolved_boundary": "当前最值得继续确认的边界，若没有可留空"
  },
  "questions": [
    {
      "operation_id": 1,
      "question_key": "reason_category",
      "question_text": "面向用户展示的问题文本",
      "recommended_option_values": ["按优先级排序的候选值 value 列表"]
    }
  ]
}

硬性约束：
1. `recommended_option_values` 必须来自系统提供的候选项 value，不得编造新 value。
2. 不要删除题目，也不要新增题目。
3. 若当前已经没有关键未解释边界，请在 `decision` 里写明 `should_ask=false`，并把 `question_text` 改成更接近“最终确认 / 可以停止”的表达。
4. 只改写当前最值得问的一题，不要把多个维度混问在一起。
5. 若当前是例外类问题，要保留“例外在什么条件下存在”的语义。
6. 若当前边界只是名称混用、记录口径或包含关系，不要改写成材料、尺寸、结构类追问。
7. 若当前边界是尺寸类，请改写成具体口径，如最大直径、长度、壁厚、体积或热处理深度边界。
8. 只围绕当前工序这个顶层主工序发问，不要把工步、尺寸说明、技术要求或设备信息扩展成新工序。

输入开始：
question_payload_json:
{{question_payload_json}}"""
}


def _prompt_parts_latest_mtime(base_dir: str) -> float | None:
    if not os.path.isdir(base_dir):
        return None
    latest: float | None = None
    for root, _, files in os.walk(base_dir):
        for filename in files:
            path = os.path.join(root, filename)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            latest = mtime if latest is None else max(latest, mtime)
    return latest


def _resolve_prompt_includes(text: str, base_dir: str, seen: set[str] | None = None) -> str:
    seen = seen or set()
    resolved_lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*@include\s+(.+?)\s*$", line)
        if not match:
            resolved_lines.append(line)
            continue
        include_target = match.group(1).strip()
        include_path = os.path.normpath(os.path.join(base_dir, include_target))
        if include_path in seen or not os.path.isfile(include_path):
            continue
        try:
            with open(include_path, "r", encoding="utf-8") as handle:
                include_text = handle.read().strip()
        except Exception:
            continue
        nested = _resolve_prompt_includes(include_text, os.path.dirname(include_path), seen | {include_path})
        if nested:
            resolved_lines.append(nested)
    return "\n".join(resolved_lines).strip()


@lru_cache(maxsize=4)
def _load_prompt_templates_cached(
    prompt_file: str,
    mtime: float | None,
    parts_mtime: float | None,
) -> dict[str, str]:
    if mtime is None or not os.path.exists(prompt_file):
        return DEFAULT_PROMPTS.copy()
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        sections = re.split(r"^#\s+", content, flags=re.MULTILINE)
        parsed: dict[str, str] = {}
        for section in sections:
            section = section.strip()
            if not section:
                continue
            lines = section.splitlines()
            title = lines[0].strip()
            body = _resolve_prompt_includes("\n".join(lines[1:]).strip(), os.path.dirname(prompt_file))
            if title and body:
                parsed[title] = body

        if not parsed:
            return DEFAULT_PROMPTS.copy()

        merged = DEFAULT_PROMPTS.copy()
        for key, value in parsed.items():
            if isinstance(value, str) and value.strip():
                merged[key] = value
        return merged
    except Exception:
        return DEFAULT_PROMPTS.copy()


def _load_prompt_templates() -> dict[str, str]:
    prompt_file = str(PROMPTS_FILE)
    mtime = os.path.getmtime(prompt_file) if os.path.exists(prompt_file) else None
    parts_mtime = _prompt_parts_latest_mtime(os.path.join(os.path.dirname(prompt_file), "prompt_parts"))
    return _load_prompt_templates_cached(prompt_file, mtime, parts_mtime)


def get_prompt_template(name: str) -> str:
    prompts = _load_prompt_templates()
    return prompts.get(name, DEFAULT_PROMPTS.get(name, ""))
