META = {"from_step": 2, "file": "workspace/game.py"}


def check(ws):
    from game import new_game, step
    s = new_game(["#####", "#@..#", "#...#", "#####"])
    s = step(s, "e")
    assert list(s["pos"]) == [1, 2], f"after e: {s['pos']}"
    s = step(s, "n")
    assert list(s["pos"]) == [1, 2], f"wall did not block n: {s['pos']}"
    s = step(s, "s")
    assert list(s["pos"]) == [2, 2], f"after s: {s['pos']}"
    s = step(s, "w")
    assert list(s["pos"]) == [2, 1], f"after w: {s['pos']}"
    edge = step(new_game(["@."]), "w")
    assert list(edge["pos"]) == [0, 0], f"grid edge did not block: {edge['pos']}"
    return "moves, walls and edges"
