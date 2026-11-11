"""conversation.jsonl: one line per message, {"step": k, "msg": {...}}. Owner: C1."""
from __future__ import annotations

import json
import os

from builder.types import CONVERSATION


def _path(disk: str) -> str:
    return os.path.join(disk, CONVERSATION)


def load(disk: str) -> list:
    """Return list of {"step","msg"} records (empty if file missing).

    A torn final line (crash mid-write without newline) is ignored.
    """
    p = _path(disk)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, "r", encoding="utf-8") as f:
        data = f.read()
    lines = data.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:  # torn tail, no trailing newline
                break
            raise
    return out


def messages(disk: str) -> list:
    """Return just the msg dicts, in order (for API history)."""
    return [r["msg"] for r in load(disk)]


def max_step(disk: str) -> int:
    """Highest step in the log, 0 if empty."""
    return max((int(r["step"]) for r in load(disk)), default=0)


def _fsync_dir(d: str) -> None:
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def append_step(disk: str, k: int, msgs: list) -> None:
    """Append all msgs of step k in ONE write + flush + fsync."""
    if not msgs:
        return
    blob = "".join(json.dumps({"step": k, "msg": m}, ensure_ascii=False) + "\n" for m in msgs)
    p = _path(disk)
    existed = os.path.exists(p)
    with open(p, "a", encoding="utf-8") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    if not existed:
        _fsync_dir(disk)


def truncate_after(disk: str, k: int) -> int:
    """Drop records with step > k (atomic rewrite). Return number dropped."""
    p = _path(disk)
    if not os.path.exists(p):
        return 0
    recs = load(disk)
    keep = [r for r in recs if int(r["step"]) <= k]
    dropped = len(recs) - len(keep)
    with open(p, "rb") as f:
        raw = f.read()
    torn = bool(raw) and not raw.endswith(b"\n")
    if dropped == 0 and not torn:
        return 0
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    _fsync_dir(disk)
    return dropped
