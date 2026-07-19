from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

log = logging.getLogger(__name__)


class CircuitOpenError(RuntimeError):
    """Raised when the circuit breaker is open for an exchange."""


@dataclass
class CircuitBreaker:
    """Trip after `failure_threshold` consecutive failures within `window_sec`.
    While tripped, calls raise CircuitOpenError until `cooldown_sec` elapses."""

    failure_threshold: int = 5
    window_sec: float = 30.0
    cooldown_sec: float = 30.0

    _failures: list[float] = field(default_factory=list)
    _opened_at: float | None = None

    def record_success(self) -> None:
        self._failures.clear()
        self._opened_at = None

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failures.append(now)
        self._failures = [t for t in self._failures if now - t < self.window_sec]
        if len(self._failures) >= self.failure_threshold and self._opened_at is None:
            self._opened_at = now
            log.warning("circuit breaker OPEN (failures=%d)", len(self._failures))

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self.cooldown_sec:
            log.info("circuit breaker cooldown elapsed — HALF-OPEN")
            self._opened_at = None
            self._failures.clear()
            return False
        return True


class RestClient:
    """Async HTTP client with per-exchange leaky-bucket rate limiting, retry
    on 429/5xx with exponential backoff, and a circuit breaker.

    One instance per exchange. Two priority lanes: `normal` and `priority`
    (executor) so screener/metadata refresh can't starve the executor."""

    def __init__(
        self,
        exchange: str,
        base_url: str,
        rate_limit_per_sec: int,
        *,
        priority_reserve_per_sec: int = 5,
        timeout_sec: float = 15.0,
        max_retries: int = 3,
        backoff_base_sec: float = 0.5,
        backoff_cap_sec: float = 10.0,
    ) -> None:
        self.exchange = exchange
        self.base_url = base_url
        self.max_retries = max_retries
        self.backoff_base_sec = backoff_base_sec
        self.backoff_cap_sec = backoff_cap_sec

        normal_rate = max(1, rate_limit_per_sec - priority_reserve_per_sec)
        self._normal_limiter = AsyncLimiter(max_rate=normal_rate, time_period=1.0)
        self._priority_limiter = AsyncLimiter(
            max_rate=priority_reserve_per_sec, time_period=1.0
        )

        self._breaker = CircuitBreaker()
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_sec,
            headers={"User-Agent": f"option-arb/{exchange}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> RestClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        priority: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._breaker.is_open:
            raise CircuitOpenError(f"circuit open for {self.exchange}")

        limiter = self._priority_limiter if priority else self._normal_limiter
        attempt = 0
        while True:
            async with limiter:
                try:
                    resp = await self._client.request(method, path, **kwargs)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    self._breaker.record_failure()
                    if attempt >= self.max_retries:
                        raise
                    await self._sleep_backoff(attempt)
                    attempt += 1
                    continue

            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                self._breaker.record_failure()
                if attempt >= self.max_retries:
                    resp.raise_for_status()
                    return resp
                retry_after = self._parse_retry_after(resp)
                await asyncio.sleep(retry_after or self._backoff_delay(attempt))
                attempt += 1
                continue

            self._breaker.record_success()
            return resp

    async def get(self, path: str, *, priority: bool = False, **kwargs: Any) -> Any:
        r = await self.request("GET", path, priority=priority, **kwargs)
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, *, priority: bool = False, **kwargs: Any) -> Any:
        r = await self.request("POST", path, priority=priority, **kwargs)
        r.raise_for_status()
        return r.json()

    def _backoff_delay(self, attempt: int) -> float:
        return min(self.backoff_base_sec * (2**attempt), self.backoff_cap_sec)

    async def _sleep_backoff(self, attempt: int) -> None:
        await asyncio.sleep(self._backoff_delay(attempt))

    @staticmethod
    def _parse_retry_after(resp: httpx.Response) -> float | None:
        val = resp.headers.get("Retry-After")
        if not val:
            return None
        try:
            return float(val)
        except ValueError:
            return None
