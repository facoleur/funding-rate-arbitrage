from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from decimal import Decimal

from option_arb.exchanges.base import Book, BookLevel, OrderRequest, OrderResult


@dataclass
class SlippageModel:
    """Simulates fills against a real L2 book snapshot.

    - walk_book: consumes levels until either the requested size is filled
      or the book runs out.
    - gaussian noise on the effective fill price.
    - random rejection probability.
    - random latency before returning.
    - respect the limit price: if effective fill breaches it, REJECTED."""

    noise_stdev_bps: float = 10.0  # 10 basis points std-dev
    reject_prob: float = 0.02
    latency_min_sec: float = 0.05
    latency_max_sec: float = 0.30
    rng_seed: int | None = None

    def __post_init__(self) -> None:
        self._rng = random.Random(self.rng_seed)

    async def simulate(self, order: OrderRequest, book: Book) -> OrderResult:
        await asyncio.sleep(self._rng.uniform(self.latency_min_sec, self.latency_max_sec))

        if self._rng.random() < self.reject_prob:
            return OrderResult(status="REJECTED", reason="random_reject")

        levels = book.asks if order.side == "BUY" else book.bids
        avg_price, filled = self._walk(order.size, levels)
        if filled <= 0:
            return OrderResult(status="REJECTED", reason="empty_book")

        # gaussian noise
        noise = self._rng.gauss(0.0, self.noise_stdev_bps / 10_000.0)
        fill_price = avg_price * (Decimal(1) + Decimal(str(noise)))

        # respect the limit price
        if order.side == "BUY" and fill_price > order.limit_price:
            return OrderResult(status="REJECTED", reason="limit_price_missed")
        if order.side == "SELL" and fill_price < order.limit_price:
            return OrderResult(status="REJECTED", reason="limit_price_missed")

        return OrderResult(
            status="FILLED" if filled >= order.size else "PARTIAL",
            filled_size=filled,
            filled_price=fill_price,
            exchange_order_id=f"mock-{self._rng.randint(1, 10**9)}",
            raw_response={"walked_avg": str(avg_price), "noise": str(noise)},
        )

    @staticmethod
    def _walk(size: Decimal, levels: list[BookLevel]) -> tuple[Decimal, Decimal]:
        if not levels:
            return Decimal(0), Decimal(0)
        remaining = size
        total_cost = Decimal(0)
        total_filled = Decimal(0)
        for lvl in levels:
            take = min(lvl.size, remaining)
            total_cost += take * lvl.price
            total_filled += take
            remaining -= take
            if remaining <= 0:
                break
        if total_filled == 0:
            return Decimal(0), Decimal(0)
        return total_cost / total_filled, total_filled
