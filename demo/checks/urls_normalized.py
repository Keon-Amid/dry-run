META = {"from_step": 1, "file": "workspace/urls.py"}


def check(ws):
    from urls import normalize
    got = normalize("HTTP://Example.COM/Path?Q=1#Frag")
    assert got == "http://example.com/Path?Q=1#Frag", f"normalize gave {got!r}"
    return "scheme+host lowercased, rest kept"
