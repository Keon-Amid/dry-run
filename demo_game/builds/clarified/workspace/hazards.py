"""Pit hazard logic for the dungeon game."""

PIT_DAMAGE = 1


def is_pit(level, pos):
    """Return True if the position holds a pit in the level."""
    return list(pos) in level["pits"]


def pit_damage():
    """Return how many lives stepping onto a pit costs."""
    return PIT_DAMAGE
