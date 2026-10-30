# Mapped Machining Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 发布只含有效映射加工节点的三表，并保持规则、快照和 KMAI 实际执行一致。

**Architecture:** 保留完整编译器；在发布边界新增纯投影函数。版本 3 快照冻结来源路线和投影结果，历史版本独立校验。

**Tech Stack:** Python/FastAPI/Pydantic、Vue/TypeScript、pytest/vitest、KMAI 标准库引擎。

**Spec:** docs/superpowers/specs/2026-10-29-mapped-machining-publication-design.md

## Global Constraints

- 用户已授权按评估直接实施，不重复请求审批。
- 保持三表字段、内部目录及 ID；辅助工序不要求几何映射。
- 不修改 KMAI 正在使用的配置，不覆盖无关工作区改动。
- 人工因素和严格孔型不进行没有依据的自动推断。

## Review Focus

- 被剔除工序处于 not/all/any 中时保持条件含义。
- required 加工工序在实际 CAD 不命中时不得残留空工序。
- 必要前置不能因导出筛选而丢失。
- 旧定稿包下载使用旧快照；新快照能检测重哈希后的不一致。
- 导出说明与实际三表数量一致，不修改内部原映射数据。

## Task 1: 纯发布投影与执行语义

**Files:** 新增 app/services/rule_packages/publication_projection.py、tests/test_publication_projection.py。

**Interfaces:** project_publication_tables(tables, package) -> (projected_tables, report)。输入已完整编译三表，输出保留原 ID 的子集。

- [x] 先写混合映射、加工必选、布尔依赖、前置约束、因素清理和不变性测试并确认失败。
- [x] 实现投影；引用被剔除节点按 false 化简；实际特征未命中的加工工序按 KMAI 默认剔除语义处理。
- [x] 用真实 KMAI 引擎验证无螺纹、仅槽、严格孔型及辅助工序行为。

## Task 2: 发布、快照、历史版本

**Files:** app/services/finalized_rule_package_helpers.py、app/routers/extract.py、tests/test_rule_package_lifecycle.py、tests/test_finalized_legacy_snapshots.py。

- [x] 写新发布筛选、来源冻结、重哈希篡改、旧版本下载和预检统计测试并确认失败。
- [x] 接入投影，版本 3 元数据；先完整验证身份，再筛选交付；快照重现不得读取实时映射。
- [x] 预检返回交付说明，保留已有格式和旧版本路径。

## Task 3: 页面说明与全链路验证

**Files:** src/components/finalize/FinalizePublishPrecheckDialog.vue 及测试；相关 API 类型（按需要）。

- [x] 先验证页面能看到实际导出数量和排除原因，再实现最小展示。
- [x] 运行 API 全套 pytest、UI 全套 vitest 和构建。
- [x] 独立审查本轮差异，修复重要问题并重跑针对性及完整验证。
- [x] 生成本轮验证记录和可审阅三表样例。

## Execution notes

工作区已有大量未提交改动，本轮原位实施并保存逐文件基线副本；不提交或回退他人内容。原位执行是为了使用用户已认可的当前项目状态。计划与设计已由会话中的“就按照以上实施”授权。
