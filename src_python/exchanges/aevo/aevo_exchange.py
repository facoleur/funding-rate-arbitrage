from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from src_python.core.http_client import create_http_client
from src_python.exchanges import OptionQuote

SIZE_THRESHOLD = 100

MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


def _float_field(data: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return float(value)
    return default


def _nested_float(data: dict[str, Any], key: str, nested_key: str, default: float = 0.0) -> float:
    value = data.get(key)
    if not isinstance(value, dict):
        return default
    nested = value.get(nested_key)
    if nested in (None, ""):
        return default
    return float(nested)


class AevoExchange:
    name = "aevo"

    def __init__(self) -> None:
        self.http = create_http_client("https://api.aevo.xyz/")
        self._semaphore = asyncio.Semaphore(1)

    async def close(self) -> None:
        await self.http.aclose()

    async def get_option_instruments(self, symbol: str) -> list[dict[str, Any]]:
        response = await self.http.get("/markets", params={"asset": symbol, "instrument_type": "OPTION"})
        response.raise_for_status()
        return response.json()

    async def get_option_chain_for_date(self, symbol: str, target_date: datetime) -> list[OptionQuote]:
        instruments = await self.get_option_instruments(symbol)
        start = target_date.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        filtered = []
        for inst in instruments:
            expiry_ms = int(inst["expiry"]) // 1_000_000
            if int(start.timestamp() * 1000) <= expiry_ms < int(end.timestamp() * 1000):
                filtered.append(inst)

        return [
            OptionQuote(
                exchange=self.name,
                normalized_name=inst["instrument_name"],
                instrument_name=inst["instrument_name"],
                option_type=inst["option_type"],
                strike=float(inst["strike"]),
                expiry=int(inst["expiry"]) // 1_000_000,
                maker_fee_rate=float(inst.get("maker_fee_rate") or 0),
                taker_fee_rate=float(inst.get("taker_fee_rate") or 0),
            )
            for inst in filtered
        ]

    async def get_option_ticker(self, instrument_name: str) -> dict[str, float]:
        response = await self.http.get(f"/instrument/{instrument_name}")
        response.raise_for_status()
        ticker = response.json()
        if not ticker:
            raise RuntimeError(f"Failed to fetch ticker for {instrument_name}")

        return {
            "bid_price": _nested_float(ticker, "best_bid", "price"),
            "ask_price": _nested_float(ticker, "best_ask", "price"),
            "bid_qty": _nested_float(ticker, "best_bid", "amount"),
            "ask_qty": _nested_float(ticker, "best_ask", "amount"),
            "underlying_price": _float_field(ticker, "index_price", "underlying_price", "mark_price"),
        }

    def get_normalized_option_name(self, instrument_name: str) -> str:
        parts = instrument_name.split("-")
        if len(parts) != 4:
            return instrument_name

        underlying, date_part, strike, option_type = parts
        day = date_part[:2]
        month = MONTHS.get(date_part[2:5].upper())
        year = "20" + date_part[5:7]
        if month is None:
            return instrument_name

        return f"{underlying}-{year}{month}{day}-{strike}-{option_type}"

    async def get_option_chain_prices(self, symbol: str, target_date: datetime) -> list[OptionQuote]:
        chain = await self.get_option_chain_for_date(symbol, target_date)

        async def price_option(opt: OptionQuote) -> OptionQuote | None:
            try:
                async with self._semaphore:
                    await asyncio.sleep(0.4)
                    ticker = await self.get_option_ticker(opt.instrument_name)
            except Exception as exc:
                print(f"aevo ticker skipped {opt.instrument_name}: {exc}")
                return None

            if ticker["bid_price"] * ticker["bid_qty"] < SIZE_THRESHOLD:
                return None

            opt.option_type = "C" if opt.option_type == "call" else "P"
            opt.normalized_name = self.get_normalized_option_name(opt.instrument_name)
            opt.bid_price = ticker["bid_price"]
            opt.ask_price = ticker["ask_price"]
            opt.bid_qty = ticker["bid_qty"]
            opt.ask_qty = ticker["ask_qty"]
            opt.maker_fee_rate = 0.0
            opt.taker_fee_rate = 0.0
            opt.underlying_price = ticker["underlying_price"]
            return opt

        priced = await asyncio.gather(*(price_option(opt) for opt in chain))
        return [opt for opt in priced if opt is not None]
