META = {"from_step": 7, "file": "workspace/links.py"}


def check(ws):
    from links import Shortlink
    s = Shortlink()
    c = s.shorten("https://example.com/d", now=0)
    assert s.delete(c) is True, "delete of a known code did not return True"
    assert s.resolve(c, now=1) is None, "deleted code still resolves"
    assert s.delete(c) is False, "second delete did not return False"
    return "deleted"
