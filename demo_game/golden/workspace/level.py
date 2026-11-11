"""Level loading."""


def load(rows) -> dict:
    """Parse a level (list of strings) into a dict of positions."""
    walls, pits, start, key, exit_ = [], [], [], None, None
    starts = []
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == "#":
                walls.append([r, c])
            elif ch == "^":
                pits.append([r, c])
            elif ch == "@":
                starts.append([r, c])
            elif ch == "k":
                key = [r, c]
            elif ch == "E":
                exit_ = [r, c]
    if len(starts) != 1:
        raise ValueError("level needs exactly one @")
    return {"height": len(rows), "width": len(rows[0]) if rows else 0, "walls": walls, "start": starts[0],
            "key": key, "exit": exit_, "pits": pits, "rows": list(rows)}
