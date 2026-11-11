"""URL normalization for the shortlink library."""

from urllib.parse import urlsplit, urlunsplit


def normalize(url: str) -> str:
    """Return the URL with scheme and host lowercased; raise ValueError if it is not a valid http(s) URL with a host."""
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"unsupported scheme: {parts.scheme!r}")
    if not parts.hostname:
        raise ValueError("URL has no host")
    userinfo, at, hostport = parts.netloc.rpartition("@")
    netloc = userinfo + at + hostport.lower()
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))
