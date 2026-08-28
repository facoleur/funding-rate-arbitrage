from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, WithJsonSchema, computed_field

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
    "net_return_pct",
    "net_profit_usd",
    "buy_premium_usd",
    "fees_usd",
]
type SortDirection = Literal["asc", "desc"]


class ApiResponse(BaseModel):
    # `from_attributes` lets routes return ORM rows directly — the response
    # model is the only place the field list is written down.
    model_config = ConfigDict(extra="forbid", from_attributes=True)


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


def _pick(verified: float | None, detected: float) -> float:
    """Valeur vérifiée si elle existe, sinon celle du screening.

    Chaque champ retombe individuellement : l'invariant « si un champ vérifié est
    renseigné, les onze le sont » n'est garanti nulle part, et le supposer était
    précisément ce que le frontend faisait avec onze assertions non-null.
    """
    return verified if verified is not None else detected


class OpportunityEconomicsResponse(ApiResponse):
    """Économie à afficher, déjà arbitrée entre valeurs vérifiées et détectées."""

    buy_price: float
    sell_price: float
    tradeable_size: float
    buy_premium_usd: float
    sell_premium_usd: float
    estimated_short_margin_usd: float
    capital_required_usd: float
    gross_profit_usd: float
    fees_usd: float
    net_profit_usd: float
    net_return_pct: float
    apr_pct: float


class OpportunityResponse(ApiResponse):
    id: int
    detected_at: IsoDatetime
    mode: Mode
    network: Network
    instrument: str
    symbol: str
    expiry: IsoDatetime
    strike: float
    option_type: Literal["C", "P"]
    buy_from: str
    sell_to: str
    top_ask: float
    top_bid: float
    walked_ask: float | None
    walked_bid: float | None
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
    verified_buy_limit: float | None
    verified_sell_limit: float | None
    verified_tradeable_size: float | None
    verified_buy_premium_usd: float | None
    verified_sell_premium_usd: float | None
    verified_estimated_short_margin_usd: float | None
    verified_capital_required_usd: float | None
    verified_gross_profit_usd: float | None
    verified_fees_usd: float | None
    verified_net_profit_usd: float | None
    verified_net_return_pct: float | None
    verified_apr_pct: float | None
    status: OpportunityStatus
    rejection_reason: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def days_to_expiry(self) -> float:
        expiry = self.expiry if self.expiry.tzinfo else self.expiry.replace(tzinfo=UTC)
        return round(max((expiry - datetime.now(UTC)).total_seconds() / 86400.0, 0), 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_verified(self) -> bool:
        """L'executor a re-vérifié les books avant exécution."""
        return self.verified_tradeable_size is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective(self) -> OpportunityEconomicsResponse:
        """Économie à afficher, sans que le client ait à arbitrer lui-même."""
        return OpportunityEconomicsResponse(
            buy_price=_pick(self.verified_buy_limit, self.top_ask),
            sell_price=_pick(self.verified_sell_limit, self.top_bid),
            tradeable_size=_pick(self.verified_tradeable_size, self.tradeable_size),
            buy_premium_usd=_pick(self.verified_buy_premium_usd, self.buy_premium_usd),
            sell_premium_usd=_pick(self.verified_sell_premium_usd, self.sell_premium_usd),
            estimated_short_margin_usd=_pick(
                self.verified_estimated_short_margin_usd, self.estimated_short_margin_usd
            ),
            capital_required_usd=_pick(
                self.verified_capital_required_usd, self.capital_required_usd
            ),
            gross_profit_usd=_pick(self.verified_gross_profit_usd, self.gross_profit_usd),
            fees_usd=_pick(self.verified_fees_usd, self.fees_usd),
            net_profit_usd=_pick(self.verified_net_profit_usd, self.net_profit_usd),
            net_return_pct=_pick(self.verified_net_return_pct, self.net_return_pct),
            apr_pct=_pick(self.verified_apr_pct, self.apr_pct),
        )


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
    min_buy_premium_usd: float
    min_leg_premium_liquidity_usd: float
    max_days_to_expiry: int
    min_net_profit_usd: float
    min_net_return_pct: float
    max_buy_premium_per_trade_usd: float
    ioc_slippage_limit_pct: float
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
    price_spread_pct: float | None
    buy_exchange: str | None
    sell_exchange: str | None
    tradeable_size: float | None
    buy_premium_usd: float | None
    sell_premium_usd: float | None
    estimated_short_margin_usd: float | None
    capital_required_usd: float | None
    gross_profit_usd: float | None
    fees_usd: float | None
    net_profit_usd: float | None
    net_return_pct: float | None
    apr_pct: float | None
    # Verdict des seuils du screener, calculé par `economics.meets_thresholds`.
    # Sert à l'UI pour atténuer les lignes non exécutables sans réimplémenter
    # le prédicat côté client.
    eligible: bool
    updated_at: IsoDatetime


class FundingHistoryResponse(ApiResponse):
    ts: int
    rate_8h: float
    rate_ann: float
    index_price: float
