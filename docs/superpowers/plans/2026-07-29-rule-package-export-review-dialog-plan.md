# 规则包导出审核弹窗实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每次点击“审核并导出规则包”都先展示中文审核弹窗，只有用户确认后才保存并下载规则包。

**Architecture:** `useFinalizeRulePackageExport` 先编译并生成结构化审核数据，通过统一回调等待用户决定；`RulePackageExportReviewDialog` 负责展示通过、映射待处理和未通过三种状态，并在需要时保存 KmAI 映射。`FinalizeView` 连接 Promise 式确认流程，保证取消和阻塞状态不会进入发布路径。

**Tech Stack:** Vue 3 Composition API、TypeScript、Vitest、Vite、Element Plus API（现有消息提示）。

## Global Constraints

- 所有面向用户的审核弹窗文案必须使用中文。
- 用户确认前不得调用规则包保存接口或下载函数。
- 最终 ZIP 必须继续使用保存接口返回的权威 KmAI 文件。
- 不改变 KmAI 映射优先级、规则包格式或后端接口。
- 设计、计划与实现只在完整验证后按功能范围提交，不单独提交半成品文档。

---

### Task 1: 为导出流程增加强制确认门

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`
- Test: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts`

**Interfaces:**
- Produces: `RulePackageExportReview`，字段包含 `status`、`projectName`、`processCount`、`ruleCount`、`validation`、`kmaiCompatibility`、`mappingIssues` 和 `rulePackage`。
- Produces: `onExportReviewRequired(review: RulePackageExportReview): Promise<boolean>`；仅返回 `true` 时允许发布。
- Preserves: `downloadRuleDocument(): Promise<void>` 和后端权威 KmAI 文件打包逻辑。

- [x] **Step 1: 写正常兼容规则包也必须确认的失败测试**

```ts
it('waits for export review before saving a compatible package', async () => {
  const review = vi.fn().mockResolvedValue(false)
  mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, true))

  const { downloadRuleDocument } = createExport({ onExportReviewRequired: review })
  await downloadRuleDocument()

  expect(review).toHaveBeenCalledWith(expect.objectContaining({ status: 'ready' }))
  expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
  expect(mocks.downloadBlob).not.toHaveBeenCalled()
})
```

- [x] **Step 2: 运行单测并确认因缺少统一审核回调而失败**

Run: `npm test -- src/composables/useFinalizeRulePackageExport.spec.ts`

Expected: FAIL，提示正常兼容路径未调用 `onExportReviewRequired`。

- [x] **Step 3: 写确认后保存下载且映射后重新编译的失败测试**

```ts
it('saves once after a compatible review is confirmed', async () => {
  const review = vi.fn().mockResolvedValue(true)
  mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, true))
  mocks.saveFinalizedRulePackage.mockResolvedValue(savedPackage())

  const { downloadRuleDocument } = createExport({ onExportReviewRequired: review })
  await downloadRuleDocument()

  expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
  expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
})
```

- [x] **Step 4: 实现结构化审核数据和强制确认门**

```ts
export type RulePackageExportReviewStatus = 'ready' | 'mapping_required' | 'blocked'

export type RulePackageExportReview = {
  status: RulePackageExportReviewStatus
  projectName: string
  processCount: number
  ruleCount: number
  validation: CompileRulePackageResponse['validation']
  kmaiCompatibility: CompileRulePackageResponse['kmai_compatibility']
  mappingIssues: KmaiMappingIssue[]
  rulePackage: RulePackageV2
}
```

在首次编译后构建审核数据。结构校验失败或存在非映射 KmAI 错误时状态为 `blocked`；只有映射错误时为 `mapping_required`；全部通过时为 `ready`。所有状态都调用审核回调，回调不是 `true` 时立即返回。映射确认后重新编译，再通过原有保存和下载路径。

- [x] **Step 5: 运行导出流程单测并确认通过**

Run: `npm test -- src/composables/useFinalizeRulePackageExport.spec.ts`

Expected: PASS，取消、正常确认、映射重编译和重编译失败路径均不发生越权保存或下载。

---

### Task 2: 建立统一中文审核弹窗

**Files:**
- Create: `process-plan-agent-ui/src/components/kmai/RulePackageExportReviewDialog.vue`
- Delete: `process-plan-agent-ui/src/components/kmai/KmaiMappingResolutionDialog.vue`
- Create: `process-plan-agent-ui/src/components/kmai/RulePackageExportReviewDialog.spec.ts`
- Reuse: `process-plan-agent-ui/src/utils/kmaiFactorMappings.ts`

**Interfaces:**
- Consumes: `RulePackageExportReview | null`、`projectId`、`allowGlobal`。
- Produces events: `confirmed`、`cancelled`、`update:modelValue`。
- Preserves: `createKmaiFactorMappingBatch`、`getKmaiFactorCatalog`、`previewKmaiFactorMappings` 的现有映射保存和预览顺序。

- [x] **Step 1: 写中文文案和三种状态的失败测试**

```ts
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import RulePackageExportReviewDialog from './RulePackageExportReviewDialog.vue'

it('renders the ready review in Chinese with an enabled confirmation', async () => {
  const context: { teleports?: Record<string, string> } = {}
  await renderToString(createSSRApp(RulePackageExportReviewDialog, {
    modelValue: true,
    review: readyReview,
    projectId: 12,
  }), context)
  const html = context.teleports?.body || ''

  expect(html).toContain('审核并导出规则包')
  expect(html).toContain('审核通过')
  expect(html).toContain('确认导出')
  expect(html).not.toContain('Resolve KmAI factor mappings')
})
```

