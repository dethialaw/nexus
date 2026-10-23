"""Purge traces (`purged_article`)."""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import PurgedArticleRow


class SqlPurgeTraceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_purged_before(self, cutoff: datetime) -> int:
        deleted = await self._session.scalars(
            delete(PurgedArticleRow)
            .where(PurgedArticleRow.purged_at < cutoff)
            .returning(PurgedArticleRow.id)
        )
        return len(deleted.all())
