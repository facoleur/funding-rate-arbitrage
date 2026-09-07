"""structured snapshots + lifecycle

Revision ID: ccd09cc5a4d8
Revises: 3a975f04ade8
Create Date: 2026-09-06 18:27:16.283067

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import context, op

revision: str = "ccd09cc5a4d8"
down_revision: str | None = "3a975f04ade8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# lifecycle columns added to structured_opportunities. NOT NULL ones carry a
# server_default so the ALTER works on a populated table; the default is then
# dropped (the app always supplies a value).
_NEW_COLS = [
    ("spot", sa.Float(), True, None),
    ("last_seen_at", sa.DateTime(timezone=True), False, sa.text("now()")),
    ("samples_count", sa.Integer(), False, sa.text("1")),
    ("peak_total_profit_usd", sa.Float(), False, sa.text("0")),
    ("peak_min_profit", sa.Float(), False, sa.text("0")),
    ("closed_at", sa.DateTime(timezone=True), True, None),
    ("close_reason", sqlmodel.sql.sqltypes.AutoString(), True, None),
    ("last_snapshot_at", sa.DateTime(timezone=True), True, None),
    ("last_snapshot_total_profit_usd", sa.Float(), True, None),
]


def upgrade() -> None:
    bind = op.get_bind()

    for name, type_, nullable, server_default in _NEW_COLS:
        op.add_column(
            "structured_opportunities",
            sa.Column(name, type_, nullable=nullable, server_default=server_default),
        )
        if server_default is not None:
            op.alter_column("structured_opportunities", name, server_default=None)

    op.create_index(
        op.f("ix_structured_opportunities_last_seen_at"),
        "structured_opportunities",
        ["last_seen_at"],
        unique=False,
    )

    # The table may already exist if a dev container ran SQLModel.create_all
    # before this migration; only create it when missing.
    table_present = (
        not context.is_offline_mode()
        and "structured_opportunity_snapshots" in sa.inspect(bind).get_table_names()
    )
    if not table_present:
        op.create_table(
            "structured_opportunity_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("opportunity_id", sa.Integer(), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("entry_cost", sa.Float(), nullable=False),
            sa.Column("max_fees", sa.Float(), nullable=False),
            sa.Column("min_profit", sa.Float(), nullable=False),
            sa.Column("max_size", sa.Float(), nullable=False),
            sa.Column("capital_required_usd", sa.Float(), nullable=False),
            sa.Column("max_total_profit_usd", sa.Float(), nullable=False),
            sa.Column("legs", sa.JSON(), nullable=False),
            sa.Column("underlying_price", sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(
                ["opportunity_id"], ["structured_opportunities.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_structured_opportunity_snapshots_opportunity_id"),
            "structured_opportunity_snapshots",
            ["opportunity_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_structured_opportunity_snapshots_ts"),
            "structured_opportunity_snapshots",
            ["ts"],
            unique=False,
        )
        op.create_index(
            "ix_structured_snap_opp_ts",
            "structured_opportunity_snapshots",
            ["opportunity_id", "ts"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("structured_opportunity_snapshots")
    op.drop_index(
        op.f("ix_structured_opportunities_last_seen_at"), table_name="structured_opportunities"
    )
    for name, *_ in reversed(_NEW_COLS):
        op.drop_column("structured_opportunities", name)
    # StructuredStatus.CLOSED left in the enum — Postgres cannot DROP an enum value.
