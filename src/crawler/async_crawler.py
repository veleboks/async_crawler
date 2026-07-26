import asyncio
import aiohttp
import logging
from typing import Any
from .html_parser import HTMLParser

logger = logging.getLogger(__name__)

class AsyncCrawler:
    def __init__(self, max_concurrent: int = 10, timeout: aiohttp.ClientTimeout | None = None):
        assert max_concurrent > 0
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(value=self.max_concurrent)
        if timeout is None:
            self.timeout = aiohttp.ClientTimeout(total=30, sock_connect=5, sock_read=10)
            logger.debug("Use default timeout %s", self.timeout)
        else:
            self.timeout = timeout
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        self.parser = HTMLParser()

    async def fetch_url(self, url: str) -> str:
        logger.info("start fetching url=%s", url)
        async with self.semaphore, self.session.get(url) as response:
            response.raise_for_status()
            text = await response.text()
            logger.info("succeeded fetching url=%s", url)
            return text

    def process_exception(self, err: BaseException, url: str):
        if isinstance(err, aiohttp.ClientResponseError):
            logger.warning("HTTP request failed url=%s status=%s error_type=%s message=%s", url, err.status, type(err).__name__, err.message)
        elif isinstance(err, asyncio.TimeoutError):
            logger.warning("HTTP request timed out url=%s error_type=%s", url, type(err).__name__)
        elif isinstance(err, aiohttp.ClientError):
            logger.warning("Network error url=%s error_type=%s message=%s", url, type(err).__name__, str(err))
        else:
            raise err

    async def fetch_urls(self, urls: list[str]) -> dict[str, str]:
        responses = await asyncio.gather(*(self.fetch_url(url) for url in urls), return_exceptions=True)
        result = {}
        for url, response in zip(urls, responses):
            if isinstance(response, BaseException):
                self.process_exception(response, url)
            else:
                result[url] = response
        return result

    async def close(self):
        await self.session.close()

    async def fetch_and_parse(self, url: str) -> dict[str, Any]:
        html = await self.fetch_url(url)
        parsed = await asyncio.to_thread(self.parser.parse_html, html, url)
        return parsed

    async def fetch_urls_and_parse(self, urls: list[str]) -> dict[str, Any]:
        results = await asyncio.gather(*(self.fetch_and_parse(url) for url in urls), return_exceptions=True)
        parsed_data = {}
        for url, result in zip(urls, results):
            if isinstance(result, BaseException):
                self.process_exception(result, url)
            else:
                parsed_data[url] = result
        return parsed_data

