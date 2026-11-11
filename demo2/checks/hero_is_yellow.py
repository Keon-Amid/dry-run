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

# Decoy (bad check): the spec says the hero is #ffffff; this check wrongly wants yellow. It fails on golden/ too,
# so triage must say "your test is wrong".
META = {"from_step": 3, "file": "workspace/painter.py"}


def check(ws):
    from painter import render_map
    root = _svg(render_map("###\n#@#\n###\n"))
    fills = [(e.get("fill") or "").lower() for e in root.iter("circle")]
    assert fills == ["#ffff00"], f"hero fill {fills!r}, want ['#ffff00']"
    return "yellow hero"
