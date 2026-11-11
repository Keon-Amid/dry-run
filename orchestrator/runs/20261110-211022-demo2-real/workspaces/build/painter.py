"""SVG renderer for Dungeon Painter maps."""

from hud import status_bar
from light import lit
from tiles import TILE, parse_map

COLORS = {
    "#": "#5b5b6b",  # wall
    ".": "#2b2b3a",  # floor
    "~": "#2a6fdb",  # water
    "+": "#a0522d",  # door
}

FLOOR = COLORS["."]
LIT_FLOOR = "#8a6d2f"

# sprite char -> (radius, fill)
SPRITES = {
    "@": (6, "#ffffff"),  # hero
    "g": (5, "#3cb043"),  # goblin
    "$": (3, "#ffd700"),  # gold
    "*": (4, "#ff8c00"),  # torch
}


def render_map(text, hp=None, max_hp=10) -> str:
    """Render map text as an SVG document string."""
    rows = parse_map(text)
    map_height = TILE * len(rows)
    width = TILE * (len(rows[0]) if rows else 0)
    height = map_height + (20 if hp is not None else 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#000000"/>',
    ]
    lit_tiles = lit(rows)
    sprites = []
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in SPRITES:
                radius, fill = SPRITES[ch]
                sprites.append(
                    f'<circle cx="{TILE * c + TILE // 2}" cy="{TILE * r + TILE // 2}" '
                    f'r="{radius}" fill="{fill}"/>'
                )
                color = FLOOR
            else:
                color = COLORS.get(ch)
            if color == FLOOR and (c, r) in lit_tiles:
                color = LIT_FLOOR
            if color is None:
                continue
            parts.append(
                f'<rect x="{TILE * c}" y="{TILE * r}" width="{TILE}" '
                f'height="{TILE}" fill="{color}"/>'
            )
    parts.extend(sprites)
    if hp is not None:
        gold = sum(row.count("$") for row in rows)
        parts.append(status_bar(map_height, hp, max_hp, gold))
    parts.append("</svg>")
    return "\n".join(parts)
