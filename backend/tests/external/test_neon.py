"""Neon `ci` branch: migrations through the direct URL, queries through the pooler."""

import asyncio

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text

from nexus.adapters.persistence.database import create_engine
from nexus.adapters.persistence.execution_lock import PostgresExecutionLock
from tests.integration.conftest import BACKEND_DIR


class NeonSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: SecretStr
    database_url_direct: SecretStr


def test_migrations_through_the_direct_url() -> None:
    settings = NeonSettings()
    config = Config(BACKEND_DIR / "alembic.ini")
    config.attributes["url"] = settings.database_url_direct.get_secret_value()
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


async def test_repeated_queries_through_the_pooler_on_several_connections() -> None:
    engine = create_engine(NeonSettings().database_url.get_secret_value())

    async def query(n: int) -> int:
        async with engine.connect() as connection:
            for _ in range(5):
                # Same statement text every time: a leaked prepared statement would collide.
                result = await connection.execute(text("SELECT :n::int"), {"n": n})
                assert result.scalar_one() == n
            return n

    try:
        assert sorted(await asyncio.gather(*(query(n) for n in range(10)))) == list(range(10))
    finally:
        await engine.dispose()


async def test_the_execution_lock_is_taken_by_the_direct_connection() -> None:
    settings = NeonSettings()
    lock = PostgresExecutionLock(settings.database_url_direct.get_secret_value())
    other = PostgresExecutionLock(settings.database_url_direct.get_secret_value())
    assert await lock.acquire()
    try:
        assert not await other.acquire()
    finally:
        await lock.release()
