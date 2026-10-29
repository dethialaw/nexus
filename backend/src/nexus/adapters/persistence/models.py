"""ORM models of every table in `docs/data-model.md`.

They never leave this adapter: repositories map them to core dataclasses.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexus.adapters.persistence.base import Base, values_check
from nexus.adapters.persistence.types import Vector
from nexus.core.conversation.entities import CitationKind, MessageRole
from nexus.core.delivery.entities import BriefingStatus, CompositionResult
from nexus.core.ingestion.entities import (
    CollectionResult,
    Connector,
    DeactivationReason,
    ExcerptOrigin,
    ExecutionResult,
    FailureCause,
    LinkedPageStatus,
)
from nexus.core.profile.entities import ChangeType, InterestOrigin, SignalKind
from nexus.core.qualification.entities import Nature

Timestamp = DateTime(timezone=True)
EMPTY_JSON_ARRAY = text("'[]'::jsonb")


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def _fk(target: str, ondelete: str | None = None, **kwargs: Any) -> Any:
    return mapped_column(BigInteger, ForeignKey(target, ondelete=ondelete), **kwargs)


# --- Common content -------------------------------------------------------------------------


class SourceRow(Base):
    __tablename__ = "source"
    __table_args__ = (
        values_check("connector", Connector),
        values_check("deactivation_reason", DeactivationReason),
        CheckConstraint(
            "is_active = (deactivation_reason IS NULL)", name="active_iff_no_deactivation_reason"
        ),
    )

    id: Mapped[int] = _id()
    source_key: Mapped[str] = mapped_column(Text, unique=True)
    connector: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    owner_user_id: Mapped[int | None] = _fk("app_user.id", ondelete="RESTRICT")
    is_active: Mapped[bool]
    deactivation_reason: Mapped[str | None] = mapped_column(Text)
    last_collected_at: Mapped[datetime | None] = mapped_column(Timestamp)
    http_etag: Mapped[str | None] = mapped_column(Text)
    http_last_modified: Mapped[str | None] = mapped_column(Text)
    reactivated_at: Mapped[datetime | None] = mapped_column(Timestamp)


class ArticleRow(Base):
    __tablename__ = "article"
    __table_args__ = (
        UniqueConstraint("source_id", "canonical_url"),
        UniqueConstraint("source_id", "fingerprint"),
        Index(None, "collected_at"),
        values_check("linked_page_status", LinkedPageStatus),
        values_check("excerpt_origin", ExcerptOrigin),
        values_check("nature", Nature),
        CheckConstraint(
            "(embedding IS NULL) = (embedding_model IS NULL)", name="embedding_has_model"
        ),
    )

    id: Mapped[int] = _id()
    source_id: Mapped[int] = _fk("source.id", ondelete="RESTRICT")
    canonical_url: Mapped[str] = mapped_column(Text)
    discussion_url: Mapped[str | None] = mapped_column(Text)
    linked_url: Mapped[str | None] = mapped_column(Text)
    linked_page_status: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    excerpt_origin: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(Timestamp)
    collected_at: Mapped[datetime] = mapped_column(Timestamp)
    nature: Mapped[str | None] = mapped_column(Text)
    nature_confidence: Mapped[float | None] = mapped_column(REAL)
    summary: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[tuple[float, ...] | None] = mapped_column(Vector)
    embedding_model: Mapped[str | None] = mapped_column(Text)


class PurgedArticleRow(Base):
    __tablename__ = "purged_article"
    __table_args__ = (
        Index(None, "source_id", "canonical_url"),
        Index(None, "source_id", "fingerprint"),
        Index(None, "purged_at"),
    )

    id: Mapped[int] = _id()
    source_id: Mapped[int] = _fk("source.id", ondelete="RESTRICT")
    canonical_url: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(Text)
    purged_at: Mapped[datetime] = mapped_column(Timestamp)


class SameEventJudgmentRow(Base):
    __tablename__ = "same_event_judgment"
    __table_args__ = (CheckConstraint("article_a_id < article_b_id", name="ordered_pair"),)

    article_a_id: Mapped[int] = _fk("article.id", ondelete="CASCADE", primary_key=True)
    article_b_id: Mapped[int] = _fk("article.id", ondelete="CASCADE", primary_key=True)
    same_event: Mapped[bool]
    probability: Mapped[float] = mapped_column(REAL)
    model: Mapped[str] = mapped_column(Text)
    judged_at: Mapped[datetime] = mapped_column(Timestamp)


# --- Profile --------------------------------------------------------------------------------


class AppUserRow(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint("briefing_hour BETWEEN 0 AND 23", name="briefing_hour_range"),
        CheckConstraint("handle ~ '^[a-z0-9_-]{3,32}$'", name="handle_format"),
    )

    id: Mapped[int] = _id()
    handle: Mapped[str] = mapped_column(Text, unique=True)
    timezone: Mapped[str] = mapped_column(Text)
    briefing_hour: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class SubscriptionRow(Base):
    __tablename__ = "subscription"

    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE", primary_key=True)
    source_id: Mapped[int] = _fk("source.id", ondelete="RESTRICT", primary_key=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class InterestRow(Base):
    __tablename__ = "interest"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE")
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    deleted_at: Mapped[datetime | None] = mapped_column(Timestamp)


class InterestVersionRow(Base):
    __tablename__ = "interest_version"
    __table_args__ = (
        UniqueConstraint("interest_id", "version_no"),
        values_check("change_type", ChangeType),
        values_check("origin", InterestOrigin),
        CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"),
    )

    id: Mapped[int] = _id()
    interest_id: Mapped[int] = _fk("interest.id", ondelete="CASCADE")
    version_no: Mapped[int] = mapped_column(Integer)
    change_type: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(REAL)
    embedding: Mapped[tuple[float, ...]] = mapped_column(Vector)
    embedding_model: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class RelevanceScoreRow(Base):
    __tablename__ = "relevance_score"

    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE", primary_key=True)
    article_id: Mapped[int] = _fk("article.id", ondelete="CASCADE", primary_key=True)
    interest_version_id: Mapped[int] = _fk(
        "interest_version.id", ondelete="CASCADE", primary_key=True
    )
    similarity: Mapped[float] = mapped_column(REAL)
    score: Mapped[float] = mapped_column(REAL)


# --- Execution and delivery -----------------------------------------------------------------


class ExecutionRow(Base):
    __tablename__ = "execution"
    __table_args__ = (
        values_check("result", ExecutionResult),
        values_check("failure_cause", FailureCause),
        CheckConstraint("(finished_at IS NULL) = (result IS NULL)", name="finished_iff_result"),
    )

    id: Mapped[int] = _id()
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp)
    result: Mapped[str | None] = mapped_column(Text)
    failure_cause: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    anomalies: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=EMPTY_JSON_ARRAY)


class SourceCollectionRow(Base):
    __tablename__ = "source_collection"
    __table_args__ = (
        values_check("result", CollectionResult),
        CheckConstraint("(finished_at IS NULL) = (result IS NULL)", name="finished_iff_result"),
    )

    id: Mapped[int] = _id()
    execution_id: Mapped[int] = _fk("execution.id", ondelete="CASCADE")
    source_id: Mapped[int] = _fk("source.id", ondelete="RESTRICT")
    result: Mapped[str | None] = mapped_column(Text)
    article_count: Mapped[int | None] = mapped_column(Integer)
    unreadable_count: Mapped[int] = mapped_column(Integer, server_default="0")
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp)


class BriefingCompositionRow(Base):
    __tablename__ = "briefing_composition"
    __table_args__ = (
        values_check("result", CompositionResult),
        values_check("failure_cause", FailureCause),
    )

    id: Mapped[int] = _id()
    execution_id: Mapped[int | None] = _fk("execution.id", ondelete="SET NULL")
    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE")
    briefing_date: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(Text)
    failure_cause: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class BriefingRow(Base):
    __tablename__ = "briefing"
    __table_args__ = (
        UniqueConstraint("user_id", "briefing_date"),
        values_check("status", BriefingStatus),
    )

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE")
    briefing_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text)
    synthesis: Mapped[str | None] = mapped_column(Text)
    failed_source_names: Mapped[list[str]] = mapped_column(JSONB, server_default=EMPTY_JSON_ARRAY)
    composition_id: Mapped[int] = _fk("briefing_composition.id")
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class EntryRow(Base):
    __tablename__ = "entry"
    __table_args__ = (
        UniqueConstraint("briefing_id", "rank"),
        Index(
            "uq_entry_user_id_article_id",
            "user_id",
            "article_id",
            unique=True,
            postgresql_where=text("article_id IS NOT NULL"),
        ),
        values_check("nature", Nature),
    )

    id: Mapped[int] = _id()
    briefing_id: Mapped[int] = _fk("briefing.id", ondelete="CASCADE")
    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE")
    article_id: Mapped[int | None] = _fk("article.id", ondelete="SET NULL")
    rank: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(Text)
    nature: Mapped[str] = mapped_column(Text)
    embedding: Mapped[tuple[float, ...]] = mapped_column(Vector)
    embedding_model: Mapped[str] = mapped_column(Text)
    interest_id: Mapped[int] = _fk("interest.id")
    interest_version_id: Mapped[int] = _fk("interest_version.id")
    interest_label: Mapped[str] = mapped_column(Text)
    also_covered_by: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, server_default=EMPTY_JSON_ARRAY
    )


class SignalRow(Base):
    __tablename__ = "signal"
    __table_args__ = (UniqueConstraint("entry_id", "kind"), values_check("kind", SignalKind))

    id: Mapped[int] = _id()
    entry_id: Mapped[int] = _fk("entry.id", ondelete="CASCADE")
    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


# --- Conversation ---------------------------------------------------------------------------


class ConversationRow(Base):
    __tablename__ = "conversation"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _fk("app_user.id", ondelete="CASCADE")
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class MessageRow(Base):
    __tablename__ = "message"
    __table_args__ = (values_check("role", MessageRole),)

    id: Mapped[int] = _id()
    conversation_id: Mapped[int] = _fk("conversation.id", ondelete="CASCADE")
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class CitationRow(Base):
    __tablename__ = "citation"
    __table_args__ = (values_check("kind", CitationKind),)

    id: Mapped[int] = _id()
    message_id: Mapped[int] = _fk("message.id", ondelete="CASCADE")
    position: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(Text)
    article_id: Mapped[int | None] = _fk("article.id", ondelete="SET NULL")
