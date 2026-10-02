import httpx
import pytest

from app.services.ratelimit import TokenBucket, with_retries


class FakeClock:
    """A controllable clock + async sleep that advances itself instead of waiting."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += seconds


@pytest.mark.asyncio
async def test_token_bucket_allows_immediate_acquire_up_to_capacity() -> None:
    clock = FakeClock()
    bucket = TokenBucket(capacity=2, refill_rate=1, clock=clock.time, sleep=clock.sleep)

    await bucket.acquire()
    await bucket.acquire()

    assert clock.sleep_calls == []


@pytest.mark.asyncio
async def test_token_bucket_waits_for_refill_when_empty() -> None:
    clock = FakeClock()
    bucket = TokenBucket(capacity=1, refill_rate=1, clock=clock.time, sleep=clock.sleep)

    await bucket.acquire()  # drains the single starting token
    await bucket.acquire()  # must wait ~1s for one token to refill

    assert clock.sleep_calls == [pytest.approx(1.0)]
    assert clock.now == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_token_bucket_refills_gradually_over_elapsed_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(capacity=5, refill_rate=2, clock=clock.time, sleep=clock.sleep)

    for _ in range(5):
        await bucket.acquire()
    assert clock.sleep_calls == []

    clock.now += 1.5  # 2 tokens/sec * 1.5s = 3 tokens refilled
    await bucket.acquire()
    await bucket.acquire()
    await bucket.acquire()
    assert clock.sleep_calls == []

    await bucket.acquire()  # bucket empty again, must wait
    assert clock.sleep_calls == [pytest.approx(0.5)]


@pytest.mark.asyncio
async def test_with_retries_retries_on_5xx_then_succeeds() -> None:
    clock = FakeClock()
    responses = [httpx.Response(503), httpx.Response(503), httpx.Response(200)]
    calls = iter(responses)

    async def fn() -> httpx.Response:
        return next(calls)

    result = await with_retries(fn, base_delay=1.0, sleep=clock.sleep, rand=lambda: 0.0)

    assert result.status_code == 200
    # exponential backoff with no jitter: 1.0, then 2.0
    assert clock.sleep_calls == [pytest.approx(1.0), pytest.approx(2.0)]


@pytest.mark.asyncio
async def test_with_retries_honours_retry_after_header() -> None:
    clock = FakeClock()
    responses = [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200)]
    calls = iter(responses)

    async def fn() -> httpx.Response:
        return next(calls)

    result = await with_retries(fn, base_delay=1.0, sleep=clock.sleep, rand=lambda: 0.0)

    assert result.status_code == 200
    assert clock.sleep_calls == [pytest.approx(3.0)]


@pytest.mark.asyncio
async def test_with_retries_gives_up_after_max_tries() -> None:
    clock = FakeClock()

    async def fn() -> httpx.Response:
        return httpx.Response(500)

    result = await with_retries(fn, max_tries=3, base_delay=0.1, sleep=clock.sleep, rand=lambda: 0.0)

    assert result.status_code == 500
    assert len(clock.sleep_calls) == 2  # sleeps between attempts, not after the last one


@pytest.mark.asyncio
async def test_with_retries_returns_immediately_on_non_retryable_status() -> None:
    clock = FakeClock()

    async def fn() -> httpx.Response:
        return httpx.Response(404)

    result = await with_retries(fn, sleep=clock.sleep)

    assert result.status_code == 404
    assert clock.sleep_calls == []
