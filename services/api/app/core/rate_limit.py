"""Sliding-window rate limiting.

``InMemoryRateLimiter`` is correct for a single API replica. Before running several replicas,
replace it with a shared store (Redis, milestone 2) behind the same ``check`` method.
"""

import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from app.core.errors import RateLimitedError

_MAX_TRACKED_KEYS = 50_000


class InMemoryRateLimiter:
    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = _MAX_TRACKED_KEYS,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        # Least recently used key first, so memory stays bounded under key-flooding.
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def check(self, key: str) -> None:
        """Record one attempt for ``key``; raise ``RateLimitedError`` when over the limit."""
        now = self._clock()
        window_start = now - self._window_seconds
        hits = self._hits.pop(key, None) or deque()
        while hits and hits[0] <= window_start:
            hits.popleft()

        if len(hits) >= self._max_attempts:
            self._hits[key] = hits
            retry_after = max(1, math.ceil(hits[0] + self._window_seconds - now))
            raise RateLimitedError(retry_after=retry_after)

        hits.append(now)
        self._hits[key] = hits
        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)
