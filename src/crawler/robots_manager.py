from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True, slots=True)
class RobotsResponse:
    status: int
    text: str = ""


type RobotsFetcher = Callable[[str], Awaitable[RobotsResponse]]


class RobotsStats(TypedDict):
    cached_origins: int
    robots_fetches: int


class RobotsManager:
    def __init__(
        self,
        fetcher: RobotsFetcher,
        *,
        user_agent: str = "*",
    ) -> None:
        raise NotImplementedError

    async def ensure_loaded(self, url: str) -> None:
        """Load and cache robots.txt rules for the URL origin if necessary."""
        raise NotImplementedError

    def can_fetch(self, url: str) -> bool:
        """Return whether the configured user agent may fetch the URL."""
        raise NotImplementedError

    def get_crawl_delay(self, url: str) -> float | None:
        raise NotImplementedError

    def get_stats(self) -> RobotsStats:
        raise NotImplementedError
