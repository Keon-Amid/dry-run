"""Apply a Patch to the disk's spec.md / rules/. Owner: C3."""
from __future__ import annotations

from builder.types import Patch


def spec_sha(disk: str) -> str:
    """sha256 hex of spec.md bytes."""
    raise NotImplementedError


def load_patch(path: str) -> Patch:
    raise NotImplementedError


def apply(disk: str, p: Patch) -> tuple:
    """Apply p, assert it landed, write routes/<route>.md. Return (sha_before, sha_after).
    Raise PatchError on 0 / >1 matches, missing rule, or edit not landed."""
    raise NotImplementedError
