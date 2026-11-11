"""Level loading for the dungeon game."""


def load(rows):
    """Parse a list of equal-length strings into a level dict with [row, col] positions."""
    walls = []
    pits = []
    starts = []
    key = None
    exit_pos = None
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            pos = [r, c]
            if ch == "#":
                walls.append(pos)
            elif ch == "^":
                pits.append(pos)
            elif ch == "@":
                starts.append(pos)
            elif ch == "k":
                key = pos
            elif ch == "E":
                exit_pos = pos
    if len(starts) != 1:
        raise ValueError(f"level must contain exactly one '@', found {len(starts)}")
    return {
        "height": len(rows),
        "width": len(rows[0]) if rows else 0,
        "walls": walls,
        "start": starts[0],
        "key": key,
        "exit": exit_pos,
        "pits": pits,
    }
