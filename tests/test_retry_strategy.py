import asyncio

import aiohttp
import pytest

from crawler import (
    NetworkError,
    PermanentError,
    RetryStrategy,
    TransientError,
    classify_request_error,
)


@pytest.mark.asyncio
async def test_timeout_is_retried():
    calls = 0
    delays: list[float] = []

    async def fake_sleep(delay: float):
        delays.append(delay)

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise classify_request_error(
                asyncio.TimeoutError(),
                "https://example.test",
            )
        return "success"

    strategy = RetryStrategy(
        max_retries=2,
        backoff_factor=1,
        sleep_func=fake_sleep,
    )

    assert await strategy.execute_with_retry(operation) == "success"
    assert calls == 2
    assert delays == [1]


@pytest.mark.asyncio
async def test_503_is_retried_with_exponential_backoff():
    calls = 0
    delays: list[float] = []

    async def fake_sleep(delay: float):
        delays.append(delay)

    async def operation():
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise TransientError(
                "Service unavailable",
                url="https://example.test",
                status=503,
            )
        return "success"

    strategy = RetryStrategy(
        max_retries=3,
        backoff_factor=1,
        sleep_func=fake_sleep,
    )

    assert await strategy.execute_with_retry(operation) == "success"
    assert calls == 3
    assert delays == [1, 2]

    stats = strategy.get_stats()
    assert stats.errors_by_type == {"TransientError": 2}
    assert stats.retries_performed == 2
    assert stats.successful_retries == 1
    assert stats.average_retry_delay == 1.5


@pytest.mark.asyncio
async def test_404_is_not_retried():
    calls = 0
    delays: list[float] = []

    async def fake_sleep(delay: float):
        delays.append(delay)

    async def operation():
        nonlocal calls
        calls += 1
        raise PermanentError(
            "Not found",
            url="https://example.test/missing",
            status=404,
        )

    strategy = RetryStrategy(sleep_func=fake_sleep)

    with pytest.raises(PermanentError):
        await strategy.execute_with_retry(operation)

    assert calls == 1
    assert delays == []


def test_aiohttp_errors_are_classified():
    timeout = classify_request_error(
        asyncio.TimeoutError(),
        "https://example.test",
    )
    connection = classify_request_error(
        aiohttp.ClientConnectionError("connection failed"),
        "https://example.test",
    )
    response_503 = classify_request_error(
        aiohttp.ClientResponseError(
            request_info=None,
            history=(),
            status=503,
            message="Service unavailable",
        ),
        "https://example.test",
    )
    response_404 = classify_request_error(
        aiohttp.ClientResponseError(
            request_info=None,
            history=(),
            status=404,
            message="Not found",
        ),
        "https://example.test",
    )

    assert isinstance(timeout, TransientError)
    assert isinstance(connection, NetworkError)
    assert isinstance(response_503, TransientError)
    assert isinstance(response_404, PermanentError)
