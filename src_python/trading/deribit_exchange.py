from __future__ import annotations

import os

from src_python.trading.deribit.deribit import DeribitOptionsTrader


class DeribitExchange:
    name = "deribit"

    def __init__(self) -> None:
        self.trader = DeribitOptionsTrader(
            os.getenv("DERIBIT_CLIENT_ID", ""),
            os.getenv("DERIBIT_CLIENT_SECRET", ""),
            True,
        )

    async def close(self) -> None:
        await self.trader.close()

    async def place_order(
        self,
        *,
        instrument_name: str,
        side: str,
        price: float,
        underlying_price: float | None,
        quantity: float,
        order_type: str = "limit",
        time_in_force: str = "fill_or_kill",
    ) -> object:
        print("deribit price conversion", price, underlying_price)
        if not underlying_price:
            raise ValueError("underlying_price is required for Deribit option order pricing")

        return await self.trader.place_order(
            instrument_name=instrument_name,
            side=side,
            amount=quantity,
            price=price / underlying_price,
            order_type=order_type,
            time_in_force=time_in_force,
        )
