import asyncio
import logging
import time
from types import TracebackType
from typing import Self

from crawler import AsyncCrawler

logger = logging.getLogger(__name__)


class TimeLogger:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def __enter__(self) -> Self:
        self.start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        trace: TracebackType | None,
    ) -> bool | None:
        elapsed = time.perf_counter() - self.start
        self.logger.info("Elapsed %ss", elapsed)


async def run_case(max_concurrent: int):
    urls = [
        "https://notvalidurl.com",
        "https://example.com/",
        "https://httpbingo.org/html",
        "https://httpbingo.org/get",
        "https://httpbingo.org/delay/1",
        "https://httpbingo.org/delay/2",
        "https://httpbingo.org/status/404",
        "https://httpbingo.org/status/500",
        "https://crawler-test.invalid/",
    ]

    with TimeLogger():
        crawler = AsyncCrawler(max_concurrent=max_concurrent)
        try:
            results = await crawler.fetch_urls(urls)
        finally:
            await crawler.close()
    logger.info("Загружено %s страниц, max_concurrent=%s", len(results), max_concurrent)


async def main():
    logging.basicConfig(level=logging.DEBUG)

    await run_case(1)
    await run_case(5)


if __name__ == "__main__":
    asyncio.run(main())
