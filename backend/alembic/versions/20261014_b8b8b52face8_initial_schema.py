"""Initial schema, snapshot guards and the current_interest_version view.

Revision ID: b8b8b52face8
Revises:
Create Date: 2026-10-14 20:12:57.121319
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision: str = "b8b8b52face8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Guarded tables (ADR-0005) and the foreign keys a purge may set to NULL.
GUARDED_TABLES: dict[str, tuple[str, ...]] = {
    "entry": ("article_id",),
    "citation": ("article_id",),
    "briefing_composition": ("execution_id",),
    "interest_version": (),
    "message": (),
    "signal": (),
    "same_event_judgment": (),
    "relevance_score": (),
}

# Compares the whole row as jsonb, so columns added later are protected too. Only allowed
# change: one listed foreign key going from a value to NULL, every other column unchanged
# (ON DELETE SET NULL runs a real UPDATE). vector columns go through their text output.
GUARD_FUNCTION = """
CREATE FUNCTION forbid_snapshot_update() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    old_row jsonb := to_jsonb(OLD);
    new_row jsonb := to_jsonb(NEW);
    fk text;
BEGIN
    FOR i IN 0 .. TG_NARGS - 1 LOOP
        fk := TG_ARGV[i];
        IF old_row ->> fk IS NOT NULL AND new_row ->> fk IS NULL
           AND (new_row - fk) = (old_row - fk) THEN
            RETURN NEW;
        END IF;
    END LOOP;
    RAISE EXCEPTION 'UPDATE refused on guarded table %', TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation',
              HINT = 'snapshot and append-only rows are never updated (ADR-0005)';
