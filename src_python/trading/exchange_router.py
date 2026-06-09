from __future__ import annotations

from src_python.trading.deribit_exchange import DeribitExchange
from src_python.trading.derive_exchange import DeriveExchange
from src_python.trading.option_exchange import OptionsExchange

_exchange_map: dict[str, OptionsExchange] | None = None


def get_exchange(name: str) -> OptionsExchange:
    global _exchange_map
    if _exchange_map is None:
        _exchange_map = {
            "deribit": DeribitExchange(),
            "derive": DeriveExchange(),
        }

    exchange = _exchange_map.get(name.lower())
    print(name, exchange)
    if exchange is None:
        raise ValueError(f"Exchange not supported: {name}")
    return exchange

