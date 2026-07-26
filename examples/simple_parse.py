import asyncio
import logging

from crawler import AsyncCrawler

logger = logging.getLogger(__name__)


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
    logger.info(
        "Загружено %s страниц, max_concurrent=%s, результат=%s",
        len(results),
        max_concurrent,
        results,
    )


if __name__ == "__main__":
    asyncio.run(main())
