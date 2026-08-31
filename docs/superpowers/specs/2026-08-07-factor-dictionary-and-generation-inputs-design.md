# Factor Dictionary and Generation Inputs Design

## Goal

Make the factor dictionary, route rules, and fifth-step inputs one traceable
data flow. A published package must export the full factor table, the full
route structure, and the rule table. Fifth-step values must never present an
example or a suggested value as a confirmed part fact.

## Scope

This change covers the defects identified between rule extraction and route
generation:

- Use a package-level factor dictionary rather than the static registry as
  the published source of truth.
- Preserve every factor definition confirmed in step four, while keeping an
  explicit execution schema for the subset referenced by rules.
- Preserve all clauses in a mixed special-requirement condition.
- Remove implicit fifth-step defaults and represent actual value origin.
- Support custom single-select values and canonicalize option aliases.
- Reject unused/unknown submitted factor keys and validate numeric units.
- Add meaningful package test cases instead of only a mainline smoke test.

No CAD or PLM adapter exists in this project. A source declaration such as
`CAD/PLM` describes where a value should come from; it is not presented as an
automatic value unless an input snapshot carries an extracted value and
evidence.

## Package Contract

The rule package has two distinct factor artifacts.

1. `factor_dictionary`: all factor definitions confirmed in step four.
   Each definition has a stable `key`, label, type, unit, validation, options,
   aliases, source declaration, and custom-value policy.
2. `input_schema.fields`: only the definitions that executable rules reference.
   A field is copied from the dictionary so the planner remains self-contained.

The database stores the factor dictionary JSON next to the input schema, route
catalog, and route rules. The export ZIP contains `factor_table.json`,
`full_route_structure.json`, and `rule_table.json`; the factor table contains
the persisted dictionary rather than an incidental copy of the active input
schema.

## Input Value Contract

The UI keeps an `InputValueState` per execution field:

```
{ value, origin: 'unset' | 'extracted' | 'manual' | 'example', evidence: [] }
```

The generation request continues to send the canonical primitive values for
the deterministic expression engine. It also sends an `input_metadata` map
for audit. Required inputs are valid only when their value is present and the
origin is `extracted` or `manual`. Examples are available only for simulation
and cannot enable production generation.

The published package may include optional `input_defaults`. A default is used
only when its origin is `extracted`; the UI exposes its evidence and requires
the user to confirm or replace it before generation. A package with no
extracted defaults starts completely unset.

## Factor Extraction

The condition parser must build one AST for every explicit conjunct or
disjunct. A known special requirement is one leaf in that tree, not an
alternative to material, feature, or precision leaves. Deterministic parsing
may return a candidate early only after verifying that it represents all
recognized clauses.

Known fields come from the factor dictionary registry. A newly identified
field receives a readable stable project key derived from its normalized label
instead of an opaque hash-only key. Its aliases and observed options are merged
into the dictionary after confirmation.

## Validation and Canonicalization

Input validation rejects keys outside the execution schema. For closed option
sets, aliases are converted to their canonical option value before both
validation and expression evaluation. Every numeric field has one canonical
unit; requests may include a unit only when it exactly equals that canonical
unit. The UI shows the canonical unit adjacent to the numeric control.

The validator reports a warning when a rule set includes multiple independent
processes for the same condition. It also requires generated test cases to
cover every conditional rule at least once, including its decisive boundary
value where the condition uses a number.

## UI Behavior

Fifth-step inputs use compact controls with a visible value-status label:

- `Awaiting input`: no value.
- `Extracted`: value and evidence came from an input snapshot.
- `Manual confirmation`: chosen or entered by the user.
- `Example`: simulation-only value that cannot submit production generation.

Single-select controls with `allow_custom` include a text input and add action.
Clearing a value restores `unset`. The completion counter shows only extracted
and manual values, and labels the two counts separately.

## Tests

Backend tests cover mixed material plus special-requirement parsing, canonical
aliases, unknown input rejection, unit mismatch rejection, and package factor
dictionary persistence. Frontend tests cover no implicit defaults, custom
single-select entry, completion counts by value origin, and example values not
enabling generation. An export test verifies the persisted factor dictionary
is the factor-table ZIP entry.
