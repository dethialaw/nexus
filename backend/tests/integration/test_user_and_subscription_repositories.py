from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import AppUserRow, SourceRow, SubscriptionRow
from nexus.adapters.persistence.unit_of_work import SqlUnitOfWork
from nexus.core.ingestion.entities import DeactivationReason
from tests.integration.seed import NOW


async def add_source(
    session_factory: async_sessionmaker[AsyncSession], name: str = "python"
) -> SourceRow:
    row = SourceRow(
        source_key=f"reddit:{name}",
        connector="reddit",
        config={"connector": "reddit", "subreddit": name},
        is_active=False,
        deactivation_reason="maintainer",
    )
    async with session_factory() as session:
        session.add(row)
        await session.commit()
    return row


async def test_upsert_creates_then_updates_a_user_by_handle(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlUnitOfWork(session_factory) as uow:
        created = await uow.users.upsert("maintainer", "Europe/Paris", 7, created_at=NOW)
        await uow.commit()
    async with SqlUnitOfWork(session_factory) as uow:
        updated = await uow.users.upsert(
            "maintainer", "Africa/Dakar", 6, created_at=NOW + timedelta(days=1)
        )
        await uow.commit()

    assert updated.id == created.id
    assert (updated.handle, updated.timezone, updated.briefing_hour) == (
        "maintainer",
        "Africa/Dakar",
        6,
    )
    async with session_factory() as session:
        row = (await session.execute(select(AppUserRow))).scalar_one()
    assert (row.timezone, row.briefing_hour, row.created_at) == ("Africa/Dakar", 6, NOW)


async def test_get_user_by_handle(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with SqlUnitOfWork(session_factory) as uow:
        created = await uow.users.upsert("maintainer", "Europe/Paris", 7, created_at=NOW)
        await uow.commit()

    async with SqlUnitOfWork(session_factory) as uow:
        assert await uow.users.get_by_handle("maintainer") == created
        assert await uow.users.get_by_handle("nobody") is None


async def test_get_source_by_key(session_factory: async_sessionmaker[AsyncSession]) -> None:
    row = await add_source(session_factory)

    async with SqlUnitOfWork(session_factory) as uow:
        source = await uow.sources.get_by_key("reddit:python")
        missing = await uow.sources.get_by_key("reddit:rust")

    assert source is not None
    assert (source.id, source.deactivation_reason) == (row.id, DeactivationReason.MAINTAINER)
    assert missing is None


async def test_subscriptions_are_added_and_removed_idempotently(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = await add_source(session_factory)
    async with SqlUnitOfWork(session_factory) as uow:
        user = await uow.users.upsert("maintainer", "Europe/Paris", 7, created_at=NOW)
        await uow.commit()

    async def add() -> bool:
        async with SqlUnitOfWork(session_factory) as uow:
            added = await uow.subscriptions.add(user.id, source.id, created_at=NOW)
            await uow.commit()
        return added

    async def remove() -> bool:
        async with SqlUnitOfWork(session_factory) as uow:
            removed = await uow.subscriptions.remove(user.id, source.id)
            await uow.commit()
        return removed

    assert [await add(), await add()] == [True, False]
    async with session_factory() as session:
        rows = (await session.execute(select(SubscriptionRow))).scalars().all()
    assert [(r.user_id, r.source_id, r.created_at) for r in rows] == [(user.id, source.id, NOW)]

    assert [await remove(), await remove()] == [True, False]
    async with session_factory() as session:
        assert (await session.execute(select(SubscriptionRow))).first() is None
