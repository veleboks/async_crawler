import asyncio
import logging
from typing import Any

from crawler import AsyncCrawler

logger = logging.getLogger(__name__)


def log_parsed_result(result: dict[str, Any]) -> None:
    logger.info(
        "Страница: url=%s, title=%r, text_length=%s, links_count=%s, images_count=%s",
        result.get("url"),
        result.get("title"),
        len(result.get("text") or ""),
        len(result.get("links") or []),
        len(result.get("images") or []),
    )


async def main():
    logging.basicConfig(level=logging.DEBUG)

    max_concurrent = 5
    urls = [
        "https://github.com",
        "https://example.com",
    ]

    crawler = AsyncCrawler(max_concurrent=max_concurrent)
    try:
        results = await crawler.fetch_urls_and_parse(urls)
    finally:
        await crawler.close()

    for result in results.values():
        log_parsed_result(result)

    logger.info(
        "Загружено %s страниц, max_concurrent=%s",
        len(results),
        max_concurrent,
    )


if __name__ == "__main__":
    asyncio.run(main())
