"""Tests for the retry backoff calculation."""

from app.config import get_settings
from app.worker import backoff_delay


def test_backoff_stays_within_jitter_bounds():
    """Delay lies between half and full of the capped exponential value."""
    settings = get_settings()
    for attempt in range(1, 8):
        full = min(
            settings.worker_backoff_cap,
            settings.worker_backoff_base * 2**attempt,
        )
        for _ in range(100):
            delay = backoff_delay(attempt)
            assert full * 0.5 <= delay <= full


def test_backoff_is_capped_for_large_attempts():
    """Delay never exceeds the configured cap, however many retries."""
    cap = get_settings().worker_backoff_cap
    for _ in range(100):
        assert backoff_delay(50) <= cap


def test_backoff_is_always_positive():
    """Delay is never zero or negative, so retries are always in the future."""
    for attempt in range(1, 20):
        assert backoff_delay(attempt) > 0
