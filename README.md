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


## 备注

1. 前端开发模式下，默认会请求 `http://当前主机:8000`
2. 后端默认会在当前包内创建并读取 `data/` 目录；离线交付包不会携带开发机现有的 `data/`
3. 不要直接分发开发目录或手工压缩包；其中可能包含数据库、上传文档和运行时密钥
4. 内网交付应使用 `scripts\pack-offline-windows.ps1` 生成并通过安全扫描的离线包
