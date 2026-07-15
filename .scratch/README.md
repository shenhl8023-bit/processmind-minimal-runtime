# Local issue tracker (agent skills)

Specs and tickets for Matt Pocock engineering skills live here.

## Layout

```text
.scratch/
  <feature-slug>/
    spec.md
    issues/
      01-short-slug.md
      02-another.md
    map.md          # optional, for large multi-session efforts
```

## Example

```text
.scratch/rule-package-v2-polish/
  spec.md
  issues/
    01-lifecycle-simulate-ui.md
    02-validation-error-display.md
```

## Status line

Near the top of each issue file:

```markdown
Status: ready-for-agent
Blocked by:
```

Allowed: `ready-for-agent` | `in-progress` | `blocked` | `done` | `needs-info`

See `docs/agents/issue-tracker.md`.
