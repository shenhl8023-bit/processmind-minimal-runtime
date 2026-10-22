# 领域知识包：实现与试用记录

## 已实现

- 独立的领域知识维护页面：Markdown / 7z 上传，AI 提取概念、关系、因素、规则候选和路线模板，保留原文、章节、行号、模型原始输出与审核历史。
- AI 结果先进入草稿，逐条审核后才可启用；启用版本不可修改，修改需创建新版本。
- 项目可绑定知识包版本及适用范围。第二步使用已审核术语和关系辅助路线归并，分别显示样本证据与领域依据。
- 第三步形成带实际样本明细引用的规则建议，经人工确认后进入原有 V2 编译与发布流程。
- V2 规则包记录知识包 ID、版本和哈希；第五步仍使用已发布规则包确定性执行。
- 切换知识包会标记分析需重算，保留已审核路线和已发布结果；读取页面不会自动覆盖用户路线。

## 试用

本地入口：http://127.0.0.1:5173/domain-knowledge

前端与后端已启动，入口和知识包详情 API 均返回 HTTP 200。简单模型连通性请求约 1.1 秒返回；整包结构化提取耗时明显更长。

1. 在领域知识页面查看“机械加工基线·单章节试验（非完整包）”草稿、原文来源及问题列表。它仅证明真实资料能完成提取、校验和草稿保存，不能用来代表完整知识库。
2. 按资源类别接受、修改或拒绝条目，再启用版本。
3. 在项目第一步选择知识包版本和适用上下文。
4. 第二步重新生成并审核归并建议，显式保存路线；第三步查看领域规则建议。
5. 只有确认、校验并发布后的 V2 规则才参与第五步。

普通项目附件不会自动提升为全局知识；目前请从独立领域知识页面导入可复用资料。

## 验证

- 后端：418 passed，9 skipped，6 个弃用警告。
- 前端：30 个测试文件、193 项测试通过。
- 前端生产构建通过；git diff --check 通过。
- 独立代码审查发现的两项重要问题已用 RED→GREEN 回归修复：知识包切换后读取覆盖路线，以及多压缩包合计解压大小限制。
- 浏览器烟测：页面渲染正常，无文件时生成按钮禁用。尚未对真实项目执行绑定、归并或规则发布。
- 用户压缩包：13/13 Markdown 解析成功。首文件首章节的真实 AI 提取生成 3 个概念、1 条关系，结构及来源校验无问题，已保存为 `baseline-smoke` 第 1 版待审核草稿；引用原文第 5–10 行。API 回读确认全部为 `needs_review`。这不是完整知识包。完整 13 文件 AI 提取仍在运行，尚未保存结果；未启用或绑定任何知识包。

## 当前边界

阶段先后关系仅作参考，尚无自动顺序冲突检查。模板当前展示名称和原文依据，缺少结构化工序序列及缺失工序建议界面。逐建议和全局引用已保留，逐路线段引用尚未贯穿最终保存结构。

跨零件族验证使用合成的壳体案例，尚不能据此认定真实生产场景已通用。原资料中的技术结论和标准有效性仍需领域人员核验。允许人工审核成功提取的部分内容后启用，因此必须先检查导入问题列表，避免误认知识包完整。

## 实施裁定（按发生顺序）

1. Ruling: Work in current feature branch without creating a separate checkout — the user authorized implementing on existing uncommitted knowledge work; a clean checkout omits these dependencies — cost: changes share files, record baseline and avoid whole-file staging.
2. Ruling: Previously activated versions remain usable by bound projects even after a newer version activates — spec requires pinned reproducibility — cost: maintain status as activated plus latest version flag rather than single mutable active content.
3. Ruling: Scope includes explicit part families/materials/stages; unknown context cannot satisfy restricted scope — spec protects cross-family use — cost: user must provide context to see restricted suggestions.
4. Ruling: Keep original documents inside version draft JSON and audit instead of a redundant source table — immutable sources remain hash-addressed and preserved — cost: larger SQLite rows.
5. Ruling: Upload/import creates a new draft version every time; runtime uses only activated records. Long unstructured sections >16k chars reported for splitting; no silent truncation — cost: partial extraction must be reviewed before activation.
6. Ruling: Replace plan's source-text UI assertions with review-controller behavior tests — source substring checks cannot prove activation guards — cost: browser appearance verified separately.
7. Ruling: Do not use existing cache invalidator on package switches — it deletes sample details and published packages — instead retain snapshots by package/context and rebuild only current proposals — cost: retained historical rows consume storage.
8. Ruling: Domain proposals use real DocumentOperationDetail IDs listed in the saved route, distinct from enterprise evidence snapshots — necessary to avoid treating guidance as historical fact — cost: routes without sample details receive no automatic rule candidate.
9. Ruling: Preserve pure DTO compilation for missing stored routes; attach provenance when route exists and require matching provenance at publish — existing compile API is also an offline draft tool — cost: offline drafts gain provenance only after being associated with a saved route.
10. Ruling: Pin py7zr and transitive dependencies and mirror root/API requirements — delivery regression requires locked identical files — cost: upgrade must update both lock lists.
11. Final: Ruling: stage-order before relations remain informational in this MVP — reviewed sources are visible, no active ordering validator or automatic reorder is claimed — cost: users must check stage-order conflicts manually.
12. Final: Ruling: partial imports may be reviewed and activated for successfully extracted resources — omitted/failed batches remain visible and activation still requires explicit human review — cost: an active package may be incomplete.
13. Final: Ruling: scientific validity and current standard validity are outside automated verification — retain unverified source markers and human review — cost: parsing and tests do not establish that source claims are correct.
14. Final: Ruling: second-family validation remains synthetic configuration-only — no production samples from another family were supplied — cost: real cross-family effectiveness remains unproven.
15. Final: Ruling: archive validation checks documented size/path/link constraints and aggregate retained Markdown size; no claim of exhaustive hostile-decompressor audit — cost: malformed archive robustness still depends on py7zr.
16. Final: Ruling: preserve branch/workspace and audit logs without merge/push/commit — user authorized local implementation and pre-existing dirty work spans shared files — cost: changes remain uncommitted and must be reviewed/staged selectively.

## 延后的小项

- Final: minor (deferred): per-suggestion and global domain references survive, but normalized/saved route segments omit per-segment domain evidence.
- Final: minor (deferred): route template names and located source excerpts are shown, but structured concept sequence and missing-operation suggestions need a richer UI.

## 审计记录

原始测试、红绿回归、导入日志与实施台账保留在 `.superpowers/sdd/2026-10-19-domain-knowledge-package/`。本次未提交、合并或推送，保留工作区原有修改。
