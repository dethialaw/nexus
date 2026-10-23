"""Unreadable item count of a Collection (spec 0002).

Revision ID: c3d4e5f6a7b8
Revises: a1c2e3f4b5d6
Create Date: 2026-10-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a1c2e3f4b5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_collection",
        sa.Column("unreadable_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("source_collection", "unreadable_count")
