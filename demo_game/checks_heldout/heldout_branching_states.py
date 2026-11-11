# Held out for the bad-rule plant: same intent (step never changes its input), different case: two branches from one state.
META = {"from_step": 2, "file": "workspace/game.py"}


def check(ws):
    from game import new_game, step
    s = step(new_game(["#####", "#...#", "#.@.#", "#...#", "#####"]), "n")
    a, b = step(s, "w"), step(s, "e")
    assert list(s["pos"]) == [1, 2], f"the shared state moved to {s['pos']}"
    assert list(a["pos"]) == [1, 1] and list(b["pos"]) == [1, 3], f"branches at {a['pos']} and {b['pos']}"
    return "branches independent"
