"""RSS ingestion schema (spec 0002): HTTP validators, handle, article uniqueness, purged_article.

Revision ID: a1c2e3f4b5d6
Revises: b8b8b52face8
Create Date: 2026-10-21 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c2e3f4b5d6"
down_revision: str | None = "b8b8b52face8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_LINKED_PAGE_STATUSES = (
    "'not_applicable', 'fetched', 'reused', 'failed', 'timeout', 'too_large', 'blocked_by_robots'"
)
NEW_LINKED_PAGE_STATUSES = (
    "'not_applicable', 'pending', 'fetched', 'reused', 'failed', 'timeout', 'too_large', "
    "'blocked_by_robots'"
)


def _set_linked_page_status_check(values: str) -> None:
    name = op.f("ck_article_linked_page_status_values")
    op.drop_constraint(name, "article", type_="check")
    op.create_check_constraint(name, "article", f"linked_page_status IN ({values})")


def upgrade() -> None:
    op.add_column("source", sa.Column("http_etag", sa.Text(), nullable=True))
    op.add_column("source", sa.Column("http_last_modified", sa.Text(), nullable=True))

    op.add_column("app_user", sa.Column("handle", sa.Text(), nullable=True))
    op.execute("UPDATE app_user SET handle = 'user_' || id")
    op.alter_column("app_user", "handle", nullable=False)
    op.create_unique_constraint(op.f("uq_app_user_handle"), "app_user", ["handle"])
    op.create_check_constraint(
        op.f("ck_app_user_handle_format"), "app_user", "handle ~ '^[a-z0-9_-]{3,32}$'"
    )

    op.drop_index(op.f("ix_article_source_id_fingerprint"), table_name="article")
    op.create_unique_constraint(
        op.f("uq_article_source_id_fingerprint"), "article", ["source_id", "fingerprint"]
    )
    _set_linked_page_status_check(NEW_LINKED_PAGE_STATUSES)

    op.create_table(
        "purged_article",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source.id"],
            name=op.f("fk_purged_article_source_id_source"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purged_article")),
    )
    op.create_index(
        op.f("ix_purged_article_source_id_canonical_url"),
        "purged_article",
        ["source_id", "canonical_url"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purged_article_source_id_fingerprint"),
        "purged_article",
        ["source_id", "fingerprint"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purged_article_purged_at"), "purged_article", ["purged_at"], unique=False
    )


def downgrade() -> None:
    op.drop_table("purged_article")

    op.execute(
        "UPDATE article SET linked_page_status = 'not_applicable' WHERE linked_page_status = 'pending'"
    )
    _set_linked_page_status_check(OLD_LINKED_PAGE_STATUSES)
    op.drop_constraint(op.f("uq_article_source_id_fingerprint"), "article", type_="unique")
    op.create_index(
        op.f("ix_article_source_id_fingerprint"),
        "article",
        ["source_id", "fingerprint"],
        unique=False,
    )

    op.drop_constraint(op.f("ck_app_user_handle_format"), "app_user", type_="check")
    op.drop_constraint(op.f("uq_app_user_handle"), "app_user", type_="unique")
    op.drop_column("app_user", "handle")

    op.drop_column("source", "http_last_modified")
    op.drop_column("source", "http_etag")
