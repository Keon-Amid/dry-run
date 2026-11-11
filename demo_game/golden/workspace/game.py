"""Game rules."""
import copy

import hazards
from level import load

DIRS = {"n": (-1, 0), "s": (1, 0), "e": (0, 1), "w": (0, -1)}


def new_game(level) -> dict:
    """A fresh state for level."""
    lv = load(level)
    return {"level": lv, "pos": list(lv["start"]), "lives": 3, "has_key": False, "status": "playing",
            "moves_left": 20}


def step(state, action) -> dict:
    """Return the state after action; never changes the given state."""
    if action not in DIRS:
        raise ValueError(f"bad action {action!r}")
    s = copy.deepcopy(state)
    if s["status"] != "playing":
        return s
    lv = s["level"]
    dr, dc = DIRS[action]
    r, c = s["pos"][0] + dr, s["pos"][1] + dc
    blocked = (not (0 <= r < lv["height"] and 0 <= c < lv["width"]) or [r, c] in lv["walls"]
               or ([r, c] == lv["exit"] and not s["has_key"]))
    if not blocked:
        if hazards.is_pit(lv, [r, c]):
            s["lives"] -= 1
        else:
            s["pos"] = [r, c]
            if lv["key"] is not None and [r, c] == lv["key"]:
                s["has_key"] = True
            if [r, c] == lv["exit"] and s["has_key"]:
                s["status"] = "won"
    s["moves_left"] -= 1
    if s["status"] == "playing" and (s["lives"] <= 0 or s["moves_left"] <= 0):
        s["status"] = "lost"
    return s
