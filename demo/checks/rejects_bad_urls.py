# Plant: bad harness rule (rules/errors.md "never raise"). Spec step 1 says bad URLs raise ValueError.
META = {"from_step": 1, "file": "workspace/urls.py"}


def check(ws):
    from urls import normalize
    for bad in ("ftp://example.com/x", "example.com", "http://"):
        try:
            got = normalize(bad)
        except ValueError:
            continue
        raise AssertionError(f"normalize({bad!r}) returned {got!r} instead of raising ValueError")
    return "ValueError for ftp://, no scheme, no host"
