"""Alembic environment: always the direct URL (DATABASE_URL_DIRECT), never the pooler."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from nexus.adapters.persistence import guards as _guards  # noqa: F401  # registers all models
from nexus.adapters.persistence.base import Base
from nexus.settings import MigrationSettings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def _url() -> str:
    # Tests pass the URL of the test database explicitly.
    explicit = config.attributes.get("url")
    if isinstance(explicit, str):
        return explicit
    return MigrationSettings().database_url_direct.get_secret_value()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported")
asyncio.run(_run_online())
