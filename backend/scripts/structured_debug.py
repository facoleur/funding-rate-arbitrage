"""Diagnostic: run the box-spread detector against the live `ticker_state`
snapshot and print every candidate's economics, thresholds ignored.

0 rows in the Structured page is normal — a real cross-exchange box that clears
fees is rare. This script lets you check the *arithmetic* on real quotes:

    cd backend
    uv run python scripts/structured_debug.py                # top 12 per (underlying, expiry)
    uv run python scripts/structured_debug.py --all          # every candidate pair
    uv run python scripts/structured_debug.py --underlying BTC --min-edge -5

What to sanity-check in the output:

* parity_gap = entry_cost - width. On liquid strikes it must be *small*
  (a few times the combined bid/ask spread), and it is the arb itself. If it is
  huge, or entry_cost is negative while width is positive, the leg prices are
  in the wrong units (e.g. a Deribit leg not converted from BTC to USD) or a
  sign is flipped.
* fees_u should equal Sum of (leg_price * taker_fee_rate) — check one row by hand.
* edge_u = width - entry_cost - fees_u, exactly.
* venues column shows which exchange won each leg (C1/P1 at K1, C2/P2 at K2).
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import select

from option_arb.db.models import TickerState
from option_arb.db.session import get_session
from option_arb.services.comparator import Quote
from option_arb.structured.strategies.box import _best_ask, _best_bid


def _row_to_quote(r: TickerState) -> Quote | None:
    if None in (r.bid_price, r.ask_price, r.bid_size, r.ask_size):
        return None
    return Quote(
        exchange=r.exchange,
        normalized_name=r.instrument,
        instrument_name=r.instrument,
        underlying=r.underlying,
        strike=Decimal(str(r.strike)),
        option_type=r.option_type,
        expiry=r.expiry if r.expiry.tzinfo else r.expiry.replace(tzinfo=UTC),
        taker_fee_rate=Decimal(str(r.taker_fee_rate)),
        bid_price=Decimal(str(r.bid_price)),
        bid_qty=Decimal(str(r.bid_size)),
        ask_price=Decimal(str(r.ask_price)),
        ask_qty=Decimal(str(r.ask_size)),
        underlying_price=Decimal(str(r.underlying_price)) if r.underlying_price else None,
    )


async def _load_quotes(underlying: str | None) -> list[Quote]:
    async with get_session() as sess:
        stmt = select(TickerState)
        if underlying:
            stmt = stmt.where(TickerState.underlying == underlying)
        rows = list((await sess.execute(stmt)).scalars())
    return [q for q in (_row_to_quote(r) for r in rows) if q is not None]


def _scan_group(quotes: list[Quote]) -> list[dict]:
    by_st: dict[tuple[Decimal, str], list[Quote]] = defaultdict(list)
    for q in quotes:
        if q.bid_price > 0 and q.ask_price > 0 and q.bid_qty > 0 and q.ask_qty > 0:
            by_st[(q.strike, q.option_type)].append(q)

    strikes = sorted({s for (s, _t) in by_st})
    out: list[dict] = []
    for i, k1 in enumerate(strikes):
        for k2 in strikes[i + 1 :]:
            c1 = _best_ask(by_st.get((k1, "C")))
            p2 = _best_ask(by_st.get((k2, "P")))
            c2 = _best_bid(by_st.get((k2, "C")))
            p1 = _best_bid(by_st.get((k1, "P")))
            if not (c1 and p2 and c2 and p1):
                continue
            width = k2 - k1
            entry = c1.ask_price + p2.ask_price - c2.bid_price - p1.bid_price
            fees = (
                c1.ask_price * c1.taker_fee_rate
                + p2.ask_price * p2.taker_fee_rate
                + c2.bid_price * c2.taker_fee_rate
                + p1.bid_price * p1.taker_fee_rate
            )
            edge = width - entry - fees
            size = min(c1.ask_qty, p2.ask_qty, c2.bid_qty, p1.bid_qty)
            out.append(
                {
                    "k1": k1,
                    "k2": k2,
                    "width": width,
                    "entry": entry,
                    "gap": entry - width,
                    "fees": fees,
                    "edge": edge,
                    "size": size,
                    "total": edge * size,
                    "venues": f"C1:{c1.exchange} P1:{p1.exchange} C2:{c2.exchange} P2:{p2.exchange}",
                }
            )
    return out


def _fmt(d: dict) -> str:
    return (
        f"  {float(d['k1']):>9,.0f} {float(d['k2']):>9,.0f} "
        f"{float(d['width']):>10,.2f} {float(d['entry']):>12,.2f} "
        f"{float(d['gap']):>+11,.2f} {float(d['fees']):>9,.2f} "
        f"{float(d['edge']):>+10,.2f} {float(d['size']):>7,.3f} "
        f"{float(d['total']):>+11,.2f}   {d['venues']}"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", default=None, help="filter, e.g. BTC")
    ap.add_argument("--all", action="store_true", help="print every candidate pair, not just top N")
    ap.add_argument("--top", type=int, default=12, help="rows per (underlying, expiry) group")
    ap.add_argument("--min-edge", type=float, default=None, help="only rows with edge_u >= this")
    args = ap.parse_args()

    quotes = await _load_quotes(args.underlying)
    if not quotes:
        print("ticker_state is empty — is `make dev` running and the screener flushing?")
        return

    groups: dict[tuple[str, datetime], list[Quote]] = defaultdict(list)
    for q in quotes:
        groups[(q.underlying, q.expiry)].append(q)

    header = (
        f"  {'K1':>9} {'K2':>9} {'width':>10} {'entry_cost':>12} "
        f"{'parity_gap':>11} {'fees_u':>9} {'edge_u':>10} {'size':>7} {'total$':>11}   venues"
    )
    now = datetime.now(UTC)
    for (underlying, expiry), qs in sorted(groups.items(), key=lambda kv: kv[0]):
        if expiry <= now:
            continue
        rows = _scan_group(qs)
        if args.min_edge is not None:
            rows = [r for r in rows if float(r["edge"]) >= args.min_edge]
        if not rows:
            continue
        rows.sort(key=lambda r: r["edge"], reverse=True)
        venues = sorted({q.exchange for q in qs})
        dte = (expiry - now).days
        print(f"\n{underlying} {expiry:%Y-%m-%d} (dte={dte}, {len(qs)} quotes, venues={venues})")
        print(header)
        shown = rows if args.all else rows[: args.top]
        for r in shown:
            print(_fmt(r))
        if not args.all and len(rows) > args.top:
            print(f"  … {len(rows) - args.top} more (use --all)")


if __name__ == "__main__":
    asyncio.run(main())
