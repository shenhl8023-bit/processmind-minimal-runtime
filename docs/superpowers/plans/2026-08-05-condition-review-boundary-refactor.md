# Condition Review Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split condition parsing and condition-review persistence into focused backend modules while preserving every parser outcome, review state, API response, database field, and V2/KmAI compatibility behavior.

**Architecture:** Keep `parse_rule_condition()` in `condition_parser.py` as the public, ordered facade. Move LLM, deterministic parsing, and semantic candidate handling into three acyclic modules. Replace the review monolith with domain errors, pure state updates, a repository, and a non-transactional application service; the API router owns workflow locks, commits, rollbacks, and HTTP mapping.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, SQLAlchemy async sessions, SQLite test databases, pytest/pytest-asyncio, Node.js 20+ frontend regression commands.

## Global Constraints

- Do not change database schema, request/response contracts, endpoint URLs, V2 contracts, KmAI V1 artifacts, frontend source, or runtime dependencies.
- Preserve `CONDITION_PARSER_VERSION`, `parse_rule_condition()`, and `validate_candidate()` imports from `condition_parser.py`.
- Preserve parser order and confidence values: local relation `0.90`, deterministic local condition `0.90`, LLM confidence, relation fallback `0.90`, local fallback `0.65`, partial fallback `0.55`, then unresolved.
- Preserve cache keys, issue ordering, source evidence behavior, standard-factor binding, manual Boolean validation, and stale-write protection.
- Service and repository modules must not import FastAPI or call `commit()`/`rollback()`.
- Keep workflow locks, transaction completion, and 404/409/422 translation in routes.
- Do not modify existing user-authored untracked plans, specs, screenshots, runtime data, uploads, or build output.
- Do not create a Git commit, push, rebase, reset, or alter branches unless the user explicitly requests it. Use `git status` at each checkpoint instead.
- Unless a step says otherwise, run backend commands from `process-plan-agent-api` and frontend commands from `process-plan-agent-ui`.

---

## File Map

**Create:**

- `process-plan-agent-api/app/services/rule_packages/condition_semantics.py`: candidate validation, payload conversion, evidence handling, factor binding, and preview post-processing.
- `process-plan-agent-api/app/services/rule_packages/condition_parser_local.py`: deterministic condition parsing, partial fallbacks, and process-relation recognition.
- `process-plan-agent-api/app/services/rule_packages/condition_parser_llm.py`: LLM configuration, prompt construction, invocation, and response conversion.
- `process-plan-agent-api/app/services/rule_packages/condition_review_errors.py`: typed domain errors and response-detail payloads without HTTP dependencies.
- `process-plan-agent-api/app/services/rule_packages/condition_review_state.py`: pure review-state update contracts and source/manual-key helpers.
- `process-plan-agent-api/app/services/rule_packages/condition_review_repository.py`: ORM loading/creation, JSON serialization, state application, and response serialization.
- `process-plan-agent-api/app/services/rule_packages/condition_review_service.py`: cache, parser preparation/completion, confirmation, manual review, and legacy migration orchestration.
- `process-plan-agent-api/tests/test_condition_parser_semantics.py`: semantic-module unit tests.
- `process-plan-agent-api/tests/test_condition_parser_local.py`: deterministic-parser unit tests.
- `process-plan-agent-api/tests/test_condition_parser_llm.py`: LLM-boundary unit tests.
- `process-plan-agent-api/tests/test_condition_review_state.py`: state-transition and domain-error tests.
- `process-plan-agent-api/tests/test_condition_review_repository.py`: repository tests with in-memory SQLite.
- `process-plan-agent-api/tests/test_condition_review_service.py`: review-service tests without FastAPI exception assertions.

**Modify:**

- `process-plan-agent-api/app/services/rule_packages/condition_parser.py`: retain the compatibility facade and ordered orchestration only.
- `process-plan-agent-api/app/services/rule_packages/condition_reviews.py`: retain only intentional compatibility re-exports.
- `process-plan-agent-api/app/routers/rule_packages.py`: own condition-review workflow locks, commits, rollbacks, and domain-error mapping.
- `process-plan-agent-api/app/services/route_analysis.py`: make saved-route response assembly read-only.
- `process-plan-agent-api/app/routers/extract.py`: explicitly run and commit changed legacy review migrations before response assembly.
- `process-plan-agent-api/tests/test_rule_condition_parser.py`: retain facade regressions; move private-module and review-service assertions to focused test files.
- `process-plan-agent-api/tests/test_rule_package_lifecycle.py`: update parser patch targets and add endpoint-level error-contract regressions.

