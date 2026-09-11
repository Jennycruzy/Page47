"""Small in-process controls for public operations with real cost."""

from __future__ import annotations

from collections import deque
from math import ceil
from threading import Lock
from time import monotonic


class SlidingWindowLimiter:
    """Bounded, process-local request limiter for a single web instance."""

    def __init__(self, maximum: int, window_seconds: float, max_keys: int = 10_000) -> None:
        if maximum < 1 or window_seconds <= 0 or max_keys < 1:
            raise ValueError("Limiter settings must be positive")
        self.maximum = maximum
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def retry_after(self, key: str, *, now: float | None = None) -> int | None:
        if not key.strip():
            raise ValueError("Limiter key must not be empty")
        current = monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            self._prune_keys(cutoff)
            if key not in self._requests and len(self._requests) >= self.max_keys:
                oldest_key = min(
                    self._requests,
                    key=lambda item: self._requests[item][-1]
                    if self._requests[item]
                    else float("-inf"),
                )
                self._requests.pop(oldest_key, None)
            timestamps = self._requests.setdefault(key, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.maximum:
                return max(1, ceil(timestamps[0] + self.window_seconds - current))
            timestamps.append(current)
        return None

    def _prune_keys(self, cutoff: float) -> None:
        stale = [
            key
            for key, values in self._requests.items()
            if not values or values[-1] <= cutoff
        ]
        for key in stale:
            self._requests.pop(key, None)
        if len(self._requests) <= self.max_keys:
            return
        oldest = sorted(
            self._requests,
            key=lambda key: self._requests[key][-1] if self._requests[key] else 0.0,
        )
        for key in oldest[: len(self._requests) - self.max_keys]:
            self._requests.pop(key, None)
