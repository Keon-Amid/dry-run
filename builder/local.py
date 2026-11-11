"""Local mode: a disk is a plain folder. Owner: C3.

save/resume are a shutil.copytree with symlinks preserved, so workspace/.git (objects, refs, tags) comes along
byte for byte and the copy is an independent repo.
"""
from __future__ import annotations

import os
import shutil

from builder.types import ResumeError


def _copy(src: str, dest: str) -> str:
    src_r = os.path.realpath(src)
    dest_r = os.path.realpath(dest)
    if not os.path.isdir(src_r):
        raise FileNotFoundError(f"disk folder not found: {src}")
    if dest_r == src_r or dest_r.startswith(src_r + os.sep):
        raise ValueError(f"dest {dest} is inside src {src}")
    if os.path.isdir(dest) and not os.listdir(dest):
        os.rmdir(dest)  # empty dest is fine: copytree wants to create it
    shutil.copytree(src, dest, symlinks=True)
    return dest


def save(disk: str, dest: str) -> str:
    """Copy disk folder to dest (git intact, symlinks preserved). Return dest."""
    if os.path.lexists(dest) and not (os.path.isdir(dest) and not os.listdir(dest)):
        raise FileExistsError(f"save dest exists and is not empty: {dest}")
    return _copy(disk, dest)


def resume(src: str, dest: str) -> str:
    """Make dest a fresh copy of saved disk src. Return dest."""
    if os.path.lexists(dest) and not (os.path.isdir(dest) and not os.listdir(dest)):
        raise ResumeError(f"resume dest exists and is not empty: {dest}")
    return _copy(src, dest)
