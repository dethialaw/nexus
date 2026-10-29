"""Assembles `run_execution` with the real RSS Connector, a fake `HttpFetcher` and in-memory
repositories (spec 0002, seam 2)."""

from collections.abc import Mapping, Sequence
from typing import Any

from nexus.adapters.connectors.rss import RssConnector
from nexus.core.ingestion.entities import Connector, DeactivationReason, Source
from nexus.core.ingestion.source_config import RssConfig
from nexus.core.pipeline import ExecutionReport, run_execution
from nexus.core.shared.ports import FetchError, FetchResponse, HttpValidators
from tests.unit.fakes import (
    FakeClock,
    FakeHttpFetcher,
    FakeSourceCatalog,
    InMemoryArticleRepository,
    InMemoryCollectionRepository,
    InMemoryExecutionRepository,
    InMemoryPurgeTraceRepository,
    InMemorySourceRepository,
    InMemoryUnitOfWork,
)

RMC = "https://rmcsport.bfmtv.com/rss/football/"
RMC_KEY = "rss:rmcsport.bfmtv.com/rss/football"


def reddit(name: str) -> dict[str, Any]:
    return {"connector": "reddit", "subreddit": name}


def rss(feed_url: str, **config: Any) -> dict[str, Any]:
    return {"connector": "rss", "feed_url": feed_url, **config}


def rss_source(
    source_id: int, feed_url: str, reason: DeactivationReason | None = None, **config: Any
) -> Source:
    return Source(
        id=source_id,
        source_key=RssConfig(feed_url=feed_url).source_key,
        connector=Connector.RSS,
        config=rss(feed_url, **config),
        owner_user_id=None,
        deactivation_reason=reason,
        last_collected_at=None,
    )


def stored_rmc(config: Mapping[str, Any], reason: DeactivationReason | None = None) -> Source:
    return Source(
        id=1,
        source_key=RMC_KEY,
        connector=Connector.RSS,
        config=config,
        owner_user_id=None,
        deactivation_reason=reason,
        last_collected_at=None,
    )


def ok(
    body: bytes,
    status: int = 200,
    url: str = "",
    validators: HttpValidators = HttpValidators(),  # noqa: B008
    moved_permanently: bool = False,
) -> FetchResponse:
    return FetchResponse(
        status=status,
        body=body,
        final_url=url,
        validators=validators,
        moved_permanently=moved_permanently,
    )


class Harness:
    def __init__(self, *sources: Source, subscribed: Sequence[int] = ()) -> None:
        self.collections = InMemoryCollectionRepository()
        self.executions = InMemoryExecutionRepository(self.collections)
        self.sources = InMemorySourceRepository(*sources, subscribed=subscribed)
        self.purge_traces = InMemoryPurgeTraceRepository()
        self.articles = InMemoryArticleRepository(self.purge_traces)
        self.fetcher = FakeHttpFetcher()
        self.clock = FakeClock()

    def uow(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(
            self.executions, self.sources, self.articles, self.collections, self.purge_traces
        )

    def serve(self, url: str, response: FetchResponse | FetchError) -> None:
        self.fetcher.responses[url] = response

    async def run(
        self, sources: Sequence[Mapping[str, Any]] | None = None, **catalog: Any
    ) -> ExecutionReport:
        """Run one Execution; by default the catalog lists the stored Sources unchanged."""
        listed = (
            [dict(source.config) for source in self.sources.rows.values()] or [reddit("python")]
            if sources is None
            else sources
        )
        return await run_execution(
            self.uow,
            self.clock,
            FakeSourceCatalog(listed, **catalog),
            {Connector.RSS: RssConnector(self.fetcher)},
        )
