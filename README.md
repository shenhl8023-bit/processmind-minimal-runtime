# ProcessMind 最小可运行包
这个包用于把当前系统交给其他开发者继续修改和运行。

它保留了：

1. 前端源码 `process-plan-agent-ui`
2. 后端源码 `process-plan-agent-api`
3. 运行所需模板 `docs/配置模板`
4. Docker 与本地启动脚本
5. 示例环境配置

它没有保留：

1. `.git`
2. `node_modules`
3. 前端 `dist`
4. Python 虚拟环境 `.venv`
5. 历史发布副本、评测资料、临时输出目录

## 用户文档

- [系统简介](docs/系统简介.md)：了解系统定位、六步工作流、主要产物和使用边界。
- [用户使用说明](docs/用户使用说明.md)：按步骤完成启动、模型配置、资料上传、路线归并、规则审核、模板映射、规则包发布和路线生成，并查找常见问题。

## 目录说明

```text
processmind-minimal-runtime/
├── process-plan-agent-api/
├── process-plan-agent-ui/
├── docs/
├── docker/
├── start-api.sh
├── start-ui.sh
├── bootstrap.sh
├── Dockerfile.api
├── Dockerfile.web
├── docker-compose.yml
└── .env.compose.example
```

## 运行方式一：本地开发运行

### 脚本启动（推荐）

API 和前端在后台运行，运行日志位于 `.runtime/logs/`。Windows 首次启动会自动安装依赖；macOS 首次运行需要先执行一次 `./bootstrap.sh`。

Windows：

1. 双击 `start-windows.cmd` 启动项目
2. 双击 `stop-windows.cmd` 停止项目

macOS：

1. 首次运行先在终端执行 `./bootstrap.sh`
2. 执行 `./scripts/manage-macos.sh start` 启动项目
3. 执行 `./scripts/manage-macos.sh stop` 停止项目

macOS 如果脚本经 Windows 压缩包传输后提示没有执行权限，请在“终端”中进入项目目录并执行一次：

```bash
chmod +x scripts/manage-macos.sh
```

本地启动需要 Python 3.11+、Node.js 20+ 和 npm。

脚本会检查 8000 和 5173 端口。端口被其他程序占用时会停止启动并显示占用进程，不会结束无关程序。

### 终端启动

#### 1. 启动后端

```bash
cd processmind-minimal-runtime
./bootstrap.sh
./start-api.sh
```

默认地址：

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

#### 2. 启动前端

新开一个终端：

```bash
cd processmind-minimal-runtime
./start-ui.sh
```

默认地址：

