# Knowledge Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现三个知识入口与离线只读目录。
**Architecture:** 共用_load_records，新增确定性catalog服务和GET列表/详情API；独立Vue目录组件嵌入现有问答页面。
**Tech Stack:** 现有FastAPI/Pydantic/Vue3/TypeScript，无新依赖。
**Spec:** docs/superpowers/specs/2026-10-26-knowledge-catalog-design.md

## Global Constraints
- CPython 3.8.10 x64；Chrome/Edge109；不修改Win7锁、启动器或打包配置。
- 当前工作区已有用户改动，直接做局部增量，不重置、不混入其他改动、不自动提交。
- 默认问答；浏览不调用模型；20条默认分页；缺失、冲突、来源及参数变体保持。

## Review Focus
- IDs含斜杠、中文时详情能正确定位。
- 快速切换、请求乱序、失败重试时不得显示旧列表/详情。
- 零值、异常上下限、缺失与来源不能丢失。
- 资源去重保留全部来源及不同参数变体。
- 目录不依赖模型、数据库或现代Python/浏览器API。

### Task 1: Read-only catalog API
Files: app/services/knowledge/catalog.py, app/schemas/knowledge_catalog.py, app/routers/knowledge.py, tests/test_knowledge_catalog.py.
Interfaces: GET /api/knowledge/catalog (section, category, topic, q, sort, page, page_size); GET /api/knowledge/catalog/record (record_id). 返回分类计数、total、raw_count、分页记录；详情保留原始fields/source/guidance。
- [x] 写行为测试并验证404失败：全量、过滤、分页、去重、异常、来源、无模型、特殊ID和非法参数。
- [x] 实现兼容3.8的catalog服务和只读API。
- [x] 运行新测试与既有知识库测试、Python3.8扫描。

### Task 2: Sidebar and catalog browser
Files: src/api/knowledge.ts, src/components/knowledge/KnowledgeCatalogPanel.vue, src/views/KnowledgeView.vue, corresponding specs.
Interfaces: CatalogPanel(section: knowledge|resources); API类型匹配Task1；详情独立按ID加载。
- [x] 写API及真实组件行为测试，观察失败。
- [x] 实现左侧三入口、分类搜索分页排序、详情与失败重试；切换保留问答和表格状态。
- [x] 运行全前端测试与chrome109生产构建。

### Task 3: Verification and review
- [x] 全后端测试、Win7契约与Python3.8扫描；报告所有失败。
- [x] 独立审查本次文件与现有改动交界；修复重要问题并回归。
- [x] 本地页面与列表/详情烟测，记录Win7实机验证限制。

## Execution Ledger
Pre-flight: Task1与Task2共享catalog契约，保持字段一致。
Ruling: 在现有工作区增量实现，不另开worktree；Win7相关未提交改动是本次兼容基线，不移走或覆盖。

Task 1: complete; catalog API tests RED→GREEN, final backend suite recorded in delivery note.
Task 2: complete; API/client/panel tests RED→GREEN; full frontend suite and chrome109 build passed.
Task 3: independent read-only review complete.
Final: fixed reversed equipment spindle bounds warning — test_catalog_flags_reversed_spindle_bounds_without_changing_source_values RED→GREEN.
Final: fixed contextual QA navigation hidden behind catalog — reveals QA for an incoming question while retaining catalog filters RED→GREEN, explicit v-show visibility asserted.
Final: minor visibility-test feedback addressed in the contextual regression test, not deferred.
Final: actual Win7 CPython3.8.10/Chrome109 execution remains target-machine acceptance; local CPython3.8.20 + pinned Pydantic2.10.6/core2.27.2 imported catalog services/contracts and validated both sections and40 details.
Final: source engineering correctness and unrelated dirty changes are preserved, not automatically corrected; raw values, status and provenance retained.
Final: current feature changes remain uncommitted for user review.
