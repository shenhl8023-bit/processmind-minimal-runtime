# ProcessMind Win7 本地运行时适配设计

## 目标

将 ProcessMind 打包为可在 Windows 7 SP1 x64 本机运行的离线交付包。目标机不需要安装 Python、Node.js 或 CEF/Qt；目标机预装 Chrome 109 或 Edge 109，由包内的 Python 服务同时提供前端静态资源和后端 API，启动脚本调用系统浏览器打开应用。

开发和构建环境保持当前项目版本：Python 3.13.5、Node.js 24.x（当前构建机为 24.13.0）。Win7 交付包使用单独的 CPython 3.8.10 x64 运行时；前端在现代构建机完成构建，目标机不运行 Node.js。

## 范围与边界

包含以下能力：

1. 后端在 CPython 3.8.10 上启动并完成现有 API 工作流。
2. 前端构建产物随包分发，并由同一 FastAPI 进程提供。
3. Win7 可用的启动、停止、状态检查、日志和浏览器打开脚本。
4. Python 3.8.10 兼容依赖的离线锁定、wheelhouse 和完整性校验。
5. 只监听 `127.0.0.1`，数据、上传文件和日志写入用户可写运行时目录。
6. 在 Chrome 109 或 Edge 109 上验证首页、深层路由、上传下载和核心业务流程。

不包含以下能力：

1. CEF、Qt 或其他内置浏览器壳。
2. Win7 上运行 Node.js 或现场执行 `npm install`。
3. IE11 支持。
4. 将外部大模型、特征服务或其他远程服务打包进本地包；这些服务仍按现有配置访问。
5. 将当前开发机数据库、上传文件、`.env` 或真实密钥复制到交付包。

## 运行时架构

交付包采用以下目录结构：

```text
processmind-win7/
  runtime/
    python/                 # CPython 3.8.10 x64 及已安装依赖
  app/
    process-plan-agent-api/
    frontend/               # Vite build 产物
  data/                     # 首次启动时创建，包内不携带真实数据
  logs/
  start-win7.cmd
  stop-win7.cmd
  status-win7.cmd
  manifest.json
```

`start-win7.cmd` 调用包内 Python 运行 `launcher_win7.py`。启动器检查运行时、数据目录和监听端口，使用 Python 标准库发现并管理由本包启动的 API 进程，等待健康检查成功后调用已安装的 Chrome 或 Edge。停止操作只结束状态文件中且命令行匹配本包路径的进程，不结束同端口的无关进程。

后端使用 Uvicorn 绑定 `127.0.0.1:<port>`。FastAPI 路由继续使用现有 `/api/...` 前缀；静态资源挂载在根路径。对不匹配 `/api`、`/docs` 和静态文件的 `GET` 请求返回 `frontend/index.html`，使 Vue `createWebHistory` 的 `/upload`、`/extract` 等深层路由在浏览器刷新后仍能工作。开发模式保留现有 Vite dev server、代理和端口，不改变开发体验。

默认端口为 `8000`。前端构建时不写入固定 API 主机，生产包使用同源相对路径；开发环境仍通过 Vite 代理访问 `127.0.0.1:8000`。启动脚本打开 `http://127.0.0.1:8000/`。

## Python 3.8 兼容策略

后端源码以现有 Python 3.13 运行和测试为基线，同时增加 Python 3.8 兼容门禁。兼容审计至少覆盖：

1. 所有运行时导入模块中的注解求值，统一使用延迟注解或 `typing` 等价写法，避免 3.8 在导入时求值 `list[...]`、`dict[...]` 和 `X | None`。
2. `str.removesuffix`、`str.removeprefix`、`asyncio.to_thread`、`Path.is_relative_to`、`zoneinfo`、`tomllib` 等 3.9+ API；每个使用点改为兼容实现或项目内小型兼容辅助函数。
3. 第三方库的 Python 下限、Windows x64 wheel、间接依赖和 C 扩展；目标包只安装在构建机准备好的 wheelhouse，不在 Win7 联网解析依赖。
4. 文件路径、中文文件名、SQLite WAL、上传临时文件和进程编码行为。

为目标运行时维护独立锁文件（例如 `requirements-win7-py38.txt`），其中的版本必须在 CPython 3.8.10 x64 上实际导入并通过 API 烟测。当前 Python 3.13 锁文件继续服务开发环境和现有 Windows 开发脚本，不直接复用为 Win7 锁文件。

