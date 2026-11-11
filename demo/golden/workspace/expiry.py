"""Expiry: a link expires 30 days after its last click (or after creation if never clicked)."""
DAY = 86400
TTL = 30 * DAY


def is_expired(created, last_click, now) -> bool:
    """True when more than 30 days have passed since the last click, or since creation if never clicked."""
    start = last_click if last_click is not None else created
    return now - start > TTL
