# Generate Input Boolean Group Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group every boolean input on the route-generation page into one compact, responsive “工艺选项” card without changing field values, validation, progress, or request payloads.

**Architecture:** Keep `useGenerateInputFields` as the single source of truth for schema order, values, validation, and submission. `GenerateInputPanel` will derive two presentation-only lists from the immutable `inputFields` prop, rendering standard fields in their existing order and boolean fields in a dedicated two-column section. A server-rendered component test will lock the grouping, empty-state, order, and responsive-class contract.

**Tech Stack:** Vue 3 composition API and scoped CSS, TypeScript, Vitest, Vue server renderer.

## Global Constraints

- Only `process-plan-agent-ui/src/components/generate/GenerateInputPanel.vue` and its focused test may change for this feature.
- Treat both `boolean` and `bool` as boolean fields by reusing the supplied `isBooleanField` predicate.
- Do not mutate `inputFields`, `fieldValues`, `customInputValues`, schema normalization, validation, progress counting, default values, or generated request payloads.
- The boolean group renders only when it has at least one field.
- Desktop uses two columns; viewports at or below 640px use one column.
- Do not add dependencies.

---

### Task 1: Specify and implement grouped boolean rendering

**Files:**
- Create: `process-plan-agent-ui/src/components/generate/GenerateInputPanel.spec.ts`
- Modify: `process-plan-agent-ui/src/components/generate/GenerateInputPanel.vue`

**Interfaces:**
- Consumes: existing `inputFields: GenerateInputField[]`, `isBooleanField(field)`, `fieldValues`, `fieldPreviewValue(key)`, `fieldSourceLabel(source)`, `fieldTypeLabel(field)`, and `setFieldBoolean(key, value)` props.
- Produces: a `.field-list` containing only non-boolean entries and an optional `.boolean-field-group` containing every boolean entry in input order.

- [ ] **Step 1: Write the failing server-rendered component tests**

Create `GenerateInputPanel.spec.ts` with a common `baseProps` factory supplying every required component prop. Provide two ordinary fields (`material`, `precision`) and two booleans (`has_hole`, `need_trace`) in interleaved input order. Render with `renderToString(createSSRApp(GenerateInputPanel, baseProps()))` and add these assertions:

```ts
expect(html).toContain('class="boolean-field-group"')
expect(html).toContain('工艺选项')
expect(html).toContain('2 项')
expect(html).toContain('是否有内孔')
expect(html).toContain('是否需要追溯标印')
expect(html.indexOf('材料牌号')).toBeLessThan(html.indexOf('boolean-field-group'))
expect(html.indexOf('尺寸精度')).toBeLessThan(html.indexOf('boolean-field-group'))
expect(html.indexOf('是否有内孔')).toBeGreaterThan(html.indexOf('boolean-field-group'))
```

Also render with no boolean inputs and assert `expect(html).not.toContain('boolean-field-group')`. Read the SFC source via `?raw` and assert the responsive rule contract:

```ts
expect(source).toMatch(/\.boolean-field-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,/s)
expect(source).toMatch(/@media\s*\(max-width:\s*640px\)[\s\S]*\.boolean-field-grid\s*\{[^}]*grid-template-columns:\s*1fr;/s)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
npm test -- --run src/components/generate/GenerateInputPanel.spec.ts
```

Expected: FAIL because the component does not yet render `.boolean-field-group` or the “工艺选项” title.

- [ ] **Step 3: Derive display-only field collections in the panel**

In `GenerateInputPanel.vue`, prepend `const props = ` to the existing `defineProps` declaration, retaining its current complete prop type body. Add exactly these computed values after `defineEmits`:

```ts
const standardFields = computed(() => props.inputFields.filter(field => !props.isBooleanField(field)))
const booleanFields = computed(() => props.inputFields.filter(field => props.isBooleanField(field)))
```

Import `computed` from `vue`. Do not change the source `inputFields` order or state.

- [ ] **Step 4: Render the standard fields and single boolean group**

Change the existing `.field-list` loop to iterate over `standardFields`. Immediately after it, add this conditional section:

