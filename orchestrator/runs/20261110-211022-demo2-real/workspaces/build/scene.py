"""Demo scene for Dungeon Painter."""

import painter

DEMO_MAP = """
   ######     #########
  ##....##    #.......#
 ##..$...##   #..g..$.#
##........#####.......#
#*...@.....+.*#...~~~.#
##........#...#..~~~~.#
 ##..g...##...+...~~..#
  ##....## #..#.......#
   ######  ####.$..g..#
              #########
"""


def render_demo() -> str:
    """Render the demo map with the status bar at 7 HP."""
    return painter.render_map(DEMO_MAP, hp=7)
