"""One row in every table, linked together, for guard and mapping tests."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import (
    AppUserRow,
    ArticleRow,
    BriefingCompositionRow,
    BriefingRow,
    CitationRow,
    ConversationRow,
    EntryRow,
    ExecutionRow,
    InterestRow,
    InterestVersionRow,
    MessageRow,
    SourceRow,
)

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
VECTOR = tuple(1.0 if i == 0 else 0.0 for i in range(768))
MODEL = "gemini-embedding-2"


@dataclass(frozen=True)
class Seeded:
    user_id: int
    article_id: int
    execution_id: int
    composition_id: int
    briefing_id: int
    entry_id: int
    citation_id: int
    interest_id: int
    interest_version_id: int


async def seed(session: AsyncSession, *, briefing_status: str = "normal") -> Seeded:
    user = AppUserRow(handle="maintainer", timezone="Europe/Paris", briefing_hour=7, created_at=NOW)
    source = SourceRow(
        source_key="reddit:python",
        connector="reddit",
        config={"connector": "reddit", "subreddit": "python"},
        is_active=True,
    )
    execution = ExecutionRow(started_at=NOW, anomalies=[])
    session.add_all([user, source, execution])
    await session.flush()

    article = ArticleRow(
        source_id=source.id,
        canonical_url="https://example.com/a",
        linked_page_status="not_applicable",
        excerpt="excerpt",
        excerpt_origin="source",
        title="Title",
        fingerprint="fp",
        published_at=NOW,
        collected_at=NOW,
        embedding=VECTOR,
        embedding_model=MODEL,
    )
    interest = InterestRow(user_id=user.id, created_at=NOW)
    composition = BriefingCompositionRow(
        execution_id=execution.id,
        user_id=user.id,
        briefing_date=date(2026, 10, 14),
        result="normal",
        created_at=NOW,
    )
    conversation = ConversationRow(user_id=user.id, created_at=NOW)
    session.add_all([article, interest, composition, conversation])
    await session.flush()

    version = InterestVersionRow(
        interest_id=interest.id,
        version_no=1,
        change_type="created",
        origin="direct",
        label="Python async",
        description="asyncio and friends",
        weight=1.0,
        embedding=VECTOR,
        embedding_model=MODEL,
        created_at=NOW,
    )
    briefing = BriefingRow(
        user_id=user.id,
        briefing_date=date(2026, 10, 14),
        status=briefing_status,
        failed_source_names=[],
        composition_id=composition.id,
        created_at=NOW,
        updated_at=NOW,
    )
    message = MessageRow(
        conversation_id=conversation.id, role="assistant", content="answer", created_at=NOW
    )
    session.add_all([version, briefing, message])
    await session.flush()

    entry = EntryRow(
        briefing_id=briefing.id,
        user_id=user.id,
        article_id=article.id,
        rank=1,
        title="Title",
        summary="Summary",
        url="https://example.com/a",
        source_name="r/python",
        nature="factual",
        embedding=VECTOR,
        embedding_model=MODEL,
        interest_id=interest.id,
        interest_version_id=version.id,
        interest_label="Python async",
        also_covered_by=[],
    )
    citation = CitationRow(
        message_id=message.id,
        position=1,
        kind="article",
        title="Title",
        url="https://example.com/a",
        source_name="r/python",
        article_id=article.id,
    )
    session.add_all([entry, citation])
    await session.flush()

    return Seeded(
        user_id=user.id,
        article_id=article.id,
        execution_id=execution.id,
        composition_id=composition.id,
        briefing_id=briefing.id,
        entry_id=entry.id,
        citation_id=citation.id,
        interest_id=interest.id,
        interest_version_id=version.id,
    )
