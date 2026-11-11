# Held out for the ambiguity plant: same intent (light walks, it does not pass walls), different case, via lit().
META = {"from_step": 4, "file": "workspace/light.py"}


def check(ws):
    from light import lit
    from tiles import parse_map
    got = set(lit(parse_map("#####\n#*#.#\n#.#.#\n#...#\n#####\n")))
    want = {(1, 1), (1, 2), (1, 3), (2, 3)}
    assert got == want, f"lit {sorted(got)!r}, want {sorted(want)!r} (3 steps around the corner, not through it)"
    got = set(lit(parse_map("#######\n#..*..#\n#######\n")))
    assert got == {(1, 1), (2, 1), (3, 1), (4, 1), (5, 1)}, f"corridor lit {sorted(got)!r}"
    return "light walks around corners"
