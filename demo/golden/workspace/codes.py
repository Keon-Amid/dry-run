"""Short codes: generated codes are 6 digits; aliases are user-picked."""
import random
import re

_ALIAS = re.compile(r"^[a-z0-9-]{3,30}$")


def is_generated_code(code) -> bool:
    """True for a string of exactly 6 digits."""
    return isinstance(code, str) and len(code) == 6 and code.isdigit()


def is_alias(code) -> bool:
    """True for 3-30 lowercase letters, digits and hyphens."""
    return isinstance(code, str) and bool(_ALIAS.match(code))


def is_valid_code(code) -> bool:
    """True for any code this app can issue: a generated code or an alias."""
    return is_generated_code(code) or is_alias(code)


def new_code(taken) -> str:
    """A random 6-digit code not in `taken`."""
    while True:
        code = f"{random.randrange(10 ** 6):06d}"
        if code not in taken:
            return code
