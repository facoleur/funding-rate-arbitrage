from __future__ import annotations

import logging

from option_arb.config import AppConfig, ExchangeConfig, settings
from option_arb.exchanges.aevo import AevoExchange
from option_arb.exchanges.auth import build_authenticator
from option_arb.exchanges.base import AbstractExchange
from option_arb.exchanges.deribit import DeribitExchange
from option_arb.exchanges.derive import DeriveExchange
from option_arb.exchanges.http import RestClient
from option_arb.exchanges.mock import MockExchange
from option_arb.exchanges.slippage import SlippageModel

log = logging.getLogger(__name__)


def _build_real_exchange(name: str, ex_cfg: ExchangeConfig, network: str) -> AbstractExchange:
    rest = RestClient(
        exchange=name,
        base_url=ex_cfg.rest_base_url,
        rate_limit_per_sec=ex_cfg.rest_rate_limit_per_sec,
    )
    auth = build_authenticator(name, settings, network=network)
    if name == "deribit":
        return DeribitExchange(rest, ws_url=ex_cfg.ws_url, auth=auth)
    if name == "derive":
        return DeriveExchange(rest, ws_url=ex_cfg.ws_url, auth=auth)
    if name == "aevo":
        return AevoExchange(rest, ws_url=ex_cfg.ws_url, auth=auth)
    raise KeyError(f"unknown exchange '{name}'")


def build_exchanges(config: AppConfig) -> dict[str, AbstractExchange]:
    """Instantiate one adapter per configured exchange.

    **Safety**: when `executor.mode == 'paper'`, every real adapter is
    wrapped in a `MockExchange(upstream=real)` so that:
      - `list_instruments` / `get_orderbook_l2` / WS ticker parsing all
        proxy the real exchange (real market data).
      - `place_order` is intercepted and simulated via `SlippageModel`,
        NEVER hitting the real API.

    This means `executor.mode` is the single knob controlling whether the
    system trades for real or on paper — no separate wiring required."""
    out: dict[str, AbstractExchange] = {}
    is_paper = config.executor.mode == "paper"
    slippage = SlippageModel() if is_paper else None

    for name in config.screener.exchanges:
        ex_cfg = config.exchanges.get(name)
        if ex_cfg is None:
            raise KeyError(f"missing config for exchange '{name}'")
        real = _build_real_exchange(name, ex_cfg, ex_cfg.network)
        if is_paper:
            log.info("paper mode: wrapping %s in MockExchange (upstream=%s)", name, ex_cfg.network)
            out[name] = MockExchange(name=name, upstream=real, slippage=slippage)
        else:
            out[name] = real
    return out


async def close_exchanges(exchanges: dict[str, AbstractExchange]) -> None:
    seen: set[int] = set()
    for ex in exchanges.values():
        # unwrap: if it's a MockExchange holding a real upstream, close that too
        rest = getattr(ex, "rest", None)
        upstream = getattr(ex, "upstream", None)
        for target_rest in (rest, getattr(upstream, "rest", None) if upstream else None):
            if target_rest is None or id(target_rest) in seen:
                continue
            await target_rest.aclose()
            seen.add(id(target_rest))
