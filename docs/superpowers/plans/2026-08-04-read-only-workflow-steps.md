# 顶部流程步骤条只读 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将顶部五步流程条改为只读进度指示器，禁止鼠标和键盘触发页面跳转。

**Architecture:** 保留 `App.vue` 现有的步骤数据和状态计算，只移除步骤项的导航行为、交互语义和悬停反馈。新增源码级回归测试，沿用项目已有的 `App.vue?raw` 测试模式，确保步骤条持续为只读状态。

**Tech Stack:** Vue 3、TypeScript、Vue Router、Vitest、Vite

## Global Constraints

- 不修改页面底部导航按钮、Vue Router 路由表、项目上下文或流程状态判断。
- 不引入新依赖、组件或抽象。
- 保留步骤条当前、已完成、可用和锁定状态的颜色、圆点和连线。
- 不执行 Git commit；仅报告工作区修改。

---

### Task 1: 将顶部步骤条改为只读进度指示器

**Files:**
- Create: `process-plan-agent-ui/src/workflowStepIndicator.spec.ts`
- Modify: `process-plan-agent-ui/src/App.vue:1-58,95-109,291-317`

**Interfaces:**
- Consumes: `workflowSteps`、`stepStatus(stepNumber: number)`、`stepIsCompleted(stepNumber: number)` 和当前路由状态。
- Produces: 仅展示进度的 `.step-indicator`；不提供新的函数、事件或导航接口。

- [ ] **Step 1: 写入失败的回归测试**

```ts
import { describe, expect, it } from 'vitest'
import appSource from './App.vue?raw'

describe('workflow step indicator', () => {
  it('keeps every workflow step display-only', () => {
    const stepIndicator = appSource.match(/<nav class="step-indicator"[\s\S]*?<\/nav>/)?.[0]

    expect(stepIndicator).toBeDefined()
    expect(stepIndicator).toContain("['step', stepStatus(step.number)]")
    expect(stepIndicator).toContain(':aria-current=')
    expect(stepIndicator).not.toContain('@click=')
    expect(stepIndicator).not.toContain('@keydown')
    expect(stepIndicator).not.toContain(':role=')
    expect(stepIndicator).not.toContain(':tabindex=')
    expect(stepIndicator).not.toContain(':title=')
    expect(appSource).not.toContain('navigateToStep')
    expect(appSource).not.toContain('useRouter')
  })
})
```

- [ ] **Step 2: 运行测试并确认因现有导航绑定而失败**

Run: `npm test -- src/workflowStepIndicator.spec.ts`

Expected: FAIL，失败信息指出步骤条仍包含 `@click`、`@keydown`、交互语义或 `navigateToStep`。

- [ ] **Step 3: 实施最小代码修改**

在 `App.vue` 中：

```ts
import { RouterView, useRoute } from 'vue-router'

const route = useRoute()
```

删除 `useRouter`、`router` 和整个 `navigateToStep` 函数。步骤项保留状态类与 `aria-current`：

```vue
<div
  :class="['step', stepStatus(step.number)]"
  :aria-current="stepStatus(step.number) === 'active' ? 'step' : undefined"
>
  <div class="step-dot">{{ step.number }}</div>
  <span>{{ step.label }}</span>
</div>
```

从 `.step.completed` 和 `.step.available` 中移除 `cursor: pointer`，并删除对应的 `:hover` 规则。`.step` 已有 `cursor: default`，无需添加重复声明。

- [ ] **Step 4: 运行针对性测试并确认通过**

Run: `npm test -- src/workflowStepIndicator.spec.ts`

Expected: PASS，1 个测试文件通过且无错误。

- [ ] **Step 5: 运行完整前端测试**

Run: `npm test`

Expected: 所有 Vitest 测试通过。

- [ ] **Step 6: 运行生产构建**

Run: `npm run build`

Expected: `vue-tsc -b` 和 `vite build` 均成功完成。

- [ ] **Step 7: 在浏览器中验证交互与视觉状态**

启动项目已有 Vite 开发服务器，打开包含 `project_id` 的流程页面。记录当前 URL，依次点击顶部五个步骤的圆点与文字，确认 URL 和当前页面均不变化；使用 Tab 键确认步骤项不进入焦点顺序；确认步骤颜色、圆点、连线和底部前后导航按钮正常显示。

- [ ] **Step 8: 检查最终差异**

Run: `git diff -- process-plan-agent-ui/src/App.vue process-plan-agent-ui/src/workflowStepIndicator.spec.ts docs/superpowers/specs/2026-08-04-read-only-workflow-steps-design.md docs/superpowers/plans/2026-08-04-read-only-workflow-steps.md`

Expected: 差异仅包含设计、计划、只读步骤条实现和对应回归测试，不包含无关文件。
