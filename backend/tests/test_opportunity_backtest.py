from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from option_arb.services.opportunity_backtest import BacktestPosition, simulate

T0 = datetime(2026, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 6, 1, tzinfo=UTC)  # well after every expiry used below


def _pos(
    *,
    instrument: str = "BTC-20260201-100000-C",
    entry: datetime,
    expiry: datetime,
    capital: float,
    profit: float,
    fees: float = 1.0,
    buy_from: str = "derive",
    sell_to: str = "deribit",
) -> BacktestPosition:
    return BacktestPosition(
        instrument=instrument,
        symbol="BTC",
        buy_from=buy_from,
        sell_to=sell_to,
        entry=entry,
        expiry=expiry,
        capital=Decimal(str(capital)),
        profit=Decimal(str(profit)),
        fees=Decimal(str(fees)),
    )


def test_empty_set_returns_zeroed_summary() -> None:
    res = simulate([], now=NOW)
    assert res.summary.n_candidates == 0
    assert res.summary.peak_capital_usd == 0.0
    assert res.summary.total_net_profit_usd == 0.0
    assert res.series == []
    assert res.by_pair == []


def test_disjoint_positions_peak_is_the_max_not_the_sum() -> None:
    res = simulate(
        [
            _pos(entry=T0, expiry=T0 + timedelta(days=10), capital=1000, profit=50),
            _pos(
                instrument="ETH-20260201-3000-C",
                entry=T0 + timedelta(days=20),
                expiry=T0 + timedelta(days=30),
                capital=1500,
                profit=70,
            ),
        ],
        now=NOW,
    )
    assert res.summary.peak_capital_usd == 1500.0
    assert res.summary.total_net_profit_usd == 120.0
    assert res.summary.n_taken == 2


def test_overlapping_positions_stack_capital() -> None:
    res = simulate(
        [
            _pos(entry=T0, expiry=T0 + timedelta(days=30), capital=1000, profit=50),
            _pos(
                instrument="ETH-20260201-3000-C",
                entry=T0 + timedelta(days=5),
                expiry=T0 + timedelta(days=30),
                capital=1500,
                profit=70,
            ),
        ],
        now=NOW,
    )
    assert res.summary.peak_capital_usd == 2500.0


def test_capital_frees_exactly_at_expiry() -> None:
    exp = T0 + timedelta(days=10)
    res = simulate(
        [
            _pos(entry=T0, expiry=exp, capital=1000, profit=50),
            _pos(
                instrument="ETH-20260201-3000-C",
                entry=exp,  # enters the instant the first frees its capital
                expiry=exp + timedelta(days=10),
                capital=1200,
                profit=60,
            ),
        ],
        now=NOW,
    )
    assert res.summary.peak_capital_usd == 1200.0


def test_dedup_skips_second_detection_on_same_instrument() -> None:
    res = simulate(
        [
            _pos(entry=T0, expiry=T0 + timedelta(days=30), capital=1000, profit=50),
            _pos(
                entry=T0 + timedelta(days=2),  # same instrument, still open
                expiry=T0 + timedelta(days=30),
                capital=1000,
                profit=999,
            ),
        ],
        one_position_per_instrument=True,
        now=NOW,
    )
    assert res.summary.n_taken == 1
    assert res.summary.n_skipped_dedup == 1
    assert res.summary.total_net_profit_usd == 50.0


def test_dedup_off_takes_both() -> None:
    res = simulate(
        [
            _pos(entry=T0, expiry=T0 + timedelta(days=30), capital=1000, profit=50),
            _pos(
                entry=T0 + timedelta(days=2),
                expiry=T0 + timedelta(days=30),
                capital=1000,
                profit=40,
            ),
        ],
        one_position_per_instrument=False,
        now=NOW,
    )
    assert res.summary.n_taken == 2
    assert res.summary.peak_capital_usd == 2000.0
    assert res.summary.total_net_profit_usd == 90.0


def test_same_instrument_after_expiry_is_a_fresh_position() -> None:
    exp = T0 + timedelta(days=10)
    res = simulate(
        [
            _pos(entry=T0, expiry=exp, capital=1000, profit=50),
            _pos(
                entry=exp + timedelta(days=1),  # same instrument, prior one settled
                expiry=exp + timedelta(days=20),
                capital=1000,
                profit=40,
            ),
        ],
        one_position_per_instrument=True,
        now=NOW,
    )
    assert res.summary.n_taken == 2
    assert res.summary.n_skipped_dedup == 0


def test_budget_cap_skips_the_position_that_would_exceed_it() -> None:
    res = simulate(
        [
            _pos(entry=T0, expiry=T0 + timedelta(days=30), capital=1000, profit=50),
            _pos(
                instrument="ETH-20260201-3000-C",
                entry=T0 + timedelta(days=1),
                expiry=T0 + timedelta(days=30),
                capital=800,
                profit=999,
            ),
        ],
        capital_budget_usd=Decimal("1500"),
        now=NOW,
    )
    assert res.summary.n_taken == 1
    assert res.summary.n_skipped_budget == 1
    assert res.summary.total_net_profit_usd == 50.0
    assert res.summary.capital_budget_usd == 1500.0
    assert res.summary.return_on_budget_pct == 50.0 / 1500.0 * 100.0


def test_budget_frees_and_admits_later_position() -> None:
    exp = T0 + timedelta(days=10)
    res = simulate(
        [
            _pos(entry=T0, expiry=exp, capital=1000, profit=50),
            _pos(
                instrument="ETH-20260201-3000-C",
                entry=exp + timedelta(days=1),
                expiry=exp + timedelta(days=10),
                capital=1000,
                profit=40,
            ),
        ],
        capital_budget_usd=Decimal("1200"),
        now=NOW,
    )
    assert res.summary.n_taken == 2
    assert res.summary.n_skipped_budget == 0


def test_annualized_return_math() -> None:
    # single position: 100 profit on 1000 peak over 100 days
    res = simulate(
        [_pos(entry=T0, expiry=T0 + timedelta(days=100), capital=1000, profit=100)],
        now=T0 + timedelta(days=100),
    )
    assert res.summary.return_on_peak_pct == 10.0
    assert res.summary.annualized_pct == 10.0 * 365.0 / 100.0


def test_open_position_profit_is_unrealized() -> None:
    now = T0 + timedelta(days=5)
    res = simulate(
        [_pos(entry=T0, expiry=T0 + timedelta(days=40), capital=1000, profit=100)],
        now=now,
    )
    assert res.summary.n_open == 1
    assert res.summary.total_net_profit_usd == 0.0
    assert res.summary.unrealized_net_profit_usd == 100.0
    # capital still deployed at `now`
    assert res.series[-1].capital_in_use_usd == 1000.0


def test_by_pair_breakdown_splits_and_sorts_by_profit() -> None:
    res = simulate(
        [
            _pos(entry=T0, expiry=T0 + timedelta(days=10), capital=1000, profit=20),
            _pos(
                instrument="ETH-20260201-3000-C",
                entry=T0 + timedelta(days=1),
                expiry=T0 + timedelta(days=10),
                capital=1000,
                profit=80,
                buy_from="deribit",
                sell_to="derive",
            ),
        ],
        one_position_per_instrument=True,
        now=NOW,
    )
    assert [b.pair for b in res.by_pair] == ["deribit → derive", "derive → deribit"]
    assert res.by_pair[0].net_profit_usd == 80.0
    assert res.by_pair[0].n_taken == 1
