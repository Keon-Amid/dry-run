"""Torch lighting for Dungeon Painter."""

RADIUS = 3  # steps a torch lights
FLOOR_CHARS = ".@g$*"  # floor, plus sprites which stand on floor


def lit(grid) -> set:
    """Return the (column, row) floor tiles within 3 steps of any torch."""
    result = set()
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch != "*":
                continue
            for dr in range(-RADIUS, RADIUS + 1):
                for dc in range(-RADIUS, RADIUS + 1):
                    if abs(dr) + abs(dc) > RADIUS:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < len(grid) and 0 <= cc < len(grid[rr]):
                        if grid[rr][cc] in FLOOR_CHARS:
                            result.add((cc, rr))
    return result
