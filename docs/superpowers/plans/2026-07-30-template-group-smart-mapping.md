# Template Group Smart Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unsafe template-group fallback mapping with validated candidates, optional batch LLM resolution, and low-effort user review.

**Architecture:** A pure TypeScript engine extracts feature and position evidence and returns deterministic candidates. A FastAPI service receives only ambiguous candidate sets, lets the configured LLM choose from controlled IDs, validates every response, and degrades to unresolved results. The Vue dialog auto-applies only high-confidence unique results and renders candidate buttons for the rest.

**Tech Stack:** Vue 3, TypeScript, Vitest, FastAPI, Pydantic, pytest, existing OpenAI-compatible LLM service.

## Global Constraints

- Preserve the current uncommitted dialog layout and manual mapping interactions.
- Never use the active manual group as an automatic fallback.
- Never create template group IDs outside the supplied candidate list.
- Never overwrite existing mappings during smart mapping.
- Keep model failure non-blocking and retain deterministic candidates.

---

### Task 1: Deterministic Candidate Engine

**Files:**
- Modify: `process-plan-agent-ui/src/composables/templateGroupMapping.ts`
- Test: `process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts`

**Interfaces:**
- Produces: `suggestTemplateGroupsForOperation(operation, root): TemplateGroupMappingSuggestion`
- Produces: `buildTemplateGroupMappingSuggestions(operations, root): TemplateGroupMappingSuggestion[]`

- [ ] Add failing tests for plain holes, side-unknown outer diameters, explicit A-side end faces, and non-feature operations.
- [ ] Run `npx vitest run src/composables/templateGroupMapping.spec.ts` and confirm the new tests fail.
- [ ] Add normalized feature/position metadata, deterministic candidate scoring, confidence, evidence, and reasons.
- [ ] Run the focused Vitest file and confirm it passes.

### Task 2: Controlled Batch LLM Resolver

**Files:**
- Create: `process-plan-agent-api/app/services/template_group_mapping.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Test: `process-plan-agent-api/tests/test_template_group_mapping.py`

**Interfaces:**
- Consumes: operation IDs, names, step items, and candidate group IDs/paths.
- Produces: `POST /api/extract/template-group-mappings/suggest` with validated choices, confidence, evidence, reason, and warnings.

- [ ] Add failing service tests for valid model choice, illegal group ID, low confidence, empty model response, and evidence preservation.
- [ ] Run `.venv/bin/python -m pytest tests/test_template_group_mapping.py -q` and confirm failure.
- [ ] Implement Pydantic request/response contracts and a resolver using `call_llm` plus `parse_json_from_llm`.
- [ ] Add the router endpoint without database writes.
- [ ] Run the focused pytest file and confirm it passes.

### Task 3: Frontend API Contract

**Files:**
- Modify: `process-plan-agent-ui/src/api/extract.ts`

**Interfaces:**
- Produces: `suggestTemplateGroupMappings(body): Promise<TemplateGroupMappingSuggestionResponse>`.

- [ ] Add request/response TypeScript types matching the backend contract.
- [ ] Implement the API call with the existing shared Axios client.
- [ ] Run `npm run build` and resolve contract errors.

### Task 4: Candidate Review Interaction

**Files:**
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue`

**Interfaces:**
- Consumes: deterministic suggestions and optional backend resolutions.
- Produces: the existing alias draft shape; persistence remains behind “保存映射”.

- [ ] Replace component-local keyword fallback with the pure candidate engine.
- [ ] Auto-apply only unique high-confidence deterministic or model results.
- [ ] Render loading, summary, reasons, confidence, and candidate group buttons for unresolved operations.
- [ ] Keep manual transfer, double-click mapping, remove, clear, and save behavior intact.
- [ ] Ensure existing aliases are excluded from smart analysis and never overwritten.

### Task 5: Regression Verification

**Files:**
- Test: existing backend and frontend suites.

- [ ] Run `.venv/bin/python -m pytest -q` in `process-plan-agent-api`.
- [ ] Run `npm test` in `process-plan-agent-ui`.
- [ ] Run `npm run build` in `process-plan-agent-ui`.
- [ ] Run `git diff --check` and inspect the final diff without touching unrelated `.vscode/` or `outputs/` files.
- [ ] Browser-test “打孔”, “磨外圆”, and explicit side examples; confirm no unsafe active-group fallback remains.
