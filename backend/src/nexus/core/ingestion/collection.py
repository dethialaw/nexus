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
from nexus.core.ingestion.normalization import normalize_batch
from nexus.core.ingestion.ports import IngestionUnitOfWork, RawArticleReader
from nexus.core.shared.ports import Clock

MAX_CONSECUTIVE_FAILURES = 24


@dataclass(frozen=True, slots=True)
class CollectionOutcome:
    """A recorded Collection, plus the counts the batch summary shows without storing them."""

    collection: SourceCollection
    unreadable_count: int = 0
    excluded_count: int = 0
    deactivated: bool = False


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
            recent = await uow.collections.recent_results(source.id, MAX_CONSECUTIVE_FAILURES)
            deactivated = len(recent) == MAX_CONSECUTIVE_FAILURES and all(
                result is CollectionResult.FAILED for result in recent
            )
            if deactivated:
                deactivated = await uow.sources.deactivate_for_repeated_failures(source.id)
            await uow.commit()
        return CollectionOutcome(collection=failed, deactivated=deactivated)

    articles, excluded_count = normalize_batch(batch, source, started_at)
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
        excluded_count=excluded_count,
    )
