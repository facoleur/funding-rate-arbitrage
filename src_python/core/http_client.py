from __future__ import annotations

import asyncio
from typing import Any

import requests


class AsyncHttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ArbitrageBot/1.0"})

    async def get(self, path: str, **kwargs: Any) -> requests.Response:
        return await asyncio.to_thread(self.session.get, self._url(path), timeout=15.0, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> requests.Response:
        return await asyncio.to_thread(self.session.post, self._url(path), timeout=15.0, **kwargs)

    async def aclose(self) -> None:
        await asyncio.to_thread(self.session.close)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


def create_http_client(base_url: str) -> AsyncHttpClient:
    return AsyncHttpClient(base_url)

