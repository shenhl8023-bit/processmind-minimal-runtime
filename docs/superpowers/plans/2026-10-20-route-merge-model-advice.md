# Route Merge Model Advice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use the configured LLM to advise on existing route-merge candidates while preserving deterministic validation, user review, and route projection.

**Architecture:** Keep local rules as the candidate generator and fallback. Add a focused advisor that sends only candidate/source evidence to the existing LLM service, validates structured output against candidate and evidence IDs, and decorates pending suggestions. Persist the advice in the existing versioned route-merge snapshot; leave the right-hand normalized route derived from review state.

**Tech Stack:** Python 3.11+, FastAPI service layer, existing `call_llm`/prompt-template support, pytest, Vue/TypeScript existing merge-suggestion types.

**Spec:** `docs/superpowers/specs/2026-10-20-route-merge-model-assistance-design.md`

## Global Constraints

- Model output is advisory only and cannot approve, reject, or overwrite a reviewed action.
- The model may refer only to supplied candidate and evidence IDs.
- Invalid output, timeout, missing model configuration, or provider failure must preserve the existing rule-based workflow.
- The right-side route remains a deterministic projection of merge groups and review status.
- Do not change PDF extraction or the left process-tree flow.

## Review Focus

- LLM unavailable or unconfigured: local rule suggestions remain available.
- Malformed JSON, unknown candidate/evidence IDs, duplicate candidate decisions, or invalid actions: discard invalid advice and fall back safely.
- Same sequence number across distinct operations: preserve both candidates unless their evidence supports a merge.
- Repeated same-name operations in different phases: keep phase evidence distinct.
- Existing reviewed state during snapshot rebuild: preserve the review and its chosen name/action.

---

### Task 1: Define and test the bounded advisor contract

**Files:**
- Create: `process-plan-agent-api/app/services/route_merge/llm_advisor.py`
- Test: `process-plan-agent-api/tests/test_route_merge_llm_advisor.py`

**Interfaces:**
- Consumes: candidate group dictionaries produced by `build_initial_merge_groups`.
- Produces: `async def advise_merge_groups(groups: list[dict[str, object]]) -> tuple[list[dict[str, object]], str]`; returns decorated copies and a diagnostic status (`model`, `fallback`, or equivalent stable values).

- [x] **Step 1: Write tests for a valid full response, malformed response, unknown IDs, duplicate decisions, and empty model response.**
- [x] **Step 2: Run `cd process-plan-agent-api && pytest tests/test_route_merge_llm_advisor.py -q` and confirm expected failures.**
- [x] **Step 3: Implement candidate/evidence ID serialization, structured response parsing, and strict validation; preserve original rule advice for any rejected response.**
- [x] **Step 4: Run the focused test file and verify all validation and fallback cases pass.**

### Task 2: Add the candidate-focused prompt and call existing LLM configuration

**Files:**
- Modify: `process-plan-agent-api/app/services/llm_service.py`
- Modify: `process-plan-agent-api/app/services/route_merge/llm_advisor.py`
- Test: `process-plan-agent-api/tests/test_route_merge_llm_advisor.py`

**Interfaces:**
- Consumes: existing `call_llm`, prompt template loader, and LLM configuration.
- Produces: one prompt template dedicated to candidate merge decisions; temperature 0.0-0.2; advisor calls it without new provider dependencies.

- [x] **Step 1: Add a prompt test asserting it requires the three allowed actions, candidate/evidence IDs, JSON-only output, phase distinction, and evidence-based independent decisions.**
- [x] **Step 2: Run the focused test and verify the new prompt contract is absent.**
- [x] **Step 3: Add the new prompt and invoke it from `advise_merge_groups`; keep the generic unused route-generation prompt separate.**
- [x] **Step 4: Re-run focused tests with mocked LLM responses for accepted and rejected advice.**

### Task 3: Integrate advice into snapshot build and version invalidation

**Files:**
- Modify: `process-plan-agent-api/app/services/route_merge/workspace.py`
- Modify: `process-plan-agent-api/app/services/route_merge/config.py`
- Test: `process-plan-agent-api/tests/test_route_merge_llm_advisor.py`
- Test: relevant route-merge snapshot tests under `process-plan-agent-api/tests/`

**Interfaces:**
- Consumes: Task 1's `advise_merge_groups` contract.
- Produces: pending groups/suggestions carry validated model advice; normalized route remains generated from reviewed groups; algorithm version changes so stale snapshots rebuild.

- [x] **Step 1: Add an async snapshot-build test proving the advisor receives rule candidates and the returned advice appears in pending suggestions.**
- [x] **Step 2: Add a fallback test proving snapshot construction completes with local advice when the LLM raises or returns invalid output.**
- [x] **Step 3: Integrate advice before merge suggestions and normalized route are assembled; preserve review state when rebuilding.**
- [x] **Step 4: Increment `ROUTE_MERGE_ALGO_VERSION` and verify existing snapshot invalidation tests rebuild old versions.**
- [x] **Step 5: Run targeted backend tests plus the complete backend test suite.**

### Task 4: Expose advice provenance without changing review authority

**Files:**
- Inspect/modify: `process-plan-agent-api/app/schemas/schemas.py`
- Inspect/modify: `process-plan-agent-ui/src/api/index.ts`
- Inspect/modify: existing merge queue/preview components only if provenance is not already shown
- Test: backend response model tests and focused UI API/component tests

**Interfaces:**
- Consumes: existing recommendation label/reason/evidence fields.
- Produces: UI can distinguish model advice from rule fallback and show its evidence/reason; current accept/reject/rename actions remain the only way to alter review state.

- [x] **Step 1: Inspect existing merge queue rendering and API types; add a failing test only for provenance not already represented.**
- [x] **Step 2: Extend the response contract with a stable advice source/status field if needed.**
- [x] **Step 3: Render the source and model rationale in the existing suggestion detail area without changing confirmation controls.**
- [x] **Step 4: Run focused UI tests, full UI tests, and UI build.**
- [x] **Step 5: Run the full backend test suite and inspect the combined diff for accidental changes to reviewed-state or right-route generation.**
