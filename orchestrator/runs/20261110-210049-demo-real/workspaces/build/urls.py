"""URL normalization for the shortlink library."""

from urllib.parse import urlsplit


def normalize(url: str) -> str | None:
    """Return the URL with lowercased scheme and host, or None if it is not a valid http(s) URL."""
    try:
        if not isinstance(url, str):
            return None
        sep = url.find("://")
        if sep < 0:
            return None
        scheme = url[:sep]
        if scheme.lower() not in ("http", "https"):
            return None
        remainder = url[sep + 3:]
        end = len(remainder)
        for ch in "/?#":
            idx = remainder.find(ch)
            if idx != -1 and idx < end:
                end = idx
        authority, tail = remainder[:end], remainder[end:]

        userinfo, at, hostport = authority.rpartition("@")
        if hostport.startswith("["):
            close = hostport.find("]")
            if close < 0:
                return None
            host, rest = hostport[:close + 1], hostport[close + 1:]
            if rest and not rest.startswith(":"):
                return None
        else:
            host, colon, port = hostport.partition(":")
            rest = colon + port

        if not host or host == "[]":
            return None
        # Validate the port (raises ValueError if malformed) and the host.
        parsed = urlsplit(url)
        if parsed.hostname is None or parsed.port is not None and not (0 <= parsed.port <= 65535):
            return None

        return scheme.lower() + "://" + (userinfo + at if at else "") + host.lower() + rest + tail
    except Exception:
        return None
