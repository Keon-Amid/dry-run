META = {"from_step": 2, "file": "workspace/game.py"}


def check(ws):
    from game import new_game, step
    s = new_game(["@."])
    for bad in ("x", "north", ""):
        try:
            step(s, bad)
        except ValueError:
            continue
        raise AssertionError(f"step(state, {bad!r}) did not raise ValueError")
    return "ValueError"
