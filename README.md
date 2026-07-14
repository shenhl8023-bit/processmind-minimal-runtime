# ProcessMind 最小可运行包

这个包用于把当前系统交给其他开发者继续修改和运行。

它保留了：

1. 前端源码 `process-plan-agent-ui`
2. 后端源码 `process-plan-agent-api`
3. 当前运行数据快照 `data`
4. 运行所需模板 `docs/配置模板`
5. Docker 与本地启动脚本

它没有保留：

1. `.git`
2. `node_modules`
3. 前端 `dist`
4. Python 虚拟环境 `.venv`
5. 历史发布副本、评测资料、临时输出目录

## 目录说明

```text
processmind-minimal-runtime-20260709/
├── process-plan-agent-api/
├── process-plan-agent-ui/
├── data/
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

### 1. 启动后端

```bash
cd processmind-minimal-runtime-20260709
./bootstrap.sh
./start-api.sh
```

默认地址：

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 2. 启动前端

新开一个终端：

```bash
cd processmind-minimal-runtime-20260709
./start-ui.sh
```

默认地址：

- Web: [http://127.0.0.1:5173](http://127.0.0.1:5173)

## 运行方式二：Docker

```bash
cd processmind-minimal-runtime-20260709
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

`data/` 里已经包含一份当前数据库快照和上传文件快照，拿到包后可以直接看到现有项目数据。

关键目录：

1. `data/db/process_mind.db`
2. `data/uploads/`

## 常用修改位置

1. 后端接口：`process-plan-agent-api/app/routers/`
2. 后端服务：`process-plan-agent-api/app/services/`
3. 前端页面：`process-plan-agent-ui/src/views/`
4. 前端组件：`process-plan-agent-ui/src/components/`
5. 路由规则知识：`process-plan-agent-api/knowledge/`
6. 提示词模板：`process-plan-agent-api/prompt_templates.md`

## 备注

1. 前端开发模式下，默认会请求 `http://当前主机:8000`
2. 后端默认会读取当前包内的 `data/` 目录
3. 如果需要对外分享给下一位开发者，直接分发整个目录或同目录下生成的 zip 包即可
