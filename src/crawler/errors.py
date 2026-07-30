import asyncio

import aiohttp


class CrawlerError(Exception):
    def __init__(
        self,
        message: str,
        *,
        url: str,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.url = url
        self.status = status


class TransientError(CrawlerError):
    """A temporary error that may disappear on a later attempt."""


class PermanentError(CrawlerError):
    """An error that should not be retried."""


class NetworkError(CrawlerError):
    """A connection, DNS, or other network-level error."""


class ParseError(CrawlerError):
    """An unexpected error raised while parsing a response."""


def classify_request_error(error: Exception, url: str) -> CrawlerError:
    if isinstance(error, CrawlerError):
        return error

    if isinstance(error, asyncio.TimeoutError):
        return TransientError("Request timed out", url=url)

    if isinstance(error, aiohttp.ClientResponseError):
        status = error.status
        message = error.message or str(error)
        if status == 429 or status >= 500:
            return TransientError(message, url=url, status=status)
        if 400 <= status < 500:
            return PermanentError(message, url=url, status=status)
        return NetworkError(message, url=url, status=status)

    if isinstance(error, aiohttp.ClientError):
        return NetworkError(str(error), url=url)

    raise TypeError(f"Cannot classify error type={type(error).__name__}") from error
