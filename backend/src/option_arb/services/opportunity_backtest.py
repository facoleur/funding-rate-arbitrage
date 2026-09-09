"""Portfolio backtest over stored `Opportunity` rows.

Pure, no I/O. Each opportunity is treated as a trade taken at ``detected_at``:
``capital_required`` is locked from detection until the instrument ``expiry``
(the option position is held to settlement regardless of whether the price
dislocation persists), and ``net_profit`` is realized at ``expiry`` together
with the freed capital.

Two admission gates, applied in order per candidate (chronological):

1. **dedup** (``one_position_per_instrument``) — skip while a simulated
   position on the same instrument is still open (its ``expiry`` in the future
   relative to the candidate's ``detected_at``). Settlement exposure is the same
   option whatever the arb direction, so the key is the instrument alone.
2. **budget** (``capital_budget_usd``) — skip when taking the candidate would
   push deployed capital above the budget. ``None`` = unlimited (answers "how
   much capital is required to take everything").

Not modelled: execution slippage beyond the screener's book walk, hedge funding
cost beyond taker fees, position sizing / adding to an existing instrument.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class BacktestPosition:
    """One candidate trade, mapped from an `Opportunity` row (effective economics)."""

    instrument: str
    symbol: str
    buy_from: str
    sell_to: str
    entry: datetime
    expiry: datetime
    capital: Decimal
    profit: Decimal
    fees: Decimal


@dataclass(frozen=True, slots=True)
class BacktestPoint:
    ts: datetime
    capital_in_use_usd: float
    cumulative_profit_usd: float


@dataclass(frozen=True, slots=True)
class BacktestPairBreakdown:
    pair: str
    buy_from: str
    sell_to: str
    n_taken: int
    net_profit_usd: float
    peak_capital_usd: float


@dataclass(frozen=True, slots=True)
class BacktestSummary:
    start: datetime
    end: datetime
    period_days: float
    capital_budget_usd: float | None
    peak_capital_usd: float
    avg_capital_usd: float
    capital_efficiency_pct: float
    total_net_profit_usd: float
    unrealized_net_profit_usd: float
    total_fees_usd: float
    return_on_peak_pct: float
    return_on_budget_pct: float | None
    annualized_pct: float
    n_candidates: int
    n_taken: int
    n_skipped_dedup: int
    n_skipped_budget: int
    n_open: int
    win_rate_pct: float
    avg_hold_days: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    summary: BacktestSummary
    series: list[BacktestPoint]
    by_pair: list[BacktestPairBreakdown]


def _empty(
    now: datetime,
    budget: Decimal | None,
    n_candidates: int,
    *,
    n_skipped_dedup: int = 0,
    n_skipped_budget: int = 0,
) -> BacktestResult:
    return BacktestResult(
        summary=BacktestSummary(
            start=now,
            end=now,
            period_days=0.0,
            capital_budget_usd=float(budget) if budget is not None else None,
            peak_capital_usd=0.0,
            avg_capital_usd=0.0,
            capital_efficiency_pct=0.0,
            total_net_profit_usd=0.0,
            unrealized_net_profit_usd=0.0,
            total_fees_usd=0.0,
            return_on_peak_pct=0.0,
            return_on_budget_pct=None,
            annualized_pct=0.0,
            n_candidates=n_candidates,
            n_taken=0,
            n_skipped_dedup=n_skipped_dedup,
            n_skipped_budget=n_skipped_budget,
            n_open=0,
            win_rate_pct=0.0,
            avg_hold_days=0.0,
        ),
        series=[],
        by_pair=[],
    )


def simulate(
    positions: list[BacktestPosition],
    *,
    capital_budget_usd: Decimal | None = None,
    one_position_per_instrument: bool = True,
    now: datetime | None = None,
) -> BacktestResult:
    now = now or datetime.now(UTC)
    n_candidates = len(positions)
    if not positions:
        return _empty(now, capital_budget_usd, 0)

    ordered = sorted(positions, key=lambda p: p.entry)

    # --- admission -----------------------------------------------------------
    taken: list[BacktestPosition] = []
    n_skipped_dedup = 0
    n_skipped_budget = 0
    deployed = _ZERO
    # min-heap of (expiry, capital) for capital release; instrument -> expiry for dedup.
    release_heap: list[tuple[datetime, Decimal]] = []
    instr_open_until: dict[str, datetime] = {}

    for p in ordered:
        while release_heap and release_heap[0][0] <= p.entry:
            _, freed = heapq.heappop(release_heap)
            deployed -= freed

        if one_position_per_instrument:
            held_until = instr_open_until.get(p.instrument)
            if held_until is not None and held_until > p.entry:
                n_skipped_dedup += 1
                continue

        if capital_budget_usd is not None and deployed + p.capital > capital_budget_usd:
            n_skipped_budget += 1
            continue

        deployed += p.capital
        heapq.heappush(release_heap, (p.expiry, p.capital))
        if one_position_per_instrument:
            prev = instr_open_until.get(p.instrument)
            instr_open_until[p.instrument] = p.expiry if prev is None else max(prev, p.expiry)
        taken.append(p)

    if not taken:
        return _empty(
            now,
            capital_budget_usd,
            n_candidates,
            n_skipped_dedup=n_skipped_dedup,
            n_skipped_budget=n_skipped_budget,
        )

    # --- capital curve + realized profit over [start, now] ------------------
    start = taken[0].entry
    # (ts, capital_delta, realized_profit_delta); releases beyond `now` are not
    # applied to the historical curve, but their profit is counted as unrealized.
    events: list[tuple[datetime, Decimal, Decimal]] = []
    for p in taken:
        events.append((p.entry, p.capital, _ZERO))
        if p.expiry <= now:
            events.append((p.expiry, -p.capital, p.profit))
    events.sort(key=lambda e: e[0])

    series: list[BacktestPoint] = []
    cap = _ZERO
    realized = _ZERO
    peak = _ZERO
    area = _ZERO  # ∫ capital dt, seconds·USD
    prev_ts = start
    for ts, dcap, dprofit in events:
        area += cap * Decimal((ts - prev_ts).total_seconds())
        prev_ts = ts
        cap += dcap
        realized += dprofit
        if cap > peak:
            peak = cap
        # collapse same-timestamp events into one point
        if series and series[-1].ts == ts:
            series[-1] = BacktestPoint(ts, float(cap), float(realized))
        else:
            series.append(BacktestPoint(ts, float(cap), float(realized)))
    # tail segment up to `now`
    area += cap * Decimal(max((now - prev_ts).total_seconds(), 0.0))
    if not series or series[-1].ts != now:
        series.append(BacktestPoint(now, float(cap), float(realized)))

    period_secs = max((now - start).total_seconds(), 1.0)
    period_days = period_secs / 86400.0
    avg_capital = area / Decimal(period_secs)

    open_positions = [p for p in taken if p.expiry > now]
    unrealized = sum((p.profit for p in open_positions), _ZERO)
    total_fees = sum((p.fees for p in taken), _ZERO)
    wins = sum(1 for p in taken if p.profit > 0)

    base = capital_budget_usd if capital_budget_usd is not None else peak
    return_on_peak = float(realized / peak * 100) if peak > 0 else 0.0
    return_on_budget = (
        float(realized / capital_budget_usd * 100)
        if capital_budget_usd is not None and capital_budget_usd > 0
        else None
    )
    return_on_base = float(realized / base * 100) if base > 0 else 0.0
    annualized = return_on_base * 365.0 / period_days if period_days > 0 else 0.0

    # --- per-pair breakdown ------------------------------------------------
    by_pair = _breakdown_by_pair(taken, now)

    summary = BacktestSummary(
        start=start,
        end=now,
        period_days=round(period_days, 2),
        capital_budget_usd=float(capital_budget_usd) if capital_budget_usd is not None else None,
        peak_capital_usd=float(peak),
        avg_capital_usd=float(avg_capital),
        capital_efficiency_pct=float(avg_capital / peak * 100) if peak > 0 else 0.0,
        total_net_profit_usd=float(realized),
        unrealized_net_profit_usd=float(unrealized),
        total_fees_usd=float(total_fees),
        return_on_peak_pct=return_on_peak,
        return_on_budget_pct=return_on_budget,
        annualized_pct=annualized,
        n_candidates=n_candidates,
        n_taken=len(taken),
        n_skipped_dedup=n_skipped_dedup,
        n_skipped_budget=n_skipped_budget,
        n_open=len(open_positions),
        win_rate_pct=wins / len(taken) * 100.0,
        avg_hold_days=sum((p.expiry - p.entry).total_seconds() for p in taken)
        / len(taken)
        / 86400.0,
    )
    return BacktestResult(summary=summary, series=series, by_pair=by_pair)


def _breakdown_by_pair(taken: list[BacktestPosition], now: datetime) -> list[BacktestPairBreakdown]:
    keys = sorted({(p.buy_from, p.sell_to) for p in taken})
    out: list[BacktestPairBreakdown] = []
    for buy_from, sell_to in keys:
        subset = [p for p in taken if p.buy_from == buy_from and p.sell_to == sell_to]
        # peak concurrent capital within this pair alone
        evts: list[tuple[datetime, Decimal]] = []
        for p in subset:
            evts.append((p.entry, p.capital))
            evts.append((p.expiry, -p.capital))
        evts.sort(key=lambda e: e[0])
        cap = _ZERO
        peak = _ZERO
        for _, d in evts:
            cap += d
            if cap > peak:
                peak = cap
        out.append(
            BacktestPairBreakdown(
                pair=f"{buy_from} → {sell_to}",
                buy_from=buy_from,
                sell_to=sell_to,
                n_taken=len(subset),
                net_profit_usd=float(sum((p.profit for p in subset), _ZERO)),
                peak_capital_usd=float(peak),
            )
        )
    out.sort(key=lambda b: b.net_profit_usd, reverse=True)
    return out
