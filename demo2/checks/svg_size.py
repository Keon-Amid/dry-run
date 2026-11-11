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

META = {"from_step": 2, "file": "workspace/painter.py"}


def check(ws):
    from painter import render_map
    s = render_map("###\n#.#\n")
    assert "http://www.w3.org/2000/svg" in s, "no SVG namespace"
    root = _svg(s)
    assert root.tag == "svg", f"root is <{root.tag}>"
    assert (_n(root.get("width")), _n(root.get("height"))) == (48, 32), \
        f"size {root.get('width')}x{root.get('height')}, want 48x32"
    bg = [e for e in root.iter("rect") if (_n(e.get("x", 0)), _n(e.get("y", 0)), _n(e.get("width", 0)),
                                           _n(e.get("height", 0))) == (0, 0, 48, 32)]
    assert bg and (bg[0].get("fill") or "").lower() == "#000000", "no #000000 background rect over the whole image"
    first = next(root.iter("rect"))
    assert _n(first.get("width")) == 48, "the background is not drawn first"
    return "48x32 with a black background"
