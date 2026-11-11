"""Expiry rules for shortlinks: a link lives 30 days after its last activity."""

import math

LIFETIME = 2592000  # 30 days in seconds


def is_valid_time(value) -> bool:
    """Return True if value is a finite int or float (not a bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def is_expired(last_activity, now) -> bool:
    """Return True if now is LIFETIME seconds or more after last_activity; False if either time is invalid."""
    if not is_valid_time(last_activity) or not is_valid_time(now):
        return False
    return now - last_activity >= LIFETIME
