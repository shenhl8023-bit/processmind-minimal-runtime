# R-010 分层质量门禁设计

## 1. 目标

把当前依赖人工执行的 pytest、Vitest、前端构建、Docker 和 Windows 离线交付检查固化为 GitHub Actions 可重复门禁，并保留完全相同的本地验证入口。R-010 只建立质量与交付验证链，不改变 ProcessMind V2、KmAI V1、数据库结构、业务 API 或发布生命周期语义。

本次完成状态分两层记录：门禁配置和本机可运行部分通过后标记为“已建立，本地已验证”；只有工作流实际在 GitHub 运行且 Docker、Windows 离线包任务通过后，才能标记为“已验证完成”。

## 2. 已确认基线

- 仓库远端是 GitHub，当前没有 `.github/workflows`。
- 后端全量测试在本机 Python 3.13.5 下为 `385 passed, 1 skipped`；安装 `httpx2` 后，FastAPI/Starlette TestClient 的迁移弃用警告消失。
- `app/services/rule_packages/` 在后端全量测试下当前语句覆盖率为 `87%`，可以建立 `85%` 的包级最低门槛。
- Ruff 全规则会一次暴露 493 个历史问题，其中包含大量格式、现代化和框架误报；高置信度的 `E9,F63,F7,F82` 规则当前通过。
- 前端已有 `test`、`build` 和 `check:api-contract`，但没有统一质量脚本。
- Docker Compose 已有 API 健康检查和 Web 对 API 健康状态的依赖；本机没有 Docker CLI，不能在本次本地验证中声称镜像或容器通过。
- Windows 离线打包已经具备允许清单、安全扫描、便携 Python、前端依赖、启动和健康探测脚本，但没有自动化任务串联整条链。

## 3. 方案比较

| 方案 | 优点 | 缺点 | 决策 |
| --- | --- | --- | --- |
| 单个 GitHub Actions 工作流，按后端、前端、Docker、Windows 离线包和交付冒烟拆成并行 job | 所有必需检查在同一提交上有清晰结果；required checks 容易配置；失败边界明确 | 一次完整运行占用较多 runner 时间 | 采用 |
| 快速 CI 与交付验证拆成两个独立工作流 | PR 反馈更快，交付任务可降低频率 | 容易出现快速 CI 已绿、交付链未运行的假完成 | 不采用 |
| 用一个跨平台总控脚本串行执行所有检查 | 本地入口看似统一 | Windows、Linux、Docker 的依赖和清理语义不同，脚本复杂且失败定位差 | 不采用 |

采用方案保持一个工作流、多个独立 job。各 job 直接调用仓库已有命令或小范围新增的稳定脚本，不在 YAML 中复制业务逻辑。

## 4. 门禁结构

### 4.1 后端兼容性与静态检查

1. 使用 Python 3.11、3.13 矩阵安装 `process-plan-agent-api/requirements-dev.txt` 并运行后端全量 pytest。
2. 在 Python 3.13 job 运行 Ruff。第一阶段只启用 `E9,F63,F7,F82`，拦截语法错误、无效控制流和未定义名称；不借 R-010 批量格式化或删除可能承担兼容导出职责的历史 import。
3. 开发依赖固定 pytest、pytest-asyncio、pytest-cov、Ruff 和 `httpx2` 的明确版本；运行时 `httpx` 保持不变，因为业务代码仍使用它访问外部 HTTP 服务。
4. pytest 配置注册 `delivery_smoke` 标记并保持测试数据隔离。

### 4.2 规则包覆盖率

1. 使用后端全量测试采集 `app.services.rule_packages` 覆盖率。
2. 包级 `fail-under` 设为 `85`，当前 87% 基线只保留有限回退空间，任何低于门槛的变更直接失败。
3. 生成终端报告和 `coverage.xml`；CI 上传 XML 作为诊断产物，不接入新的第三方覆盖率服务。

### 4.3 前端

