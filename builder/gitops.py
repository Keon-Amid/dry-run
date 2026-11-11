"""git in DISK/workspace with a fixed identity. Owner: C1."""
from __future__ import annotations


def init_workspace(disk: str) -> str:
    """If workspace/ has no .git: git init, empty commit, tag step-0. Return HEAD sha. Idempotent."""
    raise NotImplementedError


def commit_step(disk: str, k: int) -> str:
    """git add -A; commit --allow-empty -m 'step k' (identity builder/builder@dryrun.local); tag -f step-k. Return sha."""
    raise NotImplementedError


def head(disk: str) -> str:
    raise NotImplementedError


def tag_sha(disk: str, k: int) -> str | None:
    """sha of tag step-k, or None."""
    raise NotImplementedError


def reset_to(disk: str, k: int) -> None:
    """reset --hard step-k; clean -fdx; delete tags step-j for j > k."""
    raise NotImplementedError


def delete_tags_after(disk: str, k: int) -> list:
    """Delete tags step-j, j > k. Return deleted tag names."""
    raise NotImplementedError


def repair(disk: str, last_done: int) -> list:
    """Make log, HEAD and tags agree with last_done (truncate log, reset, clean, drop stale tags).
    Return list of human-readable repair actions taken ([] if consistent).
    Raise ResumeError if tag step-<last_done> is missing."""
    raise NotImplementedError
