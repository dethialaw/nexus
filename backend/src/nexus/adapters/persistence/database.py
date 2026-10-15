"""Engine and session factory."""

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nexus.adapters.persistence.guards import GuardedSession


def create_engine(url: str) -> AsyncEngine:
    """Engine safe behind Neon's pooler (PgBouncer in transaction mode).

    Prepared statements do not survive a change of server connection: asyncpg's and
    SQLAlchemy's caches are disabled, and each statement gets a unique name.
    """
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, sync_session_class=GuardedSession)


async def ping(engine: AsyncEngine) -> None:
    """Raise if the database cannot answer a trivial query."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
