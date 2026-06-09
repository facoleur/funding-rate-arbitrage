from __future__ import annotations

from typing import Protocol


class OptionsExchange(Protocol):
    name: str

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
        ...

