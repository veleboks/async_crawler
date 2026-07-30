import asyncio
import time

import pytest

from crawler import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_observes_required_delay():
    limiter = RateLimiter(max_requests_per_second=1_000, jitter=0)
    started_at: list[float] = []

    for _ in range(2):
        async with limiter("example.test", required_delay=0.02):
            started_at.append(time.perf_counter())

    assert started_at[1] - started_at[0] >= 0.018

    stats = limiter.get_stats()
    assert stats.requests_started == 2
    assert stats.total_wait >= 0
    assert stats.average_wait >= 0
    assert stats.average_interval == pytest.approx(
        started_at[1] - started_at[0],
        abs=0.003,
    )


@pytest.mark.asyncio
async def test_different_hostnames_wait_independently():
    limiter = RateLimiter(max_requests_per_second=20, jitter=0)

    async with limiter("first.test"):
        pass
    async with limiter("second.test"):
        pass

    async def start_request(hostname: str):
        async with limiter(hostname):
            pass

    started_at = time.perf_counter()
    await asyncio.gather(
        start_request("first.test"),
        start_request("second.test"),
    )
    elapsed = time.perf_counter() - started_at

    assert 0.04 <= elapsed < 0.09


def test_rate_limiter_validates_delays():
    with pytest.raises(ValueError):
        RateLimiter(max_requests_per_second=0)

    with pytest.raises(ValueError):
        RateLimiter(jitter=-0.1)

    limiter = RateLimiter()
    with pytest.raises(ValueError):
        limiter("example.test", required_delay=-0.1)
