META = {"from_step": 5, "file": "workspace/game.py"}


def check(ws):
    from game import new_game, step
    s = new_game(["###", "#@#", "###"])
    assert s["moves_left"] == 20, f"moves_left starts at {s.get('moves_left')}"
    for i in range(19):
        s = step(s, "n")
    assert s["status"] == "playing" and s["moves_left"] == 1, f"after 19 blocked moves: {s['status']}, {s['moves_left']}"
    s = step(s, "n")
    assert s["status"] == "lost", f"after 20 moves: status {s['status']!r}"
    return "lost at 0 moves"
