from __future__ import annotations

from pathlib import Path

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
