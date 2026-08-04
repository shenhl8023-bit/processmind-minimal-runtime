# Hide Template Mapping Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在路线归并结果页临时隐藏“分组模板映射”和“详细信息”两个入口，同时保留底层映射数据及导出行为。

**Architecture:** 在 `ExtractRouteShellHeader` 内使用默认关闭的本地功能开关控制两个相邻按钮的渲染。父视图、弹窗、组件事件接口、映射持久化和路线序列化逻辑均保持不变，以便后续通过一处修改恢复入口。

**Tech Stack:** Vue 3、TypeScript、Vitest、Vue SSR renderer、Vite

## Global Constraints

- 不新增依赖。
- 不修改 ProcessMind V2 或 KmAI V1 规则包协议和导出语义。
- 保留工作区中已有的“模板分组映射”改名为“分组模板映射”的未提交修改。
- 不执行 `git commit`、`git push` 或其他未经用户明确要求的 Git 写操作。
- 两个入口必须完全不渲染，不能以禁用状态保留。

---

### Task 1: Hide Template Mapping Tools

**Files:**
- Create: `process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.spec.ts`
- Modify: `process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.vue`

**Interfaces:**
- Consumes: `ExtractRouteShellHeader` 现有 props，包括 `canEnter`、`hasTemplateAliases` 和 `showTemplateAliases`。
- Produces: 本地常量 `templateMappingToolsEnabled: false`，仅控制两个按钮的模板渲染；组件 props 和 emits 接口保持不变。

- [ ] **Step 1: Write the failing SSR render test**

创建 `process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.spec.ts`：

```ts
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { describe, expect, it } from 'vitest'
import ExtractRouteShellHeader from './ExtractRouteShellHeader.vue'

describe('ExtractRouteShellHeader', () => {
  it('hides the template mapping tools while keeping rerun available', async () => {
    const html = await renderToString(createSSRApp(ExtractRouteShellHeader, {
      editUnlocked: true,
      originalCount: 48,
      resultCount: 41,
      pendingCount: 0,
      canEnter: true,
      statusLabel: '可进入规则分析',
      hasTemplateAliases: true,
      showTemplateAliases: true,
      notice: '',
    }))

    expect(html).not.toContain('分组模板映射')
    expect(html).not.toContain('详细信息')
    expect(html).toContain('重新推理')
  })
})
```

- [ ] **Step 2: Run the test and verify RED**

Run from `process-plan-agent-ui`:

```powershell
npm test -- src/components/extract/ExtractRouteShellHeader.spec.ts
```

Expected: FAIL because the rendered HTML still contains `分组模板映射` and `详细信息`.

- [ ] **Step 3: Add the minimal local feature switch**

在 `ExtractRouteShellHeader.vue` 中用一个条件模板包住现有两个按钮：

```vue
<template v-if="templateMappingToolsEnabled">
  <button
    class="btn btn-text btn-sm route-shell-tool"
    type="button"
    :disabled="!canEnter"
    @click="$emit('open-template-mapping')"
  >
    <Connection class="icon-sm" />
    分组模板映射
  </button>
  <button
    class="btn btn-text btn-sm route-shell-tool"
    :class="{ 'route-shell-tool-active': showTemplateAliases }"
    type="button"
    :disabled="!hasTemplateAliases"
    @click="$emit('toggle-template-aliases')"
  >
    <InfoFilled class="icon-sm" />
    详细信息
  </button>
</template>
```

在 `<script setup lang="ts">` 中添加默认关闭的常量：

```ts
const templateMappingToolsEnabled = false
```

不得删除 `Connection`、`InfoFilled`、相关 props、emits 或 CSS；这些内容属于保留的临时屏蔽实现，后续开启常量即可恢复入口。

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run from `process-plan-agent-ui`:

```powershell
npm test -- src/components/extract/ExtractRouteShellHeader.spec.ts
```

Expected: PASS, with `重新推理` present and both template mapping tool labels absent.

- [ ] **Step 5: Run the complete UI test suite**

Run from `process-plan-agent-ui`:

```powershell
npm test
```

Expected: all Vitest tests pass with no new warnings or errors.

- [ ] **Step 6: Run type checking and production build**

Run from `process-plan-agent-ui`:

```powershell
npm run build
```

Expected: `vue-tsc -b` and `vite build` both complete successfully.

- [ ] **Step 7: Inspect the final diff without committing**

Run from the repository root:

```powershell
git diff -- process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.vue process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.spec.ts
git status --short -- process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.vue process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.spec.ts
Get-Content -Raw -Encoding utf8 process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.spec.ts
```

Expected: the tracked diff contains only the existing label rename and local render switch, status lists the new test as untracked, and the displayed test contains the SSR assertions; no commit is created.
