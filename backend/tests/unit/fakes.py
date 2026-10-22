"""In-memory adapters for core tests."""

import copy
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, Self

from nexus.core.ingestion.entities import (
    Article,
    DeactivationReason,
    Execution,
    Source,
    SourceCollection,
)
from nexus.core.ingestion.source_catalog import CatalogSyncPlan, RawSourceCatalog
from nexus.core.shared.ports import FetchError, FetchResponse, FetchUsage, HttpValidators


class FakeClock:
    def __init__(self, start: datetime = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)) -> None:
        self._now = start

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


class FakeSourceCatalog:
    """Returns the blocks given in the test, or raises the given error."""

    def __init__(
        self,
        sources: Sequence[Mapping[str, Any]] = (),
        retired: Sequence[str] = (),
        error: Exception | None = None,
    ) -> None:
        self._catalog = RawSourceCatalog(sources=tuple(sources), retired=tuple(retired))
        self._error = error

    def read(self) -> RawSourceCatalog:
        if self._error is not None:
            raise self._error
        return self._catalog


class FakeHttpFetcher:
    """Serves the response, or raises the error, registered for each URL."""

    def __init__(self, responses: Mapping[str, FetchResponse | FetchError] | None = None) -> None:
        self.responses = dict(responses or {})
        self.requested: list[str] = []
        self.sent_validators: list[HttpValidators | None] = []

    async def fetch(
        self, url: str, usage: FetchUsage, validators: HttpValidators | None = None
    ) -> FetchResponse:
        self.requested.append(url)
        self.sent_validators.append(validators)
        response = self.responses[url]
        if isinstance(response, FetchError):
            raise response
        return response


class InMemoryExecutionRepository:
    def __init__(self) -> None:
        self.rows: dict[int, Execution] = {}

    async def open(self, started_at: datetime) -> Execution:
        execution = Execution(id=len(self.rows) + 1, started_at=started_at)
        self.rows[execution.id] = execution
        return execution

    async def close(self, execution: Execution) -> None:
        self.rows[execution.id] = execution


class InMemorySourceRepository:
    def __init__(self, *sources: Source, subscribed: Sequence[int] = ()) -> None:
        self.rows: dict[str, Source] = {source.source_key: source for source in sources}
        self.subscribed = set(subscribed)
        self.config_writes = 0

    async def list_common(self) -> tuple[Source, ...]:
        return tuple(source for source in self.rows.values() if source.is_common)

    async def list_to_collect(self) -> tuple[Source, ...]:
        return tuple(
            source
            for source in self.rows.values()
            if source.is_active and source.id in self.subscribed
        )

    async def get_by_key(self, source_key: str) -> Source | None:
        return self.rows.get(source_key)

    async def mark_collected(
        self, source_id: int, collected_at: datetime, validators: HttpValidators
    ) -> None:
        for key, source in self.rows.items():
            if source.id == source_id:
                self.rows[key] = replace(
                    source, last_collected_at=collected_at, validators=validators
                )

    async def apply_catalog_sync(self, plan: CatalogSyncPlan) -> None:
        for entry in plan.to_insert:
            self.rows.setdefault(
                entry.source_key,
                Source(
                    id=len(self.rows) + 1,
                    source_key=entry.source_key,
                    connector=entry.config.connector,
                    config=entry.config.model_dump(mode="json"),
                    owner_user_id=None,
                    deactivation_reason=None,
                    last_collected_at=None,
                ),
            )
        for key in plan.to_deactivate:
            if self.rows[key].is_active:
                self.rows[key] = replace(
                    self.rows[key], deactivation_reason=DeactivationReason.REMOVED_FROM_CATALOG
                )
        for key in plan.to_reactivate:
            if self.rows[key].deactivation_reason is DeactivationReason.REMOVED_FROM_CATALOG:
                self.rows[key] = replace(self.rows[key], deactivation_reason=None)
        for entry in plan.to_update:
            self.config_writes += 1
            self.rows[entry.source_key] = replace(
                self.rows[entry.source_key], config=entry.config.model_dump(mode="json")
            )


class InMemoryArticleRepository:
    def __init__(self) -> None:
        self.rows: list[Article] = []

    async def insert_new(self, articles: Sequence[Article]) -> int:
        inserted = 0
        for article in articles:
            if not any(
                row.source_id == article.source_id
                and (
                    row.canonical_url == article.canonical_url
                    or row.fingerprint == article.fingerprint
                )
                for row in self.rows
            ):
                self.rows.append(article)
                inserted += 1
        return inserted


class InMemoryCollectionRepository:
    def __init__(self) -> None:
        self.rows: list[SourceCollection] = []

    async def add(self, collection: SourceCollection) -> None:
        self.rows.append(collection)


class InMemoryUnitOfWork:
    """Shares its repositories across instances; writes are kept only on commit."""

    def __init__(
        self,
        executions: InMemoryExecutionRepository,
        sources: InMemorySourceRepository | None = None,
        articles: InMemoryArticleRepository | None = None,
        collections: InMemoryCollectionRepository | None = None,
    ) -> None:
        self.executions = executions
        self.sources = sources or InMemorySourceRepository()
        self.articles = articles or InMemoryArticleRepository()
        self.collections = collections or InMemoryCollectionRepository()
        self.committed = False
        self._snapshot: list[Any] = []

    def _repositories(self) -> list[Any]:
        return [self.executions, self.sources, self.articles, self.collections]

    async def __aenter__(self) -> Self:
        self._snapshot = [copy.copy(repository.rows) for repository in self._repositories()]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            for repository, rows in zip(self._repositories(), self._snapshot, strict=True):
                repository.rows = rows

    async def commit(self) -> None:
        self.committed = True
