# Decoy (bad check): the spec says stats() returns a dict; this check wrongly wants a JSON string.
# It fails on golden/ too, so triage must say "your test is wrong".
import json

META = {"from_step": 6, "file": "workspace/links.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    c = s.shorten("https://example.com/j", now=0)
    out = s.stats(c)
    assert isinstance(out, str), f"stats() returned {type(out).__name__}, not a JSON string"
    assert json.loads(out)["clicks"] == 0, "clicks not 0"
    return "json"
