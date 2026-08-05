# KmAI V1 导出上下文重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 KmAI V1 导出协议完全兼容的前提下，收敛导出器的共享状态传递，并修复无效工序引用在条件物化前留下副作用的问题。

**Architecture:** 保留 `build_kmai_compatibility_export()` 作为 facade。新增 `KmaiExportContext` 承载一次导出的规则包、因素注册表、条件预算、历史映射和 issue 列表；条件、路线、因素构建器通过上下文协作。路线规则先校验工序引用，再执行条件展开，避免无效规则污染因素注册和预算计数。保留 `_condition_dnf` facade 别名和现有输出组装顺序。

**Tech Stack:** Python 3.11+, FastAPI service modules, Pydantic 2, pytest, SQLAlchemy callers only.

## Global Constraints

- 不改变 `factor_schema.json`、`factor_expansion_rules.json`、`route_catalog.json`、`route_rules.json` 的字段、顺序、错误码、警告顺序和语义。
- 不修改数据库 schema、HTTP 路由、V2 contracts、KmAI 运行时协议或运行时依赖。
- 不改变 `build_kmai_compatibility_export()` 的参数、返回类型或现有调用方。
- `manual_override` 因素仍只能通过 `manual.factor_overrides` 提供；历史映射快照仍按发布包冻结。
- 组合数和条件对象数限制仍由 `PROCESSMIND_KMAI_MAX_COMBINATIONS`、`PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS` 控制。
- 遵循 TDD：每个生产代码变更前先增加一个会正确失败的测试并记录失败原因。
- 不覆盖工作区现有未跟踪设计文档、Playwright 输出或用户修改；不自动 commit/push。

---

### Task 1: 固定上下文和无效引用的行为基线

**Files:**
- Modify: `process-plan-agent-api/tests/test_kmai_export_context.py`
- Modify: `process-plan-agent-api/tests/test_kmai_export_routes.py`
- Modify: `process-plan-agent-api/tests/test_kmai_rule_package_export.py`（只在需要补充完整导出特征断言时修改）

**Interfaces:**
- Consumes: 现有 `RulePackageV2` fixture、`FactorRegistry`、`ConditionBudget`、`build_route_rules()`。
- Produces: 能约束 `KmaiExportContext` 的状态隔离和“先校验工序引用、后物化条件”的行为测试。

- [ ] **Step 1: 写上下文隔离的失败测试**

在 `test_kmai_export_context.py` 增加：

```python
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_export_context import KmaiExportContext


def test_export_context_keeps_issue_and_factor_state_per_export(rule_package_v2: RulePackageV2):
    first = KmaiExportContext.create(rule_package_v2, max_combinations=10, max_condition_objects=20)
    second = KmaiExportContext.create(rule_package_v2, max_combinations=10, max_condition_objects=20)

    first.warning("first_warning", "only first")
    first.registry.register("first_factor", {"factor_key": "first_factor"})

    assert [issue.code for issue in second.warnings] == []
    assert second.registry.values() == []
```

- [ ] **Step 2: 写预算拒绝不调用条件物化的失败测试**

在 `test_kmai_export_routes.py` 增加一个包含 `any` 展开的规则，并传入会抛错的 `condition_dnf_fn`；当 `condition_expansion_size_fn` 返回超过上限的数量时，断言回调未被调用、上下文注册表为空。

```python
def test_route_rules_rejects_over_budget_before_materializing(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.rules = [package.route_rules.rules[0]]
    _, process_keys = build_route_catalog(package)
    context = KmaiExportContext.create(package, max_combinations=1, max_condition_objects=100)
    calls = []

    def materialize(*_args):
        calls.append(True)
        raise AssertionError("condition materialization must not run")

    result = build_route_rules(
        context,
        process_keys,
        condition_dnf_fn=materialize,
        condition_expansion_size_fn=lambda _node: (2, 2),
    )

    assert calls == []
    assert context.registry.values() == []
    assert result.errors[0].code == "kmai_combination_limit_exceeded"
```

- [ ] **Step 3: 写无效工序引用不污染后续状态的失败测试**

构造第一条含动态因素且引用不存在工序、第二条为有效规则的包；让条件回调注册一个因素并记录调用。断言无效规则不会调用回调，后续有效规则仍能正常输出。

- [ ] **Step 4: 运行新增测试确认按预期失败**

从 `process-plan-agent-api` 执行：

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_export_context.py tests/test_kmai_export_routes.py
```

预期：因 `KmaiExportContext` 尚不存在、`build_route_rules()` 尚未接受上下文而失败；如果测试直接通过，先修正测试使其确实覆盖新行为。

---

### Task 2: 实现导出上下文和状态操作

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export_context.py`
- Test: `process-plan-agent-api/tests/test_kmai_export_context.py`

**Interfaces:**
- Consumes: `RulePackageV2`、`ValidationIssue`、既有 `FactorRegistry` 和 `ConditionBudget`。
- Produces: `KmaiExportContext.create()`、`warning()`、`error()`、`record_clauses()` 及公开的 `package`、`registry`、`budget`、`legacy_adapters`、`errors`、`warnings` 属性。

- [ ] **Step 1: 定义上下文接口测试**

补充断言：`create()` 使用传入的正数限制；`warning()`/`error()` 追加 issue；`record_clauses()` 只调用 `ConditionBudget.record()` 一次并保持计数一致。

- [ ] **Step 2: 运行测试确认接口仍失败**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_export_context.py
```

- [ ] **Step 3: 写最小实现**

在现有 context 模块中新增数据类。为避免 `kmai_export_context.py` 与 `kmai_export_factors.py` 循环导入，历史映射类型使用 `TYPE_CHECKING` 下的类型导入，运行时字段采用 `Mapping[tuple[str, str], Any] | None`。`create()` 只创建新 registry、budget 和 issue 列表，不复用模块级对象。

- [ ] **Step 4: 运行上下文测试确认通过**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_export_context.py
```

