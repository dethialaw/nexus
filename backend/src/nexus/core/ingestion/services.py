"""Services of the ingestion section."""

from dataclasses import replace

from pydantic import ValidationError

from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    Execution,
    ExecutionResult,
    FailureCause,
)
from nexus.core.ingestion.ports import IngestionUnitOfWork, SourceCatalogReader
from nexus.core.ingestion.source_catalog import (
    CatalogSyncPlan,
    SourceCatalog,
    UnreadableCatalogError,
    sync_source_catalog,
)
from nexus.core.shared.ports import Clock


async def open_execution(uow: IngestionUnitOfWork, clock: Clock) -> Execution:
    async with uow:
        execution = await uow.executions.open(started_at=clock.now())
        await uow.commit()
    return execution


async def close_execution(
    uow: IngestionUnitOfWork,
    clock: Clock,
    execution: Execution,
    result: ExecutionResult,
    *,
    failure_cause: FailureCause | None = None,
    error_detail: str | None = None,
    anomalies: tuple[Anomaly, ...] = (),
) -> Execution:
    if (result is ExecutionResult.FAILED) != (failure_cause is not None):
        raise ValueError("a failure cause is given if and only if the Execution failed")
    closed = replace(
        execution,
        finished_at=clock.now(),
        result=result,
        failure_cause=failure_cause,
        error_detail=error_detail,
        anomalies=execution.anomalies + anomalies,
    )
    async with uow:
        await uow.executions.close(closed)
        await uow.commit()
    return closed


async def synchronize_source_catalog(
    uow: IngestionUnitOfWork, reader: SourceCatalogReader
) -> CatalogSyncPlan:
    """Apply the catalog to the common Sources; a blocked plan writes nothing."""
    try:
        raw = reader.read()
    except UnreadableCatalogError as error:
        return CatalogSyncPlan(
            anomaly=Anomaly(AnomalyKind.CATALOG_SYNC_BLOCKED, f"unreadable catalog: {error}")
        )
    try:
        catalog = SourceCatalog.from_raw(raw)
    except ValidationError as error:
        return CatalogSyncPlan(
            anomaly=Anomaly(AnomalyKind.CATALOG_SYNC_BLOCKED, _invalid_catalog_detail(error))
        )
    async with uow:
        plan = sync_source_catalog(catalog, await uow.sources.list_common())
        if plan.anomaly is None:
            await uow.sources.apply_catalog_sync(plan)
            await uow.commit()
    return plan


def _invalid_catalog_detail(error: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(map(str, item['loc']))}: {item['msg']} (got {item['input']!r:.80})"
        for item in error.errors(include_url=False)
    )
    return f"invalid catalog: {problems}"
