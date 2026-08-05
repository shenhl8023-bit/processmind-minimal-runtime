# KmAI V1 导出上下文重构设计

## 目标

在不改变 KmAI V1 导出协议的前提下，降低 ProcessMind V2 到 KmAI V1 导出器的参数耦合和状态管理复杂度，使条件、路线和因素构建器可以独立验证。

## 范围与不变量

- 保留 `build_kmai_compatibility_export()` 作为唯一公共入口。
- 保持 `factor_schema.json`、`factor_expansion_rules.json`、`route_catalog.json` 和 `route_rules.json` 的顶层结构、字段语义、顺序、错误码和警告顺序不变。
- 保持 KmAI V1 的因素 ID、因素 key、条件操作符、动态因素分配和历史映射快照语义不变。
- 不修改数据库模型、HTTP 路由、V2 契约或运行时依赖。
- 不改变已发布规则包的行为；重构只调整内部状态传递方式。

## 当前问题

导出器已经按因素、条件、路线拆分，但路线构建仍需要分别接收因素注册表、条件预算、历史映射和多个回调。错误/警告与可变导出状态分散在调用栈中，导致以下风险：

1. 条件展开可能在预算检查、因素注册和错误收集之间形成隐式顺序依赖。
2. 新增导出阶段需要继续扩张函数参数，边界难以独立测试。
3. 完整导出行为依赖 facade 的组装顺序，局部构建器缺少统一的上下文契约。

## 设计

### 1. 导出上下文

新增内部 `KmaiExportContext` 数据类，集中保存一次导出的可变状态：

- `package: RulePackageV2`
- `registry: FactorRegistry`
- `budget: ConditionBudget`
- `legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None`
- `errors: list[ValidationIssue]`
- `warnings: list[ValidationIssue]`

上下文提供最小方法用于追加 issue、读取/注册因素以及记录已物化的条件子句。上下文只在单次调用中创建，不写入数据库、不缓存到模块级状态。

### 2. 构建器接口

- `build_route_catalog(package)` 继续返回 catalog 和 process key 映射；该步骤不修改上下文。
- `build_route_rules(context, process_keys)` 返回 route rules artifact；条件转换、预算检查、动态因素注册和 issue 收集通过 context 完成。
- `build_factor_schema(context)` 和 `build_factor_expansion_rules(context)` 从同一上下文读取包与因素注册结果。

构建器不直接依赖 FastAPI、数据库或路由模块。条件转换函数保留可注入的内部回调，以继续支持现有针对“超限时不物化条件”的测试钩子。

### 3. Facade 组装顺序

`build_kmai_compatibility_export()` 按以下顺序执行：

1. 解析正数限制并创建 `KmaiExportContext`。
2. 构建 `route_catalog` 和 process key 映射。
3. 构建 `route_rules`，累积错误/警告并更新因素注册表。
4. 根据最终注册表构建 `factor_schema` 和 `factor_expansion_rules`。
5. 执行跨 artifact 的因素引用校验。
6. 返回现有 `KmaiCompatibilityExport`。

任何阶段失败都只返回既有 issue 结构，不静默放宽限制或改变导出文件形状。

## 测试设计

先增加失败测试，再实现重构：

1. 同一次导出创建隔离上下文，不污染下一次导出。
2. 预算 `project()` 不改变计数；超限时不调用条件物化回调、不注册动态因素。
3. 动态因素按注册顺序分配稳定 ID，重复注册不产生新 ID。
4. 上下文构建器输出与 facade 输出逐 artifact 等价。
5. 现有 KmAI 导出、兼容性运行器、归档、生命周期和 API 测试保持通过。

## 风险与回滚

- 最大风险是参数重排导致私有测试 patch 点或历史导出顺序变化；通过保留 facade 回调别名和完整导出特征测试控制。
- 若任一协议特征测试失败，回退到只保留新增测试、不改变生产代码的状态，重新定位行为差异。
- 不涉及数据库迁移、发布数据或 KmAI 目标目录文件。

## 完成标准

- 新增上下文及边界测试先失败，随后在最小实现后通过。
- KmAI 相关重点测试和后端全量测试通过。
- `git diff --check` 无空白错误。
- 工作区中已有的未跟踪设计文档、运行输出和用户修改不被覆盖。
