"""Tile constants and map parsing for Dungeon Painter."""

TILE = 16  # pixels per tile


def parse_map(text: str) -> list:
    """Parse multi-line map text into a list of equal-length row strings."""
    rows = [line.strip() for line in text.splitlines()]
    rows = [row for row in rows if row]
    width = max((len(row) for row in rows), default=0)
    return [row.ljust(width) for row in rows]
