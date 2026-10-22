# Process-tree additional-node ordering fix

The current 20-document project showed final cleaning and inspection followed by drilling/boring, face machining and flat cutting. The builder concatenated all configured slots with unlisted nodes and only moved packaging last. Model timeout therefore exposed the same incorrect local fallback, and the snapshot retained it.

Source evidence: document 7 places 平端面 at operation 15 between turning and milling. Documents 17/20 place 钻镗孔 at operation 10/15. These are early machining nodes.

Additional nodes now use the nearest following configured node in each source document as their insertion anchor, with one vote per document and a deterministic median for differing samples. Unknown nodes without evidence stay before the release suffix. IDs are assigned before reordering, preserving source identity and existing reviews. Model output that displaces these nodes from their evidence-based anchors or reverses the final release suffix is rejected in favor of local ordering. Intermediate cleaning/inspection occurrences remain distinct.

Snapshot version v37 rebuilds the old ordering. Existing reviewed groups and manual routes use the existing preservation behavior. No PDF extraction change.

Verification: failing regressions reproduced additional machining after inspection, displacement of intermediate cleaning, model displacement of machining and reversed release order. Backend suite: 445 passed / 9 skipped. Pre-rebuild project 8 snapshot backed up to /tmp/processmind-project8-before-order-fix.json. Live rebuild and browser reload show 钻镗孔 at 60, 平端面 at 80 and final 460 清洗 / 470 检验 / 480 包装. Right route also ends 清洗 / 检验 / 包装. Four reviewed groups retain membership/status and the complete review state remains unchanged. First rebuild took 25.13 seconds due to bounded model ordering timeout; subsequent reads use the snapshot.

Changes remain uncommitted in the existing dirty checkout. Unrelated whitespace findings in README.md, routers/projects.py and ui/api/projects.ts were not changed.
