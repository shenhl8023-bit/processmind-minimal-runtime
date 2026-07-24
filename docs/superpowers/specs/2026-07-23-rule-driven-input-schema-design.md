# Rule-Driven Input Schema

## Goal

Make the fifth-step input list a faithful projection of the fourth-step
exported rule package. A material, feature, or special requirement that is not
referenced by an executable rule must not appear as a selectable input merely
because it exists in the global field registry.

## Design

The fourth-step compiler will build the package in this order:

1. Build the process catalog and current confirmed user rules.
2. Retain a static fallback rule only when no current user-confirmed rule or
   mainline decision targets the same process. A user-confirmed rule therefore
   replaces, rather than coexists with, the equivalent static fallback.
3. Collect field keys and option values by traversing the final executable
   rules, including nested `all`, `any`, and `not` nodes.
4. Materialize only those field definitions. For select fields, retain only
   options referenced by the final rules and any custom values explicitly used
   by confirmed rules.

The fifth step remains unchanged: it reads `input_schema.fields` from the
latest published V2 package. No independent field dictionary or hard-coded
material list may add values after export.

## Compatibility

Existing rule execution semantics remain unchanged. A project with no
conditional rules may still export mainline processes, but it will not receive
unreferenced condition fields. Static fallback rules remain available for
processes that have not been customized by the user.

## Verification

- A project whose confirmed rule uses only `9Cr18` exports only `9Cr18` in
  `material.grade.options`.
- `95Cr18`, `4Cr14Ni14W2Mo`, and `6061` do not appear unless a final executable
  rule references them.
- A user-confirmed rule for a process removes the equivalent static fallback
  target for that process.
- Nested conditions and custom feature/requirement tags still add their values
  to the input schema.
- Existing backend and frontend test suites continue to pass.
