from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from nexus.adapters.persistence.base import Base
from nexus.adapters.persistence.database import create_engine, create_session_factory

BACKEND_DIR = Path(__file__).parents[2]


class TestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    test_database_url: SecretStr


@pytest.fixture(scope="session")
def database_url() -> str:
    return TestSettings().test_database_url.get_secret_value()


def alembic_config(url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.attributes["url"] = url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def migrated(database_url: str) -> None:
    """Rebuild the test database from scratch: migrations are tested on every run."""
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def engine(migrated: None, database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        # TRUNCATE fires no UPDATE trigger.
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return create_session_factory(engine)
