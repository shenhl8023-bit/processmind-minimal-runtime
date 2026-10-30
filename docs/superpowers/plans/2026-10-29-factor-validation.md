# 三表输入约束修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. 用户已要求直接修复，持续执行，不重复审批。

**Goal:** 当前 IT 范围完整传到 KMAI，预检/发布通过且越界值在路线生成前被拒绝。

**Architecture:** 因素对象可选 validation，原生约束在公开三表中保留；编译版本 /5 与 /1～/4 冻结重建隔离；目标引擎强制执行，UI显示范围。

**Tech Stack:** Python 3.8+ 标准库，FastAPI/Pydantic，既有 KMAI JavaScript 模块及 Node 回归。

**Spec:** docs/superpowers/specs/2026-10-29-factor-validation-design.md

## Global Constraints

- 保持三份 JSON；不删除工程限制、不编造 CAD 参数。
- 不提交、reset 或覆盖已有改动；修改前保存 outputs/factor-validation-fix-20261029/baseline。
- 不运行 Win7 客体；历史快照只读兼容。

## Review Focus

- IT边界5/10合法，4/11拒绝；0、负值、小数与非有限值不得被truthy或溢出误判。
- optional缺失/空字符串/空数组与required独立，parameters预填不阻断用户修正。
- 重复CAD来源约束须保持语义，不可把集合长度改成每条特征名称长度。
- 旧/3与/4冻结表在添加validation后仍逐项相等，不能因版本升级失效。
- 不同请求factor_overrides/manual_defaults/CAD来源和HTTP生成都执行校验。

### Task 1: 目标引擎执行 validation

**Files:** KMAI skills/process-route-generator/scripts/config_route_engine.py；新增 tests/test_factor_validation.py。
**Interfaces:** factor.validation={min?,max?,min_length?,max_length?}；ConfigRouteEngine.run(request, parameters=False) 保持原签名。

- [x] 写实际引擎回归：范围边界、越界、长度、空值、覆盖值、重复数值来源、非法配置、参数预填。
- [x] 运行并记录 RED，随后最小实现加载及取值校验，再记录 GREEN。
- [x] 全目录 pytest 保持旧配置回归与当前安装验收。

### Task 2: 发布端保留约束与历史兼容

**Files:** API services/rule_packages/demo_tables.py、publication_projection.py、finalized_rule_package_helpers.py；test_demo_tables.py、test_rule_package_lifecycle.py、test_finalized_legacy_snapshots.py。
**Interfaces:** compile_demo_tables 默认输出约束，_v4_snapshot/_v3_snapshot保留原行为；新compiler /5；公开validator接受且验证validation。

- [x] 写失败测试覆盖真实KMAI导出执行、合法约束预检/发布、非法约束拒绝、历史/3/4不改写。
- [x] RED后实现，只对类型生效字段导出；无法等价转换的长度约束明确阻断。
- [x] 运行相关模块及API全套，保留全部失败日志和skip说明。

### Task 3: 目标界面范围提示与交付

**Files:** KMAI frontend/assets/modules/process_route.js；tests/process_route_feature_display.cjs；README_EXPORT.md。

- [x] 用实际模块回归验证min/max和范围提示，RED后实现；运行Node和KMAI全套。
- [x] 重启本次API并从当前项目真实预检；若可发布，用实际UI发布/下载，不编辑其它未确认规则。
- [x] 将当前三表与目标代码同步桌面KMAI和隔离测试副本；实际生成合法边界、拒绝4/11，确认技术要求修正不回退。
- [x] 更新覆盖包、逐文件哈希、数据库/文件备份和报告；全量API/UI/build与目标测试完成后做独立只读审查，处理重要问题。
