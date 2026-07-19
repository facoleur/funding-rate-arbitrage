from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root = 3 parents up from this file (src/option_arb/config.py → src/ → backend/ → root)
_REPO_ROOT = Path(__file__).resolve().parents[3]


class ScreenerConfig(BaseModel):
    poll_interval_ms: int = 500
    underlyings: list[str] = Field(default_factory=lambda: ["BTC", "ETH"])
    exchanges: list[str] = Field(default_factory=lambda: ["derive", "deribit", "aevo"])
    max_expiries_ahead: int = 8
    metadata_refresh_hours: int = 6


class Thresholds(BaseModel):
    min_apr_pct: float = 10.0
    min_notional_usd: float = 20.0
    size_threshold_usd: float = 100.0


class ExecutorConfig(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    order_type: Literal["ioc_limit"] = "ioc_limit"
    max_slippage_pct: float = 2.0
    walk_book: bool = True
    poll_interval_ms: int = 200
    fresh_fetch_timeout_ms: int = 500


class Limits(BaseModel):
    max_notional_per_trade_usd: float = 500.0
    max_positions_open: int = 10
    max_daily_loss_usd: float = 100.0
    kill_switch_file: str = "/data/EXECUTOR_DISABLED"


class RebalancerConfig(BaseModel):
    poll_interval_sec: int = 300
    expiry_warning_hours: int = 24
    balance_low_threshold_usd: float = 100.0


class ExchangeConfig(BaseModel):
    rest_rate_limit_per_sec: int
    ws_max_subscriptions: int
    rest_base_url: str
    ws_url: str
    network: Literal["mainnet", "testnet"] = "testnet"


class TelegramConfig(BaseModel):
    enabled: bool = True
    apr_threshold_pct: float = 10.0
    levels: list[str] = Field(default_factory=lambda: ["info", "warn", "error"])


class AlertsConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class AppConfig(BaseModel):
    screener: ScreenerConfig = Field(default_factory=ScreenerConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    limits: Limits = Field(default_factory=Limits)
    rebalancer: RebalancerConfig = Field(default_factory=RebalancerConfig)
    exchanges: dict[str, ExchangeConfig] = Field(default_factory=dict)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)


class Settings(BaseSettings):
    """Env-loaded secrets and paths. YAML holds runtime config.

    `.env` is looked up FIRST at the repo root (so `make dev-executor`
    from any directory works), then at CWD as fallback."""

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://option_arb:option_arb@localhost:5432/option_arb"
    alembic_database_url: str = ""  # if empty, derived from database_url
    config_path: str = "config.yaml"

    bot_token: str = ""
    chat_id: str = ""

    # Deribit — OAuth client_credentials
    deribit_client_id: str = ""
    deribit_client_secret: str = ""

    # Derive (Lyra V2) — EIP-712 session key signing
    derive_wallet_address: str = ""
    derive_subaccount_id: int = 0
    derive_session_private_key: str = ""

    # Aevo — EIP-712 signing key
    aevo_wallet_address: str = ""
    aevo_account: str = ""
    aevo_signing_key: str = ""

    @property
    def resolved_alembic_url(self) -> str:
        if self.alembic_database_url:
            return self.alembic_database_url
        # derive sync URL from async URL
        return (self.database_url
                .replace("+asyncpg", "+psycopg2")
                .replace("+aiosqlite", ""))


def load_config(path: str | Path | None = None) -> AppConfig:
    settings = Settings()
    # Try, in order: explicit arg → CONFIG_PATH env → CWD/config.yaml → repo root/config.yaml
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    else:
        candidates += [Path(settings.config_path), Path("config.yaml"), _REPO_ROOT / "config.yaml"]
    for cand in candidates:
        if cand.exists():
            with cand.open() as f:
                raw = yaml.safe_load(f) or {}
            return AppConfig.model_validate(raw)
    return AppConfig()


settings = Settings()
