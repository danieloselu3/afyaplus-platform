# rate_limit.py - a small sliding-window counter that says "slow down"
import time

from fastapi import HTTPException

WINDOW_SECONDS = 60
_counters: dict[str, list[float]] = {}


def check_rate_limit(key: str, max_requests: int = 5, window: int = WINDOW_SECONDS) -> None:
    """Allow at most max_requests per key per window. Raise 429 if exceeded.

    In-memory, so each service copy counts separately; production moves this
    to a shared store such as Redis (see docs/ENGINEERING_REPORT.md).
    """
    now = time.time()
    recent = [t for t in _counters.get(key, []) if now - t < window]
    if len(recent) >= max_requests:
        raise HTTPException(status_code=429,
                            detail="Too many requests. Wait a minute and try again.",
                            headers={"Retry-After": str(window)})
    recent.append(now)
    _counters[key] = recent


def reset() -> None:
    """Clear all counters (used by the test suite)."""
    _counters.clear()
