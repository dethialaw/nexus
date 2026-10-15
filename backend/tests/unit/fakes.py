"""In-memory adapters for core tests."""

from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self

from nexus.core.ingestion.entities import Execution


class FakeClock:
    def __init__(self, start: datetime = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)) -> None:
        self._now = start

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


class InMemoryExecutionRepository:
    def __init__(self) -> None:
        self.rows: dict[int, Execution] = {}

    async def open(self, started_at: datetime) -> Execution:
        execution = Execution(id=len(self.rows) + 1, started_at=started_at)
        self.rows[execution.id] = execution
        return execution

    async def close(self, execution: Execution) -> None:
        self.rows[execution.id] = execution


class InMemoryUnitOfWork:
    """Shares its repositories across instances; writes are kept only on commit."""

    def __init__(self, executions: InMemoryExecutionRepository) -> None:
        self.executions = executions
        self.committed = False
        self._snapshot: dict[int, Execution] = {}

    async def __aenter__(self) -> Self:
        self._snapshot = dict(self.executions.rows)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.executions.rows = self._snapshot

    async def commit(self) -> None:
        self.committed = True
