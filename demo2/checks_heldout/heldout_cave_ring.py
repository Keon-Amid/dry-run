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

# Held out for the contradiction plant: same intent (leading spaces are void and keep the shape), different case.
META = {"from_step": 5, "file": "workspace/tiles.py"}


def check(ws):
    from painter import render_map
    root = _svg(render_map("  ##\n #..#\n#....#\n #..#\n  ##\n"))
    t = _tiles(root)
    walls = {p for p, f in t.items() if f == "#5b5b6b"}
    want = {(2, 0), (3, 0), (1, 1), (4, 1), (0, 2), (5, 2), (1, 3), (4, 3), (2, 4), (3, 4)}
    assert walls == want, f"walls {sorted(walls)!r}, want {sorted(want)!r}"
    assert (_n(root.get("width")), _n(root.get("height"))) == (96, 80), "ring cave has the wrong size"
    return "ring cave keeps its shape"
