META = {"from_step": 1, "file": "workspace/tiles.py"}


def check(ws):
    from tiles import TILE, parse_map
    assert TILE == 16, f"TILE is {TILE!r}"
    got = parse_map("#.#  \n\n##\n#.~+#\n")
    assert got == ["#.#  ", "##   ", "#.~+#"], f"parse_map gave {got!r}"
    return "equal-length rows, blank lines skipped"