Node 固定为 20，依次执行 `npm ci`、OpenAPI 契约检查、Vitest 全量测试和生产构建。`build` 继续由现有 `vue-tsc -b && vite build` 同时承担类型检查和产物构建，不增加重复脚本。

### 4.4 Docker 交付

Linux job 执行 API/Web 镜像构建，使用 Compose 启动本地构建镜像并等待 API 健康。随后检查 API 根地址、Web 根地址以及镜像内知识目录、提示词片段和共享配置模板，最后无条件执行 `docker compose down -v` 清理。

### 4.5 Windows 离线交付

Windows job 使用仓库 `bootstrap-windows.cmd` 生成便携 Python 和前端依赖，调用 `pack-offline-windows.ps1`。打包过程必须经过现有允许清单和密钥/运行时数据扫描。任务随后解压 ZIP，在 `PROCESSMIND_OFFLINE=1`、`PROCESSMIND_NO_BROWSER=1` 下启动解压后的 API/UI，实测 8000 与 5173 健康地址，并在 `finally` 中只停止由包内状态文件确认的 ProcessMind 进程。

### 4.6 交付冒烟

新增或标记一组 `delivery_smoke` 后端 HTTP 场景，覆盖：

1. 文档上传、V2 包保存/发布、使用已发布包生成路线的主链。
2. 确认条件来源变化后，旧发布包在生成前被归档并以稳定错误码 `published_rule_package_changed` 返回 `409`。

场景使用隔离 SQLite 和确定性规则包 fixture，不调用外部 LLM，也不绕过 HTTP 路由直接断言内部 mock。全量 pytest 会包含这些测试，CI 另设可见的聚焦命令以便快速定位交付主链失败。

## 5. 失败处理与安全边界

- 每个 job 独立失败，不允许 `continue-on-error` 掩盖门禁。
- Docker 和 Windows 启动任务必须使用 `always`/`finally` 清理；只停止已确认属于当前测试包的进程和容器。
- CI 不读取真实 `.env`、数据库、上传文档或密钥；所有运行数据写入临时目录。
- 离线 ZIP 不作为源码提交，CI 也不长期上传完整运行时包；仅保留必要的测试日志和覆盖率 XML。
- GitHub Actions 未实际运行、Docker 未在本机实测时，跟踪文档明确保留“待实测”，不把配置存在等同于交付通过。

## 6. 文档与状态

更新 README 的“质量验证”入口和 `docs/重构与优化跟踪.md`：记录门禁文件、实际本机命令、通过结果、当前缺失的 Python 3.11/Docker/GitHub Actions 证据，以及 TestClient 已改用 `httpx2` 后的警告结论。

## 7. 非目标

- 不在本条目引入 Mypy 或全量 Ruff 规则；更严格的类型/风格收敛应单独建立基线并逐步推进。
- 不修改业务行为以追求覆盖率数字，不用排除正常生产代码的方式抬高覆盖率。
- 不增加浏览器 Playwright E2E；本条目的主链门禁位于稳定 HTTP/数据库边界，Docker 与 Windows job 负责真实进程和页面健康检查。
- 不修改 ProcessMind 与 KmAI 的 JSON 交接协议，也不自动发布镜像或离线包。

## 8. 完成标准

1. GitHub Actions 定义后端 3.11/3.13、Ruff、规则包覆盖率、前端、Docker、Windows 离线包和交付冒烟 job。
2. 后端开发依赖与 pytest/Ruff/coverage 配置可由本地和 CI 复用。
3. 规则包全量覆盖率低于 85% 时命令失败。
4. 两条交付冒烟场景由真实 HTTP 行为保护。
5. 本机可执行的后端、前端、离线 staging、契约检查和格式检查通过。
6. 未实测的 GitHub Actions、Python 3.11、Docker 和完整 Windows 离线包链在文档中保持明确限制。
7. `git diff --check` 通过，且不触碰用户现有的无关未跟踪文件。
