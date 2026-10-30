# Template Precision Assistance Implementation Plan

> **For agentic workers:** Implement inline using test-driven-development and verification-before-completion.

**Goal:** 补全缺失精度，并在保存前指出漏填工序。
**Architecture:** 独立只读模型建议接口，复用模板版本锁和现有模型客户端；界面只补空值；保存端双重校验。
**Tech Stack:** FastAPI、Pydantic、Vue 3、Vitest、pytest。
**Spec:** docs/superpowers/specs/2026-10-28-template-precision-assistance-design.md

## Global Constraints
- 保留已有业务数据、人工值和三表协议。
- 加工精度仅允许粗加工、半精加工、精加工。
- 不把无法判断的精度强制默认成半精加工。

## Review Focus
- 模型超时、空响应、非法输出或低置信度不能填入错误值。
- 人工修改、切换项目/模板、关闭页面后，迟到响应不能污染当前数据。
- 辅助工序无需填写加工精度。
- 同名工序按 process_id 区分。
- 保存失败不改变已保存映射和版本。

## Task 1: 保存校验
- [x] 先添加界面和 API 回归测试并验证失败。
- [x] 界面显示漏填名单、标红并定位；服务端提交前校验显式最终路线。
- [x] 运行模板映射相关前后端测试。

## Task 2: 模型建议
- [x] 先添加模型输出约束、只补空值和迟到响应测试并验证失败。
- [x] 新增 template-process-precisions/suggest 接口及 Vue 操作，复用模型配置。
- [x] 运行相关测试，修复发现的问题。

## Task 3: 验证
- [x] 完整前后端测试、前端构建、Python 3.8 兼容检查。
- [x] 真实页面验证按钮、漏填定位和当前映射不受影响。

## 完成证据
- 后端完整测试：854 passed，9 skipped；现有依赖弃用警告保持。
- 前端完整测试：472 passed；vue-tsc 与 Vite build 成功。
- Python 3.8 源码检查：128 files passed。
- 实际页面漏填验证：钻中间孔名称提示、aria-invalid 标记、自动聚焦通过。
- 实际模型调用：缺失精度获得建议与依据，已恢复测试前精度。
- 已核对映射 revision=4、映射内容哈希与已发布 V2 内容哈希均未改变。
- 本地 8001 服务已加载本次代码，浏览器保留映射工作区供用户测试。
