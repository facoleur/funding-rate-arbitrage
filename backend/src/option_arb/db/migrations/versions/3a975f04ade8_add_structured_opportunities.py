"""add structured_opportunities

Revision ID: 3a975f04ade8
Revises: f4a9c2d7e105
Create Date: 2026-09-06 00:51:27.995240

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3a975f04ade8"
down_revision: str | None = "f4a9c2d7e105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New PG enum types this migration owns. `mode` already exists (initial schema)
# so it is referenced with create_type=False below. `livestatus` is shared with
# the 1:1 `opportunities` table — whichever migration runs first creates it
# (checkfirst=True makes both idempotent).
_strategy_type = postgresql.ENUM("BOX", name="strategytype", create_type=False)
_live_status = postgresql.ENUM("LIVE", "STALE", "EXPIRED", name="livestatus", create_type=False)
# `mode` is owned by the initial schema — reference only, never re-create.
_mode = postgresql.ENUM("LIVE", "PAPER", "BACKTEST", name="mode", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _strategy_type.create(bind, checkfirst=True)
        _live_status.create(bind, checkfirst=True)

    op.create_table(
        "structured_opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_type", _strategy_type, nullable=False),
        sa.Column("underlying", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strikes", sa.JSON(), nullable=False),
        sa.Column("legs", sa.JSON(), nullable=False),
        sa.Column("is_fixed_payoff", sa.Boolean(), nullable=False),
        sa.Column("settlement_risk", sa.Boolean(), nullable=False),
        sa.Column("min_payoff", sa.Float(), nullable=False),
        sa.Column("max_payoff", sa.Float(), nullable=False),
        sa.Column("entry_cost", sa.Float(), nullable=False),
        sa.Column("max_fees", sa.Float(), nullable=False),
        sa.Column("min_profit", sa.Float(), nullable=False),
        sa.Column("max_profit", sa.Float(), nullable=False),
        sa.Column("max_size", sa.Float(), nullable=False),
        sa.Column("capital_required_usd", sa.Float(), nullable=False),
        sa.Column("max_total_profit_usd", sa.Float(), nullable=False),
        sa.Column("mode", _mode, nullable=False),
        sa.Column("network", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_status", _live_status, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_structured_opportunities_detected_at"),
        "structured_opportunities",
        ["detected_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_structured_opportunities_live_status"),
        "structured_opportunities",
        ["live_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_structured_opportunities_strategy_type"),
        "structured_opportunities",
        ["strategy_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_structured_opportunities_underlying"),
        "structured_opportunities",
        ["underlying"],
        unique=False,
    )
    op.create_index(
        "ix_structured_status_detected",
        "structured_opportunities",
        ["live_status", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_structured_underlying_expiry_type",
        "structured_opportunities",
        ["underlying", "expiry", "strategy_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_structured_underlying_expiry_type", table_name="structured_opportunities")
    op.drop_index("ix_structured_status_detected", table_name="structured_opportunities")
    op.drop_index(
        op.f("ix_structured_opportunities_underlying"), table_name="structured_opportunities"
    )
    op.drop_index(
        op.f("ix_structured_opportunities_strategy_type"), table_name="structured_opportunities"
    )
    op.drop_index(
        op.f("ix_structured_opportunities_live_status"), table_name="structured_opportunities"
    )
    op.drop_index(
        op.f("ix_structured_opportunities_detected_at"), table_name="structured_opportunities"
    )
    op.drop_table("structured_opportunities")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _live_status.drop(bind, checkfirst=True)
        _strategy_type.drop(bind, checkfirst=True)
