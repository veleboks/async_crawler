import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import aiofiles

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


async def save_results(
    path: Path,
    processed_urls: dict[str, dict[str, Any]],
    failed_urls: dict[str, str],
) -> None:
    data = {
        "processed_urls": processed_urls,
        "failed_urls": failed_urls,
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)

    async with aiofiles.open(path, "w", encoding="utf-8") as output:
        await output.write(content)


async def main():
    logging.basicConfig(level=logging.INFO)

    max_concurrent = 5
    start_urls = [
        "https://github.com",
        "https://example.com",
        "https://youtube.com",
    ]

    crawler = AsyncCrawler(max_concurrent=max_concurrent, max_concurrent_per_domain=1)
    try:
        result = await crawler.crawl(start_urls)
    finally:
        await crawler.close()

    for parsed in result.processed_urls.values():
        log_parsed_result(parsed)

    logger.info(
        "Загружено %s страниц, max_concurrent=%s",
        len(result.processed_urls),
        max_concurrent,
    )

    for url, fail in result.failed_urls.items():
        logger.info("Ошибка загрузки url=%s err=%s", url, fail)

    output_path = Path(__file__).with_name("crawl_results.json")
    await save_results(
        output_path,
        result.processed_urls,
        result.failed_urls,
    )
    logger.info("Результаты сохранены path=%s", output_path)


if __name__ == "__main__":
    asyncio.run(main())
