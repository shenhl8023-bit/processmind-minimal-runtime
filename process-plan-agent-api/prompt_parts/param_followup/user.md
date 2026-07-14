目标：基于当前工序的最小上下文，把第三步当前节点的问题改写成更适合界面展示的问题，同时决定是否值得继续问。

这不是自由生成问题，而是“问题树执行”：
- 当前节点问什么，就只问什么
- 当前节点有哪些选项，就只排序这些选项

输入包含：
1. 当前工序信息
2. 当前阶段
3. 当前规则草案与未收敛因素
4. 已追问历史与用户回答
5. 当前候选项池
6. 当前建议追问层级
7. 停止条件
8. 当前节点的 `tree_branch`、`tree_node_id`、`option_source`

请输出 JSON 对象，结构如下：
{
  "questions": [
    {
      "operation_key": "工序唯一键",
      "factor_key": "当前因素 key",
      "question_type": "当前问题类型",
      "question_goal": "当前节点目标，例如：确认合并依据 / 确认主因素类别 / 确认候选值 / 确认异常原因 / 停止追问",
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
2. 你不能新增或删除问题，只能改写当前最值得问的一题。
3. `question_text` 必须保留当前节点语义，不得换成别的层级问题。
4. 如果你判断当前无需继续追问，则：
   - `question_goal` 写为 `停止追问`
   - `continue_strategy.should_continue` 写为 `false`
   - `continue_strategy.next_focus` 留空或写 `""`
5. 组合名命名确认时，只围绕“统一名称选哪一个”改写。
6. 覆盖不足分析时，只围绕当前已选主因素方向改写，不要改写成工序是否合并。
7. 如果当前候选项已经足够形成规则说明，应优先建议停止，而不是继续追问。
8. 若候选项中包含 `other` / `unsure` / `data_issue`，可以保留，但通常排在最后。
9. 若当前节点明显应展示来自样本的候选项，应优先把样本中真实出现的候选排在前面。

输入开始：
question_payload_json:
{{question_payload_json}}
