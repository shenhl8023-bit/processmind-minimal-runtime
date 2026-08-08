# R-006 服务端发布状态与过期原因接口设计

> - 日期：2026-08-08
> - 状态：已实施，验证通过
> - 跟踪条目：`R-006`
> - 影响范围：规则包状态服务、规则包 API、第四步发布状态、第五步生成入口

## 1. 背景

ProcessMind 已经具备规则包编译、发布、下载、归档和执行期防御校验，但这些能力没有形成统一的只读状态契约：

- 第四步通过重新提交本地编译 DTO 并比较 `content_hash` 判断当前包是否过期。
- 第五步通过“最新发布包是否存在”决定是否展示输入界面，真正执行时才由服务端检查来源漂移。
- 直接 API 调用无法在执行前获得稳定的 `can_publish`、`can_generate` 和阻塞原因代码。
- 执行服务发现来源漂移时会归档规则包，不适合直接被只读状态查询调用。

根因不是缺少某一个布尔字段，而是发布准备度、包有效性、KmAI 兼容性和执行能力分散在页面、发布服务与执行服务中，且现有执行保护混合了“判断”和“失效写入”两种职责。

## 2. 已确认边界

状态接口只表达服务端已持久化的事实。尚未提交、只存在浏览器本地的条件文本或因素草稿不进入服务端状态算法，由前端作为本地 `dirty` 状态单独阻止发布、下载或进入生成。

这一区分保证：

1. 同一个项目在不同页面、浏览器标签页和直接 API 调用中获得相同的服务端状态。
2. 状态查询可以使用无请求体的 `GET`，并保持幂等和无副作用。
3. 前端只负责“是否存在未提交编辑”这一交互事实，不复制规则包有效性、来源一致性或 KmAI 兼容性算法。

## 3. 目标

1. 提供一个项目级、只读、稳定的规则包状态接口。
2. 返回当前路线版本、工作流版本和最新规则包元数据。
3. 统一表达 `can_publish`、`can_generate` 和 `package_executable`。
4. 使用稳定原因代码说明发布或生成被阻止的原因。
5. 返回服务端已持久化审核的待确认数量、无效因素绑定数量和当前包 KmAI 兼容性摘要。
6. 第四步不再通过重新编译并比较哈希判断发布包是否过期。
7. 第五步不再仅凭“最新发布包存在”推断可以生成。
8. 状态查询不得归档规则包、修改项目、写入生成记录或提交事务。

## 4. 非目标

- 不把浏览器本地草稿提交给状态接口。
- 不改变 V2 规则包或 KmAI V1 四个 JSON 文件的协议。
- 不改变内容哈希算法、版本递增规则或 ZIP 归档结构。
- 不新增数据库列、迁移、触发器或运行时依赖。
- 不把规则包完整内容复制到状态响应；第五步仍通过现有最新包接口取得 `input_schema`。
- 不在本条目中生成 OpenAPI 前端客户端；该工作仍属于 `R-009`。
- 不让只读状态查询自动修复或归档历史异常数据。

## 5. 方案比较与决策

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| 新增只读 `GET /status` 聚合接口 | 职责清晰；无请求体；跨页面和直接 API 一致 | 需要新增服务与 DTO | 采用 |
| 扩展 `/latest` | 新增代码较少 | 没有发布包时的 `404` 与状态查询冲突；把完整包读取和能力判断耦合 | 不采用 |
| 使用 `POST` 提交候选草稿评估 | 可以评估未提交草稿 | 状态依赖客户端候选；无法成为持久化事实来源；契约和负载更大 | 不采用 |

## 6. API 契约

新增接口：

```http
GET /api/extract/finalized-rule-packages/status?project_id={project_id}
```

项目不存在时保持现有项目资源语义，返回 `404`。项目存在但没有路线或没有发布包时返回 `200`，由稳定阻塞原因表达不可用状态。

响应示例：

