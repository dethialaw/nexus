"""Composition root: builds the adapters for both entrypoints."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx2
from sqlalchemy.ext.asyncio import AsyncEngine

from nexus.adapters.connectors.rss import RssConnector, check_feed
from nexus.adapters.persistence.database import create_engine, create_session_factory, ping
from nexus.adapters.persistence.unit_of_work import SqlUnitOfWork
from nexus.adapters.source_catalog.reader import TomlSourceCatalog
from nexus.adapters.web.fetcher import WebFetcher
from nexus.core.ingestion.entities import Connector, FeedCheck
from nexus.core.ingestion.ports import RawArticleReader, SourceCatalogReader
from nexus.core.shared.ports import Clock
from nexus.settings import FetchSettings, Settings


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Container:
    engine: AsyncEngine
    clock: Clock
    uow_factory: Callable[[], SqlUnitOfWork]
    source_catalog: SourceCatalogReader
    connectors: Mapping[Connector, RawArticleReader]

    def check_database(self) -> Awaitable[None]:
        return ping(self.engine)

    async def dispose(self) -> None:
        await self.engine.dispose()


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or Settings()
    engine = create_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    fetcher = WebFetcher(
        timeout_seconds=settings.fetch_timeout_seconds, max_bytes=settings.fetch_max_bytes
    )
    return Container(
        engine=engine,
        clock=SystemClock(),
        uow_factory=lambda: SqlUnitOfWork(session_factory),
        source_catalog=TomlSourceCatalog(),
        connectors={Connector.RSS: RssConnector(fetcher)},
    )


FeedChecker = Callable[[str, tuple[str, ...]], Awaitable[FeedCheck]]


def build_feed_checker(
    settings: FetchSettings | None = None, transport: httpx2.AsyncBaseTransport | None = None
) -> FeedChecker:
    """`nexus-admin source check`: needs no database, so no database setting either."""
    settings = settings or FetchSettings()
    fetcher = WebFetcher(
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
        transport=transport,
    )

    def check(feed_url: str, exclude_url_patterns: tuple[str, ...]) -> Awaitable[FeedCheck]:
        return check_feed(fetcher, feed_url, exclude_url_patterns, now=SystemClock().now())

    return check
