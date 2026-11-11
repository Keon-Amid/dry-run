"""Game state and movement for the dungeon game."""

from hazards import apply_hazards
from level import load

_MOVES = {
    "n": (-1, 0),
    "s": (1, 0),
    "e": (0, 1),
    "w": (0, -1),
}


def new_game(level):
    """Create a fresh game state from a list of level strings."""
    parsed = load(level)
    return {
        "level": parsed,
        "pos": list(parsed["start"]),
        "lives": 3,
        "has_key": False,
        "status": "playing",
    }


def step(state, action):
    """Apply one move action ('n', 's', 'e', 'w') and return the resulting state."""
    if action not in _MOVES:
        raise ValueError(f"unknown action: {action!r}")
    dr, dc = _MOVES[action]
    level = state["level"]
    r, c = state["pos"]
    target = [r + dr, c + dc]
    nr, nc = target
    in_bounds = 0 <= nr < level["height"] and 0 <= nc < level["width"]
    if not in_bounds or target in level["walls"]:
        return {**state, "pos": [r, c]}
    if target == level["exit"]:
        if not state["has_key"]:
            return {**state, "pos": [r, c]}
        return {**state, "pos": target, "status": "won"}
    has_key = state["has_key"] or target == level["key"]
    moved = {**state, "pos": target, "has_key": has_key}
    return apply_hazards(moved)