END;
$$
"""

CURRENT_INTEREST_VERSION_VIEW = """
CREATE VIEW current_interest_version AS
SELECT DISTINCT ON (iv.interest_id) i.user_id, iv.*
FROM interest_version AS iv
JOIN interest AS i ON i.id = iv.interest_id
WHERE i.deleted_at IS NULL
ORDER BY iv.interest_id, iv.version_no DESC
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("briefing_hour", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "briefing_hour BETWEEN 0 AND 23", name=op.f("ck_app_user_briefing_hour_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
    )
    op.create_table(
        "execution",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("failure_cause", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "anomalies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "failure_cause IN ('technical', 'collection')",
            name=op.f("ck_execution_failure_cause_values"),
        ),
        sa.CheckConstraint(
            "result IN ('success', 'partial', 'failed')", name=op.f("ck_execution_result_values")
        ),
        sa.CheckConstraint(
            "(finished_at IS NULL) = (result IS NULL)",
            name=op.f("ck_execution_finished_iff_result"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution")),
    )
    op.create_table(
        "briefing_composition",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("failure_cause", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "failure_cause IN ('technical', 'collection')",
            name=op.f("ck_briefing_composition_failure_cause_values"),
        ),
        sa.CheckConstraint(
            "result IN ('normal', 'partial', 'failed')",
            name=op.f("ck_briefing_composition_result_values"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["execution.id"],
            name=op.f("fk_briefing_composition_execution_id_execution"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_briefing_composition_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_briefing_composition")),
    )
    op.create_table(
        "conversation",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_conversation_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation")),
    )
    op.create_table(
        "interest",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_interest_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interest")),
    )
    op.create_table(
        "source",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("connector", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deactivation_reason", sa.Text(), nullable=True),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "connector IN ('rss', 'hackernews', 'reddit')", name=op.f("ck_source_connector_values")
        ),
        sa.CheckConstraint(
            "deactivation_reason IN ('maintainer', 'repeated_failures', 'removed_from_catalog')",
            name=op.f("ck_source_deactivation_reason_values"),
        ),
        sa.CheckConstraint(
            "is_active = (deactivation_reason IS NULL)",
            name=op.f("ck_source_active_iff_no_deactivation_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app_user.id"],
            name=op.f("fk_source_owner_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source")),
        sa.UniqueConstraint("source_key", name=op.f("uq_source_source_key")),
    )
    op.create_table(
        "article",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("discussion_url", sa.Text(), nullable=True),
        sa.Column("linked_url", sa.Text(), nullable=True),
        sa.Column("linked_page_status", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_origin", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nature", sa.Text(), nullable=True),
        sa.Column("nature_confidence", sa.REAL(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("embedding", VECTOR(dim=768), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "excerpt_origin IN ('source', 'linked_page', 'both')",
            name=op.f("ck_article_excerpt_origin_values"),
        ),
        sa.CheckConstraint(
            "linked_page_status IN ('not_applicable', 'fetched', 'reused', 'failed', 'timeout', 'too_large', 'blocked_by_robots')",
            name=op.f("ck_article_linked_page_status_values"),
        ),
        sa.CheckConstraint(
            "nature IN ('official', 'factual', 'rumor', 'opinion', 'unknown')",
            name=op.f("ck_article_nature_values"),
        ),
        sa.CheckConstraint(
            "(embedding IS NULL) = (embedding_model IS NULL)",
            name=op.f("ck_article_embedding_has_model"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source.id"],
            name=op.f("fk_article_source_id_source"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_article")),
        sa.UniqueConstraint(
            "source_id", "canonical_url", name=op.f("uq_article_source_id_canonical_url")
        ),
    )
    op.create_index(op.f("ix_article_collected_at"), "article", ["collected_at"], unique=False)
    op.create_index(
        op.f("ix_article_source_id_fingerprint"),
        "article",
        ["source_id", "fingerprint"],
        unique=False,
    )
    op.create_table(
        "briefing",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("synthesis", sa.Text(), nullable=True),
        sa.Column(
            "failed_source_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("composition_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('normal', 'partial', 'failed')", name=op.f("ck_briefing_status_values")
        ),
        sa.ForeignKeyConstraint(
            ["composition_id"],
            ["briefing_composition.id"],
            name=op.f("fk_briefing_composition_id_briefing_composition"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_briefing_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_briefing")),
        sa.UniqueConstraint(
            "user_id", "briefing_date", name=op.f("uq_briefing_user_id_briefing_date")
        ),
    )
    op.create_table(
        "interest_version",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("interest_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("weight", sa.REAL(), nullable=False),
        sa.Column("embedding", VECTOR(dim=768), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "change_type IN ('created', 'updated', 'deleted')",
            name=op.f("ck_interest_version_change_type_values"),
        ),
        sa.CheckConstraint(
            "origin IN ('direct', 'onboarding', 'not_interested')",
            name=op.f("ck_interest_version_origin_values"),
        ),
        sa.CheckConstraint(
            "weight > 0 AND weight <= 1", name=op.f("ck_interest_version_weight_range")
        ),
        sa.ForeignKeyConstraint(
            ["interest_id"],
            ["interest.id"],
            name=op.f("fk_interest_version_interest_id_interest"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interest_version")),
        sa.UniqueConstraint(
            "interest_id", "version_no", name=op.f("uq_interest_version_interest_id_version_no")
        ),
    )
    op.create_table(
        "message",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_message_role_values")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("fk_message_conversation_id_conversation"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message")),
    )
    op.create_table(
        "source_collection",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("article_count", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "result IN ('success', 'failed')", name=op.f("ck_source_collection_result_values")
        ),
        sa.CheckConstraint(
            "(finished_at IS NULL) = (result IS NULL)",
            name=op.f("ck_source_collection_finished_iff_result"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["execution.id"],
            name=op.f("fk_source_collection_execution_id_execution"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source.id"],
            name=op.f("fk_source_collection_source_id_source"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_collection")),
    )
    op.create_table(
        "subscription",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source.id"],
            name=op.f("fk_subscription_source_id_source"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_subscription_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "source_id", name=op.f("pk_subscription")),
    )
    op.create_table(
        "citation",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('article', 'followed_page')", name=op.f("ck_citation_kind_values")
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["article.id"],
            name=op.f("fk_citation_article_id_article"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["message.id"],
            name=op.f("fk_citation_message_id_message"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_citation")),
    )
    op.create_table(
        "entry",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("briefing_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=True),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("nature", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(dim=768), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("interest_id", sa.BigInteger(), nullable=False),
        sa.Column("interest_version_id", sa.BigInteger(), nullable=False),
        sa.Column("interest_label", sa.Text(), nullable=False),
        sa.Column(
            "also_covered_by",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "nature IN ('official', 'factual', 'rumor', 'opinion', 'unknown')",
            name=op.f("ck_entry_nature_values"),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["article.id"],
            name=op.f("fk_entry_article_id_article"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["briefing_id"],
            ["briefing.id"],
            name=op.f("fk_entry_briefing_id_briefing"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interest_id"], ["interest.id"], name=op.f("fk_entry_interest_id_interest")
        ),
        sa.ForeignKeyConstraint(
            ["interest_version_id"],
            ["interest_version.id"],
            name=op.f("fk_entry_interest_version_id_interest_version"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_entry_user_id_app_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entry")),
        sa.UniqueConstraint("briefing_id", "rank", name=op.f("uq_entry_briefing_id_rank")),
    )
    op.create_index(
        "uq_entry_user_id_article_id",
        "entry",
        ["user_id", "article_id"],
        unique=True,
        postgresql_where=sa.text("article_id IS NOT NULL"),
    )
    op.create_table(
        "relevance_score",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("interest_version_id", sa.BigInteger(), nullable=False),
        sa.Column("similarity", sa.REAL(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["article.id"],
            name=op.f("fk_relevance_score_article_id_article"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interest_version_id"],
            ["interest_version.id"],
            name=op.f("fk_relevance_score_interest_version_id_interest_version"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_relevance_score_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "article_id", "interest_version_id", name=op.f("pk_relevance_score")
        ),
    )
    op.create_table(
        "same_event_judgment",
        sa.Column("article_a_id", sa.BigInteger(), nullable=False),
        sa.Column("article_b_id", sa.BigInteger(), nullable=False),
        sa.Column("same_event", sa.Boolean(), nullable=False),
        sa.Column("probability", sa.REAL(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("judged_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "article_a_id < article_b_id", name=op.f("ck_same_event_judgment_ordered_pair")
        ),
        sa.ForeignKeyConstraint(
            ["article_a_id"],
            ["article.id"],
            name=op.f("fk_same_event_judgment_article_a_id_article"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["article_b_id"],
            ["article.id"],
            name=op.f("fk_same_event_judgment_article_b_id_article"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "article_a_id", "article_b_id", name=op.f("pk_same_event_judgment")
        ),
    )
    op.create_table(
        "signal",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('opened', 'not_interested')", name=op.f("ck_signal_kind_values")
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entry.id"], name=op.f("fk_signal_entry_id_entry"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_signal_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal")),
        sa.UniqueConstraint("entry_id", "kind", name=op.f("uq_signal_entry_id_kind")),
    )

    op.execute(GUARD_FUNCTION)
    for table, nullable_fks in GUARDED_TABLES.items():
        args = ", ".join(f"'{fk}'" for fk in nullable_fks)
        op.execute(
            f"CREATE TRIGGER {table}_guard BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION forbid_snapshot_update({args})"
        )
    # A failed Briefing is replaced in place; any other is final.
    op.execute(
        "CREATE TRIGGER briefing_guard BEFORE UPDATE ON briefing "
        "FOR EACH ROW WHEN (OLD.status <> 'failed') EXECUTE FUNCTION forbid_snapshot_update()"
    )
    op.execute(CURRENT_INTEREST_VERSION_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW current_interest_version")
    op.drop_table("signal")
    op.drop_table("same_event_judgment")
    op.drop_table("relevance_score")
    op.drop_index(
        "uq_entry_user_id_article_id",
        table_name="entry",
        postgresql_where=sa.text("article_id IS NOT NULL"),
    )
    op.drop_table("entry")
    op.drop_table("citation")
    op.drop_table("subscription")
    op.drop_table("source_collection")
    op.drop_table("message")
    op.drop_table("interest_version")
    op.drop_table("briefing")
    op.drop_index(op.f("ix_article_source_id_fingerprint"), table_name="article")
    op.drop_index(op.f("ix_article_collected_at"), table_name="article")
    op.drop_table("article")
    op.drop_table("source")
    op.drop_table("interest")
    op.drop_table("conversation")
    op.drop_table("briefing_composition")
    op.drop_table("execution")
    op.drop_table("app_user")
    op.execute("DROP FUNCTION forbid_snapshot_update()")
