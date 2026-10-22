from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import AppUserRow, SourceRow
from nexus.adapters.persistence.unit_of_work import SqlUnitOfWork
from nexus.core.ingestion.entities import Connector, DeactivationReason
from nexus.core.ingestion.source_catalog import CatalogEntry, CatalogSyncPlan
from nexus.core.ingestion.source_config import RedditConfig, RssConfig
from tests.integration.seed import NOW


def reddit_row(name: str, reason: DeactivationReason | None = None, **row: object) -> SourceRow:
    return SourceRow(
        source_key=f"reddit:{name}",
        connector="reddit",
        config={"connector": "reddit", "subreddit": name},
        is_active=reason is None,
        deactivation_reason=None if reason is None else str(reason),
        **row,
    )


async def add(session_factory: async_sessionmaker[AsyncSession], *rows: object) -> None:
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()


async def apply(session_factory: async_sessionmaker[AsyncSession], plan: CatalogSyncPlan) -> None:
    async with SqlUnitOfWork(session_factory) as uow:
        await uow.sources.apply_catalog_sync(plan)
        await uow.commit()


async def rows_by_key(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, SourceRow]:
    async with session_factory() as session:
        rows = (await session.execute(select(SourceRow))).scalars()
        return {row.source_key: row for row in rows}


async def test_list_common_maps_active_and_inactive_common_sources_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = AppUserRow(handle="maintainer", timezone="Europe/Paris", briefing_hour=7, created_at=NOW)
    await add(session_factory, user)
    await add(
        session_factory,
        reddit_row("python"),
        reddit_row("rust", DeactivationReason.REPEATED_FAILURES, last_collected_at=NOW),
        reddit_row("mine", owner_user_id=user.id),
    )

    async with SqlUnitOfWork(session_factory) as uow:
        sources = {source.source_key: source for source in await uow.sources.list_common()}

    assert sorted(sources) == ["reddit:python", "reddit:rust"]
    rust = sources["reddit:rust"]
    assert rust.connector is Connector.REDDIT
    assert rust.config == {"connector": "reddit", "subreddit": "rust"}
    assert rust.deactivation_reason is DeactivationReason.REPEATED_FAILURES
    assert rust.last_collected_at == NOW
    assert rust.is_common
    assert sources["reddit:python"].is_active


async def test_apply_inserts_new_sources_and_skips_existing_keys(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add(session_factory, reddit_row("python"))
    feed = RssConfig(feed_url="https://www.numerama.com/feed/", exclude_url_patterns=("x",))

    await apply(
        session_factory,
        CatalogSyncPlan(
            to_insert=(
                CatalogEntry(config=feed),
                CatalogEntry(config=RedditConfig(subreddit="python")),
            )
        ),
    )

    rows = await rows_by_key(session_factory)
    assert sorted(rows) == ["reddit:python", "rss:numerama.com/feed"]
    inserted = rows["rss:numerama.com/feed"]
    assert (inserted.connector, inserted.is_active, inserted.owner_user_id) == ("rss", True, None)
    assert inserted.config == {
        "connector": "rss",
        "feed_url": "https://www.numerama.com/feed/",
        "exclude_url_patterns": ["x"],
    }


async def test_apply_deactivates_only_active_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add(
        session_factory,
        reddit_row("python"),
        reddit_row("rust", DeactivationReason.MAINTAINER),
    )

    await apply(session_factory, CatalogSyncPlan(to_deactivate=("reddit:python", "reddit:rust")))

    rows = await rows_by_key(session_factory)
    assert (rows["reddit:python"].is_active, rows["reddit:python"].deactivation_reason) == (
        False,
        "removed_from_catalog",
    )
    assert rows["reddit:rust"].deactivation_reason == "maintainer"


async def test_apply_reactivates_only_sources_removed_from_catalog(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add(
        session_factory,
        reddit_row("python", DeactivationReason.REMOVED_FROM_CATALOG),
        reddit_row("rust", DeactivationReason.REPEATED_FAILURES),
    )

    await apply(session_factory, CatalogSyncPlan(to_reactivate=("reddit:python", "reddit:rust")))

    rows = await rows_by_key(session_factory)
    assert (rows["reddit:python"].is_active, rows["reddit:python"].deactivation_reason) == (
        True,
        None,
    )
    assert rows["reddit:rust"].deactivation_reason == "repeated_failures"


async def test_apply_updates_the_config_and_keeps_the_activity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    feed_url = "https://rmcsport.bfmtv.com/rss/football/"
    await add(
        session_factory,
        SourceRow(
            source_key="rss:rmcsport.bfmtv.com/rss/football",
            connector="rss",
            config={"connector": "rss", "feed_url": feed_url},
            is_active=False,
            deactivation_reason="repeated_failures",
        ),
    )
    config = RssConfig(feed_url=feed_url, exclude_url_patterns=("_DN-",))

    await apply(session_factory, CatalogSyncPlan(to_update=(CatalogEntry(config=config),)))

    row = (await rows_by_key(session_factory))["rss:rmcsport.bfmtv.com/rss/football"]
    assert row.config["exclude_url_patterns"] == ["_DN-"]
    assert row.deactivation_reason == "repeated_failures"
