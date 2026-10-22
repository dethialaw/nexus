"""Collections (`source_collection`)."""

from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import SourceCollectionRow
from nexus.core.ingestion.entities import SourceCollection


class SqlCollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, collection: SourceCollection) -> None:
        self._session.add(
            SourceCollectionRow(
                execution_id=collection.execution_id,
                source_id=collection.source_id,
                result=str(collection.result),
                article_count=collection.article_count,
                error_detail=collection.error_detail,
                started_at=collection.started_at,
                finished_at=collection.finished_at,
            )
        )
        await self._session.flush()
