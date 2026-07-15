# Issue tracker: Local Markdown

Issues and specs (you may know a spec as a PRD) for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## Status values (local)

Use these on each issue file:

- `Status: ready-for-agent` — ready to implement
- `Status: in-progress` — claimed / being worked
- `Status: blocked` — waiting on another ticket or decision
- `Status: done` — finished and accepted
- `Status: needs-info` — needs human input before continuing

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder` if installed. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `done` or `Status: resolved`.
- **Claim**: set `Status: in-progress` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: done`, then append a context pointer to the map's Decisions-so-far in `map.md` when a map exists.

## ProcessMind notes

- Prefer feature slugs in English kebab-case, e.g. `rule-package-v2-stage3`, `dynamic-form-step5`.
- Link related design docs in the spec body, e.g. `docs/规则包V2-通用化实施方案.md`, `docs/规则包V2-阶段3实施清单.md`.
- Do not put secrets or `process_settings.json` contents into `.scratch/`.
