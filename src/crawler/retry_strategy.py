import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar

from .errors import NetworkError, TransientError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

type Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RetryStats:
    errors_by_type: dict[str, int] = field(default_factory=dict)
    retries_performed: int = 0
    successful_retries: int = 0
    exhausted_operations: int = 0
    total_backoff: float = 0.0
    average_retry_delay: float = 0.0


class RetryStrategy:
    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        retry_on: Sequence[type[Exception]] | None = None,
        *,
        sleep_func: Sleeper = asyncio.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to zero")
        if backoff_factor < 0:
            raise ValueError("backoff_factor must be greater than or equal to zero")

        retry_types = (
            tuple(retry_on) if retry_on is not None else (TransientError, NetworkError)
        )
        if any(
            not isinstance(error_type, type) or not issubclass(error_type, Exception)
            for error_type in retry_types
        ):
            raise TypeError("retry_on must contain exception types")

        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._retry_on = retry_types
        self._sleep = sleep_func

        self._errors_by_type: Counter[str] = Counter()
        self._retries_performed = 0
        self._successful_retries = 0
        self._exhausted_operations = 0
        self._total_backoff = 0.0

    async def execute_with_retry(
        self,
        operation: Callable[P, Awaitable[T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        retries_done = 0
        max_attempts = self._max_retries + 1
        operation_url: str | None = None

        while True:
            attempt = retries_done + 1
            try:
                result = await operation(*args, **kwargs)
            except Exception as error:
                self._errors_by_type[type(error).__name__] += 1
                url = getattr(error, "url", None)
                operation_url = url

                if not isinstance(error, self._retry_on):
                    logger.warning(
                        "Operation failed without retry url=%s error_type=%s "
                        "attempt=%s/%s message=%s",
                        url,
                        type(error).__name__,
                        attempt,
                        max_attempts,
                        str(error),
                    )
                    raise

                if retries_done >= self._max_retries:
                    self._exhausted_operations += 1
                    logger.error(
                        "Retries exhausted url=%s error_type=%s attempts=%s message=%s",
                        url,
                        type(error).__name__,
                        max_attempts,
                        str(error),
                    )
                    raise

                delay = self._backoff_factor * 2**retries_done
                self._retries_performed += 1
                self._total_backoff += delay
                logger.warning(
                    "Retrying operation url=%s error_type=%s attempt=%s/%s "
                    "next_delay=%.3fs message=%s",
                    url,
                    type(error).__name__,
                    attempt,
                    max_attempts,
                    delay,
                    str(error),
                )
                await self._sleep(delay)
                retries_done += 1
            else:
                if retries_done > 0:
                    self._successful_retries += 1
                    logger.info(
                        "Operation succeeded after retry url=%s attempts=%s",
                        operation_url,
                        retries_done + 1,
                    )
                return result

    def get_stats(self) -> RetryStats:
        average_retry_delay = (
            self._total_backoff / self._retries_performed
            if self._retries_performed > 0
            else 0.0
        )
        return RetryStats(
            errors_by_type=dict(self._errors_by_type),
            retries_performed=self._retries_performed,
            successful_retries=self._successful_retries,
            exhausted_operations=self._exhausted_operations,
            total_backoff=self._total_backoff,
            average_retry_delay=average_retry_delay,
        )
