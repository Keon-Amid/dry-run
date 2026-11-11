META = {"from_step": 3, "file": "workspace/links.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    a = s.shorten("https://example.com/a", now=0)
    b = s.shorten("https://example.com/b", now=0)
    assert a != b, "two URLs got the same code"
    assert s.resolve(a, now=1) == "https://example.com/a", f"resolve({a!r}) gave {s.resolve(a, now=1)!r}"
    assert s.resolve(b, now=1) == "https://example.com/b", "second link did not resolve"
    return "round trip"
