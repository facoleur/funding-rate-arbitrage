"""add_fee_pct_to_opportunities

Revision ID: c3e8f92d4b17
Revises: a6f0281b121d
Create Date: 2026-07-23 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3e8f92d4b17"
down_revision: str | None = "a6f0281b121d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("fee_pct", sa.Float(), server_default="0.0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("opportunities", "fee_pct")
