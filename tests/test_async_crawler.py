import logging

import aiohttp
import pytest

from crawler import AsyncCrawler, RobotsDisallowedError


@pytest.mark.asyncio
async def test_user_agent_is_configured():
    crawler = AsyncCrawler(user_agent="TestBot/1.0")
    try:
        assert crawler._session.headers["User-Agent"] == "TestBot/1.0"
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_fetch_urls_skips_expected_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    valid_url = "https://example.test/valid"
    failed_url = "https://example.test/failed"
    blocked_url = "https://example.test/blocked"

    async def fake_fetch(url: str) -> str:
        if url == failed_url:
            raise aiohttp.ClientConnectionError("simulated failure")
        if url == blocked_url:
            raise RobotsDisallowedError(url)
        return "valid response"

    crawler = AsyncCrawler()
    monkeypatch.setattr(crawler, "fetch_url", fake_fetch)
    caplog.set_level(logging.INFO, logger="crawler.async_crawler")
    try:
        result = await crawler.fetch_urls([valid_url, failed_url, blocked_url])
    finally:
        await crawler.close()

    assert result == {valid_url: "valid response"}
    assert "Network error" in caplog.text
    assert "Blocked by robots.txt" in caplog.text


@pytest.mark.asyncio
async def test_crawl_fixed_graph(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    page_a = "https://example.test/a"
    page_b = "https://example.test/b"
    page_c = "https://example.test/c"
    page_d = "https://example.test/d"
    page_e = "https://example.test/e"
    page_f = "https://example.test/f"
    page_g = "https://example.test/g"

    graph = {
        page_a: [page_b, page_c, page_c],
        page_b: [page_d, page_e],
        page_c: [page_g],
        page_e: [page_f],
    }
    calls: list[str] = []

    async def fake_fetch_and_parse(url: str):
        calls.append(url)
        if url == page_d:
            raise aiohttp.ClientConnectionError("simulated failure")
        if url == page_e:
            raise RobotsDisallowedError(url)
        return {"url": url, "links": graph.get(url, [])}

    crawler = AsyncCrawler()
    monkeypatch.setattr(crawler, "fetch_and_parse", fake_fetch_and_parse)
    caplog.set_level(logging.INFO, logger="crawler.async_crawler")

    try:
        result = await crawler.crawl(
            [page_a],
            max_pages=5,
            max_depth=2,
            workers_n=3,
        )
    finally:
        await crawler.close()

    assert set(result.processed_urls) == {page_a, page_b, page_c}
    assert result.failed_urls == {page_d: "simulated failure"}
    assert result.blocked_urls == {page_e: f"URL is disallowed by robots.txt: {page_e}"}
    assert calls.count(page_c) == 1
    assert len(calls) == 5
    assert page_f not in calls
    assert page_g not in calls
    assert "blocked=1" in caplog.text
