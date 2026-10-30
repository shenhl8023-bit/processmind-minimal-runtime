# Finalize Save Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 保持规则定稿页面视觉，修复未保存编辑、草稿落库、重新识别覆盖及发布来源失配。

**Architecture:** 沿用现有 draft/parse/confirm API 和不可变发布快照。卡片向父页面报告未保存状态，父页面在发布及切换时保护编辑；后端以当前持久化审核来源作为发布依据。

**Tech Stack:** Vue 3 / TypeScript / Vitest；FastAPI / SQLAlchemy / pytest。

**Spec:** docs/superpowers/specs/2026-10-27-finalize-save-protection-design.md

## Global Constraints

- 沿用现有布局、配色、字体、间距、规则卡片及提示组件。
- 本轮不做规则类型切换、试算或工序关联编辑器重新设计，不新增结构化草稿 API。
- 保留所有已有用户修改；不重置工作区，不做批量提交。
- Python 代码保持项目既有兼容约束，不新增依赖或数据库列。

## Review Focus

- 同原文的模型版本变化或第三步草稿，不覆盖有效人工确认。
- 后台识别返回期间新确认，不被旧结果降级。
- 原文已落库但识别失败，刷新仍可恢复；本机旧草稿不覆盖服务端新值。
- 卡片隐藏、切换或保存失败，未保存状态仍能阻止发布。
- 发布请求遗漏当前人工确认，或未确认规则被伪装为主线时，服务端拒绝。

## Task 1: 同源确认与解析回写保护

**Files:** condition_reviews.py、rule_preprocessing.py；test_rule_condition_parser.py。
**Interfaces:** 保持 ParseRuleConditionRequest 与 confirm 合同，返回同源有效的已确认审核。
- [x] 添加模型变化、第三步候选覆盖、解析期间确认的失败回归；运行确认失败。
- [x] 在机器识别之前校验并复用同源确认，结果写入前检查仍处于解析状态；预处理遵循同样规则。
- [x] 运行相关后端测试。

## Task 2: 卡片未保存状态与摘要

**Files:** FinalizeRuleCard.vue、FinalizeRuleCard.spec.ts；必要摘要纯函数及测试。
**Interfaces:** emit `edit-state(segmentId: string, dirty: boolean)`，取消或确认成功后恢复；父页面集成。
- [x] 添加实际组件交互回归：已确认关系修改后未保存、取消还原、人工选择名称、父 props 更新不得误清草稿。
- [x] 按保存快照比较可执行字段；复用 existing badge，摘要从结构生成。
- [x] 运行组件测试和类型检查。

## Task 3: 父页面保存与发布保护

**Files:** FinalizeView.vue、FinalizeView.spec.ts、useFinalizeDrafts.ts/spec.ts、useFinalizeRulePackageExport.ts/spec.ts；必要纯状态 helper。
**Interfaces:** 组件未保存 ID 集合与现有 inlineEditing 文本共同构成发布阻塞；原文走 saveRuleConditionDraft → parseRuleCondition。
- [x] 添加失败回归：未保存/保存中不能发布、定位正确卡片、保存成功识别失败仍有服务端草稿、取消后可继续发布。
- [x] 实现保存流程与异步返回身份保护；成功同步草稿与服务器来源；仅复用现有提示和版本文案。
- [x] 运行页面、composable、export 测试及 npm build。

## Task 4: 发布来源完整性

**Files:** confirmation_validation.py；test_rule_package_lifecycle.py 或独立 confirmation_validation 测试。
**Interfaces:** 保持 require_confirmed_user_rule_sources 签名，同时拒绝未确认及遗漏来源。
- [x] 添加当前待确认来源、遗漏确认、合法主线转换、合法包的回归测试；确认失败。
- [x] 校验当前路线真实审核记录，兼容无审核记录的既有规则包。
- [x] 运行后端相关测试；独立审查后执行前后端完整测试并记录限制。


## 执行与验收记录（2026-10-27）

- 已按用户选定范围完成；保留既有页面布局和组件，FinalizeView.vue 与 FinalizeRuleCard.vue 的 style 块相对本轮开始快照完全一致。
- 原文通过已有服务端草稿接口保存后再识别；保存失败保留编辑，识别失败保留已保存原文；有效确认在重复识别和模型变化时保留。
- 补齐工作流冲突、外部重置、后台刷新及过期请求保护；六类规则请求同时核对项目、路线、工作流修订和已知重置信号。
- 本机恢复草稿记录服务端原文基线；服务端发生变化时不自动恢复旧副本，旧副本继续保留在本机恢复存储中。
- 发布校验反查持久化来源，拒绝遗漏、未确认或失配内容；主线豁免收紧为匹配当前工序的完整明确指令。
- 新增实质回归均先复现失败再修复；独立复核报告的三项边界问题与异步版本竞态已修正，再次复核未发现同等级遗漏。
- `cd process-plan-agent-ui && npm test`：48 个测试文件、401 项测试通过。
- `cd process-plan-agent-ui && npm run build`：类型检查与生产构建通过。
- `cd process-plan-agent-api && .venv/bin/python -m pytest -q`：696 passed，9 skipped；6 条依赖弃用提示。
- `git diff --check`：通过。未新增依赖或数据库列，未提交代码，未重启或发布运行中的服务。
