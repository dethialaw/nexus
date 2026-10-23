"""Execution lock: a PostgreSQL session-level advisory lock on a dedicated direct connection.

Never taken through the pooler: in transaction mode PgBouncer changes server connection between
two transactions, and a session lock would not follow.
"""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

EXECUTION_LOCK_KEY = 7_283_001_902_000_001


class PostgresExecutionLock:
    def __init__(self, direct_url: str | None, key: int = EXECUTION_LOCK_KEY) -> None:
        self._url = direct_url
        self._key = key
        self._connection: AsyncConnection | None = None

    async def acquire(self) -> bool:
        if self._connection is not None:
            return True
        if self._url is None:
            raise RuntimeError("DATABASE_URL_DIRECT is required to take the Execution lock")
        engine = create_async_engine(self._url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        connection = await engine.connect()
        try:
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key}
            )
            taken = bool(result.scalar_one())
        except BaseException:
            await connection.close()
            await engine.dispose()
            raise
        if not taken:
            await connection.close()
            await engine.dispose()
            return False
        self._connection = connection
        return True

    async def release(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._key})
        except DBAPIError:
            pass  # a dropped connection already freed the lock on the server
        finally:
            engine = connection.engine
            await connection.close()
            await engine.dispose()
