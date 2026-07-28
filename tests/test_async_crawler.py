import aiohttp
import pytest

from crawler import AsyncCrawler


@pytest.mark.asyncio
async def test_fetch_url_valid():
    crawler = AsyncCrawler()
    _ = await crawler.fetch_url("https://example.com/")
    await crawler.close()


@pytest.mark.asyncio
async def test_fetch_url_invalid():
    crawler = AsyncCrawler()
    with pytest.raises(aiohttp.ClientError):
        _ = await crawler.fetch_url("https://crawler-test.invalid/")
    await crawler.close()


@pytest.mark.asyncio
async def test_fetch_urls():
    crawler = AsyncCrawler(max_concurrent=2)
    urls = [
        "https://example.com/",
        "https://crawler-test.invalid/",
        "https://httpbingo.org/status/500",
    ]
    result = await crawler.fetch_urls(urls)
    assert len(result) == 1
    await crawler.close()


@pytest.mark.asyncio
async def test_crawl_fixed_graph(monkeypatch: pytest.MonkeyPatch):
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
        return {"url": url, "links": graph.get(url, [])}

    crawler = AsyncCrawler()
    monkeypatch.setattr(crawler, "fetch_and_parse", fake_fetch_and_parse)

    try:
        result = await crawler.crawl(
            [page_a],
            max_pages=5,
            max_depth=2,
            workers_n=3,
        )
    finally:
        await crawler.close()

    assert set(result.processed_urls) == {page_a, page_b, page_c, page_e}
    assert result.failed_urls == {page_d: "simulated failure"}
    assert calls.count(page_c) == 1
    assert len(calls) == 5
    assert page_f not in calls
    assert page_g not in calls
