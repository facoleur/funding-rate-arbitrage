from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, WithJsonSchema

from option_arb.config import Network
from option_arb.db.models import (
    AlertLevel,
    Mode,
    OpportunityStatus,
    OrderKind,
    OrderStatus,
    RestStatus,
    Side,
    TradeStatus,
    WsStatus,
)


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat()


type IsoDatetime = Annotated[
    datetime,
    PlainSerializer(_serialize_datetime, return_type=str),
    WithJsonSchema({"type": "string", "format": "date-time"}, mode="serialization"),
]
type OpportunitySortBy = Literal[
    "detected_at",
    "apr_pct",
    "spread_pct",
    "net_profit_usd",
    "max_notional_usd",
    "fees_usd",
]
type SortDirection = Literal["asc", "desc"]


class ApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiResponse):
    status: Literal["ok"]


class ErrorResponse(ApiResponse):
    detail: str


class StatusExchangeResponse(ApiResponse):
    instruments: int
    last_update: IsoDatetime | None
    live: bool
    network: Network | None
    rest_base_url: str | None
    ws_url: str | None


class StatusResponse(ApiResponse):
    executor: Literal["KILLED", "RUNNING"]
    mode: Mode
    exchanges: dict[str, StatusExchangeResponse]


class OpportunityStatsResponse(ApiResponse):
    buy_from: str
    sell_to: str
    pair: str
    count: int
    total_net_profit_usd: float
    total_fees_usd: float
    avg_apr_pct: float
    best_net_profit_usd: float


class OpportunityResponse(ApiResponse):
    id: int
    detected_at: IsoDatetime
    mode: Mode
    network: Network
    instrument: str
    symbol: str
    expiry: IsoDatetime
    days_to_expiry: float
    strike: float
    option_type: Literal["C", "P"]
    buy_from: str
    sell_to: str
    top_ask: float
    top_bid: float
    walked_ask: float | None
    walked_bid: float | None
    walked_size: float | None
    spread_pct: float
    fee_pct: float
    apr_pct: float
    max_notional_usd: float
    capital_deployed_usd: float
    net_profit_usd: float
    fees_usd: float
    gross_profit_usd: float
    status: OpportunityStatus
    rejection_reason: str | None


class TradeResponse(ApiResponse):
    id: int
    opportunity_id: int
    opened_at: IsoDatetime
    closed_at: IsoDatetime | None
    mode: Mode
    status: TradeStatus
    buy_exchange: str
    sell_exchange: str
    requested_size: float
    buy_fill_price: float | None
    buy_fill_size: float | None
    sell_fill_price: float | None
    sell_fill_size: float | None
    net_pnl_usd: float | None
    slippage_pct: float | None
    fees_usd: float | None
    error: str | None


class OrderResponse(ApiResponse):
    id: int
    exchange: str
    side: Side
    kind: OrderKind
    requested_price: float
    requested_size: float
    filled_price: float | None
    filled_size: float | None
    status: OrderStatus
    exchange_order_id: str | None
    placed_at: IsoDatetime
    updated_at: IsoDatetime


class TradeDetailResponse(TradeResponse):
    orders: list[OrderResponse]


class PositionResponse(ApiResponse):
    id: int
    exchange: str
    instrument: str
    size: float
    avg_price: float
    opened_at: IsoDatetime
    last_seen_at: IsoDatetime


class ExchangeStateResponse(ApiResponse):
    exchange: str
    balance_usd: float
    balances: dict[str, float]
    margin_used_usd: float
    ws_status: WsStatus
    rest_status: RestStatus
    updated_at: IsoDatetime


class ExecutorConfigResponse(ApiResponse):
    mode: Mode
    min_apr_pct: float
    min_notional_usd: float
    max_days_to_expiry: int
    min_net_profit_usd: float
    min_net_spread_pct: float
    max_notional_per_trade_usd: float
    max_positions_open: int
    max_daily_loss_usd: float


class ExecutorCountersResponse(ApiResponse):
    open_positions: int
    daily_pnl_usd: float


class ExecutorStateResponse(ApiResponse):
    status: Literal["KILLED", "RUNNING"]
    kill_switch_file: str
    config: ExecutorConfigResponse
    counters: ExecutorCountersResponse


class ExecutorToggleResponse(ApiResponse):
    killed: bool


class PerpHedgeConfigResponse(ApiResponse):
    rebalance_threshold_usd: float
    poll_interval_sec: int


class PerpHedgeStateResponse(ApiResponse):
    enabled: bool
    paused: bool
    kill_switch_file: str
    config: PerpHedgeConfigResponse


class PerpHedgeToggleResponse(ApiResponse):
    paused: bool


class AlertResponse(ApiResponse):
    id: int
    level: AlertLevel
    channel: str
    message: str
    sent_at: IsoDatetime
    meta: str | None


class TickerExchangeResponse(ApiResponse):
    bid_price: float | None
    bid_size: float | None
    ask_price: float | None
    ask_size: float | None
    underlying_price: float | None
    taker_fee_rate: float
    updated_at: IsoDatetime
    is_stale: bool


class TickerResponse(ApiResponse):
    instrument: str
    underlying: str
    expiry: IsoDatetime
    days_to_expiry: float
    strike: float
    option_type: Literal["C", "P"]
    exchanges: dict[str, TickerExchangeResponse]
    gross_spread_pct: float | None
    net_spread_pct: float | None
    apr_pct: float | None
    buy_exchange: str | None
    sell_exchange: str | None
    max_notional_usd: float | None
    max_profit_usd: float | None
    sell_collateral_usd: float | None
    updated_at: IsoDatetime


class FundingHistoryResponse(ApiResponse):
    ts: int
    rate_8h: float
    rate_ann: float
    index_price: float
