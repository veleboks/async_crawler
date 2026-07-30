import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .crawl_queue import CrawlerQueue
from .errors import (
    CrawlerError,
    ParseError,
    PermanentError,
    classify_request_error,
)
from .html_parser import HTMLParser
from .rate_limiter import RateLimiter
from .retry_strategy import RetryStats, RetryStrategy
from .robots_manager import RobotsDisallowedError, RobotsManager, RobotsResponse
from .semaphore_manager import SemaphoreManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CrawlerState:
    queue: CrawlerQueue
    processed_urls: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed_urls: dict[str, str] = field(default_factory=dict)
    permanent_urls: dict[str, str] = field(default_factory=dict)
    blocked_urls: dict[str, str] = field(default_factory=dict)
    started_at: float = field(default_factory=time.perf_counter)


@dataclass(slots=True)
class CrawlerResult:
    processed_urls: dict[str, dict[str, Any]]
    failed_urls: dict[str, str]
    permanent_urls: dict[str, str]
    blocked_urls: dict[str, str]
    retry_stats: RetryStats


class AsyncCrawler:
    def __init__(
        self,
        max_concurrent: int = 10,
        max_concurrent_per_hostname: int = 2,
        timeout: aiohttp.ClientTimeout | None = None,
        *,
        requests_per_second: float = 1.0,
        jitter: float = 0.0,
        user_agent: str = "AsyncCrawler/1.0",
        random_state: int | None = None,
        retry_strategy: RetryStrategy | None = None,
    ) -> None:
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be greater than zero")
        if max_concurrent_per_hostname <= 0:
            raise ValueError("max_concurrent_per_hostname must be greater than zero")
        if not user_agent.strip():
            raise ValueError("user_agent must not be empty")

        self._max_concurrent = max_concurrent
        self._max_concurrent_per_hostname = max_concurrent_per_hostname
        self._semaphore = SemaphoreManager(
            max_concurrent=max_concurrent,
            max_concurrent_per_hostname=max_concurrent_per_hostname,
        )
        self._rate_limiter = RateLimiter(
            max_requests_per_second=requests_per_second,
            per_hostname=True,
            jitter=jitter,
            random_state=random_state,
        )
        self._user_agent = user_agent
        self._retry_strategy = (
            retry_strategy if retry_strategy is not None else RetryStrategy()
        )

        if timeout is None:
            self._timeout = aiohttp.ClientTimeout(
                total=30, sock_connect=5, sock_read=10
            )
            logger.debug("Use default timeout %s", self._timeout)
        else:
            self._timeout = timeout
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent},
        )
        self._parser = HTMLParser()
        self._robots_manager = RobotsManager(
            self._robots_fetcher,
            user_agent=self._user_agent,
        )

    async def _robots_fetcher(self, url: str) -> RobotsResponse:
        return await self._fetch_text(url, raise_for_status=False)

    async def _fetch_text(
        self,
        url: str,
        *,
        required_delay: float = 0.0,
        raise_for_status: bool = True,
    ) -> RobotsResponse:
        hostname = urlsplit(url).hostname
        if hostname is None:
            raise ValueError(f"hostname is required in url={url!r}")

        async with (
            self._semaphore(hostname),
            self._rate_limiter(hostname, required_delay=required_delay),
            self._session.get(url) as response,
        ):
            if raise_for_status:
                response.raise_for_status()
            return RobotsResponse(
                status=response.status,
                text=await response.text(),
            )

    async def fetch_url(self, url: str) -> str:
        logger.info("start fetching url=%s", url)

        await self._robots_manager.ensure_loaded(url)

        allowed = self._robots_manager.can_fetch(url)
        if not allowed:
            raise RobotsDisallowedError(url)

        crawl_delay = self._robots_manager.get_crawl_delay(url)
        required_delay = crawl_delay if crawl_delay is not None else 0.0
        response = await self._retry_strategy.execute_with_retry(
            self._fetch_page_once,
            url,
            required_delay=required_delay,
        )
        logger.info("succeeded fetching url=%s status=%s", url, response.status)
        return response.text

    async def _fetch_page_once(
        self,
        url: str,
        *,
        required_delay: float,
    ) -> RobotsResponse:
        try:
            return await self._fetch_text(url, required_delay=required_delay)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            classified_error = classify_request_error(error, url)
            raise classified_error from error

    def process_exception(self, err: Exception, url: str) -> None:
        if isinstance(err, RobotsDisallowedError):
            logger.info("Blocked by robots.txt url=%s", url)
        elif isinstance(err, CrawlerError):
            logger.warning(
                "Crawler operation failed url=%s status=%s error_type=%s message=%s",
                url,
                err.status,
                type(err).__name__,
                err.message,
            )
        elif isinstance(err, aiohttp.ClientResponseError):
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

    def _process_batch_exception(self, err: BaseException, url: str) -> None:
        if isinstance(err, Exception):
            self.process_exception(err, url)
        else:
            raise err

    async def fetch_urls(self, urls: list[str]) -> dict[str, str]:
        responses = await asyncio.gather(
            *(self.fetch_url(url) for url in urls), return_exceptions=True
        )
        result = {}
        for url, response in zip(urls, responses):
            if isinstance(response, BaseException):
                self._process_batch_exception(response, url)
            else:
                result[url] = response
        return result

    async def close(self) -> None:
        await self._session.close()

    async def fetch_and_parse(self, url: str) -> dict[str, Any]:
        html = await self.fetch_url(url)
        try:
            return await asyncio.to_thread(self._parser.parse_html, html, url)
        except Exception as error:
            raise ParseError(str(error), url=url) from error

    async def fetch_urls_and_parse(self, urls: list[str]) -> dict[str, Any]:
        results = await asyncio.gather(
            *(self.fetch_and_parse(url) for url in urls), return_exceptions=True
        )
        parsed_data = {}
        for url, result in zip(urls, results):
            if isinstance(result, BaseException):
                self._process_batch_exception(result, url)
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
            processed_urls=state.processed_urls,
            failed_urls=state.failed_urls,
            permanent_urls=state.permanent_urls,
            blocked_urls=state.blocked_urls,
            retry_stats=self._retry_strategy.get_stats(),
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
            except RobotsDisallowedError as err:
                state.blocked_urls[task.url] = str(err)
                self.process_exception(err, task.url)
            except PermanentError as err:
                state.failed_urls[task.url] = str(err)
                state.permanent_urls[task.url] = str(err)
                self.process_exception(err, task.url)
            except CrawlerError as err:
                state.failed_urls[task.url] = str(err)
                self.process_exception(err, task.url)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                state.failed_urls[task.url] = str(err)
                self.process_exception(err, task.url)
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

    def _log_progress(self, state: CrawlerState):
        semaphore_stats = self._semaphore.get_stats()
        rate_limiter_stats = self._rate_limiter.get_stats()
        robots_stats = self._robots_manager.get_stats()
        retry_stats = self._retry_strategy.get_stats()
        queue_stats = state.queue.get_stats()
        completed = (
            len(state.processed_urls) + len(state.failed_urls) + len(state.blocked_urls)
        )
        elapsed = time.perf_counter() - state.started_at
        speed = completed / elapsed
        logger.info(
            "Progress processed=%s failed=%s blocked=%s pending=%s "
            "in_progress=%s active_requests=%s seen=%s speed=%.2f pages/s "
            "requests_started=%s average_wait=%.3fs average_interval=%.3fs "
            "average_rate=%.2f req/s robots_fetches=%s cached_origins=%s "
            "retries=%s successful_retries=%s exhausted=%s "
            "average_retry_delay=%.3fs permanent=%s errors_by_type=%s "
            "elapsed=%.3fs",
            len(state.processed_urls),
            len(state.failed_urls),
            len(state.blocked_urls),
            queue_stats["pending"],
            queue_stats["in_progress"],
            semaphore_stats["active"],
            queue_stats["seen"],
            speed,
            rate_limiter_stats.requests_started,
            rate_limiter_stats.average_wait,
            rate_limiter_stats.average_interval,
            rate_limiter_stats.average_rate,
            robots_stats.robots_fetches,
            robots_stats.cached_origins,
            retry_stats.retries_performed,
            retry_stats.successful_retries,
            retry_stats.exhausted_operations,
            retry_stats.average_retry_delay,
            len(state.permanent_urls),
            retry_stats.errors_by_type,
            elapsed,
        )

    def get_retry_stats(self) -> RetryStats:
        return self._retry_strategy.get_stats()
