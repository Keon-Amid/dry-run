"""Link expiry rules for the shortlink library."""

LIFETIME_SECONDS = 30 * 24 * 60 * 60


def is_expired(created, now) -> bool:
    """Return True once a link created at `created` is 30 days old at time `now` (or if the times are invalid)."""
    try:
        return now - created >= LIFETIME_SECONDS
    except Exception:
        return True
