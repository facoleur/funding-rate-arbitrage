from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Mode(StrEnum):
    LIVE = "live"
    PAPER = "paper"
    BACKTEST = "backtest"


class OpportunityStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"


class TradeStatus(StrEnum):
    PLACING = "PLACING"
    LEG1_FILLED = "LEG1_FILLED"
    LEG2_FILLED = "LEG2_FILLED"
    FILLED = "FILLED"
    HEDGING = "HEDGING"
    HEDGED = "HEDGED"
    STUCK = "STUCK"
    FAILED = "FAILED"


class OrderStatus(StrEnum):
    PLACING = "PLACING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class OrderKind(StrEnum):
    IOC_LIMIT = "ioc_limit"
    MARKET_OUT = "market_out"


class StrategyType(StrEnum):
    BOX = "BOX"  # BULL_CALL / BEAR_PUT / BUTTERFLY_NEG viendront ensuite


class LiveStatus(StrEnum):
    """Liveness of a screened opportunity — whether the screener still detects it.

    Orthogonal to the executor workflow (`OpportunityStatus`) on the 1:1
    `opportunities` table, and the sole status on `structured_opportunities`.
    Owned by the screeners; never written by the executor.
    """

    LIVE = "LIVE"
    STALE = "STALE"  # no longer detected for `close_after_stale_sec`
    EXPIRED = "EXPIRED"  # instrument expiry passed


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class WsStatus(StrEnum):
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    UNHEALTHY = "UNHEALTHY"


class RestStatus(StrEnum):
    OK = "OK"
    RATE_LIMITED = "RATE_LIMITED"
    DOWN = "DOWN"


class AlertLevel(StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class Opportunity(SQLModel, table=True):
    __tablename__ = "opportunities"

    id: int | None = Field(default=None, primary_key=True)
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    mode: Mode
    instrument: str = Field(index=True)
    symbol: str = Field(index=True)
    expiry: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    strike: float
    option_type: str  # "C" | "P"
    buy_from: str
    sell_to: str

    top_ask: float
    top_bid: float

    walked_ask: float | None = None
    walked_bid: float | None = None

    network: str = "mainnet"  # "mainnet" | "testnet"

    tradeable_size: float
    buy_premium_usd: float
    sell_premium_usd: float
    estimated_short_margin_usd: float
    capital_required_usd: float
    gross_profit_usd: float
    fees_usd: float
    net_profit_usd: float
    price_spread_pct: float
    net_return_pct: float
    apr_pct: float

    # Fresh executor approval uses worst IOC limits, separate from screener economics.
    verified_buy_limit: float | None = None
    verified_sell_limit: float | None = None
    verified_tradeable_size: float | None = None
    verified_buy_premium_usd: float | None = None
    verified_sell_premium_usd: float | None = None
    verified_estimated_short_margin_usd: float | None = None
    verified_capital_required_usd: float | None = None
    verified_gross_profit_usd: float | None = None
    verified_fees_usd: float | None = None
    verified_net_profit_usd: float | None = None
    verified_net_return_pct: float | None = None
    verified_apr_pct: float | None = None

    # Executor workflow state (PENDING → APPROVED/REJECTED/EXECUTED). Owned by the executor.
    status: OpportunityStatus = Field(default=OpportunityStatus.PENDING, index=True)
    rejection_reason: str | None = None

    # --- liveness + evolution history (owned by the screener, orthogonal to `status`) ---
    live_status: LiveStatus = Field(default=LiveStatus.LIVE, index=True)
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    samples_count: int = 1
    peak_net_profit_usd: float = 0.0
    peak_apr_pct: float = 0.0
    closed_at: datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True)
    )
    close_reason: str | None = None  # "stale" | "expired"
    last_snapshot_at: datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True)
    )
    last_snapshot_net_profit_usd: float | None = None


class OpportunitySnapshot(SQLModel, table=True):
    """Time series of a 1:1 cross-exchange `Opportunity`'s economics — one row
    each time `net_profit_usd` moves materially or `snapshot_min_interval_sec`
    elapses. Powers the decay + leg-convergence charts in the detail view."""

    __tablename__ = "opportunity_snapshots"
    __table_args__ = (sa.Index("ix_opportunity_snap_opp_ts", "opportunity_id", "ts"),)

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    ts: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    top_ask: float  # buy-leg quote on `buy_from` at this instant
    top_bid: float  # sell-leg quote on `sell_to` at this instant
    tradeable_size: float
    buy_premium_usd: float
    sell_premium_usd: float
    capital_required_usd: float
    fees_usd: float
    net_profit_usd: float
    net_return_pct: float
    apr_pct: float
    price_spread_pct: float
    underlying_price: float | None = None


class Trade(SQLModel, table=True):
    __tablename__ = "trades"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunities.id", index=True)
    opened_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    closed_at: datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True)
    )
    mode: Mode
    status: TradeStatus = Field(index=True)

    buy_exchange: str
    sell_exchange: str
    requested_size: float

    buy_fill_price: float | None = None
    buy_fill_size: float | None = None
    sell_fill_price: float | None = None
    sell_fill_size: float | None = None

    net_pnl_usd: float | None = None
    slippage_pct: float | None = None
    fees_usd: float | None = None
    error: str | None = None


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: int | None = Field(default=None, primary_key=True)
    trade_id: int = Field(foreign_key="trades.id", index=True)
    exchange: str
    side: Side
    kind: OrderKind
    requested_price: float
    requested_size: float
    filled_price: float | None = None
    filled_size: float | None = None
    status: OrderStatus
    exchange_order_id: str | None = None
    placed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    raw_response: str | None = None


