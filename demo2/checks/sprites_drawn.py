import xml.etree.ElementTree as ET


def _svg(s):
    """Parse SVG text; tags without their namespace."""
    root = ET.fromstring(s)
    for e in root.iter():
        e.tag = e.tag.split("}")[-1]
    return root


def _n(v):
    return float(str(v).strip().replace("px", ""))


def _tiles(root):
    """{(column, row): fill} for every 16x16 <rect>."""
    out = {}
    for e in root.iter("rect"):
        if _n(e.get("width", 0)) == 16 and _n(e.get("height", 0)) == 16:
            out[(int(_n(e.get("x", 0))) // 16, int(_n(e.get("y", 0))) // 16)] = (e.get("fill") or "").lower()
    return out

META = {"from_step": 3, "file": "workspace/painter.py"}


def _circles(root):
    return {(_n(e.get("cx")), _n(e.get("cy"))): (_n(e.get("r")), (e.get("fill") or "").lower())
            for e in root.iter("circle")}


def check(ws):
    from painter import render_map
    root = _svg(render_map("#####\n#@g$#\n#####\n"))
    c = _circles(root)
    want = {(24, 24): (6, "#ffffff"), (40, 24): (5, "#3cb043"), (56, 24): (3, "#ffd700")}
    assert c == want, f"circles {c!r}, want {want!r}"
    t = _tiles(root)
    for col in (1, 2, 3):
        assert t.get((col, 1)) == "#2b2b3a", f"no floor under the sprite at column {col}: {t.get((col, 1))!r}"
    c = _circles(_svg(render_map("###\n#*#\n###\n")))
    assert c == {(24, 24): (4, "#ff8c00")}, f"torch circles {c!r}"
    assert (1, 1) in _tiles(_svg(render_map("###\n#*#\n###\n"))), "no floor tile under the torch"
    return "hero, goblin, gold, torch centred on floor"
