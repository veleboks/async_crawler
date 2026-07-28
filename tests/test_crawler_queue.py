import pytest

from crawler import CrawlerQueue


@pytest.mark.asyncio
async def test_crawler_queue_order_duplicates_and_limit():
    queue = CrawlerQueue(max_pages=4)

    assert queue.add_url("https://example.test/deep", depth=1)
    assert queue.add_url("https://example.test/last", depth=0, priority=5)
    assert queue.add_url("https://example.test/first", depth=0, priority=1)
    assert queue.add_url("https://example.test/second", depth=0, priority=1)

    assert not queue.add_url("https://example.test/first")
    assert not queue.add_url("https://example.test/over-limit")

    urls = []
    for _ in range(4):
        task = await queue.get_next()
        urls.append(task.url)
        queue.mark_done(task)

    await queue.join()

    assert urls == [
        "https://example.test/first",
        "https://example.test/second",
        "https://example.test/last",
        "https://example.test/deep",
    ]
    assert queue.get_stats() == {
        "seen": 4,
        "pending": 0,
        "in_progress": 0,
    }
