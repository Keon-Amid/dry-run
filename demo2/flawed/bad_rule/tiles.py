"""Map parsing: one character per tile."""
TILE = 16


def parse_map(text: str) -> list:
    """Rows of equal length: trailing whitespace removed, leading spaces kept (void), blank lines skipped."""
    rows = [line.rstrip() for line in text.splitlines()]
    rows = [r for r in rows if r]
    width = max((len(r) for r in rows), default=0)
    return [r.ljust(width) for r in rows]