## Task 1: Extract Candidate Semantics Behind a Stable Parser Facade

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/condition_semantics.py`
- Create: `process-plan-agent-api/tests/test_condition_parser_semantics.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_parser.py`
- Test: `process-plan-agent-api/tests/test_rule_condition_parser.py`

**Interfaces:**
- Consumes: `RuleConditionCandidate`, `RuleConditionProcessOption`, `ConditionNode`, condition registry helpers, and standard-factor binding helpers.
- Produces: `candidate_from_payload(payload: Any) -> RuleConditionCandidate | None`, `source_evidence(source_text: str) -> str`, `with_source_evidence(candidate, source_text) -> RuleConditionCandidate | None`, `validate_candidate(candidate, processes) -> list[str]`, `bind_candidate_factors(candidate) -> tuple[RuleConditionCandidate, list[str]]`, and `has_unregistered_project_factor(candidate) -> bool`.
- Compatibility: `condition_parser.validate_candidate` remains an import alias for `condition_semantics.validate_candidate`.

- [ ] **Step 1: Write focused failing semantic tests**

Create `test_condition_parser_semantics.py` with direct tests for structural validation, source evidence replacement, and standard-factor binding:

```python
from app.services.rule_packages.condition_contracts import (
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_semantics import (
    bind_candidate_factors,
    validate_candidate,
    with_source_evidence,
)


def _candidate(process_id="process_grind_outer"):
    return RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"field": "cad.features", "op": "contains", "value": "顶尖孔"},
        "then": {"include_process_ids": [process_id], "exclude_process_ids": []},
    })


def test_semantics_binds_unambiguous_factor_and_replaces_nonliteral_evidence():
    candidate = with_source_evidence(_candidate(), "当存在顶尖孔时，纳入磨外圆工序")
    bound, issues = bind_candidate_factors(candidate)

    assert bound.when.factor_id == "feature.center_hole_location"
    assert bound.evidence == "存在顶尖孔"
    assert issues == []


