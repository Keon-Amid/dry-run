"""In-memory URL shortener for the shortlink library."""

import codes
import expiry
import urls


class Shortlink:
    """Maps normalized URLs to six-digit codes and back, kept in memory, with 30-day expiry and click counts."""

    def __init__(self):
        """Create an empty shortener."""
        self._code_by_url = {}
        self._url_by_code = {}
        self._last_activity = {}
        self._clicks = {}

    def shorten(self, url: str, now=0, alias=None) -> str | None:
        """Return the code for url (or the requested alias), or None if the URL, time or alias is invalid."""
        if not expiry.is_valid_time(now):
            return None
        normalized = urls.normalize(url)
        if normalized is None:
            return None
        if alias is not None:
            if not codes.is_valid_alias(alias):
                return None
            taken_url = self._url_by_code.get(alias)
            if taken_url is not None:
                return alias if taken_url == normalized else None
            self._register(alias, normalized, now)
            self._code_by_url.setdefault(normalized, alias)
            return alias
        existing = self._code_by_url.get(normalized)
        if existing is not None:
            return existing
        code = codes.new_code(self._url_by_code)
        if code is None:
            return None
        self._register(code, normalized, now)
        self._code_by_url[normalized] = code
        return code

    def resolve(self, code: str, now=0) -> str | None:
        """Return the URL for a live code or alias, refresh its expiry and count a click, or None otherwise."""
        if not (codes.is_valid_code(code) or codes.is_valid_alias(code)):
            return None
        if not expiry.is_valid_time(now):
            return None
        url = self._url_by_code.get(code)
        if url is None:
            return None
        if expiry.is_expired(self._last_activity[code], now):
            return None
        self._last_activity[code] = now
        self._clicks[code] += 1
        return url

    def stats(self, code: str) -> dict | None:
        """Return the URL and click count for a known code or alias, or None if unknown."""
        if not (codes.is_valid_code(code) or codes.is_valid_alias(code)):
            return None
        url = self._url_by_code.get(code)
        if url is None:
            return None
        return {"url": url, "clicks": self._clicks[code]}

    def delete(self, code: str) -> bool:
        """Remove a code or alias and its link, returning True if it existed and False otherwise."""
        if not (codes.is_valid_code(code) or codes.is_valid_alias(code)):
            return False
        url = self._url_by_code.pop(code, None)
        if url is None:
            return False
        self._last_activity.pop(code, None)
        self._clicks.pop(code, None)
        if self._code_by_url.get(url) == code:
            del self._code_by_url[url]
        return True

    def _register(self, code: str, url: str, now) -> None:
        """Store a new code for url, starting its activity clock and click count."""
        self._url_by_code[code] = url
        self._last_activity[code] = now
        self._clicks[code] = 0
