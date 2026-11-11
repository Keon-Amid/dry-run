"""Expiry rules for shortened links."""

import math

EXPIRY_SECONDS = 30 * 24 * 60 * 60


def _is_time(value) -> bool:
    """Return True if value is a finite int or float (not bool)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def expires_at(created):
    """Return the expiry time for a link created at created, or None if created is not a valid time."""
    if not _is_time(created):
        return None
    return created + EXPIRY_SECONDS


def is_expired(created, now):
    """Return True if a link created at created has expired by now; None if either time is invalid."""
    if not _is_time(created) or not _is_time(now):
        return None
    return now >= created + EXPIRY_SECONDS
