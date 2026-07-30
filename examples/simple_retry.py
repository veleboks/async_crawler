import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path

import aiofiles

from crawler import AsyncCrawler, RetryStrategy

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    retry_strategy = RetryStrategy(
        max_retries=2,
        backoff_factor=0.5,
    )
    crawler = AsyncCrawler(
        requests_per_second=5,
        user_agent="AsyncCrawler/1.0",
        retry_strategy=retry_strategy,
    )

    try:
        result = await crawler.crawl(
            [
                "https://httpbingo.org/get",
                "https://httpbingo.org/status/503",
                "https://httpbingo.org/status/404",
            ],
            max_pages=3,
            max_depth=0,
        )
    finally:
        await crawler.close()

    report = {
        "processed_urls": result.processed_urls,
        "failed_urls": result.failed_urls,
        "permanent_urls": result.permanent_urls,
        "blocked_urls": result.blocked_urls,
        "retry_stats": asdict(result.retry_stats),
    }
    output_path = Path(__file__).with_name("retry_report.json")
    async with aiofiles.open(output_path, "w", encoding="utf-8") as output:
        await output.write(json.dumps(report, ensure_ascii=False, indent=2))

    logger.info("Retry report saved path=%s", output_path)


if __name__ == "__main__":
    asyncio.run(main())
