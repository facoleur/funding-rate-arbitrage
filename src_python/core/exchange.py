from __future__ import annotations

from typing import Protocol


class Exchange(Protocol):
    name: str

    def get_fees(self) -> dict[str, float]:
        ...


class BaseExchange:
    pass

