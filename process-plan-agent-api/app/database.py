"""
数据库引擎与会话配置
"""
import os

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.paths import DEFAULT_DB_PATH
from app.services.db_schema_migrations import run_schema_migrations

DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
SUPPORTED_DATABASE_DRIVER = "sqlite+aiosqlite"


class DatabaseConfigurationError(RuntimeError):
    """The configured database cannot be used by this ProcessMind build."""


def validate_database_url(database_url: str) -> str:
    try:
        driver_name = make_url(database_url).drivername
    except (ArgumentError, TypeError, ValueError) as exc:
        raise DatabaseConfigurationError(
            "DATABASE_URL is invalid. ProcessMind currently supports SQLite only; "
            "remove DATABASE_URL to use the default database or use "
            "'sqlite+aiosqlite:///path/to/process_mind.db'."
        ) from exc

    if driver_name != SUPPORTED_DATABASE_DRIVER:
        raise DatabaseConfigurationError(
            f"Unsupported DATABASE_URL: received driver '{driver_name}'. "
            "ProcessMind currently supports SQLite only via 'sqlite+aiosqlite'; "
            "remove DATABASE_URL to use the default database or set "
            "'sqlite+aiosqlite:///path/to/process_mind.db'."
        )
    return database_url


DATABASE_URL = validate_database_url(
    os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")
)
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
