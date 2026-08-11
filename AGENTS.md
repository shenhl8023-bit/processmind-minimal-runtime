# ProcessMind Agent 协作说明

## 适用范围

本文件适用于仓库根目录及其所有子目录。若更深层目录存在新的 `AGENTS.md`，应同时遵守其中更具体的约定；用户请求、密钥安全和运行环境限制优先于本文件。

开始修改前，先读取与变更直接相关的源码、配置、测试和设计文档，确认现有实现和工作区状态。不要根据 README 的单一描述推断行为，也不要覆盖、回退或删除工作区中已有的用户修改。

## 项目定位

ProcessMind 是工艺规划与规则管理平台，负责从文档、CAD/MPS 特征和人工确认中整理工艺因素，维护工艺路线规则，编译、验证、模拟和发布规则包。

ProcessMind 不是 3DMPS 桌面端本身，也不是 KmAI Agent 的运行时。它是上游的工艺知识与规则生产端；KmAI 是下游集成到 3DMPS 中的本地执行端。

## 项目结构

- `process-plan-agent-api/`：FastAPI 后端、数据库模型、文档解析、因素抽取、路线分析、规则包 V2 编译与生命周期管理。
- `process-plan-agent-ui/`：Vue/Vite 前端，包含文档处理、规则审核、问题树、规则定稿、发布和兼容性测试界面。
- `process-plan-agent-api/app/routers/`：HTTP API 路由层。
- `process-plan-agent-api/app/services/`：业务服务层；规则包相关实现位于 `app/services/rule_packages/`。
- `process-plan-agent-api/knowledge/`：工艺路线知识和规则资料。
- `process-plan-agent-api/prompt_parts/`：按阶段拆分的提示词片段。
- `docs/`：设计、实施方案、配置模板和领域说明。
- `docker/`、`Dockerfile.*`、`docker-compose.yml`：容器化运行配置。
- `data/`：本地运行时数据库和上传文件目录，不属于源码交付内容。

修改功能时，先确认变更属于 API、服务、前端视图/组件、知识规则还是发布脚本，避免把业务逻辑塞进路由或页面组件。

## ProcessMind 与 KmAI 的边界

两者是独立 Git 项目，通过稳定的 JSON 规则包协议连接，而不是通过源码 import、npm 依赖或实时 HTTP API 连接。

```text
ProcessMind V2
  文档/特征抽取 → 因素确认 → 规则审核 → 编译/验证 → 发布
       │
       │ 导出的 ZIP 内包含 kmai-v1/*.json
       ▼
KmAI V1
  读取规则文件 → 接收 CAD/MPS 输入 → 展开因素 → 选择工序 → 提交给 3DMPS
```

KmAI 的项目目录、运行时、命名管道和桌面集成不在本项目内维护。涉及 KmAI 执行端行为时，应以 KmAI 项目中的实际代码和规则协议为准，不要假设 ProcessMind 可以直接调用 3DMPS。

## 规则包工作流

ProcessMind 的主规则模型是 V2。规则包至少包含 manifest、input schema、route catalog、route rules、测试用例和验证报告等内容。规则包在发布前应经过编译、校验和必要的模拟；草稿或未发布包不能作为正式路线生成依据。

KmAI 兼容导出由 `process-plan-agent-api/app/services/rule_packages/kmai_export.py` 负责，目标格式是 KmAI 的 V1 运行时协议。导出文件为：

```text
kmai-v1/factor_schema.json
kmai-v1/factor_expansion_rules.json
kmai-v1/route_catalog.json
kmai-v1/route_rules.json
```

KmAI 运行时目标目录为：

```text
KmMpsMcpServer/skills/process-route-generator/references/v1/
```

默认交接流程是：停止 KmAI Agent，备份目标目录中的同名文件，将导出 ZIP 中上述四个文件复制并覆盖，保留 KmAI 原有的 `group_match_rules.json`，然后重启 Agent。除非双方协议明确变更，不要改名、删字段或改变 JSON 顶层结构。

ProcessMind 导出的 `route_catalog.json` 可以带有 KmAI V1 忽略的附加元数据，例如 `template_group_aliases`；这类字段不能改变 V1 必需字段的语义。

在下载或发布前，应校验 KmAI 因素引用、工序引用、条件操作符和导出规模限制。`all` / `any` 条件展开可能产生组合爆炸，默认组合数上限为 `10000`，条件对象总数上限为 `100000`，对应环境变量为：

```text
PROCESSMIND_KMAI_MAX_COMBINATIONS
PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS
```

不能自动解析的来源值必须在规则定稿阶段完成映射。来源值映射到已有 KmAI 因素前，要确认工艺语义一致；映射本身不代表语义已经确认。`manual_override` 因素不能从来源字段自动推断，KmAI 输入必须通过 `manual.factor_overrides` 显式提供值。

## 开发约定

优先做小范围、可验证的修改，保持现有 V2/V1 边界，不要为了一个用例重写规则包协议。新增字段、改变规则语义或改变发布生命周期时，先检查对应的 contracts、validator、compiler、archive、loader 和测试，确认读写链路完整。

