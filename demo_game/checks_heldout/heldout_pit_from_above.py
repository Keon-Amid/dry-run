# Held out for the ambiguity plant: same intent (pit: lose a life, stay back), different case: from the north, twice.
META = {"from_step": 4, "file": "workspace/hazards.py"}


def check(ws):
    from game import new_game, step
    s = step(new_game(["#####", "#@..#", "#.#.#", "#..^#", "#####"]), "e")
    s = step(s, "e")
    s = step(s, "s")
    assert list(s["pos"]) == [2, 3], f"walking to [2, 3] got {s['pos']}"
    s = step(s, "s")
    assert (s["lives"], list(s["pos"])) == (2, [2, 3]), f"first fall: lives {s['lives']}, pos {s['pos']}"
    s = step(s, "s")
    assert (s["lives"], list(s["pos"])) == (1, [2, 3]), f"second fall: lives {s['lives']}, pos {s['pos']}"
    return "stayed back twice"
