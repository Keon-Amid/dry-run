# Held out for the contradiction plant: same intent (aliases are codes too), different case.
META = {"from_step": 5, "file": "workspace/codes.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    g = s.shorten("https://example.com/gen", now=0)
    for alias, url in (("q4-2026", "https://example.com/q4"), ("abc", "https://example.com/abc")):
        assert s.shorten(url, now=0, alias=alias) == alias, f"alias {alias!r} not returned"
        got = s.resolve(alias, now=1)
        assert got == url, f"resolve({alias!r}) gave {got!r}"
    assert s.resolve(g, now=1) == "https://example.com/gen", "generated code broke after aliases"
    return "aliases with digits and hyphens"