后端接口层只负责请求校验、依赖注入和响应编排；复杂规则处理应放在 `app/services/`。前端组件负责交互和展示，规则计算、兼容性判断和发布约束应由后端提供单一事实来源。

涉及规则转换时，应同时考虑 ProcessMind V2 模拟结果和 KmAI V1 执行结果。若两者存在依赖、互斥、排序或人工覆盖差异，应在兼容性测试结果中显式暴露，不能静默假设两套执行器等价。

不要把真实数据库、上传文档、`.env`、API 密钥或运行时输出提交到源码包。离线交付应使用项目提供的打包脚本和安全扫描流程，不要直接压缩开发目录。

## 运行与依赖约定

- Windows 优先使用 `bootstrap-windows.cmd` 安装或准备运行时，再使用 `start-windows.cmd` 和 `stop-windows.cmd` 管理 API 与前端；脚本会检查并只管理能够确认属于本项目的 8000、5173 端口进程。
- Windows 可优先使用仓库内 `.runtime\python\python.exe` 和 `.runtime\node\node.exe`；Unix/macOS 使用 `./bootstrap.sh`、`./start-api.sh`、`./start-ui.sh` 或 `scripts/manage-macos.sh`。
- 前端在 Windows 上执行 npm 命令时使用 `npm.cmd`，避免 PowerShell 执行策略阻止 `npm.ps1`。开发代理默认把 `/api` 转发到 `http://127.0.0.1:8000`。
- 当前后端只支持 `sqlite+aiosqlite`。默认数据位于 `data/db/process_mind.db`，上传文件位于 `data/uploads/`；不要把这些运行时数据当作源码修改提交。
- `.runtime/`、`data/`、`output/`、`node_modules/`、覆盖率文件、pytest 临时目录和 `.env` 属于本地运行或交付产物，除非任务明确要求，不要修改或纳入提交。

## 常用验证入口

本地启动要求 Python 3.11+、Node.js 20+ 和 npm。推荐使用项目已有启动脚本，不要另行创建临时运行方式：

```bash
./bootstrap.sh
./start-api.sh
./start-ui.sh
```

默认 API 地址为 `http://127.0.0.1:8000`，前端地址为 `http://127.0.0.1:5173`。Docker 开发运行使用：

```bash
cp .env.compose.example .env
docker compose up -d --build
```

修改后至少运行与变更范围对应的测试。规则包相关改动优先检查 `process-plan-agent-api/tests/` 中的规则包编译、验证、归档、生命周期和 KmAI 兼容性测试；前端改动同时运行前端类型检查/构建和相关组件测试。完成前必须读取验证输出，不能只根据代码静态阅读声称通过。

### 按变更范围选择验证

后端或规则包变更，在 `process-plan-agent-api/` 下至少运行：

```powershell
..\.runtime\python\python.exe -m ruff check app tests ..\scripts
..\.runtime\python\python.exe -m pytest -q <相关测试文件>
```

涉及规则包编译、校验、归档、生命周期、发布或 KmAI 导出时，再运行全量测试和覆盖率门禁：

```powershell
..\.runtime\python\python.exe -m pytest -q
..\.runtime\python\python.exe -m pytest -q -m delivery_smoke
..\.runtime\python\python.exe -m pytest -q --cov=app.services.rule_packages --cov-report=term --cov-report=xml
```

前端或 API 契约变更，在 `process-plan-agent-ui/` 下运行：

```powershell
npm.cmd run check:api-contract
npm.cmd test
npm.cmd run build
```

`src/api/generated/status.ts` 是由契约检查生成的文件；只有在 OpenAPI 源定义改变且检查需要更新时，才运行 `node scripts/check_api_contract.mjs --write`，不要手工编辑生成内容。离线打包或 Docker 变更还应按范围运行 `docker compose build api web`、`docker compose up -d --wait` 或 `scripts\pack-offline-windows.ps1`，并记录因缺少 Docker、Node 或网络而未执行的检查。

## 交付前检查

- 用 `git diff --check` 检查空白和冲突标记，用 `git status --short` 确认只包含任务相关文件。
- 修改规则包协议、导出格式或发布生命周期时，必须同步检查 contracts、validator、compiler、archive、loader、兼容性校验和测试；不要只修改单个 JSON 示例或 UI 文案。
- 不要自动执行 `commit`、`push`、`rebase`、`reset` 或强制推送；只有用户明确要求时才执行，并且只暂存任务相关文件。
- 最终说明实际修改的文件、执行过的验证及结果，并明确列出未验证内容和剩余风险。

## 变更前检查清单

- 是否明确这是 ProcessMind V2 内部逻辑，还是 KmAI V1 兼容导出逻辑？
- 是否保持了 V2 规则包的发布边界和版本语义？
- 如果改了导出格式，是否同步更新兼容性校验、归档内容、交接说明和测试？
- 是否会影响 `factor_schema.json`、`factor_expansion_rules.json`、`route_catalog.json` 或 `route_rules.json` 的既有消费者？
- 是否显式处理了人工因素、因素映射、条件组合上限和语义差异？
- 是否避免提交真实数据、密钥、缓存和构建产物？

如果需求会改变 ProcessMind 与 KmAI 的交接协议，先说明影响范围并与维护者确认，再修改代码或规则文件。
