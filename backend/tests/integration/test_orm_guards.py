"""ORM layer of the guards: errors raised before the statement reaches the database."""

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.guards import SnapshotUpdateError
from nexus.adapters.persistence.models import BriefingRow, EntryRow, InterestVersionRow
from tests.integration.seed import seed


async def test_flushing_a_changed_snapshot_row_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed(session)
        entry = (await session.execute(select(EntryRow))).scalar_one()
        entry.title = "changed"

        with pytest.raises(SnapshotUpdateError, match="entry"):
            await session.flush()


async def test_bulk_update_on_a_guarded_table_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed(session)

        with pytest.raises(SnapshotUpdateError, match="interest_version"):
            await session.execute(update(InterestVersionRow).values(weight=0.5))


async def test_a_final_briefing_cannot_be_changed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed(session, briefing_status="normal")
        briefing = (await session.execute(select(BriefingRow))).scalar_one()
        briefing.status = "failed"

        with pytest.raises(SnapshotUpdateError, match="briefing"):
            await session.flush()


async def test_a_failed_briefing_is_replaced_through_the_unit_of_work(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed(session, briefing_status="failed")
        briefing = (await session.execute(select(BriefingRow))).scalar_one()
        briefing.status = "normal"
        briefing.synthesis = "Quiet day."
        await session.flush()

    async with session_factory() as session:
        stored = (await session.execute(select(BriefingRow))).scalar_one()
        assert (stored.status, stored.synthesis) == ("normal", "Quiet day.")