```json
{
  "project_id": 12,
  "project_status": "ROUTE_SET_READY",
  "workflow_revision": 7,
  "route": {
    "id": 34,
    "version": 3
  },
  "latest_package": {
    "id": 56,
    "version": 4,
    "route_version_id": 34,
    "schema_version": "2.0",
    "content_hash": "8f3b...",
    "status": "published"
  },
  "can_publish": true,
  "can_generate": true,
  "package_executable": true,
  "blockers": [],
  "review_summary": {
    "total": 6,
    "confirmed": 6,
    "pending": 0,
    "invalid_factor_bindings": 0
  },
  "kmai_compatibility": {
    "available": true,
    "valid": true,
    "error_count": 0,
    "warning_count": 1,
    "factor_catalog_version": "2026.11"
  }
}
```

### 6.1 能力字段语义

- `can_publish`：当前持久化工作流已具备尝试发布新版本的服务端前置条件。实际提交包仍由现有发布服务执行结构、引用、来源和 KmAI 完整校验。
- `package_executable`：当前 `published` 包本身通过 schema、包校验、路线关联和确认来源一致性检查。
- `can_generate`：`package_executable` 为真，且当前项目和路线状态允许进入第五步生成。
- `latest_package`：项目按版本和 ID 排序后的最新历史包，可为 `published`、`superseded` 或 `archived`；没有历史包时为 `null`。
- `route`：当前最新规范化路线；没有路线时为 `null`。

`can_publish` 不表示任意客户端构造的发布请求一定成功。它只表示服务端当前持久化状态没有已知发布阻塞；提交内容的完整校验继续由 `create_published_rule_package()` 负责。

### 6.2 稳定阻塞原因

阻塞项结构：

```json
{
  "code": "pending_rule_reviews",
  "message": "仍有规则需要确认。",
  "blocks": ["publish"],
  "count": 2
}
```

首批稳定代码：

| 代码 | 阻止能力 | 含义 |
| --- | --- | --- |
| `project_not_ready` | publish, generate | 项目尚未到达路线可发布/可执行阶段 |
| `route_missing` | publish, generate | 没有当前规范化路线 |
| `pending_rule_reviews` | publish | 持久化规则审核仍有待确认项 |
| `invalid_factor_bindings` | publish | 已确认条件存在无效或缺失的标准因素绑定 |
| `no_published_package` | generate | 没有当前 `published` 包 |
| `published_package_route_changed` | generate | 发布包关联路线不是当前路线 |
| `published_rule_sources_changed` | generate | 包内用户确认来源与数据库当前确认不一致 |
| `published_package_invalid` | generate | V2 包无法解析或规则包校验失败 |
| `kmai_incompatible` | generate | 当前 V2 包无法生成有效 KmAI V1 兼容导出 |

`message` 用于展示，客户端行为只依赖 `code` 和 `blocks`。相同原因只返回一次，按服务端定义的稳定顺序排列。

## 7. 服务设计

### 7.1 纯读取聚合服务

新增 `app/services/rule_packages/status.py`，提供项目级状态评估。服务负责：

1. 加载项目、最新规范化路线、该路线的持久化规则审核和项目最新历史规则包。
2. 单独加载当前 `published` 包；历史最新包和当前活动包不能混为同一概念。
3. 汇总审核状态，并使用标准因素目录校验已确认条件的因素绑定。
4. 对活动 V2 包执行只读解析、规则包校验、路线关联、确认来源一致性和 KmAI 导出检查。
5. 生成稳定阻塞原因，并由阻塞集合派生能力字段。

该服务只能执行查询和纯函数计算，不修改 ORM 对象，不调用 `flush()`、`commit()` 或 `rollback()`。

### 7.2 发布准备度

发布准备度只使用持久化状态：

1. `Project.status` 必须属于现有发布服务允许的 `ROUTE_SET_READY` 或 `GENERATED`。
2. 必须存在当前规范化路线。
3. 当前路线中已有持久化条件来源、候选或确认内容的审核记录必须处于当前目录版本下的有效确认状态。
4. 已确认条件必须通过标准因素绑定校验。

没有提交到服务端的页面草稿不计入 `review_summary`。前端在存在本地草稿时额外禁用操作，并在草稿进入服务端审核流程后刷新状态。

发布服务允许的项目状态集合应提取为可复用常量或纯函数，避免状态服务复制字符串集合。

### 7.3 执行有效性