- Web: [http://127.0.0.1:5173](http://127.0.0.1:5173)

## 运行方式二：Docker

```bash
cd processmind-minimal-runtime
cp .env.compose.example .env
docker compose up -d --build
```

默认地址：

- Web: [http://127.0.0.1:8080](http://127.0.0.1:8080)

## 环境要求

本地开发建议：

1. Python 3.11+
2. Node.js 20+
3. npm 10+

## 数据说明

后端默认在当前包内创建并读取 `data/` 目录；Docker 运行时会把宿主机 `./data` 挂载到容器内 `/runtime-data`。

关键目录：

1. `data/db/process_mind.db`
2. `data/uploads/`

离线交付包不会携带开发机现有的 `data/`、上传文档、SQLite 数据库或 `.env` 文件。需要迁移真实数据时，请单独走备份/恢复流程。

## 常用修改位置

1. 后端接口：`process-plan-agent-api/app/routers/`
2. 后端服务：`process-plan-agent-api/app/services/`
3. 前端页面：`process-plan-agent-ui/src/views/`
4. 前端组件：`process-plan-agent-ui/src/components/`
5. 路由规则知识：`process-plan-agent-api/knowledge/`
6. 提示词模板：`process-plan-agent-api/prompt_templates.md`

## 轴套类工艺知识库 Demo

知识库使用 `process-plan-agent-api/knowledge/demo/local_records.json` 中的本地轴套类历史工艺与加工能力样例，通过关键词检索返回相关记录，再复用项目的大模型配置组织中文答案。答案只依据检索到的本地记录，并展示原始 JSON 或 Excel 的文件、工作表、行号和单元格范围等来源。

在「设置 → 大模型」配置项目已有的模型服务后，即可在「知识库」页面直接提问。未检索到本地依据时不会调用模型；模型未配置或调用失败时仍会显示已检索到的本地记录。Demo 不要求用户上传知识文件，也不接入外部知识检索服务；样例内容仅供参考，实际工艺仍需审核确认。

## 规则包 V2 说明

第 4 步「导出规则包」走 V2 主路径；导出后会成为第 5 步可用的当前规则包。第 5 步会优先使用已导出的 V2 规则包执行 `plan_route`；如果当前任务还没有规则包，则继续提示回到第 4 步导出。

导出的 ZIP 包含 `factor_table.json`、`full_route_structure.json` 和 `rule_table.json` 三张表，分别对应因素、全集路线和规则。

## 内网离线部署（Windows）

若目标机**无外网**，请使用已打好的单 ZIP 离线包：

1. 在有外网的 Windows 开发机上生成 `dist-offline\processmind-offline-windows-YYYYMMDD.zip`
2. 将 ZIP 拷到内网机并解压
3. 进入解压后的目录，双击 `start-windows.cmd`

包内已含便携 Python（后端依赖已装）与前端 `node_modules`。打包前执行 `scripts\prepare-offline-node.ps1` 可把便携 Node 一并放入 ZIP；若未包含，目标机必须预装 Node.js 20+。

在 Windows 开发机上也可重新打单文件完整包：

```bat
bootstrap-windows.cmd
powershell -File scripts\prepare-offline-node.ps1
powershell -File scripts\pack-offline-windows.ps1
```

打包脚本只复制明确允许的源码、便携运行时、前端依赖和示例配置，并在压缩前扫描运行时数据库、上传文件、`.env`、`process_settings.json` 与疑似真实密钥。扫描命中时会以非零退出码停止，且不会生成交付包。真实密钥请在目标机部署时通过环境变量或设置页单独注入；可从不含真实值的 `.env.example` 开始配置。

## Windows 7 SP1 x64 交付包

Win7 交付使用独立的 CPython 3.8.10 x64 运行时。开发和构建环境仍保持当前项目的 Python 3.13.5、Node.js 24.x；目标机不安装 Python，目标机不需要 Node.js，也不执行 `npm install`。前端在构建机生成 `process-plan-agent-ui\dist`，由同一个 FastAPI 进程提供页面和 `/api`。

目标机需要预装 Chrome 109 或 Edge 109，并允许启动包调用系统浏览器。包内不包含 CEF/Qt 或其他浏览器壳，IE11 不在支持范围内；Chrome 109 和 Edge 109 是验收基线。服务只监听 `127.0.0.1:8000`。

Win7 SP1 还必须安装 `KB2533623`，或安装包含该修复的后续更新。交付包包含离线安装文件和脚本：请先以管理员身份运行 `prerequisites\install-kb2533623.bat`，安装完成后重启系统，再运行 `start-win7.bat`。这个更新不能通过复制包内 DLL 代替；缺少时 Python 可能在加载 `_socket.pyd` 时提示“DLL load failed ... 参数错误”。

Win7 运行时锁定 `pydantic==2.10.6` 和 `pydantic-core==2.27.2`。较旧的 `pydantic-core==2.23.4` 会导入 Win7 不提供的 `ProcessPrng`，会在日志中出现 `_pydantic_core: DLL load failed`；构建脚本会在打包前拒绝这类 wheel。由于 Python 3.8 的 AnyIO 还需要 `exceptiongroup==1.2.2`，Pydantic 解析项目中的现代类型注解还需要 `eval-type-backport==0.2.2`，这两个条件依赖都已固定并随包提供。

在有网络的 Windows 构建机上，先准备 CPython 3.8.10 x64 runtime 目录和对应的 Windows x64 wheelhouse，再执行。建议直接使用你提供的 `KmAI-Win7-SP1-x64-20261018-r24\runtime` 目录，或内容等价且包含 VC/UCRT Win7 兼容 DLL 的 CPython runtime；打包脚本会拒绝缺少这些 DLL 的 runtime。runtime 不需要预装 pip，脚本会用包内的标准库 wheel 安装器离线安装锁定依赖：

```bat
npm run build
python -m pip download --only-binary=:all: --platform win_amd64 --python-version 38 --implementation cp -r requirements-win7-py38.txt -d C:\wheelhouse\processmind-py38
powershell -File scripts\pack-win7-windows.ps1 -PythonRuntime C:\tools\cpython-3.8.10 -Wheelhouse C:\wheelhouse\processmind-py38
```

`-PythonRuntime` 可以指向包含 `python.exe` 的目录；若使用官方 CPython ZIP，需要先补齐 `MSVCP140.dll`、`VCRUNTIME140*.dll`、`ucrtbase.dll` 以及对应的 `api-ms-win-*` 兼容文件。`-Wheelhouse` 必须包含 `requirements-win7-py38.txt` 中每个依赖的 CPython 3.8 / Windows x64 wheel。

脚本会检查 Python 版本、离线依赖、后端导入和 Python 3.8 源码兼容性，然后生成 `dist-win7\processmind-win7-windows-YYYYMMDD.zip`、`manifest.json` 和 `SHA256SUMS.txt`。压缩前只复制后端源码、知识/config 资源、前端 `dist`、Win7 启动器、前置更新文件和 `.runtime\python`，并拒绝 `node_modules`、`.runtime\node`、数据库、上传文件、日志、`.env` 和凭据。

压缩前必须通过 `scripts/verify-win7-package.py`：它直接核对官方 CPython 3.8.10 x64 核心文件哈希、实际安装依赖版本和必要兼容 DLL，并检查已知不兼容的原生依赖，不能只根据 manifest 判定运行时版本。开发用 `.runtime/python` 可能是 Python 3.13，不能直接复制进 Win7 包。换包请解压到新的空目录，避免覆盖解压残留其他版本文件；最终仍需在 Win7 SP1 x64 上验收。

将 ZIP 解压到目标机后：

1. 双击唯一的 `start-win7.bat` 启动 API 并打开浏览器；启动窗口会保留，按任意键关闭
2. 双击 `status-win7.cmd` 查看健康状态
3. 双击 `stop-win7.cmd` 停止由本包启动的 API
4. 可在解压目录运行 `.runtime\python\python.exe scripts\verify-win7-package.py .` 检查清单和 SHA-256

三个命令执行后均保留窗口，便于查看报错；按任意键只关闭命令窗口。API 在后台运行，启动完成后没有单独的 API 控制台窗口。自动化调用前执行 <code>set "PROCESSMIND_NO_PAUSE=1"</code>，再使用 <code>call start-win7.bat --no-browser</code>、<code>call status-win7.cmd</code>、<code>call stop-win7.cmd</code>。

状态命令只有服务健康且归属当前目录时返回 0，否则返回 1。关闭命令成功停止或确认已退出时返回 0；无法确认归属、权限不足或关闭失败时返回 1 并保留可重试的状态。不要用 <code>taskkill /IM python.exe</code> 关闭系统。自定义端口启动传入 <code>--port 18087</code>；状态和关闭默认读取状态文件里的端口，状态丢失时可显式传入同一端口。不同解压版本共用默认运行目录时，请先从原目录关闭，再启动新包。

启停和状态命令对同一运行目录互斥；提示“另一个命令正在执行”时请等待前一个命令结束后重试。无法读取匹配当前目录的进程命令行时，启动器保留状态并返回失败，不会仅凭端口或健康接口认定进程归属。

数据库、上传文件、日志、缓存和 PID 状态默认写入 `%LOCALAPPDATA%\ProcessMind`；可用同名环境变量 `PROCESSMIND_RUNTIME_DIR` 指向其他可写目录。关闭浏览器不会停止 API；再次双击 `start-win7.bat` 会复用健康的已有服务并重新打开浏览器。需要完全退出时请双击 `stop-win7.cmd`。端口被无关进程占用时启动器会失败并保留无关进程。


## 备注

1. 前端开发模式下，默认会请求 `http://当前主机:8000`
2. 后端默认会在当前包内创建并读取 `data/` 目录；离线交付包不会携带开发机现有的 `data/`
3. 不要直接分发开发目录或手工压缩包；其中可能包含数据库、上传文档和运行时密钥
4. Node-capable 开发离线包使用 `scripts\pack-offline-windows.ps1`；Win7 交付包使用 `scripts\pack-win7-windows.ps1`
