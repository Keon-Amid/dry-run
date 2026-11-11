META = {"from_step": 2, "file": "workspace/codes.py"}


def check(ws):
    from codes import new_code
    taken = {f"{i:06d}" for i in range(0, 1000000, 3)}
    for _ in range(50):
        c = new_code(taken)
        assert isinstance(c, str) and len(c) == 6 and c.isdigit(), f"new_code gave {c!r}"
        assert c not in taken, f"new_code gave a taken code {c!r}"
    return "6 digits, never taken"
