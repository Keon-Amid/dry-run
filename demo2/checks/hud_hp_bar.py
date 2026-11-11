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

META = {"from_step": 6, "file": "workspace/painter.py"}


def check(ws):
    from painter import render_map
    root = _svg(render_map("###\n#.#\n", hp=7))
    assert (_n(root.get("width")), _n(root.get("height"))) == (48, 52), \
        f"size {root.get('width')}x{root.get('height')}, want 48x52 (20 px status bar)"
    bars = [e for e in root.iter("rect") if (e.get("fill") or "").lower() == "#c0392b"]
    assert len(bars) == 1, f"{len(bars)} #c0392b bars"
    b = bars[0]
    got = tuple(_n(b.get(k)) for k in ("x", "y", "width", "height"))
    assert got == (4, 36, 42, 12), f"HP bar x,y,w,h = {got}, want (4, 36, 42, 12)"
    plain = _svg(render_map("###\n#.#\n"))
    assert _n(plain.get("height")) == 32, "status bar drawn without hp"
    return "7/10 HP bar"
