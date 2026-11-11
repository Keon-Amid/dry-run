"""Local mode: a disk is a plain folder. Owner: C3."""
from __future__ import annotations


def save(disk: str, dest: str) -> str:
    """Copy disk folder to dest (git intact, symlinks preserved). Return dest."""
    raise NotImplementedError


def resume(src: str, dest: str) -> str:
    """Make dest a fresh copy of saved disk src. Return dest."""
    raise NotImplementedError