把现有 `load_published_rule_package_for_execution()` 中的只读判断与归档副作用拆开：

- 纯读取检查负责包解析、路线关联、`validate_rule_package()`、`require_confirmed_user_rule_sources()` 和 KmAI 兼容性计算。
- 状态服务复用纯读取检查，只返回原因。
- 执行链路继续在发现 `published_rule_sources_changed` 时调用现有归档服务并返回结构化 `409`。

这样状态查询与实际执行使用同一套有效性算法，但只有命令路径可以产生生命周期写入。

### 7.4 KmAI 摘要

KmAI 摘要只针对当前活动 V2 包实时计算：

- 没有活动 V2 包时：`available=false`，其他计数为零。
- 有活动 V2 包时：复用 `build_kmai_compatibility_export()`，只返回有效性、错误数、警告数和因素目录版本，不返回四个完整 JSON 文件。
- KmAI 不兼容会阻止第五步生成，避免 ProcessMind V2 能执行但交付给 KmAI 的包不可用。

V1 历史包没有 KmAI V1 再导出步骤，状态响应返回 `available=false`，并按现有 V1 执行边界判断 `can_generate`，不对其强加 V2 来源校验。

## 8. 路由与事务边界

状态路由位于现有 `rule_packages.py`，只负责：

1. 接收并校验 `project_id`。
2. 调用状态服务。
3. 把项目不存在映射为 `404`。
4. 返回类型化响应。

路由不得获取工作流写锁，也不得提交或回滚。状态查询遇到历史异常包时返回阻塞原因；实际失效仍由条件写入或生成命令路径处理。

## 9. 前端接入

### 9.1 第四步

`useFinalizeWorkspace` 在加载项目、路线和审核数据时同时读取状态接口：

- 使用 `latest_package`、`package_executable` 和稳定阻塞码设置当前版本与过期提示。
- 删除加载时调用 `compileRulePackage()` 并比较 `content_hash` 的逻辑。
- 保留现有请求代次保护，旧项目的状态响应不得覆盖新项目。
- 发布、确认、重置或本地草稿提交成功后强制刷新状态。
- 本地存在未提交草稿时继续即时禁用发布/下载/下一步，但不伪造服务端阻塞码。

### 9.2 第五步

`GenerateView` 先读取状态接口：

- 只有 `can_generate=true` 时才使用现有最新包接口加载完整 `input_schema`。
- 不可生成时根据稳定代码展示服务端消息并清空旧包指纹。
- 生成请求仍携带包 ID、版本、哈希和工作流版本；状态查询不能替代执行时的并发与来源防御。

### 9.3 类型

在现有前端 API 模块定义封闭的状态 DTO 和阻塞码联合类型。只收敛 R-006 新增契约，不顺带清理其他 `Record<string, any>`。

## 10. 测试设计

### 10.1 后端服务与 API

1. 项目不存在返回 `404`。
2. 项目存在但无路线时返回 `route_missing`，且两个能力均为假。
3. 当前路线有待确认审核时返回准确数量和 `pending_rule_reviews`。
4. 已确认条件因素绑定无效时返回 `invalid_factor_bindings` 和准确数量。
5. 没有发布包时保留 `can_publish` 的独立结果，并以 `no_published_package` 阻止生成。
6. 最新历史包已归档时仍返回其元数据，但 `package_executable=false`。
7. 当前 V2 包有效、路线一致且来源一致时 `package_executable=true`、`can_generate=true`。
8. 路线不一致、包解析失败、校验失败、来源漂移和 KmAI 不兼容分别返回稳定代码。
9. 来源漂移状态查询前后数据库状态保持 `published`，证明查询无归档副作用。
10. 实际生成仍会归档来源漂移包并返回既有 `published_rule_package_changed`，证明命令路径行为未被削弱。
11. 来源漂移与包校验同时失败时，稳定阻塞码顺序保持来源漂移在包无效之前。
12. V1 当前执行能力保持兼容，不执行 V2 专属来源和 KmAI 再导出检查。

### 10.2 前端

