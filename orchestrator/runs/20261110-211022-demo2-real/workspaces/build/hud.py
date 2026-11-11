"""Status bar for Dungeon Painter.

Portable SVG rule: no <text> elements, so the label is drawn with shapes
using a tiny 5x7 pixel font.
"""

GLYPH_W = 5
ADVANCE = 6  # pixels per character cell

FONT = {
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
    "o": [".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."],
    "l": [".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "d": ["....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
}


def _label_path(label: str, x: int, baseline: int) -> str:
    """Draw a label as a single white <path> of pixel runs."""
    top = baseline - 7
    cmds = []
    for i, ch in enumerate(label):
        glyph = FONT.get(ch)
        if glyph is None:
            continue
        gx = x + i * ADVANCE
        for row, line in enumerate(glyph):
            col = 0
            while col < GLYPH_W:
                if line[col] != "#":
                    col += 1
                    continue
                start = col
                while col < GLYPH_W and line[col] == "#":
                    col += 1
                cmds.append(f"M{gx + start} {top + row}h{col - start}v1h-{col - start}z")
    return f'<path d="{"".join(cmds)}" fill="#ffffff"/>'


def status_bar(y, hp, max_hp, gold) -> str:
    """Return the SVG for a 20-pixel status bar whose top edge is at y."""
    width = 60 * hp // max_hp
    label = f"HP {hp}/{max_hp}  Gold {gold}"
    return (
        f'<rect x="4" y="{y + 4}" width="{width}" height="12" fill="#c0392b"/>'
        + _label_path(label, 72, y + 15)
    )
