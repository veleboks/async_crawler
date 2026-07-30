import asyncio
import random
import time
from collections import defaultdict
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RateLimiterStats:
    requests_started: int = 0
    total_wait: float = 0.0
    average_wait: float = 0.0
    average_interval: float = 0.0
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
        random_state: int | None = None,
    ) -> None:
        if max_requests_per_second <= 0:
            raise ValueError("max_requests_per_second must be greater than zero")
        if jitter < 0:
            raise ValueError("jitter must be greater than or equal to zero")

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
        self._total_interval = 0.0
        self._intervals_count = 0
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
            raise ValueError("hostname is required when per_hostname is true")
        if required_delay < 0:
            raise ValueError("required_delay must be greater than or equal to zero")

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
            wait_started_at = time.perf_counter()
            async with state.lock:
                previous_request_at = state.last_request_at
                if previous_request_at is not None:
                    now = time.perf_counter()
                    wait = max(0.0, delay - (now - previous_request_at))
                    if wait > 0:
                        await asyncio.sleep(wait)

                request_started_at = time.perf_counter()
                state.last_request_at = request_started_at
                if previous_request_at is not None:
                    self._total_interval += request_started_at - previous_request_at
                    self._intervals_count += 1
                if self._first_request_at is None:
                    self._first_request_at = request_started_at
                self._last_request_at = request_started_at
                self._requests_started += 1
                self._total_wait += request_started_at - wait_started_at
            yield

        return limiter()

    def get_stats(self) -> RateLimiterStats:
        average_wait = (
            self._total_wait / self._requests_started
            if self._requests_started > 0
            else 0.0
        )
        average_interval = (
            self._total_interval / self._intervals_count
            if self._intervals_count > 0
            else 0.0
        )
        average_rate = (
            (self._requests_started - 1)
            / (self._last_request_at - self._first_request_at)
            if self._requests_started >= 2
            and self._first_request_at is not None
            and self._last_request_at is not None
            and self._last_request_at > self._first_request_at
            else 0.0
        )
        return RateLimiterStats(
            requests_started=self._requests_started,
            total_wait=self._total_wait,
            average_wait=average_wait,
            average_interval=average_interval,
            average_rate=average_rate,
        )
