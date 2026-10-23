from dataclasses import replace
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import (
    AppUserRow,
    ArticleRow,
    ExecutionRow,
    SourceCollectionRow,
    SourceRow,
    SubscriptionRow,
)
from nexus.adapters.persistence.unit_of_work import SqlUnitOfWork
from nexus.core.ingestion.entities import (
    Article,
    CollectionResult,
    ExcerptOrigin,
    LinkedPageStatus,
    SourceCollection,
)
from tests.integration.seed import NOW


def source_row(name: str, *, active: bool = True) -> SourceRow:
    return SourceRow(
        source_key=f"rss:{name}.example.com/feed",
        connector="rss",
        config={"connector": "rss", "feed_url": f"https://{name}.example.com/feed"},
        is_active=active,
        deactivation_reason=None if active else "maintainer",
    )


async def add(session_factory: async_sessionmaker[AsyncSession], *rows: object) -> None:
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()


def article(source_id: int, url: str, fingerprint: str) -> Article:
    return Article(
        source_id=source_id,
        canonical_url=url,
        linked_url=url,
        linked_page_status=LinkedPageStatus.PENDING,
        title="A title",
        excerpt="An excerpt.",
        excerpt_origin=ExcerptOrigin.SOURCE,
        fingerprint=fingerprint,
        published_at=NOW - timedelta(hours=1),
        collected_at=NOW,
    )


async def test_list_to_collect_returns_active_subscribed_sources_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    users = [
        AppUserRow(handle=h, timezone="Europe/Paris", briefing_hour=7, created_at=NOW)
        for h in ("one", "two")
    ]
    subscribed, inactive, alone = source_row("a"), source_row("b", active=False), source_row("c")
    await add(session_factory, *users, subscribed, inactive, alone)
    await add(
        session_factory,
        *(SubscriptionRow(user_id=u.id, source_id=subscribed.id, created_at=NOW) for u in users),
        SubscriptionRow(user_id=users[0].id, source_id=inactive.id, created_at=NOW),
    )

    async with SqlUnitOfWork(session_factory) as uow:
        sources = await uow.sources.list_to_collect()

    assert [s.source_key for s in sources] == ["rss:a.example.com/feed"]


async def test_mark_collected_sets_last_collected_at(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    row = source_row("a")
    await add(session_factory, row)

    async with SqlUnitOfWork(session_factory) as uow:
        await uow.sources.mark_collected(row.id, NOW)
        await uow.commit()

    async with SqlUnitOfWork(session_factory) as uow:
        source = await uow.sources.get_by_key(row.source_key)
    assert source is not None
    assert source.last_collected_at == NOW


async def test_insert_new_skips_known_urls_and_fingerprints_of_the_same_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    a, b = source_row("a"), source_row("b")
    await add(session_factory, a, b)
    first = article(a.id, "https://a.example.com/1", "f1")

    async with SqlUnitOfWork(session_factory) as uow:
        inserted = await uow.articles.insert_new(
            [first, article(a.id, "https://a.example.com/2", "f2")]
        )
        await uow.commit()
    async with SqlUnitOfWork(session_factory) as uow:
        replayed = await uow.articles.insert_new(
            [
                first,
                article(a.id, "https://a.example.com/republished", "f1"),
                article(a.id, "https://a.example.com/1", "other"),
                article(b.id, "https://a.example.com/1", "f1"),
            ]
        )
        await uow.commit()

    assert (inserted, replayed) == (2, 1)
    async with session_factory() as session:
        rows = (await session.execute(select(ArticleRow).order_by(ArticleRow.id))).scalars().all()
    assert [(r.source_id, r.canonical_url) for r in rows] == [
        (a.id, "https://a.example.com/1"),
        (a.id, "https://a.example.com/2"),
        (b.id, "https://a.example.com/1"),
    ]
    stored = rows[0]
    assert (stored.linked_page_status, stored.excerpt_origin, stored.collected_at) == (
        "pending",
        "source",
        NOW,
    )
    assert stored.nature is None
    assert stored.embedding is None


async def test_insert_new_with_a_duplicate_inside_the_batch(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    a = source_row("a")
    await add(session_factory, a)
    one = article(a.id, "https://a.example.com/1", "f1")

    async with SqlUnitOfWork(session_factory) as uow:
        inserted = await uow.articles.insert_new([one, replace(one, fingerprint="f2")])
        await uow.commit()

    assert inserted == 1


async def test_add_a_collection(session_factory: async_sessionmaker[AsyncSession]) -> None:
    source = source_row("a")
    execution = ExecutionRow(started_at=NOW, anomalies=[])
    await add(session_factory, source, execution)
    collection = SourceCollection(
        execution_id=execution.id,
        source_id=source.id,
        result=CollectionResult.FAILED,
        article_count=0,
        error_detail="HTTP 503",
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=2),
    )

    async with SqlUnitOfWork(session_factory) as uow:
        await uow.collections.add(collection)
        await uow.commit()

    async with session_factory() as session:
        row = (await session.execute(select(SourceCollectionRow))).scalar_one()
    assert (row.execution_id, row.source_id, row.result, row.article_count, row.error_detail) == (
        execution.id,
        source.id,
        "failed",
        0,
        "HTTP 503",
    )
    assert (row.started_at, row.finished_at) == (NOW, NOW + timedelta(seconds=2))


async def test_recent_results_are_the_latest_first_and_limited(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source, other = source_row("a"), source_row("b")
    execution = ExecutionRow(started_at=NOW, anomalies=[])
    await add(session_factory, source, other, execution)
    results = [CollectionResult.FAILED, CollectionResult.SUCCESS, CollectionResult.FAILED]
    async with SqlUnitOfWork(session_factory) as uow:
        for source_id, result in [(source.id, r) for r in results] + [
            (other.id, CollectionResult.SUCCESS)
        ]:
            await uow.collections.add(
                SourceCollection(
                    execution_id=execution.id,
                    source_id=source_id,
                    result=result,
                    article_count=0,
                    error_detail=None,
                    started_at=NOW,
                    finished_at=NOW,
                )
            )
        await uow.commit()

    async with SqlUnitOfWork(session_factory) as uow:
        recent = await uow.collections.recent_results(source.id, 2)

    assert recent == (CollectionResult.FAILED, CollectionResult.SUCCESS)
