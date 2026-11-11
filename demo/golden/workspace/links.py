"""The Shortlink store, in memory."""
import codes
import expiry
import urls


class Shortlink:
    """An in-memory URL shortener."""

    def __init__(self):
        """Start empty."""
        self._links = {}   # code -> {"url", "created", "last_click", "clicks"}
        self._by_url = {}  # url -> generated code

    def shorten(self, url, now=0, alias=None) -> str:
        """Return the code for url, generating one or using alias."""
        url = urls.normalize(url)
        if alias is not None:
            if not codes.is_alias(alias):
                raise ValueError(f"bad alias: {alias!r}")
            if alias in self._links and self._links[alias]["url"] != url:
                raise ValueError(f"alias taken: {alias!r}")
            self._links.setdefault(alias, {"url": url, "created": now, "last_click": None, "clicks": 0})
            return alias
        if url in self._by_url and self._by_url[url] in self._links:
            return self._by_url[url]
        code = codes.new_code(set(self._links))
        self._links[code] = {"url": url, "created": now, "last_click": None, "clicks": 0}
        self._by_url[url] = code
        return code

    def resolve(self, code, now=0):
        """Return the URL for code and count a click, or None if unknown or expired."""
        if not codes.is_valid_code(code):
            return None
        link = self._links.get(code)
        if link is None or expiry.is_expired(link["created"], link["last_click"], now):
            return None
        link["last_click"] = now
        link["clicks"] += 1
        return link["url"]

    def stats(self, code):
        """Return {"url", "clicks"} for a known code, else None."""
        link = self._links.get(code)
        return None if link is None else {"url": link["url"], "clicks": link["clicks"]}

    def delete(self, code) -> bool:
        """Remove a link; True if it existed."""
        link = self._links.pop(code, None)
        if link is None:
            return False
        if self._by_url.get(link["url"]) == code:
            del self._by_url[link["url"]]
        return True
