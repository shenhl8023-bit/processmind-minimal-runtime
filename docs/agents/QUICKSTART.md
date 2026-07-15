# ProcessMind × Agent Skills — 快速上手

配置已完成（2026-07-15）。  
技能装在 **Claude 桌面 Cowork 账户**里；本仓库只保留场地配置（tracker / CONTEXT / ADR）。

## 本仓库不包含

- ~~`.claude/skills/`~~（已移除，避免与账户技能重复）
- ~~`skills-lock.json`~~

## 本仓库保留的配置

| 文件 | 作用 |
|------|------|
| `CLAUDE.md` | Agent 总则 + 技能使用约定 |
| `CONTEXT.md` | 领域语言与不变量 |
| `docs/agents/issue-tracker.md` | 本地 `.scratch/` 工单约定 |
| `docs/agents/domain.md` | 文档消费规则与代码边界 |
| `docs/adr/0001-*.md` | 选用本地 markdown tracker |
| `docs/adr/0002-*.md` | 与用户 skill 共存策略 |
| `.scratch/` | spec / tickets 输出目录 |

## 账户技能（在 Cowork 对话中调用）

- setup-matt-pocock-skills（本仓库已配置，一般不必重跑）
- grill-with-docs
- to-spec
- to-tickets
- implement
- diagnosing-bugs
- code-review-spec
- handoff

## 推荐第一条命令

```text
grill-with-docs 基于 docs/规则包V2-通用化实施方案.md 与当前代码，对齐你当前要做的下一切片；更新 CONTEXT.md 开放决策
```

然后：

```text
to-spec
to-tickets
implement   # 指定某一张 .scratch/.../issues/0N-*.md
```

## 不要做的事

- 不要再在本仓库安装项目级 `.claude/skills` 副本（Cowork 用账户技能）
- 不要让 draft 规则包进入第 5 步正式生成
- 不要在 implement 时顺手大重构
