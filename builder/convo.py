"""conversation.jsonl: one line per message, {"step": k, "msg": {...}}. Owner: C1."""
from __future__ import annotations


def load(disk: str) -> list:
    """Return list of {"step","msg"} records (empty if file missing)."""
    raise NotImplementedError


def messages(disk: str) -> list:
    """Return just the msg dicts, in order (for API history)."""
    raise NotImplementedError


def max_step(disk: str) -> int:
    """Highest step in the log, 0 if empty."""
    raise NotImplementedError


def append_step(disk: str, k: int, msgs: list) -> None:
    """Append all msgs of step k in ONE write + flush + fsync."""
    raise NotImplementedError


def truncate_after(disk: str, k: int) -> int:
    """Drop records with step > k (atomic rewrite). Return number dropped."""
    raise NotImplementedError
