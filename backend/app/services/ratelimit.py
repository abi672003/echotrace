import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

import httpx

from app.config import get_settings

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class TokenBucket:
    """Async token bucket: `capacity` tokens, refilled continuously at `refill_rate` tokens/second."""

    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._clock = clock
        self._sleep = sleep
        self._tokens = capacity
        self._last_refill = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    async def acquire(self, tokens: float = 1.0) -> None:
        while True:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            deficit = tokens - self._tokens
            await self._sleep(deficit / self.refill_rate)


@lru_cache
def get_bucket(provider: str) -> TokenBucket:
    settings = get_settings()
    if provider == "regulations":
        return TokenBucket(
            capacity=settings.REGULATIONS_REQS_PER_HOUR,
            refill_rate=settings.REGULATIONS_REQS_PER_HOUR / 3600,
        )
    if provider in ("gemini", "groq"):
        return TokenBucket(
            capacity=settings.LLM_REQS_PER_MINUTE,
            refill_rate=settings.LLM_REQS_PER_MINUTE / 60,
        )
    raise ValueError(f"Unknown provider: {provider}")


async def with_retries(
    fn: Callable[[], Awaitable[httpx.Response]],
    max_tries: int = 5,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rand: Callable[[], float] = random.random,
) -> httpx.Response:
    """Call `fn`, retrying on 429/5xx with exponential backoff + jitter (honouring `Retry-After`)."""
    response: httpx.Response | None = None
    for attempt in range(max_tries):
        response = await fn()
        if response.status_code not in RETRYABLE_STATUS_CODES:
            return response
        if attempt == max_tries - 1:
            break

        retry_after = response.headers.get("Retry-After")
        delay = base_delay * (2**attempt)
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                pass
        jitter = delay * rand() * 0.5
        await sleep(delay + jitter)

    assert response is not None
    return response
