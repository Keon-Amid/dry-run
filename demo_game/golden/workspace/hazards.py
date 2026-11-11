"""Hazards: a pit costs a life and the player stays on the square they came from."""


def is_pit(level, pos) -> bool:
    """True if pos is a pit."""
    return list(pos) in level["pits"]
