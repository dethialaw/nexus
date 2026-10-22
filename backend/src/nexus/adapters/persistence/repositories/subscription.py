"""Subscriptions."""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import SubscriptionRow


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
