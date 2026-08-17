"""add network to opportunities

Revision ID: d1e4a7c9f032
Revises: c3e8f92d4b17
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d1e4a7c9f032"
down_revision = "c3e8f92d4b17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("network", sa.String(), nullable=False, server_default="testnet"),
    )
    # All existing rows are testnet data — purge them.
    op.execute("DELETE FROM opportunities WHERE network = 'testnet'")


def downgrade() -> None:
    op.drop_column("opportunities", "network")
