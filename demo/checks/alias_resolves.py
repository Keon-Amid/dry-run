# Plant: contradiction. Spec step 2 "Codes are 6 digits" (origin) vs step 5 "Users may pick an alias" (surfaced).
META = {"from_step": 5, "file": "workspace/codes.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    got = s.shorten("https://example.com/summer", now=0, alias="summer-sale")
    assert got == "summer-sale", f"shorten with alias returned {got!r}"
    got = s.resolve("summer-sale", now=1)
    assert got == "https://example.com/summer", f"resolve('summer-sale') gave {got!r}"
    return "alias resolves"
