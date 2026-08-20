# Condition Review Boundary Refactor Design

Date: 2026-08-05

## Context

The natural-language condition workflow currently spans two large modules:

- `app/services/rule_packages/condition_parser.py` owns LLM configuration and
  invocation, deterministic parsing, process-relation inference, candidate
  validation, evidence normalization, factor binding, previews, and fallback
  behavior.
- `app/services/rule_packages/condition_reviews.py` owns database loading and
  creation, JSON serialization, parser cache coordination, state transitions,
  workflow locking during asynchronous parsing, HTTP exceptions, and database
  commits.

The four rule-condition API endpoints in `app/routers/rule_packages.py` already
acquire the workflow revision before calling the review functions. The review
functions then commit internally, and parsing acquires the workflow revision a
second time after the LLM call. This hides transaction ownership in a service
and makes the parser and review state difficult to test independently.

The refactor improves these boundaries without changing request or response
contracts, database columns, V2 rule semantics, KmAI V1 exports, or the
FinalizeView workflow.

## Goals

1. Split condition parsing into cohesive LLM, local parsing, and semantic
   validation responsibilities while preserving the public parser interface.
2. Move condition-review state transitions and persistence behind explicit
   repository and service boundaries.
3. Make API routes responsible for workflow locks, commits, rollbacks, and
   HTTP error mapping.
4. Preserve parser precedence, cache behavior, stale-write protection, stored
   JSON, API error status codes, and error detail shapes.
5. Keep legacy review migrations functional while removing hidden commits from
   service-layer code.

## Non-goals

- No database schema or data migration script changes.
- No request, response, URL, or frontend behavior changes.
- No changes to `RuleConditionCandidate`, condition AST semantics, standard
  factor semantics, V2 package contracts, or KmAI V1 export artifacts.
- No changes to LLM prompts, retry limits, timeout defaults, confidence values,
  issue wording, or parser fallback order.
- No FinalizeView component split in this iteration.
- No new runtime dependency.

## Compatibility Contract

The following remain stable:

- Parser imports from `condition_parser`: `CONDITION_PARSER_VERSION`,
  `parse_rule_condition()`, and `validate_candidate()`.
- Rule-condition endpoints: `/rule-conditions/draft`, `/parse`, `/confirm`,
  and `/manual`.
- Existing request and response Pydantic models and the
  `normalized_route_segment_rule_reviews` JSON/status columns.
- The parser cache key: source text/hash, field-registry version, and parser
  version including the configured model digest.
- The state names: `draft`, `parsing`, `pending_confirmation`, `confirmed`,
  and `invalid`.
- Existing 404, 409, and 422 response semantics and detail payloads.

The old `condition_reviews` import path remains a compatibility facade during
the transition. Application call sites move to focused modules; no caller needs
to import a private helper from a new module.

## Parser Structure

### `condition_parser.py`

Retain this module as the public compatibility facade and ordered parser
orchestrator. It exports the existing public symbols and coordinates the
following internal modules. It does not own prompt construction, regular
expression parsing, or semantic helper implementations.

### `condition_parser_llm.py`

Own the LLM-specific boundary:

- `RULE_CONDITION_LLM_TIMEOUT_SECONDS` and
  `RULE_CONDITION_LLM_MAX_RETRIES` normalization;
- prompt construction and allowed-field/process payload construction;
- `call_llm()` invocation and JSON extraction;
- conversion of an LLM payload into a structurally valid candidate, confidence,
  warnings, and unresolved messages.

This module may depend on LLM services, environment variables, contracts, and
the condition registry. It does not import local parsing or database modules.

### `condition_parser_local.py`

Own deterministic, no-LLM parsing:

- controlled field recognition and comparison operators;
- known and generic tag conditions;
- complete and partial condition-tree parsing;
- process-name normalization, route process resolution, and process-relation
  inference;
- local candidate construction and relation previews.

It has no LLM, environment, database, or FastAPI dependency.

### `condition_semantics.py`

Own candidate post-processing shared by local and LLM paths:

- candidate payload validation and preview completion;
- candidate validation against the active process catalog and condition tree;
- source-evidence normalization;
- standard-factor binding and binding issue conversion;
- checks for unsupported unregistered project factors.

It has no LLM, environment, database, or FastAPI dependency.

### Parser Data Flow

`parse_rule_condition()` retains the following observable order and confidence
values:

```text
explicit valid local process relation                 -> 0.90
valid deterministic local condition                   -> 0.90
validated LLM candidate                               -> model confidence
valid local process-relation fallback                 -> 0.90
valid local-condition fallback                        -> 0.65
valid partially recognized local candidate             -> 0.55
unresolved                                             -> no candidate
```

Before returning any candidate, the facade preserves source evidence and binds
unambiguous standard-factor IDs. A malformed or unavailable LLM continues to
produce the current warning and then follows local fallback rules. An LLM
candidate that conflicts with an explicit relation or known special requirement
is rejected in favor of the existing local semantic result. No parsing result
becomes a published rule without user confirmation.

## Review Structure

### `condition_review_errors.py`

Define typed domain errors without importing FastAPI. The errors cover:

- saved route or route segment not found;
- invalid process catalog or current process;
- empty source text where parsing or manual control requires one;
- source hash changed before confirmation;
- missing confirmable candidate state;
- invalid candidate or factor bindings;
- invalid manual Boolean candidate shape.

Each error carries the existing response detail value. The router maps these
errors to the current HTTP status code and detail shape.

### `condition_review_state.py`

Define pure transition functions that calculate field updates for draft,
parsing, parsed candidate, invalid parse, confirmed candidate, manual Boolean
confirmation, and legacy invalidation/migration. The functions do not query a
database, call an LLM, read configuration, commit, or raise HTTP exceptions.

