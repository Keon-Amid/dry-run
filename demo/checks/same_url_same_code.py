META = {"from_step": 3, "file": "workspace/links.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    a = s.shorten("https://Example.com/x", now=0)
    b = s.shorten("https://example.com/x", now=5)
    assert a == b, f"same URL got two codes: {a!r} {b!r}"
    return "same code"
