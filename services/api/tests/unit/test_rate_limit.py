import pytest

from app.core.errors import RateLimitedError
from app.core.rate_limit import InMemoryRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_limiter(clock: FakeClock, *, max_attempts: int = 3, **kwargs: int) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(max_attempts=max_attempts, window_seconds=60, clock=clock, **kwargs)


def test_attempts_up_to_the_limit_are_allowed() -> None:
    limiter = make_limiter(FakeClock())
    for _ in range(3):
        limiter.check("key")


def test_attempt_over_the_limit_is_rejected_with_retry_after() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)
    for _ in range(3):
        limiter.check("key")

    clock.now += 10
    with pytest.raises(RateLimitedError) as caught:
        limiter.check("key")
    assert caught.value.retry_after == 50  # the oldest hit leaves the window in 50 seconds


def test_keys_are_limited_independently() -> None:
    limiter = make_limiter(FakeClock(), max_attempts=1)
    limiter.check("alice")
    limiter.check("bob")
    with pytest.raises(RateLimitedError):
        limiter.check("alice")


def test_attempts_are_allowed_again_after_the_window() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)
    for _ in range(3):
        limiter.check("key")

    clock.now += 61
    limiter.check("key")


def test_rejected_attempts_do_not_extend_the_lockout() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, max_attempts=1)
    limiter.check("key")
    for _ in range(5):
        clock.now += 5
        with pytest.raises(RateLimitedError):
            limiter.check("key")

    clock.now += 40  # 65 seconds after the only recorded hit
    limiter.check("key")


def test_tracked_keys_are_bounded() -> None:
    limiter = make_limiter(FakeClock(), max_keys=100)
    for index in range(1000):
        limiter.check(f"key-{index}")
    assert len(limiter._hits) <= 100
