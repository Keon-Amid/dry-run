"""The demo scene."""
import painter

DEMO_MAP = """\
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
    """The SVG for the demo map with 7 HP."""
    return painter.render_map(DEMO_MAP, hp=7)
