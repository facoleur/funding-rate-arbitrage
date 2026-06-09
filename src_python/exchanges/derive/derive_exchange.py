from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from src_python.core.http_client import create_http_client
from src_python.exchanges import OptionQuote
from src_python.services.compare_options import OptionSpread

SIZE_THRESHOLD = 100


def _float_field(data: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return float(value)
    return default


class DeriveExchange:
    name = "derive"
    base_trade_url = "https://app.derive.xyz/trade/options?"

    def __init__(self) -> None:
        self.http = create_http_client("https://api.lyra.finance/")

    async def close(self) -> None:
        await self.http.aclose()

    @classmethod
    def get_link_for_option(cls, instrument: OptionSpread) -> str:
        return f"{cls.base_trade_url}symbol={instrument.instrument}"

    async def get_available_dates(self, symbol: str) -> list[datetime]:
        response = await self.http.post(
            "public/get_instruments",
            json={"expired": False, "instrument_type": "option", "currency": symbol},
        )
        response.raise_for_status()

        dates: list[datetime] = []
        seen: set[int] = set()
        for option in response.json()["result"]:
            expiry_s = int(option["option_details"]["expiry"])
            if expiry_s in seen:
                continue
            seen.add(expiry_s)
            dates.append(datetime.fromtimestamp(expiry_s, tz=timezone.utc))
        return dates

    async def get_option_instruments(self, symbol: str) -> list[dict[str, Any]]:
        response = await self.http.post(
            "public/get_instruments",
            json={"currency": symbol, "instrument_type": "option", "expired": False},
        )
        response.raise_for_status()
        result = response.json().get("result")
        if result is None:
            raise RuntimeError("Failed to fetch option instruments")
        return result

    async def get_option_chain_for_date(self, symbol: str, target_date: datetime) -> list[OptionQuote]:
        instruments = await self.get_option_instruments(symbol)
        string_date = target_date.astimezone(timezone.utc).strftime("%Y%m%d")
        filtered = [inst for inst in instruments if string_date in inst["instrument_name"]]

        return [
            OptionQuote(
                exchange=self.name,
                normalized_name=inst["instrument_name"],
                instrument_name=inst["instrument_name"],
                option_type=inst["option_details"]["option_type"],
                strike=float(inst["option_details"]["strike"]),
                expiry=int(inst["option_details"]["expiry"]) * 1000,
                maker_fee_rate=float(inst["maker_fee_rate"]),
                taker_fee_rate=float(inst["taker_fee_rate"]),
            )
            for inst in filtered
        ]

    async def get_option_ticker(self, instrument_name: str) -> dict[str, float]:
        response = await self.http.post(
            "public/get_ticker",
            json={"instrument_name": instrument_name},
        )
        response.raise_for_status()
        ticker = response.json().get("result")
        if ticker is None:
            raise RuntimeError(f"Failed to fetch ticker for {instrument_name}")

        return {
            "bid_price": _float_field(ticker, "best_bid_price"),
            "ask_price": _float_field(ticker, "best_ask_price"),
            "bid_qty": _float_field(ticker, "best_bid_amount"),
            "ask_qty": _float_field(ticker, "best_ask_amount"),
            "underlying_price": _float_field(
                ticker,
                "underlying_price",
                "index_price",
                "mark_price",
            ),
        }

    async def get_mock_option_chain_prices(self) -> list[OptionQuote]:
        return [
            OptionQuote(
                exchange=self.name,
                normalized_name="XXX-101010-10-C",
                instrument_name="XXX-101010-10-C",
                option_type="P",
                strike=50000,
                expiry=1761000000000,
                maker_fee_rate=0.001,
                taker_fee_rate=0.002,
                bid_price=1000,
                ask_price=1010,
                bid_qty=1,
                ask_qty=1,
                underlying_price=55000,
            ),
            OptionQuote(
                exchange=self.name,
                normalized_name="XXX-101010-10-C",
                instrument_name="XXX-101010-10-C",
                option_type="P",
                strike=50000,
                expiry=1761000000000,
                maker_fee_rate=0.001,
                taker_fee_rate=0.002,
                bid_price=1000,
                ask_price=1010,
                bid_qty=1,
                ask_qty=1,
                underlying_price=55000,
            ),
        ]

    async def get_option_chain_prices(self, symbol: str, target_date: datetime) -> list[OptionQuote]:
        chain = await self.get_option_chain_for_date(symbol, target_date)
        semaphore = asyncio.Semaphore(20)

        async def price_option(opt: OptionQuote) -> OptionQuote | None:
            try:
                async with semaphore:
                    await asyncio.sleep(0.015)
                    ticker = await self.get_option_ticker(opt.instrument_name)
            except Exception as exc:
                print(f"derive ticker skipped {opt.instrument_name}: {exc}")
                return None

            if ticker["bid_price"] * ticker["bid_qty"] < SIZE_THRESHOLD:
                return None

            opt.bid_price = ticker["bid_price"]
            opt.ask_price = ticker["ask_price"]
            opt.bid_qty = ticker["bid_qty"]
            opt.ask_qty = ticker["ask_qty"]
            opt.underlying_price = ticker["underlying_price"]
            return opt

        priced = await asyncio.gather(*(price_option(opt) for opt in chain))
        return [opt for opt in priced if opt is not None]
