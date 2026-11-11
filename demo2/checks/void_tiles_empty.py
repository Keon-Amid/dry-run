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

META = {"from_step": 5, "file": "workspace/painter.py"}


def check(ws):
    from painter import render_map
    root = _svg(render_map("#.# #\n#...#\n##\n"))
    t = _tiles(root)
    for pos in ((3, 0), (2, 2), (3, 2), (4, 2)):
        assert pos not in t, f"void tile {pos} was drawn ({t[pos]!r})"
    assert t.get((4, 0)) == "#5b5b6b" and t.get((1, 2)) == "#5b5b6b", "walls around the void are missing"
    assert (_n(root.get("width")), _n(root.get("height"))) == (80, 48), "void changed the image size"
    return "nothing drawn for spaces"
