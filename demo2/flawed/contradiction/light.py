"""Torch light: floor tiles within 3 walking steps of a torch."""
from collections import deque

FLOOR = set(".@g$*")
REACH = 3


def lit(grid) -> set:
    """The (column, row) floor tiles within 3 steps of a torch, walking up/down/left/right through floor only."""
    out = set()
    for r0, row in enumerate(grid):
        for c0, ch in enumerate(row):
            if ch != "*":
                continue
            seen = {(c0, r0): 0}
            q = deque([(c0, r0)])
            while q:
                c, r = q.popleft()
                d = seen[(c, r)]
                if d == REACH:
                    continue
                for nc, nr in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                    if 0 <= nr < len(grid) and 0 <= nc < len(grid[nr]) and grid[nr][nc] in FLOOR \
                            and (nc, nr) not in seen:
                        seen[(nc, nr)] = d + 1
                        q.append((nc, nr))
            out |= set(seen)
    return out
