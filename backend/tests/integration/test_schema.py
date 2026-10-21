from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import (
    AppUserRow,
    ArticleRow,
    InterestVersionRow,
    PurgedArticleRow,
    SourceRow,
)
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


async def _insert_article(session: AsyncSession, source_id: int, url: str, fingerprint: str, **kw):  # type: ignore[no-untyped-def]
    session.add(
        ArticleRow(
            source_id=source_id,
            canonical_url=url,
            linked_page_status=kw.get("status", "pending"),
            excerpt="x",
            excerpt_origin="source",
            title="t",
            fingerprint=fingerprint,
            published_at=NOW,
            collected_at=NOW,
        )
    )
    await session.flush()


async def _source_id(session: AsyncSession) -> int:
    source = SourceRow(source_key="rss:a", connector="rss", config={}, is_active=True)
    session.add(source)
    await session.flush()
    return source.id


async def test_article_accepts_pending_and_rejects_unknown_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        source_id = await _source_id(session)
        await _insert_article(session, source_id, "https://a/1", "f1")
    async with session_factory() as session, session.begin():
        source_id = (await session.execute(select(SourceRow.id))).scalar_one()
        with pytest.raises(IntegrityError):
            await _insert_article(session, source_id, "https://a/2", "f2", status="bogus")


@pytest.mark.parametrize(("url", "fingerprint"), [("https://a/1", "f2"), ("https://a/2", "f1")])
async def test_article_is_unique_per_source_url_and_fingerprint(
    session_factory: async_sessionmaker[AsyncSession], url: str, fingerprint: str
) -> None:
    async with session_factory() as session, session.begin():
        source_id = await _source_id(session)
        await _insert_article(session, source_id, "https://a/1", "f1")
    async with session_factory() as session, session.begin():
        source_id = (await session.execute(select(SourceRow.id))).scalar_one()
        with pytest.raises(IntegrityError):
            await _insert_article(session, source_id, url, fingerprint)


@pytest.mark.parametrize("handle", ["ab", "UPPER", "has space", "x" * 33, "bad.dot"])
async def test_handle_format_is_enforced_by_the_database(
    session_factory: async_sessionmaker[AsyncSession], handle: str
) -> None:
    async with session_factory() as session, session.begin():
        session.add(AppUserRow(handle=handle, timezone="UTC", briefing_hour=7, created_at=NOW))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_handle_is_unique(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        session.add(AppUserRow(handle="abc_-1", timezone="UTC", briefing_hour=7, created_at=NOW))
        await session.flush()
        session.add(AppUserRow(handle="abc_-1", timezone="UTC", briefing_hour=7, created_at=NOW))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_purged_article_holds_a_trace_and_has_no_user_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        source_id = await _source_id(session)
        session.add(
            PurgedArticleRow(
                source_id=source_id, canonical_url="https://a/1", fingerprint="f1", purged_at=NOW
            )
        )
        await session.flush()
        columns = {c.name for c in PurgedArticleRow.__table__.columns}
        indexes = (
            await session.execute(
                text("SELECT count(*) FROM pg_indexes WHERE tablename = 'purged_article'")
            )
        ).scalar_one()
    assert columns == {"id", "source_id", "canonical_url", "fingerprint", "purged_at"}
    assert indexes == 4  # primary key + the three spec indexes
