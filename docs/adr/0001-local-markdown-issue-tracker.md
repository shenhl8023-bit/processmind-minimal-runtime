# ADR-0001: Local markdown issue tracker for agent skills

## Status

Accepted — 2026-07-15

## Context

ProcessMind is primarily a solo / small-team handover package. The GitHub remote exists but is not the day-to-day work board. Matt Pocock engineering skills (`to-spec`, `to-tickets`, `implement`, etc.) need a configured issue tracker.

## Decision

Use **local markdown** under `.scratch/<feature-slug>/` as the issue tracker for agent skills.

- Spec: `.scratch/<feature-slug>/spec.md`
- Tickets: `.scratch/<feature-slug>/issues/NN-slug.md`
- Config: `docs/agents/issue-tracker.md`

## Consequences

- No `gh` dependency for the happy path.
- Specs and tickets version with the repo (if committed) or stay local (if `.scratch/` is gitignored later).
- Switching to GitHub Issues later means re-running setup mindset and rewriting `docs/agents/issue-tracker.md`.
