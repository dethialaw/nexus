"""In-memory adapters for core tests."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, Self

from nexus.core.ingestion.entities import DeactivationReason, Execution, Source
from nexus.core.ingestion.source_catalog import CatalogSyncPlan, RawSourceCatalog


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
    def __init__(self, *sources: Source) -> None:
        self.rows: dict[str, Source] = {source.source_key: source for source in sources}
        self.config_writes = 0

    async def list_common(self) -> tuple[Source, ...]:
        return tuple(source for source in self.rows.values() if source.is_common)

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


class InMemoryUnitOfWork:
    """Shares its repositories across instances; writes are kept only on commit."""

    def __init__(
        self,
        executions: InMemoryExecutionRepository,
        sources: InMemorySourceRepository | None = None,
    ) -> None:
        self.executions = executions
        self.sources = sources or InMemorySourceRepository()
        self.committed = False
        self._snapshot: tuple[dict[int, Execution], dict[str, Source]] = ({}, {})

    async def __aenter__(self) -> Self:
        self._snapshot = (dict(self.executions.rows), dict(self.sources.rows))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.executions.rows, self.sources.rows = self._snapshot

    async def commit(self) -> None:
        self.committed = True
