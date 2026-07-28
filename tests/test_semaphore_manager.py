import asyncio

import pytest

from crawler import SemaphoreManager


@pytest.mark.asyncio
async def test_semaphore_global_and_domain_limits():
    async def measure_peak(manager: SemaphoreManager, urls: list[str]) -> int:
        active = 0
        peak = 0

        async def operation(url: str):
            nonlocal active, peak

            async with manager(url):
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(0.01)
                finally:
                    active -= 1

        await asyncio.gather(*(operation(url) for url in urls))
        return peak

    global_manager = SemaphoreManager(
        max_concurrent=2,
        max_concurrent_per_domain=10,
    )
    different_domains = [f"https://site-{index}.test" for index in range(5)]

    domain_manager = SemaphoreManager(
        max_concurrent=10,
        max_concurrent_per_domain=2,
    )
    same_domain = [f"https://example.test/page-{index}" for index in range(5)]

    assert await measure_peak(global_manager, different_domains) == 2
    assert await measure_peak(domain_manager, same_domain) == 2
