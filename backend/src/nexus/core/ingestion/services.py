"""Opening and closing of an Execution."""

from dataclasses import replace

from nexus.core.ingestion.entities import Anomaly, Execution, ExecutionResult, FailureCause
from nexus.core.ingestion.ports import IngestionUnitOfWork
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