## 前端与浏览器基线

前端仍使用当前 Vue、TypeScript、Element Plus 和 Vite 工具链，由当前 Node.js 构建。生产构建配置以 Chromium 109 的 JavaScript、CSS 和 Web API 能力为兼容基线；构建产物必须避免仅在 Chromium 110+ 才存在的 API，必要时提供降级实现。

目标浏览器检测只用于给出明确错误提示和记录启动日志，不阻止用户使用其他已安装 Chromium 浏览器。Chrome/Edge 109 是交付验收基线；IE11 明确不支持。浏览器启动失败时，脚本输出可复制的本地 URL，不影响后端继续运行。

## 数据、配置与安全边界

默认运行时目录为 `%LOCALAPPDATA%\\ProcessMind`，可通过 `PROCESSMIND_RUNTIME_DIR` 覆盖。数据库、上传文件、缓存、日志和 PID 状态文件全部位于该目录；程序安装目录按只读处理。包构建阶段扫描并拒绝数据库、上传文件、`.env`、真实密钥和运行日志进入 ZIP。

后端默认设置：`PROCESSMIND_DATA_DIR` 指向运行时数据目录，`PROCESSMIND_CORS_ORIGINS` 仅允许本地开发端口；生产包同源访问不依赖 CORS。若用户配置外部模型或特征服务，凭据从目标机设置文件或设置页注入，不写入构建产物。

## 错误处理与可诊断性

启动器在以下条件下以非零状态退出并给出中文或英文的可操作提示：缺少 Python 运行时、依赖导入失败、数据目录不可写、端口被其他程序占用、健康检查超时、浏览器未找到。API 和启动器分别写入滚动前的文本日志；状态文件记录 PID、端口、包根路径和启动时间。

停止时如果状态文件不存在或进程已退出，命令应幂等成功并清理过期状态。若端口由不匹配的进程占用，启动器不得强杀该进程。

## 打包与发布

构建流程分为四步：

1. 在现代构建机安装并验证当前开发依赖，执行前端生产构建和后端测试。
2. 使用 CPython 3.8.10 x64 创建目标运行时，安装独立锁文件中的 wheelhouse 依赖，运行导入检查和 API 烟测。
3. 将源码、静态前端、Python 运行时、依赖元数据、启动脚本和示例配置 staging 到临时目录，执行敏感文件扫描与逐文件 SHA-256 清单。
4. 生成 ZIP，并在目标环境解压后运行 `status`、`start`、核心流程、`stop` 和重启验证。

manifest 必须记录目标系统、架构、Python 版本、前端构建版本、API 端口、浏览器基线、构建时间和校验清单版本。交付包不得宣称已通过 Win7 验收，除非实机或 Win7 SP1 x64 虚拟机验收矩阵全部通过。

## 验收矩阵

在干净的 Windows 7 SP1 x64 环境中验证：

1. 未安装 Python 和 Node 时，包能解压并启动。
2. Chrome 109 和 Edge 109 至少各完成一次启动和首页加载。
3. `/upload`、`/extract`、`/analysis`、`/template-mapping`、`/finalize`、`/generate`、`/settings`、`/knowledge` 的直接打开与刷新不会返回 404。
4. 文件上传、文件预览/下载、规则提取、路线生成和设置保存使用本地 API 正常工作。
5. 关闭浏览器后执行停止，再次启动不会残留旧进程或错误复用旧 PID。
6. 端口被无关进程占用时启动失败且不终止无关进程。
7. 重启后数据库、设置和上传文件仍存在，运行目录之外没有写入要求。
8. 外部模型未配置时，现有本地/关键词路径仍能返回可解释结果；外部服务配置后，失败信息可在日志中定位。

## 风险与取舍

Python 3.8、Win7 和 Chromium 109 均已停止常规安全更新，交付包仅绑定本机回环地址并依赖目标机的安全隔离。Python 3.8 的第三方 wheel 可用性会限制部分依赖版本；如果某个业务依赖只能在 Python 3.9+ 工作，应优先将该功能拆成可选能力并在启动检查中明确提示，而不是让整个服务在 Win7 上静默失败。

不打包浏览器可以显著减小包体并保留用户既有浏览器环境，但浏览器安装和版本成为交付前置条件。Chrome/Edge 109 是固定验收基线，其他浏览器只做尽力兼容。
