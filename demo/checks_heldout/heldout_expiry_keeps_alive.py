# Held out for the ambiguity plant: same intent (30 days from the last click), different case.
META = {"from_step": 4, "file": "workspace/expiry.py"}
DAY = 86400


def check(ws):
    from links import Shortlink
    s = Shortlink()
    c = s.shorten("https://example.com/news", now=0)
    for d in (29, 58, 87):
        got = s.resolve(c, now=d * DAY)
        assert got == "https://example.com/news", f"clicked every 29 days, gone on day {d} ({got!r})"
    assert s.resolve(c, now=118 * DAY) is None, "31 days after the last click, still resolves"
    idle = s.shorten("https://example.com/idle", now=0)
    assert s.resolve(idle, now=31 * DAY) is None, "never clicked, still resolves on day 31"
    return "kept alive by clicks"