def test_semantics_rejects_action_that_references_a_missing_route_process():
    issues = validate_candidate(
        _candidate("process_missing"),
        [RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
    )

    assert issues == ["规则引用了当前路线中不存在的工序：process_missing"]
```

- [ ] **Step 2: Run the new test to prove the boundary is absent**

Run from `process-plan-agent-api`:

```text
py -3 -m pytest -q tests/test_condition_parser_semantics.py
```

Expected: collection fails because `condition_semantics` does not yet exist.

- [ ] **Step 3: Move semantic helpers without changing their behavior**

Create `condition_semantics.py` by moving these existing parser helpers and their direct dependencies exactly once:

```python
def candidate_from_payload(payload: Any) -> RuleConditionCandidate | None: ...
def source_evidence(source_text: str) -> str: ...
def with_source_evidence(
    candidate: RuleConditionCandidate | None,
    source_text: str,
) -> RuleConditionCandidate | None: ...
def validate_candidate(
    candidate: RuleConditionCandidate,
    processes: list[RuleConditionProcessOption],
) -> list[str]: ...
def bind_candidate_factors(
    candidate: RuleConditionCandidate,
) -> tuple[RuleConditionCandidate, list[str]]: ...
def has_unregistered_project_factor(candidate: RuleConditionCandidate) -> bool: ...
```

Use the existing `condition_preview()`, `validate_condition_tree()`,
`iter_condition_fields()`, and `bind_unambiguous_factor_ids()` calls unchanged.
In `condition_parser.py`, import these functions and retain this compatibility
alias:

```python
from app.services.rule_packages.condition_semantics import validate_candidate
```

Do not change validation messages, the `custom.requirements` boolean exception,
or the field-definition namespace checks.

- [ ] **Step 4: Run focused and facade regressions**

```text
py -3 -m pytest -q tests/test_condition_parser_semantics.py tests/test_rule_condition_parser.py -k "binds_an_exact_standard_factor or unsupported_condition_is_blocked or registry_rejects_unknown_field"
```

Expected: all selected tests pass with the same candidate IDs and validation
messages.

- [ ] **Step 5: Inspect the checkpoint without committing**

```text
git diff --check
git status --short
```

Expected: only Task 1 source/tests and the approved docs appear; do not stage or
commit them.

## Task 2: Extract Deterministic Local Parsing

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/condition_parser_local.py`
- Create: `process-plan-agent-api/tests/test_condition_parser_local.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_parser.py`
- Test: `process-plan-agent-api/tests/test_rule_condition_parser.py`

**Interfaces:**
- Consumes: condition contracts, `ConditionNode`, `RuleAction`, registry preview helpers, and route process options.
- Produces: `parse_local_condition(source_text, current_process_id, current_process_name, processes) -> RuleConditionCandidate | None`, `parse_partial_condition_candidate(source_text, current_process_id, processes) -> tuple[RuleConditionCandidate | None, list[str]]`, `parse_process_relation(source_text, current_process_id, processes) -> RuleConditionCandidate | None`, and `known_special_requirement(source_text, current_process_name) -> str | None`.
- Compatibility: only `condition_parser.py` calls these names in production; no new public endpoint API is introduced.

- [ ] **Step 1: Write failing local-parser tests that never patch an LLM**

Create `test_condition_parser_local.py`:

```python
from app.services.rule_packages.condition_contracts import RuleConditionProcessOption
from app.services.rule_packages.condition_parser_local import (
    parse_local_condition,
    parse_process_relation,
)


PROCESSES = [
    RuleConditionProcessOption(process_id="process_copper_plate", display_name="镀铜"),
    RuleConditionProcessOption(process_id="process_strip_copper", display_name="除铜"),
]


def test_local_condition_parses_it_grade_without_external_services():
    candidate = parse_local_condition(
        "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序",
        "process_grind_outer",
        "磨外圆",
        [RuleConditionProcessOption(process_id="process_grind_outer", display_name="磨外圆")],
    )

    assert candidate.when.field == "precision.outer_diameter_it"
    assert candidate.when.op == "lte"
    assert candidate.when.value == 8


def test_local_relation_prefers_the_explicit_predecessor():
    candidate = parse_process_relation(
        "前面有镀铜时，安排除铜工序",
        "process_strip_copper",
        PROCESSES,
    )

    assert candidate.relation.relation_type == "trigger_after"
    assert candidate.relation.source_process_ids == ["process_copper_plate"]
```

- [ ] **Step 2: Run the local tests to verify the module is missing**

```text
py -3 -m pytest -q tests/test_condition_parser_local.py
```

Expected: collection fails because `condition_parser_local` does not yet exist.

- [ ] **Step 3: Move local parsing helpers and wire the facade**

Move the following parser-only helpers into `condition_parser_local.py`:

```python
def normalized_process_name(value: str) -> str: ...
def resolve_process_ids(text, current_process_id, processes) -> list[str]: ...
def comparison_operator(text: str, *, it_grade: bool = False) -> str: ...
def leaf_from_clause(clause: str) -> ConditionNode | None: ...
def generic_tag_condition(source_text: str) -> ConditionNode | None: ...
def parse_condition_tree(source_text: str) -> ConditionNode | None: ...
def parse_local_condition(...) -> RuleConditionCandidate | None: ...
def parse_partial_condition_candidate(...) -> tuple[RuleConditionCandidate | None, list[str]]: ...
def parse_process_relation(...) -> RuleConditionCandidate | None: ...
```

Keep all current regular expressions, route-stage fallbacks, target-process
selection, relation preview text, and partial-condition issue strings intact.
Update the facade to obtain `deterministic_condition`, local candidates, and
special-requirement checks through this module. The facade must still add source
evidence and factor bindings after local parsing.

- [ ] **Step 4: Run focused and existing deterministic-path tests**

```text
py -3 -m pytest -q tests/test_condition_parser_local.py tests/test_rule_condition_parser.py -k "deterministic_standard_condition or parses_process_relation or natural_language_process_relations or nondestructive_requirement or partially_recognized"
```

Expected: all selected tests pass without calling `call_llm()` for deterministic
conditions or relations.

- [ ] **Step 5: Inspect the checkpoint without committing**

```text
git diff --check
git status --short
```

Expected: local parsing has one implementation location and no unrelated files
changed.

## Task 3: Extract the LLM Boundary and Preserve Facade Ordering

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/condition_parser_llm.py`
- Create: `process-plan-agent-api/tests/test_condition_parser_llm.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_parser.py`
- Modify: `process-plan-agent-api/tests/test_rule_condition_parser.py`

**Interfaces:**
- Consumes: `call_llm`, `parse_json_from_llm`, condition contracts, registry fields, process options, and an optional resolved LLM configuration.
- Produces: `condition_llm_timeout_seconds() -> float`, `condition_llm_max_retries() -> int`, and `parse_with_llm(source_text, current_process_id, current_process_name, processes, *, llm_config=None) -> tuple[RuleConditionCandidate | None, float | None, list[str]]`.
- Compatibility: `parse_rule_condition()` keeps its current signature and still owns the complete ordering described in the approved design.

- [ ] **Step 1: Write failing LLM-boundary tests with an explicit patch target**

Create `test_condition_parser_llm.py`:

```python
import json

import pytest

from app.services.rule_packages import condition_parser_llm
from app.services.rule_packages.condition_contracts import RuleConditionProcessOption


@pytest.mark.asyncio
async def test_llm_boundary_passes_rule_specific_timeout_and_returns_candidate(monkeypatch):
    captured = {}

    async def fake_llm(*args, **kwargs):
        captured.update(kwargs)
        return json.dumps({
            "candidate": {
                "kind": "condition",
                "when": {"field": "material.grade", "op": "eq", "value": "9Cr18"},
                "then": {"include_process_ids": ["process_inspect"], "exclude_process_ids": []},
            },
            "confidence": 0.88,
            "warnings": [],
            "unresolved": [],
        }, ensure_ascii=False)

    monkeypatch.setattr(condition_parser_llm, "call_llm", fake_llm)
    candidate, confidence, issues = await condition_parser_llm.parse_with_llm(
        "复杂条件",
        "process_inspect",
        "检验",
        [RuleConditionProcessOption(process_id="process_inspect", display_name="检验")],
    )

    assert candidate.when.field == "material.grade"
    assert confidence == 0.88
    assert issues == []
    assert captured["timeout_seconds"] == 45.0
    assert captured["max_retries"] == 1
```

- [ ] **Step 2: Run the LLM-boundary test before implementation**

```text
py -3 -m pytest -q tests/test_condition_parser_llm.py
```

Expected: collection fails because `condition_parser_llm` does not yet exist.

- [ ] **Step 3: Move LLM helpers and retain the facade's exact decisions**

Move timeout/retry configuration, prompt construction, and the former
`_parse_with_llm()` body to `condition_parser_llm.py`. Use
`candidate_from_payload()` from Task 1 for payload conversion. In the facade,
retain this ordered shape:

```python
relation = parse_process_relation(source_text, current_process_id, processes)
local = parse_local_condition(
    source_text,
    current_process_id,
    current_process_name,
    processes,
)
deterministic_condition = parse_condition_tree(source_text)

if relation:
    relation_issues = validate_candidate(relation, processes)
    if not relation_issues:
        candidate = with_source_evidence(relation, source_text)
        bound_candidate, binding_issues = bind_candidate_factors(candidate)
        return bound_candidate, 0.9, binding_issues
if local and (local.field_definitions or deterministic_condition is not None):
    local_issues = validate_candidate(local, processes)
    if not local_issues:
        candidate = with_source_evidence(local, source_text)
        bound_candidate, binding_issues = bind_candidate_factors(candidate)
        return bound_candidate, 0.9, binding_issues

candidate, confidence, issues = await parse_with_llm(
    source_text,
    current_process_id,
    current_process_name,
    processes,
    llm_config=llm_config,
)
# Keep the existing validation, special-requirement correction, and fallback branches here.
```

Implement the actual existing binding and fallback branches rather than
introducing a new candidate wrapper; use the semantic helpers from Task 1
directly. Keep the current `parse_condition_tree()` result and exact issue accumulation. Update every test
that patches the private LLM call from `condition_parser.call_llm` to
`condition_parser_llm.call_llm`.

- [ ] **Step 4: Run the full parser regression suite**

```text
py -3 -m pytest -q tests/test_condition_parser_llm.py tests/test_condition_parser_semantics.py tests/test_condition_parser_local.py tests/test_rule_condition_parser.py
```

Expected: all parser output, confidence, evidence, issue, and fallback tests
pass unchanged.

- [ ] **Step 5: Confirm the parser dependency direction and Git state**

```text
rg -n "condition_parser import" app/services/rule_packages/condition_parser_llm.py app/services/rule_packages/condition_parser_local.py app/services/rule_packages/condition_semantics.py
git diff --check
git status --short
```

Expected: the three internal modules do not import the facade; do not commit.

## Task 4: Define Domain Errors and Pure Review State Transitions

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/condition_review_errors.py`
- Create: `process-plan-agent-api/app/services/rule_packages/condition_review_state.py`
- Create: `process-plan-agent-api/tests/test_condition_review_state.py`

**Interfaces:**
- Consumes: review contracts, candidate JSON strings, field-registry/parser versions, timestamps, and issue JSON strings.
- Produces: `ConditionReviewError`, `ConditionReviewNotFound`, `ConditionReviewConflict`, `ConditionReviewValidation`, `ConditionReviewStateUpdate`, `condition_source_hash()`, `manual_process_field_key()`, `new_draft_update()`, `parsing_update()`, `parse_result_update()`, `invalid_parse_update()`, `confirmation_update()`, `manual_confirmation_update()`, and `legacy_invalidation_update()`.
- Compatibility: errors carry `detail`, but no error class imports FastAPI or contains an HTTP status code.

- [ ] **Step 1: Write failing state and error tests**

Create `test_condition_review_state.py`:

```python
from app.services.rule_packages.condition_review_errors import ConditionReviewValidation
from app.services.rule_packages.condition_review_state import (
    condition_source_hash,
    manual_process_field_key,
    new_draft_update,
    parsing_update,
)


def test_draft_update_clears_confirmation_without_changing_prior_parser_metadata():
    update = new_draft_update(
        source_text="新的条件文字",
        source_hash=condition_source_hash("新的条件文字"),
        field_registry_version="2026.11",
    )

    assert update.values["condition_status"] == "draft"
    assert update.values["condition_candidate_json"] is None
    assert update.values["condition_confirmed_json"] is None
    assert update.values["condition_confirmed_by"] is None
    assert "condition_parser_version" not in update.values


def test_parsing_update_resets_duration_and_manual_key_is_stable():
    update = parsing_update("条件", condition_source_hash("条件"), "parser:v1", "2026.11")

    assert update.values["condition_status"] == "parsing"
    assert update.values["condition_parse_duration_ms"] is None
    assert manual_process_field_key("process_mark") == "project_factor.manual_process_487e1c0a"


def test_domain_error_exposes_detail_without_http_dependency():
    error = ConditionReviewValidation({"message": "候选规则校验未通过", "issues": ["x"]})
    assert error.detail == {"message": "候选规则校验未通过", "issues": ["x"]}
```

- [ ] **Step 2: Run the state tests to verify the modules are absent**

```text
py -3 -m pytest -q tests/test_condition_review_state.py
```

Expected: collection fails because the state and error modules do not yet exist.

- [ ] **Step 3: Implement typed errors and exact transition updates**

Use these concrete contracts:

```python
class ConditionReviewError(ValueError):
    def __init__(self, detail: str | dict[str, object]):
        super().__init__(str(detail))
        self.detail = detail


class ConditionReviewNotFound(ConditionReviewError):
    pass


class ConditionReviewConflict(ConditionReviewError):
    pass


class ConditionReviewValidation(ConditionReviewError):
    pass


@dataclass(frozen=True)
class ConditionReviewStateUpdate:
    values: dict[str, object]
```

Implement each update function from the corresponding assignment block in the
current review service. Preserve intentional distinctions: a draft does not
clear parser version/duration, parsing clears candidate/confirmation/duration,
normal confirmation retains parser metadata, and manual confirmation sets
parser version to `manual`, confidence to `1.0`, and duration to `0`.

- [ ] **Step 4: Run pure-state checks and verify no FastAPI import leaked**

```text
py -3 -m pytest -q tests/test_condition_review_state.py
rg -n "fastapi|commit\(|rollback\(" app/services/rule_packages/condition_review_errors.py app/services/rule_packages/condition_review_state.py
```

Expected: tests pass and the search has no matches.

- [ ] **Step 5: Inspect the checkpoint without committing**

```text
git diff --check
git status --short
```

Expected: only Task 4 modules/tests and prior intentional work appear.

## Task 5: Extract Review Repository Mechanics

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/condition_review_repository.py`
- Create: `process-plan-agent-api/tests/test_condition_review_repository.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_reviews.py`

**Interfaces:**
- Consumes: `AsyncSession`, `NormalizedRouteVersion`, `NormalizedRouteSegmentRuleReview`, review contracts, and `ConditionReviewStateUpdate`.
- Produces: `load_route_and_review(project_id, route_id, segment_id, db)`, `route_process_options(route)`, `loads_candidate(raw)`, `loads_issues(raw)`, `candidate_json(candidate)`, `serialize_condition_review(row)`, `review_response(body, row)`, and `apply_state_update(row, update)`.
- Transaction boundary: repository functions may `add()` and `flush()`, but never call `commit()` or `rollback()`.

- [ ] **Step 1: Write failing repository tests with an in-memory session**

Create `test_condition_review_repository.py` using the existing metadata setup
pattern:

```python
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import NormalizedRouteVersion, Project
from app.services.rule_packages.condition_review_errors import ConditionReviewNotFound
from app.services.rule_packages.condition_review_repository import load_route_and_review


@pytest.mark.asyncio
async def test_repository_creates_one_review_for_a_route_segment():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        db.add_all([
            Project(id=7, name="条件审核"),
            NormalizedRouteVersion(id=1, project_id=7, version=1, route_json='[{"id":"process_mark"}]'),
        ])
        await db.commit()
        route, review = await load_route_and_review(7, 1, "process_mark", db)

        assert route.id == 1
        assert review.segment_id == "process_mark"
        assert review.condition_status == "draft"
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_uses_domain_not_found_error_for_unknown_segment(db_with_route):
    with pytest.raises(ConditionReviewNotFound, match="当前工序不属于"):
        await load_route_and_review(7, 1, "process_missing", db_with_route)
```

Define `db_with_route` in this file with the same in-memory setup and route
fixture. The fixture must yield an open `AsyncSession` and dispose its engine:

```python
import pytest_asyncio


@pytest_asyncio.fixture
async def db_with_route():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    db = factory()
    db.add_all([
        Project(id=7, name="条件审核"),
        NormalizedRouteVersion(id=1, project_id=7, version=1, route_json='[{"id":"process_mark"}]'),
    ])
    await db.commit()
    try:
        yield db
    finally:
        await db.close()
        await engine.dispose()
```

- [ ] **Step 2: Run the repository test before implementation**

```text
py -3 -m pytest -q tests/test_condition_review_repository.py
```

Expected: collection fails because `condition_review_repository` does not yet
exist.

- [ ] **Step 3: Move ORM and JSON helpers into the repository**

Move `_loads_candidate`, `_loads_issues`, `_candidate_json`,
`_route_process_options`, `_load_route_and_review`, `serialize_condition_review`,
`_response`, and their model/query dependencies from `condition_reviews.py`.
Translate only route/segment absence to `ConditionReviewNotFound` with the
existing messages. Apply state updates centrally:

```python
def apply_state_update(
    review: NormalizedRouteSegmentRuleReview,
    update: ConditionReviewStateUpdate,
) -> None:
    for field_name, value in update.values.items():
        setattr(review, field_name, value)
```

After creating a review row, call `await db.flush()` so a later repository
operation in the same transaction can query it; do not commit.

- [ ] **Step 4: Run repository and serialization regressions**

```text
py -3 -m pytest -q tests/test_condition_review_repository.py tests/test_rule_condition_parser.py -k "serialize_condition_review or invalidates_legacy_nondestructive"
```

Expected: new repository tests pass. Existing serialization tests may still use
the compatibility facade while Task 6 migrates the remaining callers.

- [ ] **Step 5: Inspect transaction ownership**

```text
rg -n "commit\(|rollback\(|HTTPException" app/services/rule_packages/condition_review_repository.py
git diff --check
git status --short
```

Expected: the repository search has no matches; do not commit.

## Task 6: Implement the Non-Transactional Review Service

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/condition_review_service.py`
- Create: `process-plan-agent-api/tests/test_condition_review_service.py`
- Modify: `process-plan-agent-api/tests/test_rule_condition_parser.py`
- Modify: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`

**Interfaces:**
- Consumes: review repository functions, state updates, domain errors, standard-factor validation, `get_llm_config()`, and `parse_rule_condition()`.
- Produces: `ParseReviewPreparation`, `save_condition_draft(body, db)`, `prepare_condition_parse(body, db)`, `execute_condition_parse(body, preparation)`, `complete_condition_parse(body, preparation, result, db)`, `confirm_condition_review(body, db)`, `set_manual_condition_review(body, db)`, `invalidate_legacy_nondestructive_relation_reviews(route, db)`, `migrate_legacy_standard_factor_reviews(route, db)`, and `migrate_legacy_condition_reviews(route, db)`.
- Transaction boundary: every function mutates only the current `AsyncSession`; it never acquires workflow revision or completes a transaction.

- [ ] **Step 1: Write failing service tests for cache, errors, and stale completion**

Create `test_condition_review_service.py` with the existing in-memory SQLite
setup pattern. Start with these contract tests:

```python
import pytest

from app.services.rule_packages.condition_review_errors import (
    ConditionReviewConflict,
    ConditionReviewValidation,
)
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_review_state import condition_source_hash
from app.services.rule_packages.condition_review_service import (
    complete_condition_parse,
    confirm_condition_review,
    prepare_condition_parse,
)


@pytest.mark.asyncio
async def test_prepare_parse_returns_cached_response_without_reparsing(db, parse_request):
    first = await prepare_condition_parse(parse_request, db)
    assert first.cache_hit is False
    candidate = RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {"field": "precision.outer_diameter_it", "op": "lte", "value": 8},
        "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
    })
    await complete_condition_parse(parse_request, first, (candidate, 0.9, []), db)
    await db.commit()

    cached = await prepare_condition_parse(parse_request, db)
    assert cached.cache_hit is True
    assert cached.cached_response.review.candidate is not None


