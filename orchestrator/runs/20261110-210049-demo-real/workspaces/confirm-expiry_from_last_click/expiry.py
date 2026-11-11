"""Expiry rule: a link expires after 30 days without use."""

EXPIRY_SECONDS = 30 * 24 * 60 * 60


def is_expired(last_used, now) -> bool:
    """Return True if more than 30 days passed between last_used and now (True on bad input)."""
    try:
        return (now - last_used) > EXPIRY_SECONDS
    except Exception:
        return True
