# Control: a correct step (6) with no plant. Must stay green in every arm.
META = {"from_step": 6, "file": "workspace/links.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    c = s.shorten("https://example.com/c", now=0)
    assert s.stats(c) == {"url": "https://example.com/c", "clicks": 0}, f"stats before clicks: {s.stats(c)!r}"
    for t in (1, 2, 3):
        s.resolve(c, now=t)
    s.resolve("000000" if c != "000000" else "000001", now=4)
    assert s.stats(c) == {"url": "https://example.com/c", "clicks": 3}, f"stats after 3 clicks: {s.stats(c)!r}"
    assert s.stats("nope") is None, "stats of unknown code is not None"
    return "3 clicks"
