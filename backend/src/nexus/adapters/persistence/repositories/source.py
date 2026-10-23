"""Sources."""

from datetime import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import SourceRow, SubscriptionRow
from nexus.core.ingestion.entities import Connector, DeactivationReason, Source
from nexus.core.ingestion.source_catalog import CatalogSyncPlan


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

    async def list_to_collect(self) -> tuple[Source, ...]:
        subscribed = exists().where(SubscriptionRow.source_id == SourceRow.id)
        rows = await self._session.scalars(
            select(SourceRow).where(SourceRow.is_active, subscribed).order_by(SourceRow.id)
        )
        return tuple(source_to_domain(row) for row in rows)

    async def mark_collected(self, source_id: int, collected_at: datetime) -> None:
        await self._session.execute(
            update(SourceRow)
            .where(SourceRow.id == source_id)
            .values(last_collected_at=collected_at)
        )

    async def deactivate_for_repeated_failures(self, source_id: int) -> bool:
        result = await self._session.execute(
            update(SourceRow)
            .where(SourceRow.id == source_id, SourceRow.is_active)
            .values(
                is_active=False,
                deactivation_reason=str(DeactivationReason.REPEATED_FAILURES),
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def reactivate(self, source_id: int) -> bool:
        result = await self._session.execute(
            update(SourceRow)
            .where(SourceRow.id == source_id, SourceRow.is_active.is_(False))
            .values(is_active=True, deactivation_reason=None)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

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
