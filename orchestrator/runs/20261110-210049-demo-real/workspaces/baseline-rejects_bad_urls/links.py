"""In-memory URL shortener for the shortlink library."""

import codes
import expiry
import urls

_ALIAS_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def _is_valid_alias(alias) -> bool:
    """Return True if alias is a string of 3 to 30 lowercase letters, digits or hyphens."""
    return isinstance(alias, str) and 3 <= len(alias) <= 30 and all(c in _ALIAS_CHARS for c in alias)


class Shortlink:
    """Keeps an in-memory mapping between normalized URLs and codes or aliases, with 30-day expiry and click counts."""

    def __init__(self):
        """Create an empty shortener."""
        self._code_by_url = {}
        self._url_by_code = {}
        self._created_by_code = {}
        self._clicks_by_code = {}

    def _remove(self, code):
        """Forget the link stored under code."""
        url = self._url_by_code.pop(code, None)
        self._created_by_code.pop(code, None)
        self._clicks_by_code.pop(code, None)
        if url is not None and self._code_by_url.get(url) == code:
            del self._code_by_url[url]

    def shorten(self, url, now=0, alias=None):
        """Return the code or alias for url; None if the URL, time or alias is invalid, taken, or no code is free."""
        if not expiry._is_time(now):
            return None
        if alias is not None and not _is_valid_alias(alias):
            return None
        try:
            normalized = urls.normalize(url)
        except ValueError:
            return None
        if alias is not None:
            if alias in self._url_by_code:
                if not expiry.is_expired(self._created_by_code[alias], now):
                    return alias if self._url_by_code[alias] == normalized else None
                self._remove(alias)
            self._url_by_code[alias] = normalized
            self._created_by_code[alias] = now
            self._clicks_by_code[alias] = 0
            return alias
        existing = self._code_by_url.get(normalized)
        if existing is not None:
            if not expiry.is_expired(self._created_by_code[existing], now):
                return existing
            self._remove(existing)
        code = codes.new_code(self._url_by_code.keys())
        if code is None:
            return None
        self._code_by_url[normalized] = code
        self._url_by_code[code] = normalized
        self._created_by_code[code] = now
        self._clicks_by_code[code] = 0
        return code

    def resolve(self, code, now=0):
        """Return the URL for a code or alias and count a click, or None if it is invalid, unknown, or expired."""
        if not (codes.is_valid_code(code) or _is_valid_alias(code)):
            return None
        if code not in self._url_by_code:
            return None
        expired = expiry.is_expired(self._created_by_code[code], now)
        if expired is None or expired:
            return None
        self._clicks_by_code[code] += 1
        return self._url_by_code[code]

    def stats(self, code):
        """Return {"url": ..., "clicks": ...} for a known code or alias, or None if unknown or invalid."""
        if not (codes.is_valid_code(code) or _is_valid_alias(code)):
            return None
        if code not in self._url_by_code:
            return None
        return {"url": self._url_by_code[code], "clicks": self._clicks_by_code[code]}

    def delete(self, code) -> bool:
        """Remove a code or alias and return True, or return False if there is no such link."""
        if not (codes.is_valid_code(code) or _is_valid_alias(code)):
            return False
        if code not in self._url_by_code:
            return False
        self._remove(code)
        return True
