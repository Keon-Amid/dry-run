# Decoy (bad check): the spec says actions are lowercase "n"/"s"/"e"/"w" and anything else raises ValueError; this
# check wrongly wants uppercase "E". It fails on golden/ too, so triage must say "your test is wrong".
META = {"from_step": 2, "file": "workspace/game.py"}


def check(ws):
    from game import new_game, step
    s = step(new_game(["@."]), "E")
    assert list(s["pos"]) == [0, 1], f"after 'E': {s['pos']}"
    return "uppercase"
