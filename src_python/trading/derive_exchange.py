from __future__ import annotations

import os

from src_python.trading.derive.derive import DeriveOptionsTrader


class DeriveExchange:
    name = "derive"

    def __init__(self) -> None:
        self.trader = DeriveOptionsTrader(
            os.getenv("Derive_CLIENT_ID", ""),
            os.getenv("Derive_CLIENT_SECRET", ""),
            True,
        )

    async def place_order(
        self,
        *,
        instrument_name: str,
        side: str,
        price: float,
        quantity: float,
        underlying_price: float | None = None,
        order_type: str = "limit",
        time_in_force: str = "fill_or_kill",
    ) -> object:
        return await self.trader.place_order(
            instrument_name=instrument_name,
            side=side,
            amount=quantity,
            price=price,
            order_type=order_type,
            time_in_force=time_in_force,
        )
