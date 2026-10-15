from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import ArticleRow, InterestVersionRow
from tests.integration.seed import MODEL, NOW, VECTOR, seed


async def test_vectors_are_read_back_as_tuples_of_floats(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await seed(session)

    async with session_factory() as session:
        article = (await session.execute(select(ArticleRow))).scalar_one()

    assert isinstance(article.embedding, tuple)
    assert article.embedding == VECTOR


async def test_current_interest_version_is_the_latest_of_live_interests(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        ids = await seed(session)
        session.add(
            InterestVersionRow(
                interest_id=ids.interest_id,
                version_no=2,
                change_type="updated",
                origin="direct",
                label="Python asyncio",
                description="asyncio only",
                weight=0.8,
                embedding=VECTOR,
                embedding_model=MODEL,
                created_at=NOW + timedelta(days=1),
            )
        )
        await session.flush()
        current = (
            await session.execute(text("SELECT user_id, version_no FROM current_interest_version"))
        ).all()
        assert current == [(ids.user_id, 2)]

        await session.execute(
            text("UPDATE interest SET deleted_at = now() WHERE id = :id"), {"id": ids.interest_id}
        )
        assert (await session.execute(text("SELECT * FROM current_interest_version"))).all() == []
