from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime

import httpx

from option_arb.config import AlertsConfig, settings
from option_arb.db.models import Alert, AlertLevel
from option_arb.db.session import get_session
from option_arb.events import Event, bus

log = logging.getLogger(__name__)

_MDV2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def escape_mdv2(text: str) -> str:
    """Escape MarkdownV2 special characters — Telegram rejects unescaped
    `._*[]()~`` etc. Port of the TS `escapeMdV2` helper."""
    return _MDV2_SPECIAL.sub(r"\\\1", str(text))


def deep_link(
    exchange: str, instrument: str, *, symbol: str | None = None, symbol_date: str | None = None
) -> str | None:
    """Best-effort deep link back to the exchange trading UI."""
    if exchange == "derive":
        return f"https://app.derive.xyz/trade/options?symbol={instrument}"
    if exchange == "deribit" and symbol and symbol_date:
        return f"https://deribit.com/options/{symbol}/{symbol_date}/{instrument}"
    return None


def format_opportunity(event: Event) -> str:
    p = event.payload
    instrument = p.get("instrument", "")
    apr = p.get("apr_pct", 0)
    buy_from = p.get("buy_from", "")
    sell_to = p.get("sell_to", "")
    max_notional = p.get("max_notional_usd", 0)

    lines = [
        f"*{escape_mdv2(instrument)}*",
        f"APR: {escape_mdv2(f'{apr:.1f}%')} · Notional: {escape_mdv2(f'${max_notional:.0f}')}",
        f"Buy: {escape_mdv2(buy_from)} → Sell: {escape_mdv2(sell_to)}",
    ]
    return "\n".join(lines)


def format_event(event: Event) -> str:
    if event.type == "opportunity_detected":
        return format_opportunity(event)
    icon = {"info": "ℹ️", "warn": "⚠️", "error": "🚨"}.get(event.level, "•")  # noqa: RUF001
    return f"{icon} *{escape_mdv2(event.type)}*\n{escape_mdv2(event.message)}"


class TelegramSender:
    """Async Telegram sender — one connection reused across calls."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._client = httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send(self, text: str) -> bool:
        if not self.bot_token or not self.chat_id:
            log.debug("telegram disabled (missing BOT_TOKEN / CHAT_ID)")
            return False
        try:
            r = await self._client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
            )
            if r.status_code != 200:
                log.warning("telegram %d: %s", r.status_code, r.text[:200])
                return False
            return True
        except Exception as e:
            log.exception("telegram send failed: %s", e)
            return False


class Alerter:
    """Consumes events from the bus and dispatches to Telegram + DB.

    Filters:
      - APR-gated events (opportunity_detected) require apr >= threshold
      - Level filter matches config.alerts.telegram.levels"""

    def __init__(self, alerts_cfg: AlertsConfig, sender: TelegramSender | None = None) -> None:
        self.cfg = alerts_cfg
        self.sender = sender or TelegramSender(settings.bot_token, settings.chat_id)
        self._stop = asyncio.Event()

    async def run(self) -> None:
        q = bus.subscribe()
        log.info("alerter started")
        try:
            while not self._stop.is_set():
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                except TimeoutError:
                    continue
                await self._handle(event)
        finally:
            bus.unsubscribe(q)
            await self.sender.aclose()

    async def stop(self) -> None:
        self._stop.set()

    async def _handle(self, event: Event) -> None:
        # persist every event to DB (audit trail)
        try:
            async with get_session() as sess:
                sess.add(
                    Alert(
                        level=AlertLevel(event.level),
                        channel="bus",
                        message=event.message,
                        sent_at=datetime.now(UTC),
                        meta=json.dumps({"type": event.type, "payload": event.payload}),
                    )
                )
                await sess.commit()
        except Exception as e:
            log.exception("alert persist failed: %s", e)

        # dispatch to Telegram if enabled + level passes filter
        tg = self.cfg.telegram
        if not tg.enabled:
            return
        if event.level not in tg.levels:
            return
        if event.type == "opportunity_detected":
            apr = float(event.payload.get("apr_pct", 0))
            if apr < tg.apr_threshold_pct:
                return
        text = format_event(event)
        ok = await self.sender.send(text)
        if ok:
            log.info("telegram sent (%s): %s", event.type, event.message[:80])
