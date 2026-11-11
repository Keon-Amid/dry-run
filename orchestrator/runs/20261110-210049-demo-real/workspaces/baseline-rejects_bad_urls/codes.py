"""Six-digit code generation and validation for the shortlink library."""

import random

_DIGITS = frozenset("0123456789")
_CODE_SPACE = 10 ** 6


def is_valid_code(code) -> bool:
    """Return True only if code is a string of exactly 6 ASCII digits."""
    return isinstance(code, str) and len(code) == 6 and all(c in _DIGITS for c in code)


def new_code(taken):
    """Return a random 6-digit code not in taken, or None if taken is invalid or no code is free."""
    try:
        taken_set = set(taken)
    except TypeError:
        return None
    used = {c for c in taken_set if is_valid_code(c)}
    if len(used) >= _CODE_SPACE:
        return None
    for _ in range(100):
        candidate = f"{random.randrange(_CODE_SPACE):06d}"
        if candidate not in used:
            return candidate
    free = [f"{n:06d}" for n in range(_CODE_SPACE) if f"{n:06d}" not in used]
    return random.choice(free)
