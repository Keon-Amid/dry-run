# Plant: ambiguity. Spec step 4 "The pit costs a life." This check wants: the player does not enter the pit, stays on
# the square they came from, and loses a life.
META = {"from_step": 4, "file": "workspace/hazards.py"}


def check(ws):
    from game import new_game, step
    s = step(new_game(["######", "#@.^.#", "######"]), "e")
    s = step(s, "e")
    assert s["lives"] == 2, f"lives after the pit: {s['lives']}"
    assert list(s["pos"]) == [1, 2], f"after the pit the player is at {s['pos']}, not back on [1, 2]"
    return "life lost, stayed back"