@pytest.mark.asyncio
async def test_confirm_uses_domain_conflict_when_source_hash_changed(db, confirm_request):
    with pytest.raises(ConditionReviewConflict, match="条件文字已经发生变化"):
        await confirm_condition_review(confirm_request, db)


@pytest.mark.asyncio
async def test_confirm_uses_domain_validation_for_unbound_factor(db, confirm_request):
    with pytest.raises(ConditionReviewValidation) as error:
        await confirm_condition_review(confirm_request, db)

    assert error.value.detail["message"] == "标准因子绑定校验未通过"
```

Define local `db`, `parse_request`, and `confirm_request` fixtures in this file
with a saved project/route/review. Do not import a test-local fixture from
`test_rule_condition_parser.py`. Use a route containing
`process_grind_outer` and define the requests explicitly:

```python
@pytest.fixture
def parse_request():
    return ParseRuleConditionRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text="当外圆尺寸精度达到 IT8 时，纳入磨外圆工序",
        process_id="process_grind_outer",
        process_name="磨外圆",
        processes=[RuleConditionProcessOption(
            process_id="process_grind_outer",
            display_name="磨外圆",
        )],
    )


@pytest.fixture
def confirm_request(parse_request):
    return ConfirmRuleConditionRequest(
        project_id=parse_request.project_id,
        route_id=parse_request.route_id,
        expected_workflow_revision=parse_request.expected_workflow_revision,
        segment_id=parse_request.segment_id,
        source_text=parse_request.source_text,
        source_hash=condition_source_hash("已改变的条件"),
        candidate=RuleConditionCandidate.model_validate({
            "kind": "condition",
            "when": {"field": "precision.outer_diameter_it", "op": "lte", "value": 8},
            "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
        }),
        processes=parse_request.processes,
    )
