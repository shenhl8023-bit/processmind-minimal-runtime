# ProcessMind Domain Context

## 一句话

从历史工艺规程提炼规则，再按零件因素**确定性**生成工艺路线的典型工艺规程智能体（最小可运行包）。

## 核心不变量

1. 在给定**已发布规则包** + **零件因素输入**下，工艺路线生成必须确定性（同输入同输出）。
2. LLM 用于辅助（抽取、解释、问答、配置），**不是**正式路线生成的隐式随机源。
3. 第 5 步正式生成只读 **published** 规则包；草稿不影响生产路径。
4. V2 规则通过稳定 **`process_id`** 关联工序，不依赖中文工序名匹配。
5. V1 历史包继续可用；有 published V2 时优先正式 V2 路径。

## 五步业务闭环（摘要）

| 步 | 含义 | 主要落点 |
|----|------|----------|
| 1 | 上传/解析历史规程 | API 解析 + UI 上传 |
| 2 | 母路线/样本归并 | route merge 相关 composables |
| 3 | 规则因素分析与问答审核 | analysis / question tree |
| 4 | 规则定稿与规则包生命周期 | finalize + `rule_packages` + lifecycle panel |
| 5 | 按因素填写并生成路线 | generate + input fields / plan_route |

## 规则包 V2（进行中）

- 方案：`docs/规则包V2-通用化实施方案.md`
- 阶段清单：`docs/规则包V2-阶段3实施清单.md`
- 后端核心：`process-plan-agent-api/app/services/rule_packages/`
- 预览接口：`POST /compile` · `POST /validate` · `POST /simulate`（不写库预览）
- 生命周期：草稿保存、发布、回滚、按 ID 模拟
- 前端：第 4 步生命周期面板；第 5 步按 `schema_version=2.0` 的 `fields` 动态渲染（以代码为准，文档若滞后以代码为准）

### 已知后续增强（非阻塞主路径时可单独立项）

- 第 4 步面板内嵌模拟预览与校验错误结构化展示
- 跨项目模板库（阶段 4）
- 项目级引擎开关 UI（当前策略：有 published V2 即正式 V2）

## 模块地图

| 区域 | 路径 | 职责 |
|------|------|------|
| API | `process-plan-agent-api/app/` | 规则加载、校验、路线生成、表单 schema、提炼流程 |
| Rule packages | `process-plan-agent-api/app/services/rule_packages/` | V2 契约、编译、校验、规划、生命周期 |
| UI | `process-plan-agent-ui/src/` | 五步向导、动态表单、结果展示 |
| Knowledge | `process-plan-agent-api/knowledge/` | 内置工艺知识与提问规范 |
| Prompts | `process-plan-agent-api/prompt_parts/` | 提示片段 |
| Data | `data/` | SQLite 与上传快照（勿把密钥写进 skill 产物） |
| Docs | `docs/` | 方案、分析报告、配置模板、agent 配置 |
| Tickets | `.scratch/` | 本地 spec 与实现工单 |

## 术语表

| 术语 | 含义 | 避免混用 |
|------|------|----------|
| 规则包 | 可版本化的物化规则快照（含 schema、目录、规则等） | 不是单次 LLM 对话记忆 |
| V1 规则包 | 早期五文件导出形态；名称匹配等限制较多 | 不是 V2 草稿 |
| V2 规则包 | 严格契约 + 表达式引擎 + 生命周期（draft/published） | 不是「仅前端写死字段」 |
| 零件因素 / factor_values | 第 5 步提交的结构化输入 | 不是自由文本 prompt |
| input_schema | 描述第 5 步表单字段（V2 用 `fields`） | 不是 route_catalog |
| process_id | 工序稳定标识 | 不是工序显示名 |
| 确定性生成 / plan_route | 规则包+输入 → 可复现工序序列 | 不是「模型觉得合理」 |
| published | 已发布、可供第 5 步正式使用 | 不是 draft |
| draft | 可模拟/可编辑，不进正式生成 | 不是 published |
| 母路线 | 从样本归并得到的典型工序骨架 | 不是单次生成结果 |
| 定稿（第 4 步） | 将分析结果固化为规则包 | 不是第 5 步填表 |

## 技术栈

- 前端：Vue 3 · TypeScript · Vite · Element Plus · Axios · Vitest
- 后端：FastAPI · SQLAlchemy 2 异步 · aiosqlite · Pydantic v2
- 数据：SQLite（`data/db/`）
- LLM：可配置 OpenAI 兼容接口（设置勿提交密钥）

## 开放决策 / 待澄清

（由 `/grill-with-docs` 更新。当前占位：）

- 项目级 V1/V2 引擎开关是否需要独立 UI，还是维持「有 published V2 即 V2」
- 第 4 步模拟预览的错误展示信息架构
- 阶段 4 模板库的边界（跨项目合并策略）

## 相关 ADR

见 `docs/adr/`（有决策时新增 `NNNN-title.md`）。
