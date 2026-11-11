"""Torch light, read literally: floor tiles within 3 steps (grid distance) of a torch. Walls don't block it."""
FLOOR = set(".@g$*")
REACH = 3


def lit(grid) -> set:
    """The (column, row) floor tiles whose Manhattan distance to a torch is at most 3."""
    torches = [(c, r) for r, row in enumerate(grid) for c, ch in enumerate(row) if ch == "*"]
    return {(c, r) for r, row in enumerate(grid) for c, ch in enumerate(row)
            if ch in FLOOR and any(abs(c - tc) + abs(r - tr) <= REACH for tc, tr in torches)}
