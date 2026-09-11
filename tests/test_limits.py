from __future__ import annotations

import pytest

from page47.web.limits import SlidingWindowLimiter


def test_sliding_window_limits_requests_and_expires_them() -> None:
    limiter = SlidingWindowLimiter(maximum=2, window_seconds=10)

    assert limiter.retry_after("resident", now=100.0) is None
    assert limiter.retry_after("resident", now=100.0) is None
    assert limiter.retry_after("resident", now=100.0) == 10
    assert limiter.retry_after("resident", now=110.0) is None


def test_limiter_keeps_key_count_bounded() -> None:
    limiter = SlidingWindowLimiter(maximum=1, window_seconds=10, max_keys=2)

    assert limiter.retry_after("one", now=1.0) is None
    assert limiter.retry_after("two", now=2.0) is None
    assert limiter.retry_after("three", now=3.0) is None
    assert limiter.retry_after("three", now=3.0) == 10
    assert len(limiter._requests) <= 2


def test_limiter_rejects_empty_keys() -> None:
    limiter = SlidingWindowLimiter(maximum=1, window_seconds=10)

    with pytest.raises(ValueError, match="key"):
        limiter.retry_after(" ", now=1.0)
