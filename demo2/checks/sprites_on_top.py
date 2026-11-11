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

# Placebo-owned: plants.json paraphrases the step 3 sentence this tests; it must not flip.
META = {"from_step": 3, "file": "workspace/painter.py"}


def check(ws):
    from painter import render_map
    root = _svg(render_map("#####\n#@..#\n#.g.#\n#.$##\n#####\n"))
    kinds = [e.tag for e in root.iter() if e.tag in ("rect", "circle")]
    assert kinds.count("circle") == 3, f"{kinds.count('circle')} circles, want 3"
    first_circle = kinds.index("circle")
    assert "rect" not in kinds[first_circle:], "a tile is drawn after a sprite (it would cover it)"
    return "sprites after all tiles"
