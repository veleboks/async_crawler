from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TypedDict
from dataclasses import dataclass, field
from collections import defaultdict
import asyncio
import time
import random


@dataclass(slots=True)
class RateLimiterStats:
    requests_started: int = 0
    total_wait: float = 0.0
    average_wait: float = 0.0
    average_rate: float = 0.0


@dataclass(slots=True)
class HostnameState:
    last_request_at: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RateLimiter:
    def __init__(
        self,
        max_requests_per_second: float = 1.0,
        *,
        per_hostname: bool = True,
        jitter: float = 0.0,
        random_state: int = 123,
    ) -> None:
        if max_requests_per_second <= 0:
            raise ValueError("max_request_per_second must be more than zero")
        self._max_request_per_second = max_requests_per_second
        self._per_hostname = per_hostname
        self._jitter = jitter
        self._state_per_hostname: defaultdict[str, HostnameState] = defaultdict(
            HostnameState
        )
        self._state: HostnameState = HostnameState()
        self._random = random.Random(random_state)

        self._requests_started = 0
        self._total_wait = 0.0
        self._first_request_at: float | None = None
        self._last_request_at: float | None = None

    def __call__(
        self,
        hostname: str | None = None,
        *,
        required_delay: float = 0.0,
    ) -> AbstractAsyncContextManager[None]:
        """Return a context that waits for permission before entering."""

        if self._per_hostname and hostname is None:
            raise ValueError("When per_hostname is true, hostname is requred")

        state = (
            self._state_per_hostname[hostname]
            if self._per_hostname and hostname is not None
            else self._state
        )

        delay = max(
            1 / self._max_request_per_second, required_delay
        ) + self._random.uniform(0, self._jitter)

        @asynccontextmanager
        async def limiter():
            async with state.lock:
                if state.last_request_at is not None:
                    now = time.perf_counter()
                    wait = delay - (now - state.last_request_at)
                    self._total_wait += wait
                    await asyncio.sleep(wait)
                state.last_request_at = time.perf_counter()
                if self._first_request_at is None:
                    self._first_request_at = time.perf_counter()
                self._last_request_at = time.perf_counter()
                self._requests_started += 1
            yield

        return limiter()

    def get_stats(self) -> RateLimiterStats:
        average_wait = (
            self._total_wait / self._requests_started
            if self._requests_started > 0
            else 0.0
        )
        average_rate = (
            (self._requests_started - 1)
            / (self._last_request_at - self._first_request_at)
            if self._requests_started >= 2
            and self._first_request_at is not None
            and self._last_request_at is not None
            else 0.0
        )
        return RateLimiterStats(
            requests_started=self._requests_started,
            total_wait=self._total_wait,
            average_wait=average_wait,
            average_rate=average_rate,
        )
