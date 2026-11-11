"""Six-digit short code generation and validation for the shortlink library."""

import random
from collections.abc import Container

_DIGITS = frozenset("0123456789")
_CODE_SPACE = 10 ** 6
_RANDOM_ATTEMPTS = 1000


def is_valid_code(code: str) -> bool:
    """Return True only if code is a string of exactly six ASCII digits."""
    if not isinstance(code, str) or len(code) != 6:
        return False
    return all(ch in _DIGITS for ch in code)


def new_code(taken: Container) -> str | None:
    """Return a random valid six-digit code not in taken, or None if none is available."""
    if not isinstance(taken, Container):
        return None
    for _ in range(_RANDOM_ATTEMPTS):
        code = f"{random.randrange(_CODE_SPACE):06d}"
        if code not in taken:
            return code
    # Dense fallback: pick uniformly among the codes that are still free.
    free = [f"{n:06d}" for n in range(_CODE_SPACE) if f"{n:06d}" not in taken]
    if not free:
        return None
    return random.choice(free)


_ALIAS_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def is_valid_alias(alias: str) -> bool:
    """Return True if alias is 3 to 30 characters of lowercase letters, digits and hyphens."""
    if not isinstance(alias, str) or not 3 <= len(alias) <= 30:
        return False
    return all(ch in _ALIAS_CHARS for ch in alias)
