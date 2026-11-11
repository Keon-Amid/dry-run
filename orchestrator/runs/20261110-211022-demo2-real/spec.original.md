# Dungeon Painter

A roguelike dungeon-map renderer, written as a Python library (no web server, no command line). Standard library
only. A map is plain text, one character per tile; the output is an SVG document as a string. All sizes and
coordinates are plain numbers of pixels. Put every file directly in the workspace folder.

## Step 1
Create `tiles.py` with `TILE = 16` (pixels per tile) and `parse_map(text: str) -> list`, which turns a multi-line
map into a list of equal-length row strings.
Each line is stripped of surrounding whitespace and blank lines are skipped; shorter rows are padded on the right
with spaces.

## Step 2
Create `painter.py` with `render_map(text) -> str`. It parses the map with `tiles.parse_map` and returns
`<svg xmlns="http://www.w3.org/2000/svg" width="W" height="H">` where W is 16 times the number of columns and H is
16 times the number of rows. Draw a `#000000` background `<rect>` covering the whole image first, then one 16x16
`<rect>` per tile at x = 16 * column, y = 16 * row, filled by kind: wall `#` `#5b5b6b`, floor `.` `#2b2b3a`,
water `~` `#2a6fdb`, door `+` `#a0522d`.

## Step 3
Sprites stand on floor: for a sprite tile draw the floor `<rect>`, then a `<circle>` centred in the tile. Hero `@`:
r 6, `#ffffff`. Goblin `g`: r 5, `#3cb043`. Gold `$`: r 3, `#ffd700`. Torch `*`: r 4, `#ff8c00`.
Draw every sprite after all the tiles, so they sit on top.

## Step 4
Create `light.py` with `lit(grid) -> set`, taking the rows from `parse_map` and returning the `(column, row)` floor
tiles that are lit (sprite tiles count as floor). Every torch lights the floor tiles within 3 steps of it.
`render_map` fills lit floor tiles with `#8a6d2f` instead of `#2b2b3a`.

## Step 5
Caves: a space in the map is void. Draw nothing for a void tile, so the black background shows through. For
example, the middle tile of this room is a hole:

```
#####
#. .#
#####
```

## Step 6
Create `hud.py` with `status_bar(y, hp, max_hp, gold) -> str`: the SVG for a 20-pixel status bar whose top edge is
at `y`. It is a `#c0392b` `<rect>` at x 4, y + 4, height 12, width 60 * hp // max_hp, then a `#ffffff` `<text>` at
x 72, y + 15 that reads `HP 7/10  Gold 3` (with the real numbers). `render_map(text, hp=None, max_hp=10)`: when
`hp` is given, the image is 20 pixels taller and ends with the status bar, where gold is the number of `$` tiles.

## Step 7
Create `scene.py` with `render_demo() -> str`, which returns `painter.render_map(DEMO_MAP, hp=7)`. `DEMO_MAP` is a
module-level string holding exactly this map, with no extra indentation:

```
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
```

## Harness rules (rules/, read by the builder every turn; not part of spec.md)

### portable.md

Portable SVG: never emit `<text>` elements. Fonts render differently in every SVG viewer, so draw every label with
shapes or leave it out.

### style.md

Use only the Python standard library. Give every public function a one-line docstring.