```

- [ ] **Step 2: Run the service tests to verify the boundary is absent**

```text
py -3 -m pytest -q tests/test_condition_review_service.py
```

Expected: collection fails because `condition_review_service` does not yet
exist.

- [ ] **Step 3: Implement preparation, completion, and confirmation contracts**

Create this preparation contract:

```python
@dataclass
class ParseReviewPreparation:
    cache_hit: bool
    cached_response: RuleConditionReviewResponse | None
    source_text: str
    source_hash: str
    parser_version: str
    llm_config: dict[str, str] | None
    review: NormalizedRouteSegmentRuleReview
```

`prepare_condition_parse()` must validate the route catalog/current process,
compute the source hash, resolve one model-digest parser version plus LLM config,
and either return a cache hit or apply `parsing_update()`. `execute_condition_parse()`
must call the parser once with `preparation.llm_config`. `complete_condition_parse()`
must refresh the review, compare its stored source hash and parser version with
the preparation, and return the current response without changing it when a
newer request won. Otherwise it applies the candidate or invalid update with
the measured duration and current issue ordering.

Move save, confirm, and manual validation into the service. Replace every
former `HTTPException` with the corresponding `ConditionReviewNotFound`,
`ConditionReviewConflict`, or `ConditionReviewValidation`, preserving the
existing `detail` strings and `{message, issues}` dictionaries exactly.

- [ ] **Step 4: Move legacy migrations without hidden commits**

Move `_binding_issue_text`, `_semantic_review_issues`, `_selected_factor_paths`,
and `_migrate_review_candidate` into the service or a private sibling helper.
Keep `invalidate_legacy_nondestructive_relation_reviews()` and
`migrate_legacy_standard_factor_reviews()` return values unchanged, but remove
their `db.commit()` calls. Add this coordinator:

```python
async def migrate_legacy_condition_reviews(
    route: NormalizedRouteVersion,
    db: AsyncSession,
) -> bool:
    invalidated = await invalidate_legacy_nondestructive_relation_reviews(route, db)
    migrated = await migrate_legacy_standard_factor_reviews(route, db)
    return invalidated or migrated