They explicitly clear stale candidate, confirmation, confidence, issue,
registry, parser, and confirmation metadata fields where the current behavior
does so. This makes transition invariants testable without an `AsyncSession`.

### `condition_review_repository.py`

Own persistence mechanics only:

- load the saved route and validate that the segment belongs to it;
- load or create one review record;
- derive route process options from route JSON;
- serialize/deserialize stored candidate and issue JSON;
- apply state field updates to ORM rows and serialize API review data.

Repository methods may add or flush ORM records but never commit or roll back a
transaction.

### `condition_review_service.py`

Own application-level coordination without FastAPI or transaction completion:

- validate the supplied process catalog against the saved route;
- resolve the parser version and one LLM configuration snapshot;
- determine cache hits;
- prepare, complete, confirm, and manually confirm review transitions;
- perform factor-binding checks;
- run legacy NDT and standard-factor review migrations.

For parsing, the service exposes separate prepare and completion operations.
The prepare result either represents a cache hit or carries the immutable
source hash, parser version, and LLM config that must be used for that parse.
The completion operation rechecks the persisted hash and parser version before
applying a result, so an older request cannot overwrite a newer draft or parse.

### `condition_reviews.py`

Reduce this file to a compatibility facade that re-exports supported review
functions and serializers from the focused modules. It contains no business
logic, HTTP exception, or transaction completion.

## Route Transactions and HTTP Mapping

`app/routers/rule_packages.py` owns the workflow lock and transaction boundary
for all four condition-review endpoints.

For draft, confirm, and manual actions, the route follows this sequence:

```text
acquire workflow revision
    -> invoke review service
    -> commit
    -> refresh serialized review if required
    -> return response
```

For parsing, two short transactions preserve the current asynchronous behavior:

```text
acquire workflow revision
    -> prepare parsing state
    -> commit parsing state

invoke parser outside a database transaction

acquire workflow revision again
    -> complete only if source hash and parser version still match
    -> commit final state
```

A cache hit returns the stored candidate without invoking the parser. A newer
draft or parse request remains authoritative if it changes the source hash or
parser version while the earlier parser call is in flight.

The route rolls back on every domain or unexpected exception. It maps domain
errors as follows:

| Domain error class | HTTP status | Response detail |
| --- | --- | --- |
| route or segment missing | 404 | existing message string |
| source changed or candidate not confirmable | 409 | existing message string |
| catalog, candidate, binding, or manual-shape invalid | 422 | existing string or `{message, issues}` payload |

`acquire_workflow_revision()` remains at the router boundary and keeps its
current stale-page 404/409 response behavior. Parser service failures remain
review warnings and fallback behavior, not HTTP failures.

## Legacy Migration Ownership

`build_saved_normalized_route_response()` currently causes legacy review
migrations as a read-time side effect. The refactor makes that ownership
explicit:

1. `get_saved_normalized_route()` invokes the non-committing migration service
   before serializing the saved route.
2. The route commits the migration when it changes reviews.
3. `build_saved_normalized_route_response()` only serializes and assembles the
   response; it no longer writes database state.

This preserves the existing automatic repair of incorrect legacy NDT relations
and stale standard-factor bindings while removing hidden commits from a read
assembly service.

## Test Plan

### Parser Characterization

- Keep facade-level assertions for local relation precedence, deterministic
  local conditions, LLM candidates, semantic correction, fallback order,
  confidence values, issues, evidence, factor binding, and unresolved output.
- Move LLM timeout, retry, prompt, malformed JSON, and unavailable-service
  tests to `condition_parser_llm` through explicit monkeypatch targets.
- Add focused local-parser and semantic tests that do not patch LLM services.

### Review State and Persistence

- Unit-test every state transition's changed and cleared fields without a
  database or FastAPI exception.
- Test repository route/segment lookup, review creation, JSON handling, and
  response serialization with an in-memory SQLite session.
- Test service cache hits, parser-version invalidation, same-config version and
  inference behavior, source-hash invalidation, manual Boolean shape checks,
  and standard-factor binding errors through domain error assertions.

### Endpoint and Concurrency Regression

- Add or retain route-level tests for all existing 404, 409, and 422 status
  codes and detail payloads.
- Preserve the regression where an older in-flight parser result cannot replace
  a newer source text or parser version.
- Preserve legacy NDT and standard-factor migration behavior when reopening a
  saved route, including persistence across a fresh session.

### Verification Commands

```text
py -3 -m pytest -q
npm.cmd test -- --run
npm.cmd run build
git diff --check
```

The frontend commands are regression checks only; no frontend source is in
scope for this refactor.

## Implementation Constraints

- Use test-driven extraction steps: characterize a seam, write a focused
  failing test, implement the smallest move, then run affected tests.
- Preserve the existing untracked plans, specs, and screenshots in the
  workspace. Do not stage, delete, or overwrite them.
- Do not commit, push, rebase, reset, or alter branches unless explicitly
  requested by the user.
- Keep dependencies acyclic: the facade may depend on internal modules, but
  internal modules must not import the facade.
- Do not introduce a generic transaction abstraction; the four routes are the
  explicit unit-of-work boundary.

## Completion Criteria

The refactor is complete when:

1. `condition_parser.py` exposes the current parser compatibility interface
   while LLM, local parsing, and semantic responsibilities are separated.
2. Review state, repository, service, and error modules have focused
   responsibilities and no service-layer code commits, rolls back, or imports
   FastAPI.
3. Rule-condition routes own locks, commits, rollbacks, and HTTP mapping,
   including the two-phase parser lifecycle.
4. Public requests, responses, stored data, parser outcomes, cache behavior,
   error semantics, V2 packages, and KmAI V1 exports are unchanged.
5. Focused and full verification commands pass, and `git diff --check` reports
   no whitespace errors.
