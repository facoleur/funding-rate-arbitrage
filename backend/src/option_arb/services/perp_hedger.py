from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from option_arb.config import PerpHedgeConfig
from option_arb.events import Event, bus

if TYPE_CHECKING:
    from option_arb.exchanges.deribit import DeribitExchange

log = logging.getLogger(__name__)

_PERP = "BTC-PERPETUAL"
_CONTRACT_USD = 10  # Deribit BTC-PERPETUAL minimum contract size


class PerpHedger:
    """Maintains a BTC-PERPETUAL short on Deribit inverse to neutralize BTC collateral exposure.

    Target short = btc_balance * btc_price (in USD).
    Rebalances whenever |target - actual| > rebalance_threshold_usd.

    In dry_run mode (paper trading), logs the delta but places no orders."""

    def __init__(
        self, exchange: DeribitExchange, config: PerpHedgeConfig, *, dry_run: bool = True
    ) -> None:
        self.exchange = exchange
        self.config = config
        self.dry_run = dry_run
        self._stop = asyncio.Event()

    async def run(self) -> None:
        log.info(
            "perp_hedger started (interval=%ds, dry_run=%s)",
            self.config.poll_interval_sec,
            self.dry_run,
        )
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:
                log.exception("perp_hedger tick failed: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.config.poll_interval_sec)
                break
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    async def _tick(self) -> None:
        if Path(self.config.kill_switch_file).exists():
            log.debug("perp_hedger: kill switch active, skipping")
            return

        balances = await self.exchange.get_balances()
        btc = float(balances.get("BTC", 0))
        if btc <= 0:
            return

        btc_price = float(await self.exchange.get_index_price())
        if btc_price <= 0:
            return

        target_short_usd = btc * btc_price
        current_pos_usd = await self.exchange.get_perp_position_usd(_PERP)
        current_short_usd = -current_pos_usd  # positive when short

        delta_usd = target_short_usd - current_short_usd

        log.debug(
            "perp_hedge: btc=%.6f price=%.0f target=$%.2f current=$%.2f delta=$%.2f",
            btc,
            btc_price,
            target_short_usd,
            current_short_usd,
            delta_usd,
        )

        if abs(delta_usd) < self.config.rebalance_threshold_usd:
            return

        side: Literal["SELL", "BUY"] = "SELL" if delta_usd > 0 else "BUY"
        amount_usd = max(_CONTRACT_USD, round(abs(delta_usd) / _CONTRACT_USD) * _CONTRACT_USD)

        if self.dry_run:
            log.info(
                "perp_hedger (DRY RUN): would %s $%.0f on %s (delta=$%.2f)",
                side,
                amount_usd,
                _PERP,
                delta_usd,
            )
            return

        log.info("perp_hedger: placing %s $%.0f on %s", side, amount_usd, _PERP)
        result = await self.exchange.place_perp_order(_PERP, side, amount_usd)

        if result.status in ("FILLED", "PARTIAL"):
            filled_usd = float(result.filled_size or 0)
            log.info("perp_hedger: %s $%.0f filled @ %s", side, filled_usd, result.filled_price)
            await bus.publish(
                Event(
                    type="perp_hedge_rebalanced",
                    level="info",
                    message=f"BTC-PERP {side} ${amount_usd:.0f} → {result.status} @ {result.filled_price}",
                    payload={"side": side, "amount_usd": amount_usd, "status": result.status},
                )
            )
        else:
            log.warning(
                "perp_hedger: %s $%.0f → %s (%s)",
                side,
                amount_usd,
                result.status,
                result.reason,
            )
