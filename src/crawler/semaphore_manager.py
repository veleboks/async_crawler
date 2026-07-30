import asyncio
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TypedDict


class SemaphoreStats(TypedDict):
    active: int
    hostnames: int


class SemaphoreManager:
    def __init__(
        self,
        max_concurrent: int,
        max_concurrent_per_hostname: int,
    ) -> None:
        self._global_semaphore = asyncio.Semaphore(max_concurrent)
        self._hostname_semaphores: dict[str, asyncio.Semaphore] = dict()
        self._max_concurrent_per_hostname = max_concurrent_per_hostname
        self._active = 0

    def __call__(self, hostname: str) -> AbstractAsyncContextManager[None]:
        hostname_semaphore = self._hostname_semaphores.get(hostname)

        if hostname_semaphore is None:
            hostname_semaphore = asyncio.Semaphore(self._max_concurrent_per_hostname)
            self._hostname_semaphores[hostname] = hostname_semaphore

        @asynccontextmanager
        async def manager():
            async with hostname_semaphore, self._global_semaphore:
                self._active += 1
                try:
                    yield
                finally:
                    self._active -= 1

        return manager()

    def get_stats(self) -> SemaphoreStats:
        return SemaphoreStats(
            active=self._active, hostnames=len(self._hostname_semaphores)
        )
