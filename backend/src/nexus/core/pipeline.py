"""Chaining of one Execution: catalog sync, then close.

Collections and Compositions come next.
"""

from collections.abc import Callable
from dataclasses import dataclass

from nexus.core.ingestion.entities import Execution, ExecutionResult
from nexus.core.ingestion.ports import IngestionUnitOfWork, SourceCatalogReader
from nexus.core.ingestion.services import (
    close_execution,
    open_execution,
    synchronize_source_catalog,
)
from nexus.core.shared.ports import Clock


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """The closed Execution, plus what the batch summary shows without storing it."""

    execution: Execution
    updated_source_keys: tuple[str, ...] = ()


async def run_execution(
    uow_factory: Callable[[], IngestionUnitOfWork],
    clock: Clock,
    source_catalog: SourceCatalogReader,
) -> ExecutionReport:
    execution = await open_execution(uow_factory(), clock)
    plan = await synchronize_source_catalog(uow_factory(), source_catalog)
    closed = await close_execution(
        uow_factory(),
        clock,
        execution,
        ExecutionResult.SUCCESS,
        anomalies=() if plan.anomaly is None else (plan.anomaly,),
    )
    return ExecutionReport(
        execution=closed,
        updated_source_keys=tuple(entry.source_key for entry in plan.to_update),
    )
