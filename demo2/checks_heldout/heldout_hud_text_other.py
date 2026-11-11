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

# Held out for the bad-rule plant: same intent (the status bar has its label), different numbers.
META = {"from_step": 6, "file": "workspace/hud.py"}


def check(ws):
    from hud import status_bar
    from painter import render_map
    root = _svg(render_map("$$$\n...\n", hp=3, max_hp=12))
    texts = [" ".join("".join(e.itertext()).split()) for e in root.iter("text")]
    assert "HP 3/12 Gold 3" in texts, f"texts {texts!r}, want 'HP 3/12 Gold 3'"
    frag = _svg('<svg xmlns="http://www.w3.org/2000/svg">' + status_bar(100, 10, 10, 0) + "</svg>")
    t = [(" ".join("".join(e.itertext()).split()), _n(e.get("x")), _n(e.get("y"))) for e in frag.iter("text")]
    assert t == [("HP 10/10 Gold 0", 72, 115)], f"status_bar(100, 10, 10, 0) text {t!r}"
    return "label present"
