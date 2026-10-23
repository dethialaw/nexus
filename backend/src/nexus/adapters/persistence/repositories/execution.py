"""Executions."""

from datetime import datetime
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import ExecutionRow
from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    Execution,
    ExecutionResult,
    FailureCause,
)


def execution_to_domain(row: ExecutionRow) -> Execution:
    return Execution(
        id=row.id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        result=None if row.result is None else ExecutionResult(row.result),
        failure_cause=None if row.failure_cause is None else FailureCause(row.failure_cause),
        error_detail=row.error_detail,
        anomalies=tuple(
            Anomaly(kind=AnomalyKind(item["kind"]), detail=item["detail"]) for item in row.anomalies
        ),
    )


def _anomalies_to_row(anomalies: tuple[Anomaly, ...]) -> list[dict[str, Any]]:
    return [{"kind": str(anomaly.kind), "detail": anomaly.detail} for anomaly in anomalies]


class SqlExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open(self, started_at: datetime) -> Execution:
        row = ExecutionRow(started_at=started_at, anomalies=[])
        self._session.add(row)
        await self._session.flush()
        return execution_to_domain(row)

    async def close(self, execution: Execution) -> None:
        await self._session.execute(
            update(ExecutionRow)
            .where(ExecutionRow.id == execution.id)
            .values(
                finished_at=execution.finished_at,
                result=None if execution.result is None else str(execution.result),
                failure_cause=(
                    None if execution.failure_cause is None else str(execution.failure_cause)
                ),
                error_detail=execution.error_detail,
                anomalies=_anomalies_to_row(execution.anomalies),
            )
        )

    async def delete_started_before(self, cutoff: datetime) -> int:
        # Collections go with their Execution (ON DELETE CASCADE); Compositions are kept.
        deleted = await self._session.scalars(
            delete(ExecutionRow).where(ExecutionRow.started_at < cutoff).returning(ExecutionRow.id)
        )
        return len(deleted.all())
