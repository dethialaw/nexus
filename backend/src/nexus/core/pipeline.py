"""Chaining of one Execution: catalog sync, Collections, then close.

Compositions come next.
"""

import asyncio
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
    Source,
    SourceCollection,
)
from nexus.core.ingestion.ports import IngestionUnitOfWork, RawArticleReader, SourceCatalogReader
from nexus.core.ingestion.services import close_execution, open_execution
from nexus.core.shared.ports import Clock

MAX_CONCURRENT_COLLECTIONS = 8


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
        slots = asyncio.Semaphore(MAX_CONCURRENT_COLLECTIONS)

        async def collect(source: Source) -> CollectionOutcome:
            async with slots:
                return await collect_source(
                    uow_factory(), connectors.get(source.connector), clock, execution, source
                )

        # Every Collection ends before the Execution does, even when one of them breaks.
        settled = await asyncio.gather(
            *(collect(source) for source in sources), return_exceptions=True
        )
        for item in settled:
            if isinstance(item, BaseException):
                raise item
        outcomes = [item for item in settled if isinstance(item, CollectionOutcome)]
        anomalies.extend(anomaly for outcome in outcomes for anomaly in outcome.anomalies)
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
