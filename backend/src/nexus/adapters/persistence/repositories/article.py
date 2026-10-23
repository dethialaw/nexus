"""Articles."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, bindparam, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import ArticleRow, PurgedArticleRow
from nexus.core.ingestion.entities import Article


class SqlArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_new(self, articles: Sequence[Article]) -> int:
        articles = await self._not_purged(articles)
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

    async def purge_collected_before(self, cutoff: datetime, purged_at: datetime) -> int:
        deleted = (
            delete(ArticleRow)
            .where(ArticleRow.collected_at < cutoff)
            .returning(ArticleRow.source_id, ArticleRow.canonical_url, ArticleRow.fingerprint)
            .cte("deleted")
        )
        traces = await self._session.scalars(
            insert(PurgedArticleRow)
            .from_select(
                ["source_id", "canonical_url", "fingerprint", "purged_at"],
                select(
                    deleted.c.source_id,
                    deleted.c.canonical_url,
                    deleted.c.fingerprint,
                    bindparam("purged_at", purged_at, type_=PurgedArticleRow.purged_at.type),
                ),
            )
            .returning(PurgedArticleRow.id)
        )
        return len(traces.all())

    async def _not_purged(self, articles: Sequence[Article]) -> list[Article]:
        """Drop the Articles recognized by a Purge trace of their Source."""
        if not articles:
            return []
        result = await self._session.execute(
            select(
                PurgedArticleRow.source_id,
                PurgedArticleRow.canonical_url,
                PurgedArticleRow.fingerprint,
            ).where(
                or_(
                    *(
                        and_(
                            PurgedArticleRow.source_id == source_id,
                            or_(
                                PurgedArticleRow.canonical_url.in_(urls),
                                PurgedArticleRow.fingerprint.in_(fingerprints),
                            ),
                        )
                        for source_id, urls, fingerprints in _by_source(articles)
                    )
                )
            )
        )
        known = result.all()
        urls = {(row.source_id, row.canonical_url) for row in known}
        fingerprints = {(row.source_id, row.fingerprint) for row in known}
        return [
            article
            for article in articles
            if (article.source_id, article.canonical_url) not in urls
            and (article.source_id, article.fingerprint) not in fingerprints
        ]


def _by_source(articles: Sequence[Article]) -> list[tuple[int, set[str], set[str]]]:
    grouped: dict[int, tuple[set[str], set[str]]] = {}
    for article in articles:
        urls, fingerprints = grouped.setdefault(article.source_id, (set(), set()))
        urls.add(article.canonical_url)
        fingerprints.add(article.fingerprint)
    return [(source_id, urls, fingerprints) for source_id, (urls, fingerprints) in grouped.items()]


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
