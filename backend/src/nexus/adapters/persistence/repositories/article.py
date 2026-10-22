"""Articles."""

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import ArticleRow
from nexus.core.ingestion.entities import Article


class SqlArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_new(self, articles: Sequence[Article]) -> int:
        if not articles:
            return 0
        # Both UNIQUE constraints of `article` make the write idempotent, inside the batch too.
        inserted = await self._session.scalars(
            insert(ArticleRow)
            .values([_to_row(article) for article in articles])
            .on_conflict_do_nothing()
            .returning(ArticleRow.id)
        )
        return len(inserted.all())


def _to_row(article: Article) -> dict[str, object]:
    return {
        "source_id": article.source_id,
        "canonical_url": article.canonical_url,
        "linked_url": article.linked_url,
        "linked_page_status": str(article.linked_page_status),
        "title": article.title,
        "excerpt": article.excerpt,
        "excerpt_origin": str(article.excerpt_origin),
        "fingerprint": article.fingerprint,
        "published_at": article.published_at,
        "collected_at": article.collected_at,
    }
