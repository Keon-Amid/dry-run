META = {"from_step": 3, "file": "workspace/links.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    s.shorten("https://example.com/", now=0)
    for code in ("999999", "nope", ""):
        got = s.resolve(code, now=1)
        if got is not None and code == "999999" and s.shorten("https://example.com/", now=0) == "999999":
            continue  # the random code happened to be 999999
        assert got is None, f"resolve({code!r}) gave {got!r}"
    return "None"
