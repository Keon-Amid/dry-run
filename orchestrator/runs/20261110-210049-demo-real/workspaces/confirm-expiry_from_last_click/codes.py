"""Six-digit short code generation and validation."""

import re
import secrets

_CODE_RE = re.compile(r"[0-9]{6}")
_MAX_RANDOM_TRIES = 100


def is_valid_code(code: str) -> bool:
    """Return True only if code is a string of exactly six ASCII digits."""
    try:
        return isinstance(code, str) and _CODE_RE.fullmatch(code) is not None
    except Exception:
        return False


def new_code(taken: set) -> str:
    """Return a random six-digit code not in taken, or None if none is available."""
    try:
        for _ in range(_MAX_RANDOM_TRIES):
            code = "%06d" % secrets.randbelow(1000000)
            if code not in taken:
                return code
        # Fall back to scanning all codes in a random starting offset.
        start = secrets.randbelow(1000000)
        for i in range(1000000):
            code = "%06d" % ((start + i) % 1000000)
            if code not in taken:
                return code
        return None
    except Exception:
        return None


_ALIAS_RE = re.compile(r"[a-z0-9\-]{3,30}")


def is_valid_alias(alias: str) -> bool:
    """Return True only if alias is 3 to 30 lowercase letters, digits or hyphens."""
    try:
        return isinstance(alias, str) and _ALIAS_RE.fullmatch(alias) is not None
    except Exception:
        return False
