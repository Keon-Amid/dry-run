"""URL normalization for the shortlink library."""

_SCHEMES = ("http", "https")


def normalize(url: str) -> str | None:
    """Return the normalized http(s) URL, or None if the input is not a valid http(s) URL with a host."""
    if not isinstance(url, str):
        return None
    scheme_end = url.find("://")
    if scheme_end == -1:
        return None
    scheme = url[:scheme_end].lower()
    if scheme not in _SCHEMES:
        return None
    rest = url[scheme_end + 3:]

    # The authority ends at the first '/', '?' or '#'.
    end = len(rest)
    for marker in "/?#":
        idx = rest.find(marker)
        if idx != -1 and idx < end:
            end = idx
    authority = rest[:end]
    tail = rest[end:]

    # Split off userinfo (kept as given), then the port.
    userinfo, sep, hostport = authority.rpartition("@")
    prefix = userinfo + sep
    if hostport.startswith("["):
        close = hostport.find("]")
        if close == -1:
            return None
        host = hostport[:close + 1]
        port = hostport[close + 1:]
    else:
        host, colon, port_part = hostport.partition(":")
        port = colon + port_part

    if not host or host == "[]":
        return None
    if port and not (port.startswith(":") and len(port) > 1):
        return None

    return f"{scheme}://{prefix}{host.lower()}{port}{tail}"
