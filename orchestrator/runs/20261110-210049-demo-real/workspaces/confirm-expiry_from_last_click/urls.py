"""URL normalization for the shortlink library."""

import re
from urllib.parse import urlsplit

_URL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*)://([^/?#]*)(.*)$", re.DOTALL)


def normalize(url: str) -> str:
    """Return the normalized http(s) URL with lowercased scheme and host, or None if invalid."""
    try:
        if not isinstance(url, str):
            return None
        match = _URL_RE.match(url)
        if match is None:
            return None
        scheme, authority, remainder = match.groups()
        scheme = scheme.lower()
        if scheme not in ("http", "https"):
            return None
        if not authority:
            return None
        if urlsplit("//" + authority).hostname in (None, ""):
            return None
        userinfo, sep, hostport = authority.rpartition("@")
        return scheme + "://" + userinfo + sep + hostport.lower() + remainder
    except Exception:
        return None
