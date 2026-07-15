# ADR-0002: Coexistence of Matt Pocock skills and existing user skills

## Status

Accepted — 2026-07-15

## Context

The repo installs Matt Pocock package-B skills (setup, grill-with-docs, to-spec, to-tickets, implement, diagnosing-bugs, code-review, handoff). The user also has global/user skills: `grill-me`, `tdd-workflow`, `coding-standards`, `karpathy-guidelines`, `review`, `security-review`.

Duplicate TDD/grill skills would fight each other.

## Decision

| Concern | Canonical skill |
|---------|-----------------|
| Pure plan pressure-test (no docs) | User `grill-me` |
| Domain alignment + CONTEXT/ADR | Matt `grill-with-docs` |
| Spec / tickets / implement orchestration | Matt `to-spec` → `to-tickets` → `implement` |
| TDD discipline while implementing | User `tdd-workflow` (do **not** install Matt `tdd` unless migrating fully) |
| Surgical edits / no drive-by refactors | User `karpathy-guidelines` |
| Naming / immutability baseline | User `coding-standards` |
| Spec fidelity + standards on a diff | Matt `code-review` |
| Generic PR review / security | User `review` / `security-review` |
| Hard bugs | Matt `diagnosing-bugs` |
| Session continuity | Matt `handoff` |

## Consequences

- `implement` must be steered in-prompt or via `CLAUDE.md` to use `tdd-workflow` semantics.
- Do not install Matt `grill-me` or Matt `tdd` into this repo unless the user explicitly replaces the user skills.
