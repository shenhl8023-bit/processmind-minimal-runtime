# Button latency investigation and fix

## Evidence

The running API logged SQLite `database is locked` on force re-extraction and project deletion. Connections wait up to 30 seconds for a writer. `clear_project_extraction_results` flushed deletes, then the extraction pipeline entered document processing without committing. Separately, every merge review acquired a workflow write lock and rebuilt the process tree through a model call with the default 180-second timeout and two retries.

## Changes

- Commit extraction cleanup before entering slow document work, releasing the SQLite writer.
- Use the snapshot's saved superset route for accept/reject/rename; a review no longer rebuilds or reorders the tree.
- Bound initial model tree ordering to 25 seconds with no retries, then fall back to the existing local order. Model merge advice retains its separate 25-second budget, so initial generation may still take time.

## Verification

Tests first reproduced the concurrent-write failure and all three review actions entering tree rebuilding. All four passed after the fix. A stalled-provider ordering regression also failed before its deadline was added and passes afterward.

Final suites: backend 441 passed / 9 skipped; frontend 30 files / 198 tests passed; TypeScript and production build passed.

Live service restarted with the fixes. In a disposable three-operation task, browser click to merge response took 48 ms, UI update 59 ms; delete response took 438 ms, UI update 440 ms. Temporary task 7 was deleted through its confirmation dialog. Existing task 6 (123) was read only during verification, with a cached workspace response of 13 ms. These are local observations, not guarantees for every dataset or initial model generation.

Browser returned to task 6 with four pending candidates. No task commit created because this checkout contains pre-existing changes.
