# Question Rule Handoff Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline in this session.

**Goal:** 第三步完整草稿与模型补缺，可信地传给第四步。
**Architecture:** 复用现有条件AST和review；新增有界模型建议服务、审核知识子集、独立草稿面板；兼容旧记录。
**Tech Stack:** FastAPI / SQLAlchemy / Pydantic / Vue 3 / Vitest / pytest.
**Spec:** docs/superpowers/specs/2026-10-20-question-rule-handoff-design.md

## Global Constraints
- 在用户当前运行的工作区增量修改，不覆盖既有未提交工作；不改第二步。
- 不因计划文件再次索取已给出的执行授权，不自动提交混合工作区。
- 模型不替用户确认、不杜撰阈值，不每次点击等待模型。

## Review Focus
- 全覆盖样本不能绕过范围确认；未知信息不是false。
- 模型非法/不完整输出不能被确认或批量采纳。
- 来源不匹配或回答变更不能复用旧候选与旧确认。
- 同名多阶段工序必须按ID引用，顺序不表示触发。
- 超时/无模型/切换工序时草稿可恢复，迟到结果不覆盖。

### Task 1: Draft contracts, validation and persistence
Files: new app/services/analysis_drafts.py; models/schemas/review save/serialization/migration; tests/test_analysis_drafts.py.
Interfaces: AnalysisRuleDraft with scope, object, source_text, candidate, missing, provenance; validate_draft; build_source_text.
- [ ] Write failing validator and pending/confirmation persistence tests.
- [ ] Run pytest, implement minimal contract and persistence, rerun tests.

### Task 2: Knowledge and bounded model assistance
Files: new analysis_assistant router/service, curated knowledge JSON, prompt parts and loader sections; tests/test_analysis_assistant.py.
Interfaces: POST /api/extract/analysis-assistant, typed request/output with draft and next question; versioned cache/deadline.
- [ ] Write failing tests for hallucinated ID, insufficient answers, no model and cache invalidation.
- [ ] Implement evidence-scoped prompts, local fallback and cache; run targeted tests.

### Task 3: Third-step UI draft workflow
Files: new RuleDraftPanel.vue, useAnalysisRuleDraft.ts, api/analysisDrafts.ts; AnalysisView/workspace/helpers/QuestionTreePanel.
Interfaces: draft editor receives selected segment + answer trail; emits persisted review; automatic acceptance disabled; explicit confirmation only.
- [ ] Write failing helper/composable tests for sample coverage, stale response and pending drafts.
- [ ] Implement panel, local state, model checks and save/confirm; run UI tests.

### Task 4: Fourth-step handoff and verification
Files: condition_reviews/parser, finalizeViewHelpers/finalizeRulePackage, fourth-step card presentation and preprocessing.
Interfaces: exact confirmed source reuses validated structured candidate; scope/object preserved; pending drafts unresolved.
- [ ] Write failing handoff and invalidation tests.
- [ ] Implement reuse, prompt grounding and UI context; run all API/UI tests and build.
- [ ] Review changed files and record results/limitations.