class Position(SQLModel, table=True):
    __tablename__ = "positions"

    id: int | None = Field(default=None, primary_key=True)
    exchange: str = Field(index=True)
    instrument: str = Field(index=True)
    size: float
    avg_price: float
    opened_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )


class ExchangeState(SQLModel, table=True):
    __tablename__ = "exchange_state"

    exchange: str = Field(primary_key=True)
    balance_usd: float = 0.0
    balances: dict[str, float] = Field(
        default_factory=dict,
        sa_column=sa.Column(sa.JSON, nullable=False, server_default="{}"),
    )
    margin_used_usd: float = 0.0
    ws_status: WsStatus = WsStatus.RECONNECTING
    rest_status: RestStatus = RestStatus.OK
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: int | None = Field(default=None, primary_key=True)
    level: AlertLevel = Field(index=True)
    channel: str
    message: str
    sent_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    meta: str | None = None  # JSON string


class TickerState(SQLModel, table=True):
    __tablename__ = "ticker_state"

    exchange: str = Field(primary_key=True)
    instrument: str = Field(primary_key=True)  # normalized_name
    underlying: str
    expiry: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    strike: float
    option_type: str  # "C" | "P"
    bid_price: float | None = None
    bid_size: float | None = None
    ask_price: float | None = None
    ask_size: float | None = None
    underlying_price: float | None = None
    taker_fee_rate: float
    updated_at: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))


class BookSnapshot(SQLModel, table=True):
    __tablename__ = "book_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    exchange: str = Field(index=True)
    instrument: str = Field(index=True)
    ts: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    )
    underlying_price: float | None = None
    bids_json: str
    asks_json: str


class StructuredOpportunity(SQLModel, table=True):
    """Multi-leg structured arb (box spread for now). Written by the standalone
    `StructuredScreener` in the `workers` container; never touched by the 1:1
    screener or the executor. `strikes` / `legs` use `sa.JSON` (not JSONB/ARRAY)
    so the same model runs under SQLite in pytest."""

    __tablename__ = "structured_opportunities"
    __table_args__ = (
        sa.Index("ix_structured_status_detected", "live_status", "detected_at"),
        sa.Index("ix_structured_underlying_expiry_type", "underlying", "expiry", "strategy_type"),
    )

    id: int | None = Field(default=None, primary_key=True)

    strategy_type: StrategyType = Field(index=True)
    underlying: str = Field(index=True)
    expiry: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    # [K1, K2] ascending
    strikes: list[float] = Field(sa_column=sa.Column(sa.JSON, nullable=False))
    # 4 entries: {exchange, instrument, side: "buy"|"sell", price, qty, taker_fee_rate}
    legs: list[dict[str, Any]] = Field(sa_column=sa.Column(sa.JSON, nullable=False))

    is_fixed_payoff: bool  # True only when all 4 legs on the same exchange
    settlement_risk: bool  # True when venues mix settlement classes (deribit inverse vs linear)

    min_payoff: float  # box: both == K2 - K1
    max_payoff: float

    entry_cost: float  # net debit per unit (negative = credit)
    max_fees: float  # per unit, sum of the 4 legs

    min_profit: float  # per unit: width - entry_cost - max_fees
    max_profit: float

    max_size: float  # capped by the least-liquid leg
    capital_required_usd: float  # max(entry_cost, 0) * max_size
    max_total_profit_usd: float  # min_profit * max_size

    spot: float | None = None  # underlying price at the latest snapshot

    mode: Mode
    network: str = "mainnet"

    detected_at: datetime = Field(  # first seen
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    # --- lifecycle (Phase 2) ---
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    samples_count: int = 1
    peak_total_profit_usd: float = 0.0  # max of max_total_profit_usd over life
    peak_min_profit: float = 0.0  # max edge/unit over life
    closed_at: datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True)
    )
    close_reason: str | None = None  # "stale" | "expired"
    # denormalized to decide, without a query, whether a new snapshot is due
    last_snapshot_at: datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True)
    )
    last_snapshot_total_profit_usd: float | None = None

    live_status: LiveStatus = Field(default=LiveStatus.LIVE, index=True)


class StructuredOpportunitySnapshot(SQLModel, table=True):
    """Time series of a `StructuredOpportunity`'s economics — one row each time
    the edge moves materially or `snapshot_min_interval_sec` elapses. Powers the
    decay chart + payoff-diagram scrubber in the detail view."""

    __tablename__ = "structured_opportunity_snapshots"
    __table_args__ = (sa.Index("ix_structured_snap_opp_ts", "opportunity_id", "ts"),)

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("structured_opportunities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    ts: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )
    entry_cost: float
    max_fees: float
    min_profit: float  # edge / unit at this instant
    max_size: float
    capital_required_usd: float
    max_total_profit_usd: float
    legs: list[dict[str, Any]] = Field(sa_column=sa.Column(sa.JSON, nullable=False))
    underlying_price: float | None = None
