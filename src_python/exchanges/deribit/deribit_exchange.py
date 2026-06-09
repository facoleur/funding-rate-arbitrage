from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from src_python.core.http_client import create_http_client
from src_python.exchanges import OptionQuote
from src_python.exchanges.derive.derive_exchange import SIZE_THRESHOLD
from src_python.services.compare_options import OptionSpread

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


class DeribitExchange:
    name = "deribit"
    base_trade_url = "https://test.deribit.com/options"

    def __init__(self) -> None:
        self.http = create_http_client("https://www.deribit.com/api/v2/")

    async def close(self) -> None:
        await self.http.aclose()

    @classmethod
    def get_link_for_option(cls, instrument: OptionSpread) -> str:
        return f"{cls.base_trade_url}/{instrument.symbol}/{instrument.symbol_date}/{instrument.instrument}"

    async def get_option_instruments(self, symbol: str) -> list[dict[str, Any]]:
        response = await self.http.post(
            "",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "public/get_instruments",
                "params": {"currency": symbol.upper(), "kind": "option", "expired": False},
            },
        )
        response.raise_for_status()
        result = response.json().get("result")
        if result is None:
            raise RuntimeError("Failed to fetch option instruments")
        return result

    async def get_option_chain_for_date(self, symbol: str, target_date: datetime) -> list[OptionQuote]:
        instruments = await self.get_option_instruments(symbol)
        target = target_date.astimezone(timezone.utc)
        reverse_months = {v: k for k, v in MONTHS.items()}
        target_date_str = f"{target.day:02d}{reverse_months[f'{target.month:02d}']}{str(target.year)[-2:]}"
        filtered = [inst for inst in instruments if target_date_str in inst["instrument_name"]]

        return [
            OptionQuote(
                exchange=self.name,
                normalized_name=normalize_instrument_name(inst["instrument_name"]),
                instrument_name=inst["instrument_name"],
                option_type="C" if inst["option_type"] == "call" else "P",
                strike=float(inst["strike"]),
                expiry=int(inst["expiration_timestamp"]),
                maker_fee_rate=float(inst["maker_commission"]),
                taker_fee_rate=float(inst["taker_commission"]),
            )
            for inst in filtered
        ]

    async def get_option_ticker(self, instrument_name: str) -> dict[str, float]:
        response = await self.http.post(
            "",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "public/ticker",
                "params": {"instrument_name": instrument_name},
            },
        )
        response.raise_for_status()
        ticker = response.json().get("result")
        if ticker is None:
            raise RuntimeError(f"Failed to fetch ticker for {instrument_name}")

        underlying_price = _float_field(ticker, "underlying_price", "index_price", "mark_price")
        best_bid = _float_field(ticker, "best_bid_price")
        best_ask = _float_field(ticker, "best_ask_price")
        return {
            "bid_price": best_bid * underlying_price,
            "ask_price": best_ask * underlying_price,
            "bid_price_raw": best_bid,
            "ask_price_raw": best_ask,
            "underlying_price": underlying_price,
            "bid_qty": _float_field(ticker, "best_bid_amount"),
            "ask_qty": _float_field(ticker, "best_ask_amount"),
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
                bid_price=980,
                ask_price=990,
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
                print(f"deribit ticker skipped {opt.instrument_name}: {exc}")
                return None

            if ticker["bid_price"] * ticker["bid_qty"] < SIZE_THRESHOLD:
                return None

            opt.normalized_name = normalize_instrument_name(opt.instrument_name)
            opt.bid_price = ticker["bid_price"]
            opt.ask_price = ticker["ask_price"]
            opt.bid_price_raw = ticker["bid_price_raw"]
            opt.ask_price_raw = ticker["ask_price_raw"]
            opt.underlying_price = ticker["underlying_price"]
            opt.bid_qty = ticker["bid_qty"]
            opt.ask_qty = ticker["ask_qty"]
            return opt

        priced = await asyncio.gather(*(price_option(opt) for opt in chain))
        return [opt for opt in priced if opt is not None]


def normalize_instrument_name(instrument: str) -> str:
    match = re.match(r"^([A-Z]+)-(\d{2})([A-Z]{3})(\d{2})-(\d+)-(C|P)$", instrument)
    if not match:
        raise ValueError(f"Invalid instrument format: {instrument}")

    coin, day, month_str, year, strike, side = match.groups()
    month = MONTHS.get(month_str.upper())
    if month is None:
        raise ValueError(f"Invalid month: {month_str}")

    return f"{coin}-20{year}{month}{day}-{strike}-{side}"
