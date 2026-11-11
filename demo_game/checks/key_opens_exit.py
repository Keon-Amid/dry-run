# Control: a correct step (3) with no plant. Must stay green in every arm.
META = {"from_step": 3, "file": "workspace/game.py"}


def check(ws):
    from game import new_game, step
    lvl = ["######", "#@.kE#", "######"]
    s = step(step(new_game(lvl), "e"), "e")
    assert s["has_key"] is True, "walking onto the key did not pick it up"
    s = step(s, "e")
    assert s["status"] == "won", f"exit with key: status {s['status']!r}"
    locked = step(step(new_game(["#####", "#@.E#", "#####"]), "e"), "e")
    assert list(locked["pos"]) == [1, 2] and locked["status"] == "playing", f"locked exit let the player in: {locked}"
    return "key opens exit"
