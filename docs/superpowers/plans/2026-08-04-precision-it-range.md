# 尺寸精度 IT 范围限制实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将内孔、其他尺寸和外圆三个 IT 精度输入限制为整数 5–10，且前后端保持一致。

**Architecture:** 在 V2 输入 schema 的通用 `validation` 中增加 `integer` 标记，由标准字段注册表为三个 IT 字段声明 `min=5`、`max=10`、`integer=true`。后端输入校验负责最终拒绝越界和小数；前端复用同一 schema 元数据设置数字控件边界、步长并阻止非法值参与生成。

**Tech Stack:** FastAPI/Pydantic、Vue 3 Composition API、TypeScript、pytest、Vitest。

## Global Constraints

- 只修改三个 IT 字段的输入约束，不改变其它尺寸、公差或硬度字段。
- 5 和 10 为合法边界；4、11、5.5 等值必须无法生成并由后端拒绝。
- 不添加依赖，不覆盖工作区中已有的用户改动，不执行 commit/push。

---

### Task 1: 后端 schema 和输入校验

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_registry.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/input_validation.py`
- Modify: `process-plan-agent-api/tests/test_rule_condition_parser.py`
- Create: `process-plan-agent-api/tests/test_precision_input_validation.py`

- [ ] **Step 1: Write failing tests**

测试 `input_field_for` 为三个 IT 字段返回 `min=5`、`max=10`、`integer=True`，并测试 `validate_inputs` 接受 5/10、拒绝 4/11/5.5。

- [ ] **Step 2: Run focused tests and confirm failure**

运行 `pytest tests/test_precision_input_validation.py tests/test_rule_condition_parser.py -q`（工作目录 `process-plan-agent-api`），确认旧注册表仍为 1–18 且小数尚未被拒绝。

- [ ] **Step 3: Implement the minimum backend change**

给 `InputValidation` 增加默认关闭的 `integer` 字段；三个注册字段声明 5–10 和整数约束；`InputField` 加载这三个标准字段时将历史规则包中的旧范围规范化为新约束；`validate_inputs` 在 number 分支对 `integer=true` 拒绝非整数并返回字段级错误。

- [ ] **Step 4: Run focused tests and confirm pass**

重新运行上述 pytest 命令，并确认原有条件范围测试的上限断言更新为 10。

### Task 2: 前端数字输入约束

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useGenerateInputFields.ts`
- Modify: `process-plan-agent-ui/src/composables/useGenerateInputFields.spec.ts`
- Modify: `process-plan-agent-ui/src/components/generate/GenerateInputPanel.vue`
- Modify: `process-plan-agent-ui/src/components/generate/GenerateInputPanel.spec.ts`

- [ ] **Step 1: Write failing tests**

在 composable 测试中加入 IT schema，断言 5/10 可生成，4/11/5.5 不计入有效值；在组件 SSR 测试中断言 number input 输出 `min="5" max="10" step="1"`。

- [ ] **Step 2: Run focused UI tests and confirm failure**

运行 `npm test -- --run src/composables/useGenerateInputFields.spec.ts src/components/generate/GenerateInputPanel.spec.ts`（工作目录 `process-plan-agent-ui`），确认当前无整数校验和边界属性。

- [ ] **Step 3: Implement the minimum frontend change**

将 `validation.integer` 纳入 `GenerateInputField` 类型和数值有效性判断；在 number input 上绑定 schema 的 min/max，并在整数约束下设置 `step=1`。

- [ ] **Step 4: Run focused UI tests and confirm pass**

重新运行同一 Vitest 命令，确认所有边界和控件属性测试通过。

### Task 3: 回归验证

- [ ] **Step 1:** 运行后端相关规则包测试：`pytest tests/test_rule_condition_parser.py tests/test_rule_package_v2.py tests/test_rule_package_api.py -q`。
- [ ] **Step 2:** 运行前端全量测试和构建：`npm test`、`npm run build`。
- [ ] **Step 3:** 检查 `git diff`，确认只包含本需求文件、对应测试和计划文件，不触碰已有用户改动。
