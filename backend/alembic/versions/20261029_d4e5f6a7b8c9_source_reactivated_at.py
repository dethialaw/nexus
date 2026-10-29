"""Date of the last reactivation of a Source (spec 0002, #46).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source", sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("source", "reactivated_at")
