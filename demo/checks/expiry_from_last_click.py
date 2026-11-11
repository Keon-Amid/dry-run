# Plant: ambiguity. Spec step 4 "Links expire after 30 days." This check wants 30 days from the LAST CLICK.
META = {"from_step": 4, "file": "workspace/expiry.py"}
DAY = 86400


def check(ws):
    from links import Shortlink
    s = Shortlink()
    c = s.shorten("https://example.com/sale", now=0)
    assert s.resolve(c, now=20 * DAY) == "https://example.com/sale", "gone on day 20"
    got = s.resolve(c, now=45 * DAY)
    assert got == "https://example.com/sale", f"clicked on day 20, gone on day 45 ({got!r}): expiry counts from creation"
    got = s.resolve(c, now=80 * DAY)
    assert got is None, f"last click day 45, still resolves on day 80 ({got!r})"
    return "30 days from the last click"
