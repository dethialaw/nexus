"""Use-case repositories. Only they call `add`, `flush` and `commit`."""

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import AppUserRow, ExecutionRow, SourceRow, SubscriptionRow
from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    Connector,
    DeactivationReason,
    Execution,
    ExecutionResult,
    FailureCause,
    Source,
)
from nexus.core.ingestion.source_catalog import CatalogSyncPlan
from nexus.core.profile.entities import User


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


def source_to_domain(row: SourceRow) -> Source:
    return Source(
        id=row.id,
        source_key=row.source_key,
        connector=Connector(row.connector),
        config=row.config,
        owner_user_id=row.owner_user_id,
        deactivation_reason=(
            None if row.deactivation_reason is None else DeactivationReason(row.deactivation_reason)
        ),
        last_collected_at=row.last_collected_at,
    )


class SqlSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_common(self) -> tuple[Source, ...]:
        rows = await self._session.execute(
            select(SourceRow).where(SourceRow.owner_user_id.is_(None)).order_by(SourceRow.id)
        )
        return tuple(source_to_domain(row) for row in rows.scalars())

    async def get_by_key(self, source_key: str) -> Source | None:
        row = await self._session.scalar(
            select(SourceRow).where(SourceRow.source_key == source_key)
        )
        return None if row is None else source_to_domain(row)

    async def apply_catalog_sync(self, plan: CatalogSyncPlan) -> None:
        common = SourceRow.owner_user_id.is_(None)
        if plan.to_insert:
            await self._session.execute(
                insert(SourceRow)
                .values(
                    [
                        {
                            "source_key": entry.source_key,
                            "connector": str(entry.config.connector),
                            "config": entry.config.model_dump(mode="json"),
                            "is_active": True,
                        }
                        for entry in plan.to_insert
                    ]
                )
                .on_conflict_do_nothing(index_elements=[SourceRow.source_key])
            )
        if plan.to_deactivate:
            await self._session.execute(
                update(SourceRow)
                .where(common, SourceRow.is_active, SourceRow.source_key.in_(plan.to_deactivate))
                .values(
                    is_active=False,
                    deactivation_reason=str(DeactivationReason.REMOVED_FROM_CATALOG),
                )
            )
        if plan.to_reactivate:
            await self._session.execute(
                update(SourceRow)
                .where(
                    common,
                    SourceRow.deactivation_reason == str(DeactivationReason.REMOVED_FROM_CATALOG),
                    SourceRow.source_key.in_(plan.to_reactivate),
                )
                .values(is_active=True, deactivation_reason=None)
            )
        for entry in plan.to_update:
            await self._session.execute(
                update(SourceRow)
                .where(common, SourceRow.source_key == entry.source_key)
                .values(config=entry.config.model_dump(mode="json"))
            )


def user_to_domain(row: AppUserRow) -> User:
    return User(
        id=row.id, handle=row.handle, timezone=row.timezone, briefing_hour=row.briefing_hour
    )


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self, handle: str, timezone: str, briefing_hour: int, *, created_at: datetime
    ) -> User:
        statement = (
            insert(AppUserRow)
            .values(
                handle=handle, timezone=timezone, briefing_hour=briefing_hour, created_at=created_at
            )
            .on_conflict_do_update(
                index_elements=[AppUserRow.handle],
                set_={"timezone": timezone, "briefing_hour": briefing_hour},
            )
            .returning(AppUserRow)
        )
        row = (await self._session.scalars(statement)).one()
        return user_to_domain(row)

    async def get_by_handle(self, handle: str) -> User | None:
        row = await self._session.scalar(select(AppUserRow).where(AppUserRow.handle == handle))
        return None if row is None else user_to_domain(row)


class SqlSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: int, source_id: int, *, created_at: datetime) -> bool:
        inserted = await self._session.execute(
            insert(SubscriptionRow)
            .values(user_id=user_id, source_id=source_id, created_at=created_at)
            .on_conflict_do_nothing()
            .returning(SubscriptionRow.user_id)
        )
        return inserted.first() is not None

    async def remove(self, user_id: int, source_id: int) -> bool:
        deleted = await self._session.execute(
            delete(SubscriptionRow)
            .where(SubscriptionRow.user_id == user_id, SubscriptionRow.source_id == source_id)
            .returning(SubscriptionRow.user_id)
        )
        return deleted.first() is not None
