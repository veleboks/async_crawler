import asyncio
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TypedDict
from urllib.parse import urlsplit


class SemaphoreStats(TypedDict):
    active: int
    domains: int


class SemaphoreManager:
    def __init__(
        self,
        max_concurrent: int,
        max_concurrent_per_domain: int,
    ) -> None:
        self._global_semaphore = asyncio.Semaphore(max_concurrent)
        self._domain_semaphores: dict[str, asyncio.Semaphore] = dict()
        self._max_concurrent_per_domain = max_concurrent_per_domain
        self._active = 0

    def __call__(self, url: str) -> AbstractAsyncContextManager[None]:

        hostname = urlsplit(url).hostname
        if hostname is None:
            raise ValueError(f"Hostname is required for domain semaphore url={url}")

        domain_semaphore = self._domain_semaphores.get(hostname)

        if domain_semaphore is None:
            domain_semaphore = asyncio.Semaphore(self._max_concurrent_per_domain)
            self._domain_semaphores[hostname] = domain_semaphore

        @asynccontextmanager
        async def manager():
            async with domain_semaphore, self._global_semaphore:
                self._active += 1
                try:
                    yield
                finally:
                    self._active -= 1

        return manager()

    def get_stats(self) -> SemaphoreStats:
        return SemaphoreStats(active=self._active, domains=len(self._domain_semaphores))
