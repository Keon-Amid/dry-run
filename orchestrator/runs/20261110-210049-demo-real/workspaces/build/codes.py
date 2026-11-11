"""Six-digit code generation for the shortlink library."""

import secrets

_DIGITS = "0123456789"
_CODE_SPACE = 10 ** 6


def is_valid_code(code) -> bool:
    """Return True only if the value is a string of exactly six ASCII digits."""
    try:
        return isinstance(code, str) and len(code) == 6 and all(c in _DIGITS for c in code)
    except Exception:
        return False


def new_code(taken):
    """Return a random six-digit code not in `taken`, or None if none is available or input is invalid."""
    try:
        taken_codes = {c for c in taken if is_valid_code(c)}
        if len(taken_codes) >= _CODE_SPACE:
            return None

        # Fast path: rejection sampling while the space is mostly free.
        for _ in range(100):
            candidate = f"{secrets.randbelow(_CODE_SPACE):06d}"
            if candidate not in taken_codes:
                return candidate

        # Slow path: pick uniformly among the remaining free codes.
        k = secrets.randbelow(_CODE_SPACE - len(taken_codes))
        for n in range(_CODE_SPACE):
            candidate = f"{n:06d}"
            if candidate in taken_codes:
                continue
            if k == 0:
                return candidate
            k -= 1
        return None
    except Exception:
        return None


_ALIAS_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"


def is_valid_alias(alias) -> bool:
    """Return True only if the value is a string of 3 to 30 lowercase letters, digits or hyphens."""
    try:
        return isinstance(alias, str) and 3 <= len(alias) <= 30 and all(c in _ALIAS_CHARS for c in alias)
    except Exception:
        return False
