from __future__ import annotations

import time
from typing import Any

import requests

from src_python.core.http_client import create_http_client


class DeribitAuth:
    def __init__(self, client_id: str, client_secret: str, testnet: bool = False) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://test.deribit.com/api/v2/" if testnet else "https://www.deribit.com/api/v2/"
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.expiry_time = 0.0

    def _is_token_valid(self) -> bool:
        return self.access_token is not None and time.time() * 1000 < self.expiry_time - 30_000

    async def authenticate(self) -> None:
        client = create_http_client(self.base_url)
        try:
            response = await client.get(
                "public/auth",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            response.raise_for_status()
        finally:
            await client.aclose()
        data = response.json()["result"]
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expiry_time = time.time() * 1000 + int(data["expires_in"]) * 1000

    async def get_auth_header(self) -> dict[str, str]:
        if not self._is_token_valid():
            await self.authenticate()
        return {"Authorization": f"Bearer {self.access_token}"}


class DeribitOptionsTrader:
    def __init__(self, client_id: str, client_secret: str, testnet: bool = False) -> None:
        self.auth = DeribitAuth(client_id, client_secret, testnet)
        self.base_url = self.auth.base_url
        self.http = create_http_client(self.base_url)

    async def close(self) -> None:
        await self.http.aclose()

    async def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        headers = await self.auth.get_auth_header()
        response = await self.http.get(f"{self.base_url}{endpoint}", headers=headers, params=params or {})
        response.raise_for_status()
        return response.json()["result"]

    async def get_instrument(self, instrument_name: str) -> Any:
        return await self._request("public/get_instrument", {"instrument_name": instrument_name})

    async def get_order_book(self, instrument_name: str) -> Any:
        return await self._request("public/get_order_book", {"instrument_name": instrument_name})

    async def place_order(
        self,
        *,
        instrument_name: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float | None = None,
        time_in_force: str = "fill_or_kill",
        label: str | None = None,
    ) -> Any:
        endpoint = "private/buy" if side == "buy" else "private/sell"
        payload: dict[str, Any] = {
            "instrument_name": instrument_name,
            "amount": amount,
            "type": order_type,
            "time_in_force": time_in_force,
            "label": label or f"arb-{int(time.time() * 1000)}",
        }
        if price is not None and order_type == "limit":
            payload["price"] = price

        headers = await self.auth.get_auth_header()
        url = f"{self.base_url}{endpoint}"
        print("DERIBIT ORDER:", url, payload)
        try:
            response = await self.http.get(url, headers=headers, params=payload)
            response.raise_for_status()
            return response.json()["result"]
        except requests.RequestException as exc:
            print("Network/Config Error:", exc)
            return None

    async def cancel_order(self, order_id: str) -> Any:
        return await self._request("private/cancel", {"order_id": order_id})

    async def get_open_orders(self, instrument_name: str | None = None) -> Any:
        params = {"instrument_name": instrument_name} if instrument_name else {}
        return await self._request("private/get_open_orders", params)

    async def get_positions(self) -> Any:
        return await self._request("private/get_positions")
