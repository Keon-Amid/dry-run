"""URL normalization."""
from urllib.parse import urlsplit, urlunsplit


def normalize(url: str) -> str:
    """Return the URL with scheme and host lowercased; raise ValueError if it is not http(s) with a host."""
    if not isinstance(url, str):
        raise ValueError("url must be a string")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) URL: {url!r}")
    netloc = parts.netloc
    host_start = netloc.rfind("@") + 1
    netloc = netloc[:host_start] + netloc[host_start:].lower()
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))
