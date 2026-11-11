"""In-memory URL shortener."""

from codes import is_valid_alias, is_valid_code, new_code
from expiry import is_expired
from urls import normalize


class Shortlink:
    """Maps normalized URLs to codes (generated or alias) and back, entirely in memory."""

    def __init__(self):
        """Create an empty shortener."""
        self._code_by_url = {}
        self._url_by_code = {}
        self._last_used = {}
        self._clicks = {}

    def _forget(self, code):
        """Remove a code and its URL from all stores."""
        url = self._url_by_code.pop(code, None)
        self._last_used.pop(code, None)
        self._clicks.pop(code, None)
        if url is not None and self._code_by_url.get(url) == code:
            del self._code_by_url[url]
            # Another live code for the same URL may take over the lookup.
            for other, other_url in self._url_by_code.items():
                if other_url == url:
                    self._code_by_url[url] = other
                    break

    def _live_url(self, code, now):
        """Return the URL stored under code if it has not expired, else None (expired codes are dropped)."""
        url = self._url_by_code.get(code)
        if url is None:
            return None
        if is_expired(self._last_used[code], now):
            self._forget(code)
            return None
        return url

    def _store(self, code, url, now):
        """Record code for url as used at now, with no clicks yet."""
        self._url_by_code[code] = url
        self._last_used[code] = now
        self._clicks[code] = 0
        self._code_by_url.setdefault(url, code)

    def shorten(self, url, now=0, alias=None):
        """Return a code for url (or the given alias), or None if the input is invalid or unavailable."""
        try:
            normalized = normalize(url)
            if normalized is None:
                return None

            if alias is not None:
                if not is_valid_alias(alias):
                    return None
                existing = self._live_url(alias, now)
                if existing is not None:
                    if existing != normalized:
                        return None
                    self._last_used[alias] = now
                    return alias
                self._store(alias, normalized, now)
                return alias

            code = self._code_by_url.get(normalized)
            if code is not None and self._live_url(code, now) is not None:
                self._last_used[code] = now
                return code
            code = new_code(self._url_by_code)
            if code is None:
                return None
            self._store(code, normalized, now)
            self._code_by_url[normalized] = code
            return code
        except Exception:
            return None

    def resolve(self, code, now=0):
        """Return the URL for a generated code or alias and count a click, or None if invalid, unknown or expired."""
        try:
            if not (is_valid_code(code) or is_valid_alias(code)):
                return None
            url = self._live_url(code, now)
            if url is None:
                return None
            self._last_used[code] = now
            self._clicks[code] += 1
            return url
        except Exception:
            return None

    def stats(self, code, now=0):
        """Return {"url": ..., "clicks": ...} for a known code, or None if unknown or expired."""
        try:
            if not (is_valid_code(code) or is_valid_alias(code)):
                return None
            url = self._live_url(code, now)
            if url is None:
                return None
            return {"url": url, "clicks": self._clicks[code]}
        except Exception:
            return None

    def delete(self, code) -> bool:
        """Remove a generated code or alias; return True if it existed, else False."""
        try:
            if not (is_valid_code(code) or is_valid_alias(code)):
                return False
            if code not in self._url_by_code:
                return False
            self._forget(code)
            return True
        except Exception:
            return False
