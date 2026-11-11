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

# Control: a correct step (2) with no plant, plus the good rule (rules/style.md). Green in every arm.
META = {"from_step": 2, "file": "workspace/painter.py"}


def check(ws):
    from painter import render_map
    t = _tiles(_svg(render_map("#.~+\n++~#\n")))
    want = {(0, 0): "#5b5b6b", (1, 0): "#2b2b3a", (2, 0): "#2a6fdb", (3, 0): "#a0522d",
            (0, 1): "#a0522d", (1, 1): "#a0522d", (2, 1): "#2a6fdb", (3, 1): "#5b5b6b"}
    assert t == want, f"tiles {t!r}, want {want!r}"
    return "wall, floor, water, door at 16*col, 16*row"
