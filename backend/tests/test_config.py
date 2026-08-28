from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from option_arb.config import AppConfig, load_config


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nope.yaml")
    assert isinstance(cfg, AppConfig)
    assert cfg.thresholds.min_apr_pct == 10.0


def test_load_config_from_root_yaml() -> None:
    cfg = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
    assert "derive" in cfg.exchanges
    assert cfg.executor.mode in ("paper", "live")
    assert cfg.limits.max_positions_open >= 1
    assert cfg.thresholds.min_buy_premium_usd == 10
    assert cfg.executor.ioc_slippage_limit_pct == 2
    assert cfg.limits.max_buy_premium_per_trade_usd == 50


def test_removed_config_names_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"thresholds": {"min_notional_usd": 10}})
