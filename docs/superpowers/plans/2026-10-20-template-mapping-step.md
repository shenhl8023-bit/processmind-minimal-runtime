# 模板分组映射独立步骤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将模板分组映射作为第三步之后的独立工作流页面，并以“至少一条有效映射”作为进入第四步和发布的条件。

**Architecture:** 新增 `TemplateMappingView.vue` 复用现有 `useProjectGroupTemplate` 与映射组件能力；在 `App.vue` 和路由中加入独立步骤；将第三步完成后的跳转改到新页面；保留第二步弹窗兼容入口，并让第四步发布状态读取同一套映射校验。

**Tech Stack:** Vue 3、TypeScript、Vue Router、现有 CSS/组件和 Vitest。

**Spec:** `docs/superpowers/specs/2026-10-20-template-mapping-step.md`

## Global Constraints

- 保持现有系统样式、颜色、字体、卡片和按钮风格。
- 未映射全部工序不阻塞，只要求至少一条有效确认映射。
- 模型候选不得自动作为用户确认结果。
- 不删除旧弹窗，直到新页面验证完成。

## Review Focus

- 无模板：页面显示上传/绑定入口，不能进入第四步。
- 有模板但零条有效确认映射：显示待建立状态，不能进入第四步。
- 只有部分工序映射：允许进入第四步和发布。
- 失效映射：不计入有效数，并保留修正入口。
- 刷新或携带项目 ID重新进入：恢复正确项目状态。

### Task 1: 工作流路由与步骤导航

**Files:**
- Modify: `process-plan-agent-ui/src/router/index.ts`
- Modify: `process-plan-agent-ui/src/App.vue`
- Test: `process-plan-agent-ui/src/router/templateMappingRoute.spec.ts`

- [ ] 新增 `/template-mapping` 路由及懒加载组件。
- [ ] 将工作流步骤插入第三步和第四步之间，更新顺序校验和预加载列表。
- [ ] 测试路由存在、步骤标签和导航顺序。

### Task 2: 独立模板映射页面

**Files:**
- Create: `process-plan-agent-ui/src/views/TemplateMappingView.vue`
- Test: `process-plan-agent-ui/src/views/TemplateMappingView.spec.ts`

- [ ] 复用 `useProjectGroupTemplate` 和现有映射编辑组件能力。
- [ ] 实现顶部统计、三栏布局、保存、返回第四步和状态提示。
- [ ] 页面只把至少一条有效确认映射视为完成，不要求所有工序覆盖。
- [ ] 覆盖无模板、零映射、部分映射和失效映射测试。

### Task 3: 第三步到映射页的流程接入

**Files:**
- Modify: `process-plan-agent-ui/src/views/AnalysisView.vue`
- Modify: `process-plan-agent-ui/src/components/workflow/TemplateMappingRequiredDialog.vue`

- [ ] 第三步完成后把模板映射前置检查跳转到 `/template-mapping`。
- [ ] 弹窗文案改为引导进入独立映射步骤。
- [ ] 保留第二步旧入口用于兼容。

### Task 4: 第四步和发布校验接入

**Files:**
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`
- Test: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts`

- [ ] 在第四步显示映射状态入口和有效映射数量。
- [ ] 发布仅在没有任何有效映射时阻塞；部分未映射允许发布。
- [ ] 失效映射不计入有效映射。
- [ ] 增加对应发布预检测试。

### Task 5: 全量验证

- [ ] 运行 `npm test -- --run`。
- [ ] 运行 `npm run build`。
- [ ] 手动检查第二步、第三步、映射页、第四步和发布拦截的连续流程。
