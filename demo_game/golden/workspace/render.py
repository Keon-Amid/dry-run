"""Text rendering."""


def render(state) -> str:
    """The level as text with @ at the player."""
    lv = state["level"]
    grid = [list(row) for row in lv["rows"]]
    sr, sc = lv["start"]
    grid[sr][sc] = "."
    if state["has_key"] and lv["key"]:
        grid[lv["key"][0]][lv["key"][1]] = "."
    r, c = state["pos"]
    grid[r][c] = "@"
    return "\n".join("".join(row) for row in grid)
