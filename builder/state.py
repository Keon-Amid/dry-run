"""state.json read/write, atomic. Owner: C1."""
from __future__ import annotations

import json
import os

from builder.types import STATE, State


def _path(disk: str) -> str:
    return os.path.join(disk, STATE)


def load(disk: str) -> State:
    """Load state.json; if missing return State(last_done=0)."""
    p = _path(disk)
    if not os.path.exists(p):
        return State(last_done=0)
    with open(p, "r", encoding="utf-8") as f:
        return State.from_dict(json.load(f))


def save(disk: str, st: State) -> None:
    """Atomic: write tmp, fsync, os.replace, fsync dir."""
    p = _path(disk)
    tmp = p + ".tmp"
    data = json.dumps(st.to_dict(), indent=2, sort_keys=True) + "\n"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    fd = os.open(disk, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
