META = {"from_step": 6, "file": "workspace/game.py"}


def check(ws):
    from game import new_game, step
    s = new_game(["#####", "#@^.#", "#####"])
    for _ in range(6):  # works whether the pit leaves the player on it or sends them back
        if s["status"] != "playing":
            break
        s = step(s, "e") if list(s["pos"]) == [1, 1] else step(s, "w")
    assert s["lives"] == 0 and s["status"] == "lost", f"lives {s['lives']}, status {s['status']!r}"
    after = step(s, "e")
    assert after["status"] == "lost" and list(after["pos"]) == list(s["pos"]), "game went on after it was lost"
    return "lost at 0 lives"
