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

META = {"from_step": 7, "file": "workspace/scene.py"}


def check(ws):
    from scene import render_demo
    root = _svg(render_demo())
    assert (_n(root.get("width")), _n(root.get("height"))) == (368, 180), \
        f"demo size {root.get('width')}x{root.get('height')}, want 368x180"
    circ = [((e.get("fill") or "").lower(), _n(e.get("cx")), _n(e.get("cy"))) for e in root.iter("circle")]
    assert ("#ffffff", 88, 72) in circ, f"no hero at (88, 72): {circ!r}"
    fills = sorted(f for f, _, _ in circ)
    assert fills.count("#3cb043") == 3 and fills.count("#ffd700") == 3 and fills.count("#ff8c00") == 2, \
        f"sprites {fills!r}"
    bars = [e for e in root.iter("rect") if (e.get("fill") or "").lower() == "#c0392b"]
    assert len(bars) == 1 and _n(bars[0].get("y")) == 164, "no HP bar under the map"
    return "demo scene"
