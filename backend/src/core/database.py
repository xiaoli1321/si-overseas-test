from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"server_settings": {"search_path": settings.db_schema}},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def create_all() -> None:
    from src.models.tables import (  # noqa: F401
        AuditLog,
        BatchTask,
        ChatMessage,
        ChatSession,
        DetectRecord,
        Threshold,
        UploadedFile,
        User,
    )

    async with engine.begin() as conn:
        # Ensure schema exists before creating tables
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.db_schema}"))
        await conn.run_sync(Base.metadata.create_all)
