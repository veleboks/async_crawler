import asyncio

import aiohttp
import pytest

from crawler import RobotsManager, RobotsResponse


@pytest.mark.asyncio
async def test_robots_rules_are_loaded_once_and_applied():
    calls: list[str] = []

    async def fetcher(url: str) -> RobotsResponse:
        calls.append(url)
        await asyncio.sleep(0)
        return RobotsResponse(
            status=200,
            text="""
User-agent: TestBot
Disallow: /private
Crawl-delay: 2
""",
        )

    manager = RobotsManager(fetcher, user_agent="TestBot/1.0")
    await asyncio.gather(
        manager.ensure_loaded("https://example.test/public"),
        manager.ensure_loaded("https://example.test/private"),
    )

    assert calls == ["https://example.test/robots.txt"]
    assert manager.can_fetch("https://example.test/public") is True
    assert manager.can_fetch("https://example.test/private") is False
    assert manager.get_crawl_delay("https://example.test/public") == 2.0
    assert manager.get_stats().robots_fetches == 1
    assert manager.get_stats().cached_origins == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, True), (500, False)],
)
async def test_robots_http_policy(status: int, expected: bool):
    async def fetcher(url: str) -> RobotsResponse:
        return RobotsResponse(status=status)

    manager = RobotsManager(fetcher)
    url = "https://example.test/page"

    await manager.ensure_loaded(url)

    assert manager.can_fetch(url) is expected


@pytest.mark.asyncio
async def test_robots_network_error_is_cached_as_disallow():
    calls = 0

    async def fetcher(url: str) -> RobotsResponse:
        nonlocal calls
        calls += 1
        raise aiohttp.ClientConnectionError("simulated failure")

    manager = RobotsManager(fetcher)
    url = "https://example.test/page"

    await manager.ensure_loaded(url)
    await manager.ensure_loaded(url)

    assert manager.can_fetch(url) is False
    assert calls == 1
    assert manager.get_stats().robots_fetches == 1