```

Update legacy tests to explicitly call `await db.commit()` after a changed
migration and then verify the stored review from a fresh session.

- [ ] **Step 5: Run service, migration, and existing behavioral regressions**

```text
py -3 -m pytest -q tests/test_condition_review_service.py tests/test_rule_condition_parser.py tests/test_rule_package_lifecycle.py
```

Expected: service tests assert domain errors rather than `HTTPException`, while
parser, cache, stale-result, manual-rule, and factor-migration behavior remains
unchanged.

- [ ] **Step 6: Inspect the service boundary without committing**

```text
rg -n "fastapi|commit\(|rollback\(|acquire_workflow_revision" app/services/rule_packages/condition_review_service.py
git diff --check
git status --short
```

Expected: the service-boundary search has no matches; do not commit.

## Task 7: Move Transactions and HTTP Mapping to Routes

**Files:**
- Modify: `process-plan-agent-api/app/routers/rule_packages.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_reviews.py`
- Modify: `process-plan-agent-api/app/services/route_analysis.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Modify: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`
- Modify: `process-plan-agent-api/tests/test_rule_condition_parser.py`

**Interfaces:**
- Consumes: `ConditionReviewNotFound`, `ConditionReviewConflict`, `ConditionReviewValidation`, review-service functions, `ParseReviewPreparation`, and `acquire_workflow_revision()`.
- Produces: unchanged four HTTP endpoints; `condition_reviews.py` compatibility re-exports; read-only `build_saved_normalized_route_response()`; explicit legacy-migration persistence in the extract route.
- Error mapping: not found to 404, conflict to 409, validation to 422, with unchanged detail values.

- [ ] **Step 1: Add route-level error-contract tests before changing the router**

Add to `test_rule_package_lifecycle.py`, using its existing `lifecycle_client`
fixture and request helpers:

```python
def test_confirm_endpoint_preserves_source_changed_conflict(lifecycle_client):
    source_text = "当外圆尺寸精度达到 IT8 时，纳入铣槽工序"
    parsed = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/parse",
        json=_parse_body(source_text),
    )
    candidate = parsed.json()["review"]["candidate"]

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/confirm",
        json=_confirm_body("新的条件文字", parsed.json()["review"]["source_hash"], candidate),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "条件文字已经发生变化，请重新解析后再确认。"