- [x] **Step 2: 运行组件文案测试并确认组件尚不存在而失败**

Run: `npm test -- src/components/kmai/RulePackageExportReviewDialog.spec.ts`

Expected: FAIL，提示无法导入 `RulePackageExportReviewDialog.vue`。

- [x] **Step 3: 实现统一弹窗骨架和摘要**

```vue
<h2>审核并导出规则包</h2>
<p>请确认本次规则包的审核结果。确认后将发布并下载规则包。</p>
<dl>
  <div><dt>项目</dt><dd>{{ review?.projectName }}</dd></div>
  <div><dt>工序</dt><dd>{{ review?.processCount }}</dd></div>
  <div><dt>规则</dt><dd>{{ review?.ruleCount }}</dd></div>
</dl>
```

`ready` 显示“审核通过”；`mapping_required` 渲染现有映射表单；`blocked` 显示中文错误详情并禁用确认按钮。

- [x] **Step 4: 迁移映射处理并修正中文错误信息**

保留草稿创建、候选过滤、项目作用域、手工布尔因子提示、批量保存和预览。只有 `mapping_required` 状态加载因子目录；普通通过状态直接发出 `confirmed`；预览失败时保持弹窗打开并显示 `映射预览仍有未解决项，请调整后重试。`。

- [x] **Step 5: 删除旧英文弹窗并运行组件及映射工具测试**

Run: `npm test -- src/components/kmai/RulePackageExportReviewDialog.spec.ts src/utils/kmaiFactorMappings.spec.ts`

Expected: PASS，审核弹窗无旧英文主文案，映射请求结构保持兼容。

---

### Task 3: 接入第四步并统一阻塞状态

**Files:**
- Create: `process-plan-agent-ui/src/composables/useRulePackageExportReview.ts`
- Create: `process-plan-agent-ui/src/composables/useRulePackageExportReview.spec.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`

**Interfaces:**
- Consumes: `RulePackageExportReview` 和 `onExportReviewRequired`。
- Produces: 每次按钮点击后的唯一审核弹窗；确认 Promise 解析为 `true`，取消解析为 `false`。

- [x] **Step 1: 写审核 Promise 状态机的失败测试**

```ts
it('resolves only the active review and clears its state', async () => {
  const state = useRulePackageExportReview()
  const first = state.request(readyReview)
  expect(state.review.value).toBe(readyReview)
  expect(state.visible.value).toBe(true)

  state.complete(true)

  await expect(first).resolves.toBe(true)
  expect(state.visible.value).toBe(false)
  expect(state.review.value).toBeNull()
})
```

- [x] **Step 2: 运行测试并确认审核状态组合函数尚不存在而失败**

Run: `npm test -- src/composables/useRulePackageExportReview.spec.ts`

Expected: FAIL，提示无法导入 `useRulePackageExportReview`。

- [x] **Step 3: 接入 Promise 式统一审核弹窗**

将 `mappingDialogVisible`、`mappingRulePackage` 和 `mappingResolutionPromise` 替换为 `exportReviewVisible`、`exportReview` 和 `exportReviewPromise`。`requestExportReview(review)` 每次覆盖前先以 `false` 结束旧 Promise，`completeExportReview(confirmed)` 清理状态并结束当前 Promise。

- [x] **Step 4: 将批量审核后仍未完成的规则放入同一弹窗**

在 `handleReviewAndExport` 发现 `remaining` 时构造 `blocked` 审核状态，摘要显示当前项目、工序和规则数量，详情列出待处理工序；不再打开旧的独立导出阻塞弹窗。确认按钮保持禁用，关闭后返回规则页面。

- [x] **Step 5: 运行相关前端测试和构建检查**

Run: `npm test -- src/composables/useRulePackageExportReview.spec.ts src/composables/useFinalizeRulePackageExport.spec.ts src/components/kmai/RulePackageExportReviewDialog.spec.ts src/utils/kmaiFactorMappings.spec.ts`

Expected: PASS；随后运行 `npm run build`，确认 `FinalizeView` 已正确连接新组件和类型。

---

### Task 4: 全量验证与交互检查

**Files:**
- Verify only; no new files.

**Interfaces:**
- Verifies all earlier task contracts together.

- [x] **Step 1: 运行前端完整单元测试**

Run: `npm test`

Expected: 所有 Vitest 测试通过，0 failures。

- [x] **Step 2: 运行类型检查和生产构建**

Run: `npm run build`

Expected: `vue-tsc -b` 和 `vite build` 均以退出码 0 完成。

- [x] **Step 3: 启动开发服务器并在浏览器验证**

Run: `npm run dev -- --host 127.0.0.1`

检查桌面和窄屏视口：按钮点击后弹窗无英文、摘要不溢出、取消不下载、确认后进入导出、映射表单可滚动且操作区始终可见。

- [x] **Step 4: 检查最终差异和未提交状态**

Run: `git diff --check` 和 `git status --short`

Expected: 无空白错误；设计、计划、测试和实现位于同一功能分支，提交范围不包含依赖缓存或构建产物。
