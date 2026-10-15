from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import ExecutionRow
from nexus.bootstrap import build_container
from nexus.entrypoints.api.app import create_app
from nexus.entrypoints.batch.__main__ import run
from nexus.settings import ApiSettings, Settings

UNREACHABLE_DATABASE = "postgresql+asyncpg://nexus:nexus@127.0.0.1:1/nexus"


def settings_for(url: str) -> Settings:
    return Settings(database_url=SecretStr(url))


def test_health_reports_a_reachable_database(database_url: str, migrated: None) -> None:
    app = create_app(lambda: build_container(settings_for(database_url)))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_an_unreachable_database() -> None:
    app = create_app(lambda: build_container(settings_for(UNREACHABLE_DATABASE)))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}


async def test_batch_records_one_finished_execution(
    session_factory: async_sessionmaker[AsyncSession], database_url: str
) -> None:
    await run(build_container(settings_for(database_url)))

    async with session_factory() as session:
        row = (await session.execute(select(ExecutionRow))).scalar_one()
    assert row.result == "success"
    assert row.finished_at is not None


def test_cors_allows_the_front_end_origin() -> None:
    app = create_app(
        lambda: build_container(settings_for(UNREACHABLE_DATABASE)),
        ApiSettings(cors_allowed_origins=["http://localhost:3000"]),
    )

    with TestClient(app) as client:
        allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
        other = client.get("/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in other.headers
