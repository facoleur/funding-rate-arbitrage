from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

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
    walked_size: float | None = None

    spread_pct: float
    apr_pct: float
    max_notional_usd: float

    status: OpportunityStatus = Field(default=OpportunityStatus.PENDING, index=True)
    rejection_reason: str | None = None


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
    bids_json: str
    asks_json: str
