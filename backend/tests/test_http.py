from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from option_arb.exchanges.http import CircuitOpenError, RestClient


@pytest.mark.asyncio
async def test_get_success() -> None:
    async with RestClient("test", "https://api.test", rate_limit_per_sec=100) as client:
        with respx.mock(base_url="https://api.test") as mock:
            mock.get("/x").mock(return_value=httpx.Response(200, json={"ok": True}))
            data = await client.get("/x")
            assert data == {"ok": True}


@pytest.mark.asyncio
async def test_retry_on_429_then_success() -> None:
    async with RestClient(
        "test",
        "https://api.test",
        rate_limit_per_sec=100,
        backoff_base_sec=0.01,
        backoff_cap_sec=0.01,
    ) as client:
        with respx.mock(base_url="https://api.test") as mock:
            mock.get("/x").mock(
                side_effect=[
                    httpx.Response(429, headers={"Retry-After": "0"}),
                    httpx.Response(200, json={"ok": True}),
                ]
            )
            data = await client.get("/x")
            assert data == {"ok": True}


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures() -> None:
    async with RestClient(
        "test",
        "https://api.test",
        rate_limit_per_sec=100,
        max_retries=0,
        backoff_base_sec=0.001,
        backoff_cap_sec=0.001,
    ) as client:
        with respx.mock(base_url="https://api.test") as mock:
            mock.get("/x").mock(return_value=httpx.Response(503))
            # burn through failure_threshold (default 5) failures
            for _ in range(5):
                with pytest.raises(httpx.HTTPStatusError):
                    await client.get("/x")
            # circuit now open — next call raises CircuitOpenError without hitting network
            with pytest.raises(CircuitOpenError):
                await client.get("/x")


@pytest.mark.asyncio
async def test_rate_limiter_serialises_calls() -> None:
    """With rate_limit_per_sec=2, two calls take at most a small delay
    but a third call must wait ~0.5s."""
    async with RestClient(
        "test",
        "https://api.test",
        rate_limit_per_sec=2,
        priority_reserve_per_sec=0,
    ) as client:
        with respx.mock(base_url="https://api.test") as mock:
            mock.get("/x").mock(return_value=httpx.Response(200, json={"ok": True}))
            start = asyncio.get_event_loop().time()
            await asyncio.gather(*(client.get("/x") for _ in range(3)))
            elapsed = asyncio.get_event_loop().time() - start
            # 3 calls at 2 rps: at least ~0.4s
            assert elapsed >= 0.4
