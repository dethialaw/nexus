"""Database layer of the guards: the trigger, reached with raw SQL that bypasses the ORM."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.seed import seed


async def scalar(session: AsyncSession, sql: str, **params: object) -> object:
    return (await session.execute(text(sql), params)).scalar_one()


async def test_purging_an_article_sets_entry_and_citation_links_to_null(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        ids = await seed(session)
        await session.execute(text("DELETE FROM article WHERE id = :id"), {"id": ids.article_id})

        assert await scalar(session, "SELECT article_id FROM entry") is None
        assert await scalar(session, "SELECT article_id FROM citation") is None
        assert await scalar(session, "SELECT title FROM entry") == "Title"


async def test_purging_an_execution_keeps_its_compositions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        ids = await seed(session)
        await session.execute(
            text("DELETE FROM execution WHERE id = :id"), {"id": ids.execution_id}
        )

        assert await scalar(session, "SELECT execution_id FROM briefing_composition") is None


@pytest.mark.parametrize(
    "update",
    [
        "UPDATE entry SET title = 'changed'",
        "UPDATE entry SET embedding = array_fill(0.5, ARRAY[768])::vector",
        "UPDATE entry SET embedding_model = 'other-model'",
        "UPDATE entry SET article_id = NULL, title = 'changed'",
        "UPDATE citation SET url = 'https://evil.example'",
        "UPDATE briefing_composition SET result = 'failed'",
        "UPDATE briefing_composition SET execution_id = NULL, error_detail = 'x'",
        "UPDATE interest_version SET weight = 0.5",
        "UPDATE message SET content = 'rewritten'",
        "UPDATE briefing SET synthesis = 'rewritten'",
    ],
)
async def test_any_other_update_is_refused(
    session_factory: async_sessionmaker[AsyncSession], update: str
) -> None:
    async with session_factory() as session:
        async with session.begin():
            await seed(session)
        with pytest.raises(IntegrityError, match="UPDATE refused on guarded table"):
            async with session.begin():
                await session.execute(text(update))


async def test_setting_a_purge_foreign_key_to_null_alone_is_allowed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed(session)
        await session.execute(text("UPDATE entry SET article_id = NULL"))

        assert await scalar(session, "SELECT article_id FROM entry") is None


async def test_a_failed_briefing_can_be_replaced(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed(session, briefing_status="failed")
        await session.execute(text("UPDATE briefing SET status = 'normal', synthesis = 'ok'"))

        assert await scalar(session, "SELECT status FROM briefing") == "normal"
        with pytest.raises(IntegrityError, match="UPDATE refused"):
            async with session.begin_nested():
                await session.execute(text("UPDATE briefing SET synthesis = 'again'"))


async def test_deletes_are_not_blocked(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        ids = await seed(session)
        await session.execute(text("DELETE FROM app_user WHERE id = :id"), {"id": ids.user_id})

        assert await scalar(session, "SELECT count(*) FROM entry") == 0
        assert await scalar(session, "SELECT count(*) FROM interest_version") == 0
