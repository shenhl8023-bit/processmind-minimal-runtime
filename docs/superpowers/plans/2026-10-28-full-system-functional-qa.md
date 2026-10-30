# 全系统功能验收与缺陷修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans; independent API/UI domains follow superpowers:dispatching-parallel-agents. Verify defects RED → GREEN before completion.

**Goal:** 逐项验证用户功能，修复可复现缺陷，记录覆盖与外部依赖限制。
**Architecture:** 保留现有 Vue/FastAPI/SQLite 结构。只在数据库、上传目录和设置的隔离副本执行写入测试，真实项目只读比对。分域审查与浏览器六步验收并行。
**Tech Stack:** Vue 3, TypeScript, Vitest, FastAPI, pytest, SQLite, Tabbit/Playwright。
**Spec:** 用户本轮“全流程好好验证，把用户可能用的每一个功能测试，有问题修复”；功能目录以 docs/用户使用说明.md 与现行页面为准。

## Global Constraints
- 不回滚既有未提交修改，不清理真实业务数据，不提交密钥，不批量提交 Git。
- 生产 API 保持 Python 3.8/Win7 兼容；本机无法替代 Windows 实机验收。
- 模型外部调用只进行必要的小样本验证，受控替身与真实联调分别记录。
- 每项新缺陷先证明失败，再修根因，完成定向与全量回归。

## Review Focus
- 项目切换时旧异步响应不能覆盖新项目或误保存。
- 上传、删除、重生成与下游工作流失效保持一致。
- 映射保存及规则定稿的版本一致、缺项定位、取消与重试。
- 生成与导出处理非法输入、过期版本、空结果，并符合三文件契约。
- 设置失败、知识目录空数据、服务异常均有用户可理解的恢复方式。

## Tasks
- [x] 1. 建立隔离副本与功能覆盖矩阵，记录真实数据基线。
- [x] 2. 项目、上传、文档、设置：测试正常/非法/删除/失败，缺陷 RED → GREEN。
- [x] 3. 路线归并与规则分析：测试编辑、持久化、重生成、切项目竞态与门禁。
- [x] 4. 映射、定稿、三文件发布：浏览器串联已发布项目与隔离项目，验证输出结构及负例。
- [x] 5. 知识库、验证生成与全局导航：测试查询、输入、复制下载、错误恢复。
- [x] 6. 独立复核全部本轮修改，运行 API/UI 全量、构建、Python 3.8 检查；更新报告和证据。

## Verification Commands
- API: process-plan-agent-api/.venv/bin/python -m pytest process-plan-agent-api/tests -q
- UI: cd process-plan-agent-ui && npm test
- Build: cd process-plan-agent-ui && npm run build
- Compatibility: python3 scripts/validate-python38.py process-plan-agent-api/app