---

### Task 3: 迁移条件与路线构建器

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export_conditions.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export_routes.py`
- Modify: `process-plan-agent-api/tests/test_kmai_export_conditions.py`
- Modify: `process-plan-agent-api/tests/test_kmai_export_routes.py`

**Interfaces:**
- Consumes: `KmaiExportContext`。
- Produces: `condition_dnf()` 的 facade 兼容包装和 `build_route_rules(context, process_keys, *, condition_dnf_fn, condition_expansion_size_fn)`。

- [ ] **Step 1: 增加条件上下文调用的失败测试**

为条件翻译增加一个测试：通过 context 调用后，动态因素进入 `context.registry`，警告进入 `context.warnings`，而不是由调用者维护平行列表。

- [ ] **Step 2: 增加路线参数契约的失败测试**

更新路线测试调用 `build_route_rules(context, process_keys, ...)`，并保留现有 `result.payload`、`result.errors` 断言，确保 artifact 返回契约不变。

- [ ] **Step 3: 运行测试确认迁移前失败**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_export_conditions.py tests/test_kmai_export_routes.py
```

- [ ] **Step 4: 迁移条件内部实现**

新增内部 `condition_dnf_with_context(context, node, path)`；将 `_fixed_leaf_condition`、递归展开和动态因素/历史映射访问改为从 context 读取。保留现有 `condition_dnf(package, node, registry, warnings, path, legacy_adapters)` 作为薄包装，构造临时 context 后调用新实现，以兼容现有直接导入和 facade patch 点。

- [ ] **Step 5: 迁移路线构建并调整校验顺序**

`build_route_rules()` 先执行无副作用的条件规模估算和预算检查，再计算 include/exclude 的 `missing_ids`。发现无效工序时记录既有 `kmai_process_reference_missing` 并跳过该规则；只有工序引用有效时才执行条件物化和 `record_clauses()`。这样保留原有错误顺序：规则按输入顺序处理，同一规则仍先组合数错误、再条件对象数错误，同时无效工序引用不会注册因素或消耗预算。

- [ ] **Step 6: 运行构建器测试确认通过**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_export_context.py tests/test_kmai_export_conditions.py tests/test_kmai_export_routes.py
```

---

### Task 4: 迁移因素构建器和 facade

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export_factors.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py`
- Modify: `process-plan-agent-api/tests/test_kmai_export_factors.py`
- Modify: `process-plan-agent-api/tests/test_kmai_rule_package_export.py`

**Interfaces:**
- Consumes: `KmaiExportContext` 及现有因素/映射辅助函数。
- Produces: `build_factor_schema(context)`、`build_factor_expansion_rules(context)` 的内部调用；facade 的既有签名、返回模型和 `_condition_dnf` patch hook。

- [ ] **Step 1: 增加上下文因素 artifact 等价性失败测试**

从 facade 导出结果和同一 context 构建的两个因素 artifact 逐项比较；同时断言 factor ID、动态因素顺序和 material options 不变。

- [ ] **Step 2: 运行测试确认迁移前失败**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_export_factors.py tests/test_kmai_rule_package_export.py
```

- [ ] **Step 3: 迁移因素构建器签名**

让因素 schema 从 `context.package` 和 `context.registry` 读取；让 expansion rules 从 `context.package` 读取。保留必要的旧签名薄包装，避免 archive、runner 和历史测试的直接导入失效。

- [ ] **Step 4: 重写 facade 为显式组装流程**

在 `build_kmai_compatibility_export()` 中创建一次 context，调用各构建器，并将 route artifact 的 errors/warnings 合并到 context；保留 `files` 字典键顺序及最终 factor reference 检查。`_condition_dnf` 仍指向兼容包装，确保现有超限 patch 测试继续有效。

- [ ] **Step 5: 运行导出回归测试**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_export_context.py tests/test_kmai_export_factors.py tests/test_kmai_export_conditions.py tests/test_kmai_export_routes.py tests/test_kmai_rule_package_export.py tests/test_kmai_compatibility_runner.py
```

---

### Task 5: 全链路验证与差异审查

**Files:**
- Verify only: `process-plan-agent-api/app/services/rule_packages/`
- Verify only: `process-plan-agent-api/tests/`

**Interfaces:**
- Consumes: Tasks 1–4 的上下文、构建器和 facade。
- Produces: 协议等价性证据、测试结果和可审阅的最小 diff。

- [ ] **Step 1: 运行导出特征签名和重点测试**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_kmai_rule_package_export.py tests/test_kmai_export_*.py
```

在 PowerShell 中若通配符不被 pytest 接受，改用已列出的四个 `test_kmai_export_*.py` 文件逐个传入。

- [ ] **Step 2: 运行受影响的归档、生命周期、执行和 API 测试**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_rule_package_archive.py tests/test_rule_package_lifecycle.py tests/test_rule_package_execution.py tests/test_rule_package_api.py
```

- [ ] **Step 3: 运行后端全量测试**

```powershell
..\.runtime\python\python.exe -m pytest -q
```

- [ ] **Step 4: 检查协议 diff 和空白**

```powershell
git diff --check
git diff -- process-plan-agent-api/app/services/rule_packages process-plan-agent-api/tests
```

逐项确认没有数据库、路由、V2 契约或四个 V1 文件顶层结构的非必要变更。

- [ ] **Step 5: 汇报验证结果和剩余风险**

只报告实际命令输出；不自动提交、推送或删除任何文件。
