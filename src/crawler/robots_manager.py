import asyncio
import enum
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import aiohttp

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RobotsResponse:
    status: int
    text: str = ""


type RobotsFetcher = Callable[[str], Awaitable[RobotsResponse]]


class RobotsDisallowedError(Exception):
    def __init__(self, url: str) -> None:
        super().__init__(f"URL is disallowed by robots.txt: {url}")
        self.url = url


@dataclass(slots=True)
class RobotsStats:
    cached_origins: int = 0
    robots_fetches: int = 0


class RobotsPolicy(enum.Enum):
    RULES = enum.auto()
    ALLOW_ALL = enum.auto()
    DISALLOW_ALL = enum.auto()


@dataclass(slots=True)
class OriginState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    policy: RobotsPolicy | None = None
    parser: RobotFileParser | None = None


class RobotsManager:
    def __init__(
        self,
        fetcher: RobotsFetcher,
        *,
        user_agent: str = "*",
    ) -> None:
        self._fetcher = fetcher
        self._user_agent = user_agent
        self._states: defaultdict[str, OriginState] = defaultdict(OriginState)
        self._stats = RobotsStats()

    def _get_origin(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in ["http", "https"]:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
        if parsed.hostname is None:
            raise ValueError(f"URL hostname is missing: {url!r}")

        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    def _get_robots_url(self, url: str) -> str:
        origin = self._get_origin(url)
        return urljoin(origin, "/robots.txt")

    async def ensure_loaded(self, url: str) -> None:
        """Load and cache robots.txt rules for the URL origin if necessary."""
        robots_url = self._get_robots_url(url)
        state = self._states[robots_url]
        if state.policy is not None:
            return
        async with state.lock:
            if state.policy is not None:
                return

            self._stats.robots_fetches += 1
            try:
                response = await self._fetcher(robots_url)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                logger.warning(
                    "Failed to fetch robots.txt url=%s error_type=%s message=%s; "
                    "disallowing origin",
                    robots_url,
                    type(err).__name__,
                    str(err),
                )
                state.policy = RobotsPolicy.DISALLOW_ALL
            else:
                self._process_response(state, robots_url, response)

            self._stats.cached_origins += 1

    def _process_response(
        self,
        state: OriginState,
        robots_url: str,
        response: RobotsResponse,
    ) -> None:
        logger.debug("Fetched robots.txt url=%s status=%s", robots_url, response.status)
        if 200 <= response.status < 300:
            state.policy = RobotsPolicy.RULES
            state.parser = RobotFileParser(robots_url)
            state.parser.parse(response.text.splitlines())
        elif 400 <= response.status < 500:
            state.policy = RobotsPolicy.ALLOW_ALL
        else:
            state.policy = RobotsPolicy.DISALLOW_ALL

    def can_fetch(self, url: str) -> bool:
        """Return whether the configured user agent may fetch the URL."""
        robots_url = self._get_robots_url(url)
        state = self._states.get(robots_url)
        if state is None or state.policy is None:
            raise RuntimeError(f"robots.txt is not loaded for url={url!r}")

        if state.policy is RobotsPolicy.RULES:
            if state.parser is None:
                raise RuntimeError(f"Robots parser is not loaded for url={url!r}")
            return state.parser.can_fetch(self._user_agent, url)

        return state.policy is RobotsPolicy.ALLOW_ALL

    def get_crawl_delay(self, url: str) -> float | None:
        robots_url = self._get_robots_url(url)
        state = self._states.get(robots_url)
        if state is None or state.policy is not RobotsPolicy.RULES:
            return None

        if state.parser is None:
            return None

        delay = state.parser.crawl_delay(self._user_agent)
        return float(delay) if delay is not None else None

    def get_stats(self) -> RobotsStats:
        return RobotsStats(
            cached_origins=self._stats.cached_origins,
            robots_fetches=self._stats.robots_fetches,
        )