1. 第四步使用状态响应识别当前包和过期包，加载时不再调用编译接口。
2. 状态接口失败时显示明确加载错误，不把未知状态当成可发布或可生成。
3. 旧项目的延迟状态响应不会覆盖新项目状态。
4. 本地未提交草稿仍能即时禁用相关操作。
5. 第五步仅在 `can_generate=true` 时加载完整包和输入 schema。
6. 稳定阻塞码驱动提示和清理，不匹配中文消息。
7. 条件解析、确认、批量确认和人工规则持久化成功后刷新服务端状态，最后一条确认完成后发布能力立即更新。

### 10.3 回归范围

- 规则包 API、生命周期、发布、执行和 KmAI 导出聚焦 pytest。
- 后端全量 pytest。
- `useFinalizeWorkspace`、发布动作、下载动作和生成上下文相关 Vitest。
- 前端全量 Vitest、`vue-tsc -b` 和 Vite 生产构建。
- `git diff --check` 与工作区状态核对。

## 11. 文件边界

| 文件 | 职责 |
| --- | --- |
| `app/services/rule_packages/status.py` | 纯读取状态聚合与稳定阻塞原因 |
| `app/services/rule_packages/execution.py` | 提取可由状态查询和执行共同复用的只读有效性判断 |
| `app/services/rule_packages/publishing.py` | 暴露发布允许状态的共享定义，不改变发布事务 |
| `app/services/rule_packages/contracts.py` | 状态响应、摘要和阻塞项 Pydantic 契约 |
| `app/routers/rule_packages.py` | 新增只读状态路由 |
| `tests/test_rule_package_status.py` | 状态服务/API 及无副作用覆盖 |
| `tests/test_generate_v2_production.py` | 保持执行期归档与结构化冲突回归 |
| `src/api/rulePackages.ts` | 状态 DTO 和 API 调用 |
| `src/composables/useFinalizeWorkspace.ts` | 用服务端状态替代本地编译哈希判断 |
| `src/composables/useFinalizeWorkspace.spec.ts` | 第四步状态接入和请求过期保护 |
| `src/views/GenerateView.vue` 及相关测试 | 使用 `can_generate` 保护第五步上下文加载 |
| `docs/重构与优化跟踪.md` | 记录 R-006 实际范围、证据和剩余风险 |

## 12. 兼容性与风险

### 12.1 兼容性

- 新增接口，不删除或改变现有成功响应。
- 现有发布、下载和生成请求结构保持不变。
- 无数据库迁移和数据重写。
- V2 与 KmAI V1 文件结构、字段和哈希保持不变。

### 12.2 风险与控制

- **只读检查与执行检查漂移：** 提取共享纯读取函数，状态和执行不得各写一套来源校验。
- **状态查询产生写入：** 用数据库前后状态断言覆盖来源漂移场景，路由不调用事务提交。
- **误把历史最新包当作活动包：** 分别查询 `latest_package` 和当前 `published` 包。
- **客户端缓存过期：** 状态查询纳入现有工作流缓存失效和请求代次保护；写操作后强制刷新。
- **本地草稿与服务端状态不同：** UI 明确组合服务端能力和本地 dirty 状态；不把本地状态写成服务端原因。
- **KmAI 导出成本：** 仅计算摘要且不序列化 ZIP；如果实测成为热点，再基于不可变 `content_hash` 增加缓存，本条目不预先引入缓存。

## 13. 完成标准

- [x] 只读状态接口和类型化响应已实现。
- [x] `can_publish`、`can_generate`、`package_executable` 及稳定阻塞码由服务端产生。
- [x] 当前路线、工作流、最新包、审核、因素绑定和 KmAI 摘要齐全。
- [x] 状态查询与执行复用只读有效性判断，且查询没有数据库副作用。
- [x] 第四步不再通过本地重新编译和哈希比较判断包是否过期。
- [x] 第五步只在服务端允许生成时加载并使用当前包。
- [x] 本地未提交草稿仍由前端 dirty 状态即时保护。
- [x] V2、KmAI V1、ZIP、哈希、数据库和现有写请求协议保持不变。
- [x] 聚焦测试、后端全量测试、前端全量测试和生产构建通过。
- [x] `docs/重构与优化跟踪.md` 已更新为实际完成状态和验证证据。
