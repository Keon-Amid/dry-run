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

# Plant: ambiguity. Spec step 4 "lights the floor tiles within 3 steps of it". This check wants walking steps
# (light does not pass through walls); the literal grid-distance reading lights the room behind the wall.
META = {"from_step": 4, "file": "workspace/light.py"}
MAP = """\
#########
#...#...#
#.*.#...#
#...#...#
#########
"""


def check(ws):
    from painter import render_map
    t = _tiles(_svg(render_map(MAP)))
    for r in (1, 2, 3):
        for c in (1, 2, 3):
            assert t.get((c, r)) == "#8a6d2f", f"floor ({c},{r}) next to the torch is {t.get((c, r))!r}, not lit"
        for c in (5, 6, 7):
            assert t.get((c, r)) == "#2b2b3a", \
                f"floor ({c},{r}) behind the wall is {t.get((c, r))!r}: light passes through the wall"
    return "torch lights its room, not the room behind the wall"
