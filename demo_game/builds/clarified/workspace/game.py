"""Game state and movement for the dungeon game."""

from hazards import is_pit, pit_damage
from level import load

_MOVES = {"n": (-1, 0), "s": (1, 0), "e": (0, 1), "w": (0, -1)}


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
    """Return a new state after moving the player one cell in direction action ('n', 's', 'e', 'w')."""
    if action not in _MOVES:
        raise ValueError(f"unknown action: {action!r}")
    level = state["level"]
    dr, dc = _MOVES[action]
    r, c = state["pos"]
    nr, nc = r + dr, c + dc
    target = [nr, nc]
    has_key = state["has_key"]
    status = state["status"]
    lives = state["lives"]
    if not (0 <= nr < level["height"] and 0 <= nc < level["width"]):
        target = [r, c]
    elif target in level["walls"]:
        target = [r, c]
    elif target == level["exit"] and not has_key:
        target = [r, c]
    elif target == level["exit"]:
        status = "won"
    elif is_pit(level, target):
        target = [r, c]
        lives -= pit_damage()
    elif target == level["key"]:
        has_key = True
    new_state = dict(state)
    new_state["pos"] = target
    new_state["has_key"] = has_key
    new_state["status"] = status
    new_state["lives"] = lives
    return new_state
