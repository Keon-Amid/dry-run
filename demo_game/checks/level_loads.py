META = {"from_step": 1, "file": "workspace/level.py"}


def check(ws):
    from level import load
    lv = load(["#####", "#@k^#", "#..E#", "#####"])
    assert [list(lv["start"]), list(lv["key"]), list(lv["exit"])] == [[1, 1], [1, 2], [2, 3]], f"positions: {lv}"
    assert [list(p) for p in lv["pits"]] == [[1, 3]], f"pits: {lv['pits']}"
    assert [1, 1] not in [list(p) for p in lv["walls"]] and [0, 0] in [list(p) for p in lv["walls"]], "walls wrong"
    assert (lv["height"], lv["width"]) == (4, 5), f"size {lv['height']}x{lv['width']}"
    return "positions parsed"
