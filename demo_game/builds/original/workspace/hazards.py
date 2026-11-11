"""Hazard handling (pits) for the dungeon game."""


def apply_hazards(state):
    """Return a state with one life lost if the player stands on a pit."""
    if state["pos"] in state["level"]["pits"]:
        return {**state, "lives": state["lives"] - 1}
    return state
