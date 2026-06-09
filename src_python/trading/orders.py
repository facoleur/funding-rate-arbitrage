from __future__ import annotations

import asyncio

from src_python.services.compare_options import OptionSpread
from src_python.trading.exchange_router import get_exchange

MAX_LEG_SIZE_USD = 10_000


async def place_orders_on_exchanges(data: OptionSpread) -> None:
    buy_exchange = get_exchange(data.buy_from)
    sell_exchange = get_exchange(data.sell_to)
    quantity = min(data.maxSize, MAX_LEG_SIZE_USD)

    buy_params = {
        "instrument_name": data.buy_from_instrument,
        "side": "buy",
        "price": data.buy_ask,
        "underlying_price": data.buy_from_underlying_price,
        "quantity": quantity,
        "time_in_force": "fill_or_kill",
    }
    sell_params = {
        "instrument_name": data.sell_to_instrument,
        "side": "sell",
        "price": data.sell_bid,
        "underlying_price": data.sell_to_underlying_price,
        "quantity": quantity,
        "time_in_force": "fill_or_kill",
    }

    results = await asyncio.gather(
        buy_exchange.place_order(**buy_params),
        sell_exchange.place_order(**sell_params),
        return_exceptions=True,
    )
    print("Buy result:", results[0])
    print("Sell result:", results[1])

