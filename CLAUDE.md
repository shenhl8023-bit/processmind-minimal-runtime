# ProcessMind — Agent Guide

Typical process-procedure agent (最小可运行包): extract rules from historical procedures, then **deterministically** generate process routes from part factors.

## Stack & layout

- API: `process-plan-agent-api/` (FastAPI, SQLAlchemy/SQLite, rule_packages V2)
- UI: `process-plan-agent-ui/` (Vue3, Vite, Element Plus)
- Knowledge / prompts: `process-plan-agent-api/knowledge/`, `prompt_parts/`
- Runtime data: `data/` (do not commit secrets from `process_settings.json`)
- Design docs: `docs/规则包V2-通用化实施方案.md`, `docs/规则包V2-阶段3实施清单.md`, `docs/项目深入分析报告.md`
- Domain glossary: `CONTEXT.md`

## Non-negotiables

1. Deterministic generation for published package + factor inputs.
2. Draft rule packages never drive step-5 production generation.
3. Prefer surgical diffs; no drive-by refactors.
4. V2 rules use `process_id`, not process display names.
5. Keep V1 packages working.

## Agent skills

Skills are **account-level** (Claude Desktop Cowork), not stored under this repo.  
This repo only holds **venue config** that those skills read/write.

### Issue tracker

Local markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Expected account skills (Cowork)

| Skill | When |
|-------|------|
| `grill-with-docs` | Align domain + update CONTEXT/ADR |
| `to-spec` | Conversation → `.scratch/.../spec.md` |
| `to-tickets` | Spec → tracer-bullet tickets with blockers |
| `implement` | Build a ticket end-to-end |
| `diagnosing-bugs` | Reproduce → minimise → fix → regression |
| `code-review-spec` | Standards + **spec fidelity** on a diff |
| `handoff` | Compact session for the next agent/day |
| `setup-matt-pocock-skills` | Reconfigure tracker/docs (already done here) |

### Coexistence with other user skills

| Concern | Use |
|---------|-----|
| Pressure-test a plan only | `grill-me` |
| Domain + docs | `grill-with-docs` |
| TDD while coding | **`tdd-workflow`** |
| Minimal diffs | `karpathy-guidelines` |
| Coding baseline | `coding-standards` |
| Spec-oriented review | `code-review-spec` |
| Security / generic PR | `security-review` / `review` |

When running `implement`:

1. Follow **tdd-workflow** (failing test first where applicable).
2. Follow **karpathy-guidelines** (surgical changes only).
3. End with **code-review-spec** against the ticket/spec acceptance criteria.

### Default delivery path

```text
grill-with-docs  →  to-spec  →  to-tickets  →  implement (per ticket)  →  code-review-spec
```

Hard bugs: `diagnosing-bugs`. End of day: `handoff`.

### Quick prompts (Chinese OK)

```text
grill-with-docs 对齐规则包 V2 相关边界，并更新 CONTEXT.md
to-spec 把已达成一致的内容写成规格，放到 .scratch/
to-tickets 按 tracer-bullet 拆单并标注阻塞边
implement 实现 .scratch/<feature>/issues/01-....md
code-review-spec 对照 spec 验收标准审查当前 diff
diagnosing-bugs 先复现再最小化，不要直接猜
handoff 输出明天可续做的交接
```

## Commands (local)

- Windows: `start-windows.cmd` / `stop-windows.cmd`
- API/UI scripts: `start-api.*`, `start-ui.*`
- Prefer existing project test commands under each package when implementing.
