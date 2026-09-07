"""opportunity snapshots + liveness

Revision ID: aeaaf127bb20
Revises: ccd09cc5a4d8
Create Date: 2026-09-06 19:26:15.954927

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "aeaaf127bb20"
down_revision: str | None = "ccd09cc5a4d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Shared with structured_opportunities. `checkfirst=True` → created here only if
# the structured migration didn't already.
_live_status = postgresql.ENUM("LIVE", "STALE", "EXPIRED", name="livestatus", create_type=False)

# NOT NULL columns carry a server_default so the ALTER works on the populated
# `opportunities` table; the default is then dropped (the app always supplies one).
_NEW_COLS = [
    ("live_status", _live_status, False, sa.text("'LIVE'")),
    ("last_seen_at", sa.DateTime(timezone=True), False, sa.text("now()")),
    ("samples_count", sa.Integer(), False, sa.text("1")),
    ("peak_net_profit_usd", sa.Float(), False, sa.text("0")),
    ("peak_apr_pct", sa.Float(), False, sa.text("0")),
    ("closed_at", sa.DateTime(timezone=True), True, None),
    ("close_reason", sqlmodel.sql.sqltypes.AutoString(), True, None),
    ("last_snapshot_at", sa.DateTime(timezone=True), True, None),
    ("last_snapshot_net_profit_usd", sa.Float(), True, None),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _live_status.create(bind, checkfirst=True)

    for name, type_, nullable, server_default in _NEW_COLS:
        op.add_column(
            "opportunities",
            sa.Column(name, type_, nullable=nullable, server_default=server_default),
        )
        if server_default is not None:
            op.alter_column("opportunities", name, server_default=None)

    op.create_index(
        op.f("ix_opportunities_live_status"), "opportunities", ["live_status"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_last_seen_at"), "opportunities", ["last_seen_at"], unique=False
    )

    # A dev container may have run SQLModel.create_all before / racing this
    # migration; only create the table when it is actually missing.
    table_present = (
        not context.is_offline_mode()
        and "opportunity_snapshots" in sa.inspect(bind).get_table_names()
    )
    if not table_present:
        op.create_table(
            "opportunity_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("opportunity_id", sa.Integer(), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("top_ask", sa.Float(), nullable=False),
            sa.Column("top_bid", sa.Float(), nullable=False),
            sa.Column("tradeable_size", sa.Float(), nullable=False),
            sa.Column("buy_premium_usd", sa.Float(), nullable=False),
            sa.Column("sell_premium_usd", sa.Float(), nullable=False),
            sa.Column("capital_required_usd", sa.Float(), nullable=False),
            sa.Column("fees_usd", sa.Float(), nullable=False),
            sa.Column("net_profit_usd", sa.Float(), nullable=False),
            sa.Column("net_return_pct", sa.Float(), nullable=False),
            sa.Column("apr_pct", sa.Float(), nullable=False),
            sa.Column("price_spread_pct", sa.Float(), nullable=False),
            sa.Column("underlying_price", sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_opportunity_snapshots_opportunity_id"),
            "opportunity_snapshots",
            ["opportunity_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_opportunity_snapshots_ts"), "opportunity_snapshots", ["ts"], unique=False
        )
        op.create_index(
            "ix_opportunity_snap_opp_ts",
            "opportunity_snapshots",
            ["opportunity_id", "ts"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("opportunity_snapshots")
    op.drop_index(op.f("ix_opportunities_last_seen_at"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_live_status"), table_name="opportunities")
    for name, *_ in reversed(_NEW_COLS):
        op.drop_column("opportunities", name)
    # `livestatus` type is shared with structured_opportunities — left in place.
