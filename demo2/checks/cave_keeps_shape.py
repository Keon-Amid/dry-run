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

# Plant: contradiction, origin != surfaced. Spec step 1 "Each line is stripped of surrounding whitespace" (origin)
# silently eats the leading spaces that step 5 makes meaningful (void). Checkable only from step 5.
META = {"from_step": 5, "file": "workspace/tiles.py"}


def check(ws):
    from painter import render_map
    root = _svg(render_map(" ###\n##.##\n ###\n"))
    t = _tiles(root)
    want = {(1, 0): "#5b5b6b", (2, 0): "#5b5b6b", (3, 0): "#5b5b6b",
            (0, 1): "#5b5b6b", (1, 1): "#5b5b6b", (2, 1): "#2b2b3a", (3, 1): "#5b5b6b", (4, 1): "#5b5b6b",
            (1, 2): "#5b5b6b", (2, 2): "#5b5b6b", (3, 2): "#5b5b6b"}
    assert t == want, f"cave tiles {sorted(t)!r}: the round cave lost its shape (leading spaces dropped?)"
    return "round cave keeps its shape"