```

Also add one `/manual` request with a spoofed target field and assert a 422
detail containing `人工 Bool`. Add an endpoint assertion that an unbound standard
factor returns the existing `{message, issues}` payload, not a string.

- [ ] **Step 2: Run the new endpoint tests against the old implementation**

```text
py -3 -m pytest -q tests/test_rule_package_lifecycle.py -k "source_changed_conflict or manual or unknown_custom_factor"
```

Expected: the error-contract tests pass before the route refactor, establishing
the current HTTP behavior as the oracle.

- [ ] **Step 3: Implement explicit router transactions**

Add a small HTTP-only mapper in `rule_packages.py` and write each endpoint's
transaction block explicitly; do not create a generic unit-of-work abstraction:

```python
def _condition_review_http_error(error: ConditionReviewError) -> HTTPException:
    if isinstance(error, ConditionReviewNotFound):
        return HTTPException(404, detail=error.detail)
    if isinstance(error, ConditionReviewConflict):
        return HTTPException(409, detail=error.detail)
    return HTTPException(422, detail=error.detail)
```

For draft, confirm, and manual endpoints: acquire the workflow revision, call
the service, commit, and map/roll back on error. For parse, use this two-phase
shape:

```python
await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
preparation = await prepare_condition_parse(body, db)
if preparation.cache_hit:
    await db.rollback()
    return preparation.cached_response
