# Held out for the bad-rule plant: same intent (bad URLs raise ValueError), different case, through shorten().
META = {"from_step": 3, "file": "workspace/urls.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    for bad in ("javascript:alert(1)", "mailto:a@example.com"):
        try:
            got = s.shorten(bad, now=0)
        except ValueError:
            continue
        raise AssertionError(f"shorten({bad!r}) returned {got!r} instead of raising ValueError")
    return "ValueError through shorten"
