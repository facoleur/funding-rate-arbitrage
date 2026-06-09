from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import time

from src_python.exchanges import OptionQuote


@dataclass(slots=True)
class OptionSpread:
    symbol: str
    symbol_date: str
    instrument: str
    buy_from_instrument: str
    sell_to_instrument: str
    buy_from_underlying_price: float
    sell_to_underlying_price: float
    strike: float
    bid_raw: float | None
    ask_raw: float | None
    bid_price: float
    ask_price: float
    type: str
    expiration: str
    buy_from: str
    sell_to: str
    buy_ask: float
    sell_bid: float
    spread: float
    apr: float
    maxSize: float
    buyLink: str | None = None
    sellLink: str | None = None


OptionMap = dict[str, list[OptionQuote]]


def _is_valid_quote(q: OptionQuote) -> bool:
    return (
        q.bid_price is not None
        and q.ask_price is not None
        and q.bid_qty is not None
        and q.ask_qty is not None
        and q.bid_price > 0
        and q.ask_price > 0
    )


def group_options_by_instrument(all_quotes: list[OptionQuote]) -> OptionMap:
    grouped: defaultdict[str, list[OptionQuote]] = defaultdict(list)
    for quote in all_quotes:
        grouped[quote.normalized_name].append(quote)
    return dict(grouped)


def compare_options(option_groups: list[list[OptionQuote]]) -> list[OptionSpread]:
    now_ms = int(time() * 1000)
    results: list[OptionSpread] = []

    for quotes in option_groups:
        if len(quotes) < 2:
            continue

        names = {q.normalized_name for q in quotes}
        if len(names) > 1:
            raise ValueError(f"Mismatched instruments in group: {', '.join(sorted(names))}")

        name = quotes[0].normalized_name
        expiry = quotes[0].expiry
        days_to_exp = (expiry - now_ms) / (1000 * 60 * 60 * 24)
        if days_to_exp <= 0:
            continue

        valid = [q for q in quotes if _is_valid_quote(q)]
        if len(valid) < 2:
            continue

        lowest_ask = min(valid, key=lambda q: q.ask_price or float("inf"))
        highest_bid = max(valid, key=lambda q: q.bid_price or 0)

        if lowest_ask.exchange == highest_bid.exchange:
            continue

        assert lowest_ask.ask_price is not None
        assert highest_bid.bid_price is not None
        assert lowest_ask.ask_qty is not None
        assert highest_bid.bid_qty is not None

        price_diff_pct = ((highest_bid.bid_price - lowest_ask.ask_price) / lowest_ask.ask_price) * 100
        net_diff_pct = price_diff_pct - (lowest_ask.taker_fee_rate + highest_bid.taker_fee_rate) * 100
        if net_diff_pct <= 0:
            continue

        apr = (net_diff_pct / days_to_exp) * 365
        max_size = min(
            lowest_ask.ask_qty * lowest_ask.ask_price,
            highest_bid.bid_qty * highest_bid.bid_price,
        )

        first_dash = name.find("-")
        second_dash = name.find("-", first_dash + 1) if first_dash != -1 else -1
        symbol_date = name if second_dash == -1 else name[:second_dash]

        results.append(
            OptionSpread(
                symbol=name[:3],
                symbol_date=symbol_date,
                instrument=name,
                buy_from_instrument=lowest_ask.instrument_name,
                sell_to_instrument=highest_bid.instrument_name,
                buy_from_underlying_price=float(lowest_ask.underlying_price or 0),
                sell_to_underlying_price=float(highest_bid.underlying_price or 0),
                strike=quotes[0].strike,
                bid_raw=highest_bid.bid_price_raw,
                ask_raw=lowest_ask.ask_price_raw,
                bid_price=float(highest_bid.bid_price),
                ask_price=float(lowest_ask.ask_price),
                type=quotes[0].option_type,
                expiration=f"{days_to_exp:.1f}d",
                buy_from=lowest_ask.exchange,
                sell_to=highest_bid.exchange,
                buy_ask=float(lowest_ask.ask_price),
                sell_bid=float(highest_bid.bid_price),
                spread=round(net_diff_pct, 2),
                apr=round(apr, 2),
                maxSize=round(max_size, 2),
            )
        )

    return results

