# AI 规则草稿预填实施计划

> **实施要求：** 按测试驱动顺序逐项执行；每个行为先写失败测试，再写最小实现。

**目标：** 让需要人工审核的工序获得完整、已标准化、可直接修补的 AI 规则草稿，同时保持现有确认和发布安全门槛。

**架构：** 后端解析器在标准因素绑定前规范化受控字段同义词，并保留未识别残句为审核问题；前端卡片只根据现有 review 状态决定是否默认展开编辑器。协议和数据库结构不变。

**技术栈：** Python 3.11、FastAPI/Pydantic、pytest、Vue 3、TypeScript、Vitest。

---

## 任务 1：孔类同义词规范化

**文件：**

- 修改：`process-plan-agent-api/app/services/rule_packages/standard_factors.py`
- 测试：`process-plan-agent-api/tests/test_standard_factors.py`

1. 增加失败测试，覆盖单个同义词、枚举字符串拆分、去重和已有规范值不变。
2. 实现确定性规范化并在绑定前调用。
3. 运行 `pytest tests/test_standard_factors.py -q`。

## 任务 2：部分识别生成可编辑候选

**文件：**

- 修改：`process-plan-agent-api/app/services/rule_packages/condition_parser.py`
- 测试：`process-plan-agent-api/tests/test_rule_condition_parser.py`

1. 将现有“模糊复合孔条件返回空候选”测试改为期望已绑定的 `any` 草稿。
2. 断言说明性残句仍在 `issues` 中，置信度不能触发安全批量确认。
3. 提升 `CONDITION_PARSER_VERSION`，让历史候选重新解析。
4. 运行解析器相关测试。

## 任务 3：人工审核候选默认展开

**文件：**

- 修改：`process-plan-agent-ui/src/components/finalize/FinalizeRuleCard.vue`
- 测试：`process-plan-agent-ui/src/components/finalize/StandardFactorPicker.spec.ts`

1. 增加组件测试：待人工审核且有候选时直接渲染条件编辑器。
2. 增加组件测试：已确认或可安全批量确认候选保持折叠。
3. 在候选同步 watcher 中按当前 review 状态设置展开状态。
4. 运行对应 Vitest。

## 任务 4：回归验证

1. 增加模型请求异常回归测试，确认本地部分识别仍返回待审核草稿，不让接口残留 `parsing` 状态。
2. 运行后端解析器、条件审核和标准因素测试。
3. 运行后端完整测试。
4. 运行前端完整测试与构建。
5. 在本地页面复查“割型孔”和“研孔”候选，确认字段、运算符、值、目标工序已预填且仍显示人工审核提示。
6. 检查 Git diff，确认没有改动既有 KmAI 导出重构和运行时数据。
