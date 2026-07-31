# Template Replacement Auto-Parse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse a selected Kmsoft group-template XML immediately while preserving explicit confirmation before replacement.

**Architecture:** Add a small file-acceptance helper beside the existing template mapping utilities so validation and automatic preview dispatch are independently testable. The dialog keeps the selected file visible during parsing, exposes retry only after a failed parse, and continues to use `useProjectGroupTemplate.selectFile` for request ordering and error state.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vite.

## Global Constraints

- Selecting or dropping a valid `.xml` must start preview parsing immediately.
- Parsing must never commit or replace the current template.
- A failed parse must retain the file for retry and allow choosing another file.
- Existing same-file reselection and drag-and-drop behavior must remain supported.

---

### Task 1: Automatic Template Preview Dispatch

**Files:**
- Modify: `process-plan-agent-ui/src/composables/templateGroupMapping.ts`
- Test: `process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts`
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue`

**Interfaces:**
- Consumes: `File | undefined` and `(file: File) => Promise<void>`.
- Produces: `acceptTemplateGroupFile(file, parseFile)` returning the accepted file and validation error after automatically invoking preview parsing for valid XML.

- [x] **Step 1: Write the failing test**

Add tests proving a valid `临时壳体4.xml` invokes the parser before the acceptance promise resolves and a non-XML file returns the existing Chinese validation message without invoking parsing.

- [x] **Step 2: Run the focused test to verify RED**

Run: `npm test -- src/composables/templateGroupMapping.spec.ts`

Expected: FAIL because `acceptTemplateGroupFile` is not exported.

- [x] **Step 3: Implement the minimal helper and dialog wiring**

Implement `acceptTemplateGroupFile`, call it from file input and drop handlers, keep `pendingFile` during loading/failure, remove the manual parse action from the successful path, and show `重新解析` only when parsing failed.

- [x] **Step 4: Run focused tests to verify GREEN**

Run: `npm test -- src/composables/templateGroupMapping.spec.ts`

Expected: all focused tests pass.

- [x] **Step 5: Verify the complete frontend**

Run: `npm test`

Run: `npm run build`

Expected: all Vitest files pass and the production build exits with status 0.

- [x] **Step 6: Browser regression with the reported XML**

Open project 51, choose `临时壳体4.xml`, verify the preview automatically shows 9 groups and 105 feature selections, then cancel replacement so project data remains unchanged.

---

### Task 2: Preserve Replacement Preview Across Native Picker Focus Refresh

**Files:**
- Modify: `process-plan-agent-ui/src/composables/extractViewHelpers.ts`
- Test: `process-plan-agent-ui/src/composables/extractViewHelpers.spec.ts`
- Modify: `process-plan-agent-ui/src/views/ExtractView.vue`

- [x] **Step 1: Add a failing display-state regression test**

Prove that route loading keeps the workspace mounted while the template mapping dialog is visible, but still shows normal loading progress when the dialog is closed.

- [x] **Step 2: Implement the minimal route display-state guard**

Use the tested display state in `ExtractView.vue` so a native file-picker focus refresh cannot unmount the mapping dialog and discard its preview.

- [x] **Step 3: Verify the reported replacement flow**

Import `临时壳体4.xml`, verify the preview reports 9 groups and 105 feature selections, return focus to the browser, and confirm that `确认更换并进入映射` remains visible and enabled. Cancel replacement afterward so project data remains unchanged.
