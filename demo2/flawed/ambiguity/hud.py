"""The status bar under the map."""


def status_bar(y, hp, max_hp, gold) -> str:
    """SVG for a 20-pixel status bar whose top edge is at y: an HP bar and an 'HP a/b  Gold n' label."""
    w = 60 * hp // max_hp
    return (f'<rect x="4" y="{y + 4}" width="{w}" height="12" fill="#c0392b"/>'
            f'<text x="72" y="{y + 15}" fill="#ffffff" font-family="monospace" font-size="12">'
            f'HP {hp}/{max_hp}  Gold {gold}</text>')
