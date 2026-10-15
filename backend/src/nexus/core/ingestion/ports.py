"""Ports of the ingestion section."""

from datetime import datetime
from typing import Protocol

from nexus.core.ingestion.entities import Execution
from nexus.core.shared.ports import UnitOfWork


class ExecutionRepository(Protocol):
    async def open(self, started_at: datetime) -> Execution:
        """Insert a new Execution, not finished yet."""
        ...

    async def close(self, execution: Execution) -> None:
        """Record the end of an Execution: `finished_at`, result, cause and anomalies."""
        ...


class IngestionUnitOfWork(UnitOfWork, Protocol):
    @property
    def executions(self) -> ExecutionRepository: ...
