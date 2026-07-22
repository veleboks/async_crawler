import pytest
from crawler import AsyncCrawler
import aiohttp


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
