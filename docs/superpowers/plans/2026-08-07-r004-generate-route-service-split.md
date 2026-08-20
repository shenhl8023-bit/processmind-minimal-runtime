# R-004 生成路由应用服务拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将参数审核聚合和 V1/V2 路线生成领域编排从 `routers/generate.py` 移到可独立测试的应用服务，同时保持现有 HTTP、规则包和事务契约。

**Architecture:** `param_audit.py` 负责参数审核数据聚合、答案读取和稳定/待确认/数据问题状态计算；`route_generation.py` 负责加载当前发布包、校验指纹、选择 V1/V2 执行器、处理旧规则兜底并返回类型化生成结果。路由只负责工作流锁、领域异常到 HTTP 的映射、`GeneratedRoute` 持久化、提交和响应包装。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic 2、SQLAlchemy async、pytest。

## Global Constraints

- 保持 `/api/generate/` 的成功字段、错误状态和“无有效已发布包返回 409”契约。
- 不改变 V1 算法、V2 规则包协议、数据库结构或 KmAI 导出内容。
- 应用服务不提交或回滚外层事务；归档状态的最终提交仍由路由负责。
- 保留 `_normalize_input_values` 的兼容导入，避免旧测试/调用方破坏。

## Task 1: 参数审核应用服务

**Files:**
- Create: `process-plan-agent-api/app/services/param_audit.py`
- Modify: `process-plan-agent-api/app/routers/generate.py`
- Create: `process-plan-agent-api/tests/test_param_audit_service.py`

- [x] 写失败测试，使用最小 `ParamJsonStageOut`、规则和样本对，覆盖稳定、待确认和数据问题三种状态。
- [x] 运行聚焦测试并确认先因服务模块缺失或聚合入口缺失而失败。
- [x] 迁移参数审核聚合、问题增强、答案读取和 overview 构造到服务模块，补齐 `defaultdict` 等依赖。
- [x] 运行测试确认三种状态通过，并确保服务不执行数据库提交。
- [x] 从路由移除重复参数审核实现，仅保留兼容性别名或显式服务入口。

## Task 2: 路线生成应用服务

**Files:**
- Create: `process-plan-agent-api/app/services/route_generation.py`
- Modify: `process-plan-agent-api/app/routers/generate.py`
- Modify: `process-plan-agent-api/tests/test_generate_v2_production.py`
- Create: `process-plan-agent-api/tests/test_route_generation_service.py`

- [x] 写失败测试，覆盖当前发布包指纹匹配、旧客户端省略指纹、V2 规划结果和 V1/旧规则路径选择。
- [x] 运行聚焦测试确认服务入口尚不存在。
- [x] 实现类型化 `RouteGenerationResult` 和异步生成入口，集中项目/操作查询、输入归一化、发布包读取及 V1/V2 选择。
- [x] 保持来源漂移、指纹冲突、无包、输入无效、规则无效和规划失败异常类型不变。
- [x] 运行服务及现有 API 测试，确认结果元数据和步骤顺序不变。

## Task 3: 路由收缩与文档同步

**Files:**
- Modify: `process-plan-agent-api/app/routers/generate.py`
- Modify: `docs/重构与优化跟踪.md`

- [x] 让路由只保留锁、HTTP 异常映射、`GeneratedRoute` 写入、项目状态更新、提交和响应组装。
- [x] 修正注释中“无规则包回退第二步”的过期描述。
- [x] 将 R-004 标为已验证完成，记录聚焦/全量测试证据和未验证环境限制。
- [x] 运行后端聚焦、全量、`git diff --check`，必要时运行前端构建回归。