await db.commit()

result = await execute_condition_parse(body, preparation)

await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
response = await complete_condition_parse(body, preparation, result, db)
await db.commit()
return response
```

Wrap each phase in `try`/`except ConditionReviewError` plus a final unexpected
exception rollback. Do not catch or remap the existing `HTTPException` raised
by `acquire_workflow_revision()`.

- [ ] **Step 4: Make legacy migration persistence explicit**

Replace the `condition_reviews` imports in `route_analysis.py` with no migration
calls; `build_saved_normalized_route_response()` must only load and serialize
data. In `extract.py:get_saved_normalized_route()`, call
`migrate_legacy_condition_reviews(version_row, db)` before building the
response. Commit only when it returns `True`; roll back and re-raise unexpected
migration exceptions.

Reduce `condition_reviews.py` to re-export intentional compatibility symbols:

```python
from app.services.rule_packages.condition_review_repository import serialize_condition_review
from app.services.rule_packages.condition_review_service import (
    confirm_condition_review,
    invalidate_legacy_nondestructive_relation_reviews,
    migrate_legacy_standard_factor_reviews,
    save_condition_draft,
    set_manual_condition_review,
)
from app.services.rule_packages.condition_review_state import condition_source_hash
```

Migrate application imports to the focused service/repository modules; update
tests that previously imported the monolithic `parse_condition_review()` to use
the prepare/execute/complete service API.

- [ ] **Step 5: Run route, migration, and integration tests**

```text
py -3 -m pytest -q tests/test_rule_package_lifecycle.py tests/test_rule_condition_parser.py tests/test_condition_review_service.py tests/test_workflow_invalidation.py
```

Expected: endpoint statuses/details, workflow invalidation, parser cache,
in-flight stale-result protection, and persisted legacy migrations all pass.

- [ ] **Step 6: Check that responsibilities ended in the intended layers**

```text
rg -n "HTTPException|commit\(|rollback\(" app/services/rule_packages/condition_reviews.py app/services/rule_packages/condition_review_*.py
rg -n "acquire_workflow_revision|commit\(|rollback\(" app/routers/rule_packages.py app/routers/extract.py
git diff --check
git status --short
```

Expected: FastAPI and transaction calls appear only in routers; compatibility
facade, errors, state, repository, and service contain none. Do not commit.

## Task 8: Remove Duplicate Logic and Run Full Verification

**Files:**
- Modify only files from Tasks 1-7 when removing stale imports, duplicate helper bodies, or obsolete private test patch targets.
- Test: all backend tests and frontend regression commands.

**Interfaces:**
- Consumes: completed parser and review boundaries.
- Produces: one implementation for each moved responsibility, stable public facades, and verification evidence.

- [ ] **Step 1: Scan for duplicate ownership and stale imports**

```text
rg -n "def (_parse_with_llm|parse_with_llm|_parse_locally|parse_local_condition|_parse_process_relation|parse_process_relation|_load_route_and_review|load_route_and_review|_validate_process_catalog)" app/services/rule_packages
rg -n "from app.services.rule_packages.condition_reviews import" app tests
```

Expected: moved implementations exist only in their focused modules. The
remaining facade imports are intentional compatibility imports and no production
route depends on the old monolithic parser/review implementation.

- [ ] **Step 2: Run the complete backend suite**

From `process-plan-agent-api`:

```text
py -3 -m pytest -q
```

Expected: all tests pass. Compare the result with the pre-refactor baseline of
`272 passed, 1 skipped`; additional focused tests may increase the passing count.

- [ ] **Step 3: Run frontend regression checks without changing frontend files**

From `process-plan-agent-ui`:

```text
npm.cmd test -- --run
npm.cmd run build
```

Expected: all frontend tests pass and the production build completes.

- [ ] **Step 4: Run final diff and workspace checks**

From the repository root:

```text
git diff --check
git status --short
```

Expected: no whitespace errors; only intentional backend source/tests and the
approved spec/plan documents are present. Existing user-authored untracked
files remain untouched. Do not commit unless the user explicitly requests it.

## Handoff

This plan is saved at
`docs/superpowers/plans/2026-08-05-condition-review-boundary-refactor.md`.
Execute it task-by-task with test evidence before proceeding to the next task.