```vue
<section v-if="booleanFields.length" class="boolean-field-group" aria-labelledby="boolean-field-group-title">
  <div class="boolean-field-group-head">
    <div>
      <h3 id="boolean-field-group-title">工艺选项</h3>
      <p>统一设置与工艺路线相关的是否条件</p>
    </div>
    <span class="boolean-field-count">{{ booleanFields.length }} 项</span>
  </div>
  <div class="boolean-field-grid">
    <div v-for="field in booleanFields" :key="field.key" class="boolean-field-item" :class="{ complete: Boolean(fieldPreviewValue(field.key)) }">
      <div class="field-label-row">
        <div class="field-name-line">
          <span class="field-label">{{ field.name || field.key }}</span>
          <svg v-if="Boolean(fieldPreviewValue(field.key))" class="field-complete-icon" width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="7" fill="#22c55e" opacity="0.15"/>
            <path d="M5 8l2.5 2.5L11 5.5" stroke="#16a34a" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="field-meta">
          <span class="field-source" :class="`field-source-${fieldSourceKind(field.source)}`" :title="field.source || '规则包输入'">{{ fieldSourceLabel(field.source) }}</span>
          <span class="field-type">{{ fieldTypeLabel(field) }}</span>
          <span v-if="field.required" class="field-required">必填</span>
        </div>
      </div>
      <div class="boolean-choice" role="radiogroup" :aria-label="field.name">
        <button type="button" class="select-chip" :class="{ active: fieldValues[field.key] === true }" @click="setFieldBoolean(field.key, true)">是</button>
        <button type="button" class="select-chip" :class="{ active: fieldValues[field.key] === false }" @click="setFieldBoolean(field.key, false)">否</button>
      </div>
    </div>
  </div>
</section>
```

The buttons must call `setFieldBoolean(field.key, true)` / `setFieldBoolean(field.key, false)`. The `false` active-state comparison is explicit, so choosing “否” remains visibly selected even though it does not produce a completion icon.

- [ ] **Step 5: Add compact, responsive scoped styles**

Append styles adjacent to the existing `.field-list` and `.field-block` rules:

```css
.boolean-field-group { margin-top: 12px; padding: 12px; border: 1px solid #c7d2fe; border-radius: 9px; background: linear-gradient(135deg, #f8faff, #f5f3ff); }
.boolean-field-group-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.boolean-field-group-head h3 { margin: 0; color: var(--ink); font-size: 13px; font-weight: 750; }
.boolean-field-group-head p { margin: 3px 0 0; color: var(--muted); font-size: 11px; }
.boolean-field-count { flex-shrink: 0; padding: 2px 6px; border-radius: 999px; background: #e0e7ff; color: #4338ca; font-size: 10px; font-weight: 700; }
.boolean-field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.boolean-field-item { min-width: 0; padding: 8px; border: 1px solid #dbe3ee; border-radius: 7px; background: #ffffff; }
.boolean-field-item.complete { border-color: #c7d2fe; }
.boolean-field-item .field-label-row { margin-bottom: 7px; }
.boolean-field-item .field-meta { max-width: 50%; overflow: hidden; }
.boolean-field-item .field-source { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 640px) { .boolean-field-grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 6: Run the focused test and verify it passes**

Run:

```powershell
npm test -- --run src/components/generate/GenerateInputPanel.spec.ts
```

Expected: PASS. The test verifies a single group, interleaved-field reordering only in presentation, an omitted empty group, and the two-column-to-one-column responsive rule.

- [ ] **Step 7: Run the UI test suite and production build**

Run:

```powershell
npm test
npm run build
```

Expected: both commands exit with code 0. This covers existing Vue SSR tests and verifies type checking plus Vite production compilation.

- [ ] **Step 8: Inspect the rendered page at desktop and narrow viewport**

Start the UI with the project’s normal command, load the route-generation page using a rule package containing boolean fields, and inspect it at 1440px and 390px widths. Confirm one “工艺选项” card appears after ordinary fields, it uses two columns on desktop and one on mobile, every “是/否” field is inside it, and no text or buttons overflow.

- [ ] **Step 9: Commit the focused implementation**

Run:

```powershell
git add -- process-plan-agent-ui/src/components/generate/GenerateInputPanel.vue process-plan-agent-ui/src/components/generate/GenerateInputPanel.spec.ts
git commit -m "feat: group boolean generate inputs"
```

Expected: one commit that contains only the boolean-group component and its test. Do not include unrelated working-tree changes.
