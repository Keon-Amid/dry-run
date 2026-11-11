"""state.json read/write, atomic. Owner: C1."""
from __future__ import annotations

from builder.types import State


def load(disk: str) -> State:
    """Load state.json; if missing return State(last_done=0)."""
    raise NotImplementedError


def save(disk: str, st: State) -> None:
    """Atomic: write tmp, fsync, os.replace, fsync dir."""
    raise NotImplementedError
