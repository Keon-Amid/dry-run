META = {"from_step": 7, "file": "workspace/render.py"}


def check(ws):
    from game import new_game, step
    from render import render
    s = step(step(new_game(["#####", "#@kE#", "#####"]), "e"), "w")
    got = render(s)
    assert got == "#####\n#@.E#\n#####", f"render gave {got!r}"
    return "rendered"
