from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self._interval = max(0.0, min_interval_seconds)
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._interval - (now - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.4,
    max_delay: float = 5.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    should_retry: Callable[[BaseException], bool] | None = None,
) -> T:
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except retry_on as exc:
            if attempt >= max_attempts or (should_retry and not should_retry(exc)):
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            time.sleep(delay + random.uniform(0, 0.25))
