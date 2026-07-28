import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
import time

import aiohttp

from .crawl_queue import CrawlerQueue
from .html_parser import HTMLParser
from .semaphore_manager import SemaphoreManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CrawlerState:
    queue: CrawlerQueue
    processed_urls: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed_urls: dict[str, str] = field(default_factory=dict)
    started_at: float = field(default_factory=time.perf_counter)


@dataclass(slots=True)
class CrawlerResult:
    processed_urls: dict[str, dict[str, Any]]
    failed_urls: dict[str, str]


class AsyncCrawler:
    def __init__(
        self,
        max_concurrent: int = 10,
        max_concurrent_per_domain: int = 2,
        timeout: aiohttp.ClientTimeout | None = None,
    ):
        assert max_concurrent > 0
        assert max_concurrent_per_domain > 0
        self.max_concurrent = max_concurrent
        self.max_concurrent_per_domain = max_concurrent_per_domain
        self.semaphore = SemaphoreManager(
            max_concurrent=max_concurrent,
            max_concurrent_per_domain=max_concurrent_per_domain,
        )
        if timeout is None:
            self.timeout = aiohttp.ClientTimeout(total=30, sock_connect=5, sock_read=10)
            logger.debug("Use default timeout %s", self.timeout)
        else:
            self.timeout = timeout
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        self.parser = HTMLParser()

    async def fetch_url(self, url: str) -> str:
        logger.info("start fetching url=%s", url)
        async with self.semaphore(url), self.session.get(url) as response:
            response.raise_for_status()
            text = await response.text()
            logger.info("succeeded fetching url=%s", url)
            return text

    def process_exception(self, err: BaseException, url: str):
        if isinstance(err, aiohttp.ClientResponseError):
            logger.warning(
                "HTTP request failed url=%s status=%s error_type=%s message=%s",
                url,
                err.status,
                type(err).__name__,
                err.message,
            )
        elif isinstance(err, asyncio.TimeoutError):
            logger.warning(
                "HTTP request timed out url=%s error_type=%s", url, type(err).__name__
            )
        elif isinstance(err, aiohttp.ClientError):
            logger.warning(
                "Network error url=%s error_type=%s message=%s",
                url,
                type(err).__name__,
                str(err),
            )
        else:
            raise err

    async def fetch_urls(self, urls: list[str]) -> dict[str, str]:
        responses = await asyncio.gather(
            *(self.fetch_url(url) for url in urls), return_exceptions=True
        )
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
        results = await asyncio.gather(
            *(self.fetch_and_parse(url) for url in urls), return_exceptions=True
        )
        parsed_data = {}
        for url, result in zip(urls, results):
            if isinstance(result, BaseException):
                self.process_exception(result, url)
            else:
                parsed_data[url] = result
        return parsed_data

    async def crawl(
        self,
        start_urls: list[str],
        *,
        max_pages: int = 10,
        max_depth: int = 2,
        workers_n: int = 10,
    ) -> CrawlerResult:

        if workers_n <= 0:
            raise ValueError(f"workers_n must be > 0, workers_n={workers_n}")

        state = CrawlerState(queue=CrawlerQueue(max_pages))
        for url in start_urls:
            state.queue.add_url(url)

        async with asyncio.TaskGroup() as group:
            workers = []
            for i in range(workers_n):
                workers.append(
                    group.create_task(self._worker(state, max_depth=max_depth))
                )
            await state.queue.join()

            for worker in workers:
                worker.cancel()

        return CrawlerResult(
            processed_urls=state.processed_urls, failed_urls=state.failed_urls
        )

    async def _worker(
        self,
        state: CrawlerState,
        *,
        max_depth: int,
    ) -> None:
        while True:
            task = await state.queue.get_next()
            try:
                parsed = await self.fetch_and_parse(task.url)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                self._record_failure(state, task.url, err)
            else:
                state.processed_urls[task.url] = parsed

                if task.depth < max_depth:
                    self._enqueue_links(state.queue, parsed["links"], task.depth + 1)
            finally:
                state.queue.mark_done(task)
            self._log_progress(state)

    def _enqueue_links(self, queue: CrawlerQueue, urls: list[str], depth: int):
        for url in urls:
            queue.add_url(url, depth=depth)

    def _record_failure(self, state: CrawlerState, url: str, err: BaseException):
        state.failed_urls[url] = str(err)
        self.process_exception(err, url)

    def _log_progress(self, state: CrawlerState):
        semaphore_stats = self.semaphore.get_stats()
        queue_stats = state.queue.get_stats()
        completed = len(state.processed_urls) + len(state.failed_urls)
        elapsed = time.perf_counter() - state.started_at
        speed = completed / elapsed
        logger.info(
            "Progress stats processed=%s failed=%s pending=%s in_progress=%s active=%s seen=%s speed=%.2f page/s elapsed=%.3f",
            len(state.processed_urls),
            len(state.failed_urls),
            queue_stats["pending"],
            queue_stats["in_progress"],
            semaphore_stats["active"],
            queue_stats["seen"],
            speed,
            elapsed,
        )
