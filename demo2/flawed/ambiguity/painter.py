"""Render a text map to an SVG string."""
import hud
import light
import tiles

COLORS = {"#": "#5b5b6b", ".": "#2b2b3a", "~": "#2a6fdb", "+": "#a0522d"}
LIT = "#8a6d2f"
SPRITES = {"@": (6, "#ffffff"), "g": (5, "#3cb043"), "$": (3, "#ffd700"), "*": (4, "#ff8c00")}


def render_map(text, hp=None, max_hp=10) -> str:
    """The SVG for a map, with a status bar when hp is given."""
    grid = tiles.parse_map(text)
    t = tiles.TILE
    rows, cols = len(grid), (len(grid[0]) if grid else 0)
    w, h = cols * t, rows * t + (20 if hp is not None else 0)
    lit = light.lit(grid)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">',
           f'<rect x="0" y="0" width="{w}" height="{h}" fill="#000000"/>']
    sprites = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            kind = ch
            if ch in SPRITES:
                sprites.append((c, r, ch))
                kind = "."
            fill = COLORS.get(kind)
            if fill is None:  # void (space) or unknown: nothing drawn
                continue
            if kind == "." and (c, r) in lit:
                fill = LIT
            out.append(f'<rect x="{c * t}" y="{r * t}" width="{t}" height="{t}" fill="{fill}"/>')
    for c, r, ch in sprites:
        rad, fill = SPRITES[ch]
        out.append(f'<circle cx="{c * t + t // 2}" cy="{r * t + t // 2}" r="{rad}" fill="{fill}"/>')
    if hp is not None:
        gold = sum(row.count("$") for row in grid)
        out.append(hud.status_bar(rows * t, hp, max_hp, gold))
    out.append("</svg>")
    return "\n".join(out) + "\n"
