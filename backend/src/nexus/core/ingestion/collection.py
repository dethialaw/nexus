"""Collections: reading one Source into Articles."""

from dataclasses import dataclass

from nexus.core.ingestion.entities import (
    Anomaly,
    CollectionResult,
    Execution,
    Source,
    SourceCollection,
)
from nexus.core.ingestion.errors import CollectionError
from nexus.core.ingestion.normalization import to_article
from nexus.core.ingestion.ports import IngestionUnitOfWork, RawArticleReader
from nexus.core.shared.ports import Clock


@dataclass(frozen=True, slots=True)
class CollectionOutcome:
    """A recorded Collection, plus the counts the batch summary shows without storing them."""

    collection: SourceCollection
    unreadable_count: int = 0
    excluded_count: int = 0
    anomalies: tuple[Anomaly, ...] = ()


async def list_sources_to_collect(uow: IngestionUnitOfWork) -> tuple[Source, ...]:
    async with uow:
        return await uow.sources.list_to_collect()


async def collect_source(
    uow: IngestionUnitOfWork,
    reader: RawArticleReader | None,
    clock: Clock,
    execution: Execution,
    source: Source,
) -> CollectionOutcome:
    """One Collection: its Articles, its record and `last_collected_at` in one transaction.

    A `CollectionError` is a failed Collection; any other error is left to the Execution.
    """
    started_at = clock.now()
    try:
        if reader is None:
            raise CollectionError(f"no Connector for {source.connector} yet")
        batch = await reader.read(source)
    except CollectionError as error:
        failed = SourceCollection(
            execution_id=execution.id,
            source_id=source.id,
            result=CollectionResult.FAILED,
            article_count=0,
            error_detail=str(error),
            started_at=started_at,
            finished_at=clock.now(),
        )
        async with uow:
            await uow.collections.add(failed)
            await uow.commit()
        return CollectionOutcome(collection=failed)

    articles = [to_article(raw, source.id, started_at) for raw in batch.raw_articles]
    async with uow:
        inserted = await uow.articles.insert_new(articles)
        finished_at = clock.now()
        collection = SourceCollection(
            execution_id=execution.id,
            source_id=source.id,
            result=CollectionResult.SUCCESS,
            article_count=inserted,
            error_detail=None,
            started_at=started_at,
            finished_at=finished_at,
        )
        await uow.collections.add(collection)
        await uow.sources.mark_collected(source.id, finished_at, batch.validators)
        await uow.commit()
    return CollectionOutcome(
        collection=collection,
        unreadable_count=batch.unreadable_count,
        anomalies=batch.anomalies,
    )
