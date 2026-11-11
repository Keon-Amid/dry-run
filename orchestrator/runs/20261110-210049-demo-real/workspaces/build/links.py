"""In-memory shortlink store for the shortlink library."""

import codes
import expiry
import urls


class Shortlink:
    """Maps normalized URLs to codes (generated or user aliases) and back, in memory, with 30-day expiry and click counts."""

    def __init__(self):
        """Create an empty store."""
        self._code_by_url = {}  # normalized url -> generated code
        self._entries = {}  # code or alias -> {"url": ..., "created": ..., "clicks": ...}

    def _new_entry(self, normalized, now):
        """Build a fresh store entry for a normalized URL created at `now`."""
        return {"url": normalized, "created": now, "clicks": 0}

    def _drop(self, key):
        """Remove a stored code or alias, and its generated-code mapping if it has one."""
        entry = self._entries.pop(key)
        if self._code_by_url.get(entry["url"]) == key:
            del self._code_by_url[entry["url"]]

    def shorten(self, url, now=0, alias=None):
        """Return the code (or the requested alias) for a URL, or None if the URL or alias is invalid or taken."""
        try:
            normalized = urls.normalize(url)
            if normalized is None:
                return None
            if alias is not None:
                return self._shorten_alias(normalized, now, alias)
            existing = self._code_by_url.get(normalized)
            if existing is not None:
                if not expiry.is_expired(self._entries[existing]["created"], now):
                    return existing
                self._drop(existing)
            code = codes.new_code(self._entries)
            if code is None:
                return None
            self._code_by_url[normalized] = code
            self._entries[code] = self._new_entry(normalized, now)
            return code
        except Exception:
            return None

    def _shorten_alias(self, normalized, now, alias):
        """Store a user alias for a normalized URL, or return None if the alias is invalid or held by another live link."""
        if not codes.is_valid_alias(alias):
            return None
        entry = self._entries.get(alias)
        if entry is not None:
            if not expiry.is_expired(entry["created"], now):
                return alias if entry["url"] == normalized else None
            self._drop(alias)
        self._entries[alias] = self._new_entry(normalized, now)
        return alias

    def resolve(self, code, now=0):
        """Return the URL for a live code or alias and count a click, or None if it is malformed, unknown, or expired."""
        try:
            if not (codes.is_valid_code(code) or codes.is_valid_alias(code)):
                return None
            entry = self._entries.get(code)
            if entry is None:
                return None
            if expiry.is_expired(entry["created"], now):
                return None
            entry["clicks"] += 1
            return entry["url"]
        except Exception:
            return None

    def stats(self, code):
        """Return {"url": ..., "clicks": ...} for a known code or alias, or None if it is malformed or unknown."""
        try:
            if not (codes.is_valid_code(code) or codes.is_valid_alias(code)):
                return None
            entry = self._entries.get(code)
            if entry is None:
                return None
            return {"url": entry["url"], "clicks": entry["clicks"]}
        except Exception:
            return None

    def delete(self, code):
        """Remove a code or alias and return True, or return False if it is malformed or unknown."""
        try:
            if not (codes.is_valid_code(code) or codes.is_valid_alias(code)):
                return False
            if code not in self._entries:
                return False
            self._drop(code)
            return True
        except Exception:
            return False
