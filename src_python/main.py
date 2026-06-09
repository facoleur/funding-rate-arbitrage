from __future__ import annotations

import asyncio
from dataclasses import asdict

from src_python.core.env import load_dotenv
from src_python.core.table import format_table
from src_python.exchanges.aevo.aevo_exchange import AevoExchange
from src_python.exchanges.deribit.deribit_exchange import DeribitExchange
from src_python.exchanges.derive.derive_exchange import DeriveExchange
from src_python.services.compare_options import OptionSpread, compare_options, group_options_by_instrument
from src_python.telegram import send_telegram_message
from src_python.trading.orders import place_orders_on_exchanges

load_dotenv()


async def run_task() -> None:
    derive = DeriveExchange()
    deribit = DeribitExchange()
    aevo = AevoExchange()

    try:
        expiries = await derive.get_available_dates("BTC")
        tickers = ["ETH"]
        data: list[OptionSpread] = []

        for ticker in tickers:
            for exp in expiries:
                l_chain = await derive.get_option_chain_prices(ticker, exp)
                d_chain = await deribit.get_option_chain_prices(ticker, exp)

                grouped = group_options_by_instrument([*l_chain, *d_chain])
                results = compare_options(list(grouped.values()))

                order_passed = False
                for result in results:
                    if result.apr and result.apr < 10:
                        continue

                    if order_passed:
                        print("order already passed")
                        continue

                    print("Placing order:", result)
                    await place_orders_on_exchanges(result)
                    order_passed = True
                    await send_telegram_message(result)

                print("ticker:", ticker, "opportunities:", len(results))
                if results:
                    print(
                        format_table(
                            [asdict(result) for result in results],
                            [
                                "instrument",
                                "buy_from",
                                "sell_to",
                                "expiration",
                                "spread",
                                "apr",
                            ],
                        )
                    )
                data.extend(results)

        if data:
            print(format_table([asdict(item) for item in data]))
    finally:
        await derive.close()
        await deribit.close()
        await aevo.close()


def test() -> OptionSpread:
    return OptionSpread(
        symbol="BTC",
        symbol_date="BTC-31OCT25",
        instrument="BTC-31OCT25-100000-C",
        buy_from_instrument="BTC-31OCT25-100000-C",
        sell_to_instrument="BTC-20251031-100000-C",
        buy_from_underlying_price=1587,
        sell_to_underlying_price=27100,
        strike=30000,
        bid_raw=None,
        ask_raw=None,
        bid_price=2000,
        ask_price=1500,
        type="call",
        expiration="5.0d",
        buy_from="derive",
        sell_to="deribit",
        buy_ask=1500,
        sell_bid=2000,
        spread=500,
        apr=15,
        maxSize=5000,
        buyLink="",
        sellLink="",
    )


if __name__ == "__main__":
    try:
        asyncio.run(run_task())
    except Exception as error:
        print("Error in main task:", error)
