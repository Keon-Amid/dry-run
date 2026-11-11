"""Map parsing, read literally from step 1: each line is stripped of surrounding whitespace."""
TILE = 16


def parse_map(text: str) -> list:
    """Rows of equal length: lines stripped, blank lines skipped, short rows padded on the right with spaces."""
    rows = [line.strip() for line in text.splitlines()]
    rows = [r for r in rows if r]
    width = max((len(r) for r in rows), default=0)
    return [r.ljust(width) for r in rows]
