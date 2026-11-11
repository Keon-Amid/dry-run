"""The status bar under the map, following rules/portable.md: no <text>, so the label is left out."""


def status_bar(y, hp, max_hp, gold) -> str:
    """SVG for a 20-pixel status bar whose top edge is at y: the HP bar only (no <text> allowed)."""
    w = 60 * hp // max_hp
    return f'<rect x="4" y="{y + 4}" width="{w}" height="12" fill="#c0392b"/>'
