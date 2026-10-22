"""Composition root: builds the adapters for both entrypoints."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from nexus.adapters.persistence.database import create_engine, create_session_factory, ping
from nexus.adapters.persistence.unit_of_work import SqlUnitOfWork
from nexus.adapters.source_catalog.reader import TomlSourceCatalog
from nexus.core.ingestion.ports import SourceCatalogReader
from nexus.core.shared.ports import Clock
from nexus.settings import Settings


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Container:
    engine: AsyncEngine
    clock: Clock
    uow_factory: Callable[[], SqlUnitOfWork]
    source_catalog: SourceCatalogReader

    def check_database(self) -> Awaitable[None]:
        return ping(self.engine)

    async def dispose(self) -> None:
        await self.engine.dispose()


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or Settings()
    engine = create_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    return Container(
        engine=engine,
        clock=SystemClock(),
        uow_factory=lambda: SqlUnitOfWork(session_factory),
        source_catalog=TomlSourceCatalog(),
    )
