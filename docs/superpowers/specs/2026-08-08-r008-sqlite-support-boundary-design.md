# R-008 SQLite 支持边界设计

## 1. 目标

ProcessMind 当前数据库模型、版本化迁移和维护命令都依赖 SQLite。R-008 将这一事实变为启动期显式契约：API 只接受 `sqlite+aiosqlite` 数据库 URL，其他数据库后端、同步 SQLite 驱动和非法 URL 在创建 SQLAlchemy 引擎之前失败，并给出可操作且不泄露连接凭据的错误。

## 2. 根因

`app/database.py` 目前用字符串前缀判断 SQLite，但会把任意 `DATABASE_URL` 直接交给 `create_async_engine()`。非 SQLite URL 因此可能先触发缺少驱动，或进入后续 SQLite 专用迁移后再触发 `PRAGMA`、`sqlite_master` 或 DDL 错误，无法准确表达产品支持边界。

## 3. 方案选择

| 方案 | 优点 | 缺点 | 决策 |
| --- | --- | --- | --- |
| 创建引擎前精确校验 `sqlite+aiosqlite` | 最早失败；错误稳定；不会先加载未支持数据库驱动 | 当前明确拒绝同步 SQLite URL | 采用 |
| 只校验后端名为 `sqlite` | 改动略少 | `sqlite://` 仍会由异步引擎给出底层错误 | 不采用 |
| 在 `init_db()` 或迁移入口校验 | 校验靠近迁移 | 模块导入时可能已因驱动缺失失败 | 不采用 |

## 4. 实现边界

1. 在 `app/database.py` 增加数据库配置异常和 URL 校验函数，使用 SQLAlchemy URL 解析器识别驱动。
2. 校验必须在 `create_async_engine()` 之前执行；错误只报告解析出的驱动名或“非法 URL”，不回显用户名、密码、主机或查询参数。
3. 保留现有默认 SQLite 路径、WAL、外键、超时、会话和迁移行为。
4. README、`.env.example`、`.env.compose.example`、`docker-compose.yml` 和数据库维护说明统一声明只支持 `sqlite+aiosqlite`。
5. 更新 `docs/重构与优化跟踪.md` 的 R-008 状态、验收证据和剩余边界。

## 5. 测试

- 通过独立 Python 进程导入 `app.database`，验证 PostgreSQL URL 在驱动加载前以明确配置错误失败，且错误不包含密码。
- 验证同步 `sqlite://` URL 被明确拒绝并提示使用 `sqlite+aiosqlite`。
- 运行数据库启动安全测试和交付配置测试，确认既有 SQLite 启动、迁移与交付配置不回归。
- 运行后端全量测试和 Python 编译检查；Docker 仅在本机存在 Docker CLI 时实测。

## 6. 非目标

- 不增加 PostgreSQL、MySQL 或其他数据库驱动。
- 不改写 ORM 模型、迁移 SQL、维护命令或规则包协议。
- 不改变 ProcessMind V2 与 KmAI V1 的交接格式。
- 不增加运行时数据库自动转换或跨数据库迁移能力。

## 7. 完成标准

1. 所有不受支持的数据库 URL 在引擎创建前被明确拒绝，错误可操作且不泄露凭据。
2. 默认和显式 `sqlite+aiosqlite` 配置保持可用。
3. 相关启动、迁移和交付回归测试通过。
4. 面向本地、Docker 和维护场景的文档表述一致。
