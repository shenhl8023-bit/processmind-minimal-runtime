# 规则定稿编辑区紧凑化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将规则定稿的配置编辑区优化为参考效果图中的紧凑单列工作区。

**Architecture:** 保留规则配置的数据、事件和保存流程，只调整 `ProcessConfigurationEditor.vue` 的轻量结构标记和 scoped CSS。视觉沿用映射工作区的浅分隔、整齐列表行和克制蓝色状态，嵌套条件编辑器只通过父组件 scoped deep selector 收紧尺寸。

**Tech Stack:** Vue 3 SFC、TypeScript、scoped CSS、Vitest、Vite。

**Spec:** `docs/superpowers/specs/2026-10-28-finalize-rule-editor-compact-design.md`

## Global Constraints

- 不调整规则语义、API、持久化、原文编辑或规则卡片整体信息架构。
- 保留全部出现方式、条件组合、关联类型、错误提示、未保存状态、规则摘要和保存行为。
- 不复制模板映射的双栏布局；窄屏按序换行或堆叠。

## Review Focus

- 多条件/嵌套条件在紧凑宽度仍可操作；运行现有 `FinalizeRuleCard.spec.ts`。
- 多来源历史关联及其选择规则不被样式裁切；运行现有规则编辑相关测试。
- 校验错误与过期原文提示仍完整可见；检查对应组件测试和桌面截图。
- 窄屏不发生横向溢出或控件遮挡；检查 390px 预览。
- 各出现模式的内容显隐和保存行为不变；运行编辑器相关组件测试。

---

### Task 1: 紧凑化规则配置编辑器

**Files:**
- Modify: `process-plan-agent-ui/src/components/finalize/ProcessConfigurationEditor.vue`
- Test: `process-plan-agent-ui/src/components/finalize/FinalizeRuleCard.spec.ts`
- Verify: `process-plan-agent-ui` test suite and production build; desktop/mobile visual preview.

**Interfaces:**
- Consumes: current `RuleConditionCandidate`, `ProcessConfiguration`, and existing save/update events.
- Produces: identical events and rule payloads with compact responsive presentation.

- [x] **Step 1: Tighten the configuration editor layout.** Reduce vertical gaps, control heights, segmented mode spacing, heading margins, helper text density, and footer padding; use light dividers and the existing blue accent without gradients or pronounced shadows.
- [x] **Step 2: Align condition and relation rows.** Give controls stable minimum widths; compact the nested leaf editor using a scoped deep selector; define an explicit narrow-screen stacking order for condition, relation, legacy-match, and helper rows.
- [x] **Step 3: Run interaction tests.** The focused editor and presentation tests passed: 27/27.
- [x] **Step 4: Verify responsive presentation and build.** Full front-end tests passed (49 files / 447 tests), production build passed, and the 390px component preview showed no clipping or horizontal overflow.
