# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root
- **`docs/adr/`** — read ADRs that touch the area you're about to work in
- **`docs/规则包V2-通用化实施方案.md`** — V2 product/architecture source of truth
- **`docs/规则包V2-阶段3实施清单.md`** — stage-3 delivery checklist (may lag code; verify against source)
- **`README.md`** — module map, startup and operational overview

If a file doesn't exist, proceed without inventing parallel documentation. Prefer updating `CONTEXT.md` via `/grill-with-docs` when terms or decisions get resolved.

## File structure

Single-context repo:

```text
/
├── CONTEXT.md
├── docs/
│   ├── agents/           ← skill setup (this folder)
│   ├── adr/              ← architecture decision records
│   ├── 配置模板/
│   └── 规则包V2-*.md
├── process-plan-agent-api/
├── process-plan-agent-ui/
├── data/
└── .scratch/             ← local specs & tickets
```

## Use the glossary's vocabulary

When your output names a domain concept (issue title, refactor proposal, hypothesis, test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, either use existing project language or note the gap for `/grill-with-docs` / `/domain-modeling`.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0001 (…) — but worth reopening because…_

## Code boundaries (edit only what the ticket needs)

| Area | Path | Responsibility |
|------|------|----------------|
| API routers | `process-plan-agent-api/app/routers/` | HTTP endpoints |
| API services | `process-plan-agent-api/app/services/` | Business logic, rule packages, generation |
| Rule package V2 | `process-plan-agent-api/app/services/rule_packages/` | Compile / validate / plan / lifecycle |
| Knowledge | `process-plan-agent-api/knowledge/` | Built-in process knowledge |
| Prompts | `process-plan-agent-api/prompt_parts/` | LLM prompt fragments |
| UI views | `process-plan-agent-ui/src/views/` | Five-step pages + settings |
| UI composables | `process-plan-agent-ui/src/composables/` | Flow state |
| UI config | `process-plan-agent-ui/src/config/` | Question trees / strategies |
| UI API client | `process-plan-agent-ui/src/api/` | Axios wrappers |

## Invariants agents must not break

1. **Deterministic route generation** for a given published rule package + factor inputs (same inputs → same process sequence).
2. **Draft packages never drive step-5 production generation** — only `published` packages.
3. **V1 historical packages remain usable** while V2 is the preferred path for new finalized packages.
4. **Rules reference stable `process_id`**, not display names, in V2.
5. **Surgical changes** — do not "clean up" unrelated files while implementing a ticket.
