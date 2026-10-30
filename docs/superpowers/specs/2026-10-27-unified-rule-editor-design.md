# Unified Rule Editor Design

## Approved interaction
Preserve current clean card layout, colors, fonts and spacing. Replace modification/more with one 规则修改 entry. Offer 始终出现（主工序）, 人工选择 and 条件判断. Mode changes stay local until 保存并确认; cancel restores the saved rule. Reset/reparse remain secondary editor actions.

Manual selection asks a per-part question in step 6, e.g. 是否需要镀铜: yes includes it; no excludes it. Conditions support adding/deleting field/operator/value rows and an explicit 全部满足 (all) / 满足其一 (any) selector. Default all; preserve nested combinations. The chosen input predicate is then AND every trigger association. Preserve existing all/any/not trees exactly. Empty conditional configurations cannot save or silently become mainline.

Relationships use current process plus relationship and linked process; add/delete rows. Four existing types remain: trigger_after adds current process after linked sources; order_after orders already included processes only; requires adds linked prerequisites; conflicts reports simultaneous-selection errors. New trigger rows are all required. Mainline supports independent order/dependency/conflict relations; triggers belong to conditional appearance.

## Execution semantics
除铜 appears only if input conditions AND every triggering association match. Manual 镀铜=yes AND material=4Cr14Ni14W2Mo includes 镀铜 then 除铜. Either false omits 除铜; no separate 除铜 question. Chained associations reach a fixed point. Dependencies cannot bypass failed configuration gates; contradictory requirements report errors. Manual no stays authoritative. Reject self links and cycles.

## Contract
Keep legacy condition/process_relation candidates valid. Add kind process_configuration with configuration={process_id, occurrence:always|manual|conditional, when:ConditionNode|null, relations:ProcessRelationCandidate[]}; field_definitions remains top-level. Dedicated POST /rule-conditions/configuration validates project/route/workflow revision/current segment and saves existing review JSON/audit metadata without DB migration.

Compile complete audited configurations through CompileRulePackageRequest.process_configurations into RouteRulesV2.process_configurations. Each adds enabled/source/source_segment_id/source_text/confirmed_by/confirmed_at. Omit empty configuration array when serializing legacy packages to preserve hashes. Configuration is authoritative over generic static rules and auto-inclusion. Gather referenced fields into input schema/factor dictionary. Publication must match every complete configuration against server confirmations and reject missing/altered artifacts.

Demo export and native planning agree for supported configurations, translating occurrence AND selected sources. Keep explicit rejection of constraints Demo cannot faithfully express. Never silently downgrade AND to OR or discard relationships.

## Safety and acceptance
Use current codex/zhaoyw feature checkout to build on existing unsaved fixes and active local testing setup. Preserve unrelated edits; no reset/bulk-stage/commit. Never mutate original or active copied DB/uploads for tests. Tests use temporary data. UI verification preserves the user's active page.

Acceptance: three modes save/reopen; condition/relationship add/delete; cancel/failed-save/stale-response safeguards; empty conditional rejection; manual yes/no; two conditions AND two triggers; chains; ordering never creates; requires/conflicts/cycles; legacy any/not roundtrip; full publication authenticity and Demo parity.
