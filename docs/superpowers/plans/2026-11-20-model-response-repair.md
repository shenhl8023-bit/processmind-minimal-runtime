# 模型响应与第三步保存时序 Implementation Plan

> **For agentic workers:** 使用superpowers:executing-plans，按用户直接实施授权在当前会话连续完成；保留现有工作区改动，无需再次申请实施许可。

**Goal:** 恢复偶发模型无正文时的有限重试，明确错误原因，并阻止问答未就绪时自动保存。
**Architecture:** 在共用LLM客户端分类响应错误并限制重试；第三步复用现有错误映射，在工作区集中控制保存就绪状态。
**Tech Stack:** Python3.8兼容源码、httpx、FastAPI、Vue3、Vitest；不新增依赖。
**Spec:** `docs/superpowers/specs/2026-11-20-model-response-repair-design.md`

## Global Constraints

- Win7 Pro部署，Python3.8及既有Chrome109构建目标。
- 保留正式数据、用户配置及PM-091工作区改动，PM-065仍deferred。
- 不把reasoning_content当正文，不把截断输出当完成，不跳过必答校验。
- 不记录凭据、URL、模型正文或供应商原始错误；无打包/提交/推送。

## Review Focus

- 连续空正文须停止重试；连接测试不重试也不误报成功。
- 非空但length截断的正文不进入业务校验/发布；拒绝和未知结构不能伪装为空正文反复重试。
- 错误日志和公开响应不泄露任意供应商字段、密钥或原文。
- 生成失败/生成中不自动确认；就绪后自动确认可以恢复，已保存回答保留。
- 真实模型波动不能被离线测试通过掩盖，必须报告真实联通与完整生成的实际结果。

## Task 1：共用响应分类与有限恢复

Files: `app/services/llm_client.py`、`llm_errors.py`；测试`tests/test_llm_response_recovery.py`及现有设置/生成回归。

- [x] 新增真实httpx MockTransport边界回归：空正文后成功、连续空、max_retries=0、推理内容、截断、拒绝、非法JSON/结构和脱敏。
- [x] 执行新增测试，确认当前代码在重试、分类和截断拒绝断言失败。
- [x] 保持LLMResponseError导入兼容，统一安全原因映射及元数据日志；只对可识别空正文额外尝试一次且不超原max_attempts。
- [x] 执行定向后端回归，验证第三步失败不覆盖原配置及连接测试单次请求。

## Task 2：问答就绪后才保存

Files: `src/composables/useAnalysisWorkspace.ts`及`useAnalysisWorkspaceBatchAccept.spec.ts`。

- [x] 新增生成中/失败无guidance时不自动确认、不误报必答，以及就绪后恢复的回归，先确认旧代码失败。
- [x] 将自动判定、持久化与批量入口统一绑定loading/generating/guidance就绪状态，不改回答树和业务规则。
- [x] 执行前端定向回归；保留已有部分采纳和过期响应保护。

## Task 3：联动验证与收尾

- [x] 前后端完整测试、生产构建、Python3.8静态语法和diff检查。
- [x] 使用项目10数据副本验证真实连接、第三步生成和浏览器采纳/第四步交接，正式数据摘要保持。
- [x] 一次独立复核，实证问题按TDD修复；记录真实模型及Win7实机边界。
- [x] 更新PM-092/PM-038与总账，清理本次临时调试设施；启动本机最新代码供复测。

## 执行记录

- 基线：连接4.13秒成功；副本第三步34节点30.67秒成功，原数据/配置不变。原11月18日错误具体响应仍不可恢复，不伪造根因。

- 联合验收完成：后端2294 passed/111 skipped、前端1418 passed/1 skipped、构建与151份Python3.8静态语法通过；独立审查P2按TDD修正后窄复核通过。
- 浏览器连接5.12秒成功；一次91.51秒超时后重试55.77秒生成34工序，进入第四步/第五步并生成34工序25工步路线。正式DB/设置摘要未变；外部超时和Win7实机边界见联合验收。
