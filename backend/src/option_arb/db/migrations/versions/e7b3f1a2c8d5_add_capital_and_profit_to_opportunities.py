"""add capital_deployed_usd and net_profit_usd to opportunities

Revision ID: e7b3f1a2c8d5
Revises: d1e4a7c9f032
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7b3f1a2c8d5"
down_revision = "d1e4a7c9f032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("capital_deployed_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "opportunities",
        sa.Column("net_profit_usd", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("opportunities", "net_profit_usd")
    op.drop_column("opportunities", "capital_deployed_usd")
