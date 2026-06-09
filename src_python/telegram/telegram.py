from __future__ import annotations

import os
import re
from urllib.parse import quote

import requests

from src_python.core.env import load_dotenv
from src_python.core.http_client import create_http_client
from src_python.exchanges.deribit.deribit_exchange import DeribitExchange
from src_python.exchanges.derive.derive_exchange import DeriveExchange
from src_python.services.compare_options import OptionSpread

load_dotenv()


def _is_empty_string(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _escape_md_v2(text: object) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", str(text))


def _mk_link(name: str, url: str | None) -> str:
    if _is_empty_string(url):
        return _escape_md_v2(name)
    return f"[{_escape_md_v2(name)}]({quote(str(url), safe=':/?=&%')})"


def _add_links(item: OptionSpread) -> None:
    try:
        if item.buy_from == "derive":
            item.buyLink = DeriveExchange.get_link_for_option(item)
        elif item.buy_from == "deribit":
            item.buyLink = DeribitExchange.get_link_for_option(item)
    except Exception as exc:
        print("link generation error (buy):", exc)
        item.buyLink = ""

    try:
        if item.sell_to == "derive":
            item.sellLink = DeriveExchange.get_link_for_option(item)
        elif item.sell_to == "deribit":
            item.sellLink = DeribitExchange.get_link_for_option(item)
    except Exception as exc:
        print("link generation error (sell):", exc)
        item.sellLink = ""


def _format_message(items: list[OptionSpread]) -> str:
    parts = []
    for item in items:
        title = f"*{_escape_md_v2(item.symbol)} {_escape_md_v2(item.instrument)}*"
        buy_part = f"Buy from: {_mk_link(item.buy_from, item.buyLink)} at {_escape_md_v2(item.buy_ask)}"
        sell_part = f"Sell to: {_mk_link(item.sell_to, item.sellLink)} at {_escape_md_v2(item.sell_bid)}"
        tail = f"Spread: {_escape_md_v2(item.spread)} APR: {_escape_md_v2(item.apr)}"
        parts.append(f"{title}\n{buy_part}\n{sell_part}\n{tail}\n")
    return "\n".join(parts)


async def _post_message(message: str) -> None:
    if _is_empty_string(message):
        return

    bot_token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if _is_empty_string(bot_token) or _is_empty_string(chat_id):
        return

    client = create_http_client("https://api.telegram.org/")
    try:
        response = await client.post(
            f"bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
        )
        response.raise_for_status()
    except requests.RequestException:
        pass
    finally:
        await client.aclose()


async def send_telegram_message_batch(data: list[OptionSpread]) -> None:
    for item in data:
        if item.apr < 10:
            return
        _add_links(item)

    await _post_message(_format_message(data))


async def send_telegram_message(item: OptionSpread) -> None:
    if item.apr < 10:
        print(f"APR {item.apr}% is below threshold, not sending Telegram message.")
        return

    _add_links(item)
    await _post_message(_format_message([item]))
