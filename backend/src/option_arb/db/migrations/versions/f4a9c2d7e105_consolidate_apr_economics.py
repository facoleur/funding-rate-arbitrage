"""consolidate APR economics

Revision ID: f4a9c2d7e105
Revises: e7b3f1a2c8d5
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4a9c2d7e105"
down_revision = "e7b3f1a2c8d5"
branch_labels = None
depends_on = None

_NEW_REQUIRED = (
    "tradeable_size",
    "buy_premium_usd",
    "sell_premium_usd",
    "estimated_short_margin_usd",
    "capital_required_usd",
    "gross_profit_usd",
    "fees_usd",
    "net_profit_usd",
    "price_spread_pct",
    "net_return_pct",
    "apr_pct",
)
_NEW_VERIFIED = (
    "verified_buy_limit",
    "verified_sell_limit",
    "verified_tradeable_size",
    "verified_buy_premium_usd",
    "verified_sell_premium_usd",
    "verified_estimated_short_margin_usd",
    "verified_capital_required_usd",
    "verified_gross_profit_usd",
    "verified_fees_usd",
    "verified_net_profit_usd",
    "verified_net_return_pct",
    "verified_apr_pct",
)


def upgrade() -> None:
    # Old margin-only/per-unit rows cannot be converted into the new total semantics.
    op.execute(sa.text("DELETE FROM orders"))
    op.execute(sa.text("DELETE FROM trades"))
    op.execute(sa.text("DELETE FROM opportunities"))

    op.add_column("book_snapshots", sa.Column("underlying_price", sa.Float(), nullable=True))

    for column in (
        "walked_size",
        "spread_pct",
        "fee_pct",
        "apr_pct",
        "max_notional_usd",
        "capital_deployed_usd",
        "net_profit_usd",
    ):
        op.drop_column("opportunities", column)
    for column in _NEW_REQUIRED:
        op.add_column("opportunities", sa.Column(column, sa.Float(), nullable=False))
    for column in _NEW_VERIFIED:
        op.add_column("opportunities", sa.Column(column, sa.Float(), nullable=True))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM orders"))
    op.execute(sa.text("DELETE FROM trades"))
    op.execute(sa.text("DELETE FROM opportunities"))

    for column in _NEW_VERIFIED:
        op.drop_column("opportunities", column)
    for column in _NEW_REQUIRED:
        op.drop_column("opportunities", column)
    op.add_column("opportunities", sa.Column("walked_size", sa.Float(), nullable=True))
    op.add_column("opportunities", sa.Column("spread_pct", sa.Float(), nullable=False))
    op.add_column(
        "opportunities", sa.Column("fee_pct", sa.Float(), nullable=False, server_default="0")
    )
    op.add_column("opportunities", sa.Column("apr_pct", sa.Float(), nullable=False))
    op.add_column("opportunities", sa.Column("max_notional_usd", sa.Float(), nullable=False))
    op.add_column(
        "opportunities",
        sa.Column("capital_deployed_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "opportunities",
        sa.Column("net_profit_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.drop_column("book_snapshots", "underlying_price")
