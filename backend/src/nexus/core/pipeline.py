"""Chaining of one Execution: catalog sync, Collections, then close.

Compositions come next.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from nexus.core.ingestion.catalog_sync import synchronize_source_catalog
from nexus.core.ingestion.collection import (
    CollectionOutcome,
    collect_source,
    list_sources_to_collect,
)
from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    CollectionResult,
    Connector,
    Execution,
    ExecutionResult,
    FailureCause,
    SourceCollection,
)
from nexus.core.ingestion.ports import IngestionUnitOfWork, RawArticleReader, SourceCatalogReader
from nexus.core.ingestion.services import close_execution, open_execution
from nexus.core.shared.ports import Clock


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """The closed Execution, plus what the batch summary shows without storing it."""

    execution: Execution
    updated_source_keys: tuple[str, ...] = ()
    collections: tuple[CollectionOutcome, ...] = ()


async def run_execution(
    uow_factory: Callable[[], IngestionUnitOfWork],
    clock: Clock,
    source_catalog: SourceCatalogReader,
    connectors: Mapping[Connector, RawArticleReader],
) -> ExecutionReport:
    execution = await open_execution(uow_factory(), clock)
    try:
        plan = await synchronize_source_catalog(uow_factory(), source_catalog)
        anomalies = [] if plan.anomaly is None else [plan.anomaly]
        sources = await list_sources_to_collect(uow_factory())
        if not sources:
            anomalies.append(
                Anomaly(AnomalyKind.NO_SOURCE_TO_COLLECT, "no active Source has a Subscription")
            )
        outcomes = [
            await collect_source(
                uow_factory(), connectors.get(source.connector), clock, execution, source
            )
            for source in sources
        ]
    except Exception as error:
        await close_execution(
            uow_factory(),
            clock,
            execution,
            ExecutionResult.FAILED,
            failure_cause=FailureCause.TECHNICAL,
            error_detail=f"{type(error).__name__}: {error}",
        )
        raise
    result = _result([outcome.collection for outcome in outcomes])
    closed = await close_execution(
        uow_factory(),
        clock,
        execution,
        result,
        failure_cause=FailureCause.COLLECTION if result is ExecutionResult.FAILED else None,
        anomalies=tuple(anomalies),
    )
    return ExecutionReport(
        execution=closed,
        updated_source_keys=tuple(entry.source_key for entry in plan.to_update),
        collections=tuple(outcomes),
    )


def _result(collections: list[SourceCollection]) -> ExecutionResult:
    failed = sum(c.result is CollectionResult.FAILED for c in collections)
    if failed == 0:
        return ExecutionResult.SUCCESS
    return ExecutionResult.FAILED if failed == len(collections) else ExecutionResult.PARTIAL
