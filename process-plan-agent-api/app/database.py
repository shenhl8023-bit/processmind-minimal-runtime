"""
数据库引擎与会话配置
"""
import os

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.paths import DEFAULT_DB_PATH
from app.services.db_schema_migrations import run_schema_migrations

DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30} if IS_SQLITE else {},
)


def configure_sqlite_engine(async_engine) -> None:
    """Install SQLite pragmas on every new DB-API connection."""
    if not str(async_engine.url).startswith("sqlite"):
        return

    @event.listens_for(async_engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()


configure_sqlite_engine(engine)


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    # 延迟导入模型，确保 Base.metadata 已完整注册所有表
    import app.models.models  # noqa: F401
    async with engine.begin() as conn:
        if IS_SQLITE:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))
        await conn.run_sync(Base.metadata.create_all)
        await run_schema_migrations(conn)
