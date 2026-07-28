import asyncio
import logging
from dataclasses import dataclass, field
from typing import TypedDict

logger = logging.getLogger(__name__)


@dataclass(order=True, frozen=True, slots=True)
class CrawlTask:
    depth: int
    priority: int
    sequence_number: int
    url: str = field(compare=False)


class QueueStats(TypedDict):
    seen: int
    pending: int
    in_progress: int


class CrawlerQueue:
    def __init__(self, max_pages: int) -> None:
        self.queue = asyncio.PriorityQueue()
        self.sequence_number = 0
        self.pending = set()
        self.seen = set()
        self.in_progress = set()
        self.max_pages = max_pages

    def add_url(
        self,
        url: str,
        *,
        depth: int = 0,
        priority: int = 0,
    ) -> bool:

        if url in self.seen:
            logger.debug("URL '%s' have seen", url)
            return False

        if len(self.seen) >= self.max_pages:
            logger.debug(
                "Cannot put url='%s', max_pages=%s limit exceeded", url, self.max_pages
            )
            return False

        task = CrawlTask(
            depth=depth,
            priority=priority,
            sequence_number=self.sequence_number,
            url=url,
        )
        self.sequence_number += 1
        try:
            self.queue.put_nowait(task)
        except asyncio.QueueFull as err:
            logger.warning("Failed to put task=%s in queue error=%s", task, err)
            return False

        self.seen.add(url)
        self.pending.add(url)

        return True

    async def get_next(self) -> CrawlTask:
        task = await self.queue.get()
        self.pending.remove(task.url)
        self.in_progress.add(task.url)
        return task

    def mark_done(self, task: CrawlTask) -> None:
        self.in_progress.remove(task.url)
        self.queue.task_done()

    async def join(self) -> None:
        await self.queue.join()

    def get_stats(self) -> QueueStats:
        return QueueStats(
            seen=len(self.seen),
            pending=len(self.pending),
            in_progress=len(self.in_progress),
        )
