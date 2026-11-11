"""Play a dungeon level in the terminal using a built workspace's own game.py / render.py.

    python3 demo_game/play.py [WORKSPACE]                       # default: demo_game/golden/workspace
    python3 demo_game/play.py --side-by-side WS_A WS_B          # same moves to two builds, boards next to each other
    ... --moves eesn                                            # scripted moves instead of typing (n/s/e/w, q quits)

Type n, s, e or w then Enter (several at once is fine: "ees"). q quits. Standard library only.
It runs the built code in this process: point it only at workspaces you built.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden", "workspace")
MODULES = ("game", "render", "level", "hazards", "expiry")
LEVEL = [
    "########",
    "#@..#.k#",
    "#.#.^..#",
    "#.#..#.#",
    "#...^.E#",
    "########",
]


class Build:
    """One workspace's new_game/step/render, loaded under its own copies of the modules."""

    def __init__(self, ws: str, label: str):
        self.label = label
        for m in MODULES:
            sys.modules.pop(m, None)
        sys.path.insert(0, ws)
        try:
            game = importlib.import_module("game")
            render = importlib.import_module("render")
        finally:
            sys.path.remove(ws)
            for m in MODULES:  # functions keep their own globals; free the names for the next build
                sys.modules.pop(m, None)
        self.new_game, self.step, self.render = game.new_game, game.step, render.render
        self.state = self.new_game(LEVEL)
        self.error = None

    def move(self, a: str) -> None:
        if self.error:
            return
        try:
            self.state = self.step(self.state, a)
        except Exception as e:  # a broken build shows its error instead of crashing the player
            self.error = f"{type(e).__name__}: {e}"

    def panel(self) -> list:
        try:
            board = self.render(self.state).split("\n")
        except Exception as e:
            board = [f"render failed: {type(e).__name__}: {e}"]
        s = self.state
        status = (f"lives {s.get('lives')}  key {'yes' if s.get('has_key') else 'no'}  "
                  f"moves {s.get('moves_left', '-')}  {s.get('status')}")
        return [self.label, *board, status, *([self.error] if self.error else [])]


def show(builds: list) -> None:
    panels = [b.panel() for b in builds]
    width = max(len(line) for p in panels for line in p) + 4
    for i in range(max(len(p) for p in panels)):
        print("".join((p[i] if i < len(p) else "").ljust(width) for p in panels).rstrip())
    print()


def play(builds: list, moves) -> None:
    show(builds)
    feed = iter(moves) if moves is not None else None
    while True:
        if feed is not None:
            a = next(feed, "q")
        else:
            try:
                line = input("move (n/s/e/w, q quits)> ").strip().lower()
            except EOFError:
                return
            for a in line[:-1]:
                _apply(builds, a)
            a = line[-1:] or ""
        if a == "q":
            return
        if _apply(builds, a):
            show(builds)
        if all(b.state.get("status") != "playing" or b.error for b in builds):
            return


def _apply(builds: list, a: str) -> bool:
    if a not in "nsew" or not a:
        return False
    print(f"> {a}")
    for b in builds:
        b.move(a)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", nargs="?", default=GOLDEN)
    ap.add_argument("--side-by-side", nargs=2, metavar=("WS_A", "WS_B"))
    ap.add_argument("--labels", nargs=2, default=("spec as-is", "clarified pit line"))
    ap.add_argument("--moves", help="scripted moves, e.g. eesse")
    a = ap.parse_args(argv)
    if a.side_by_side:
        builds = [Build(ws, label) for ws, label in zip(a.side_by_side, a.labels)]
    else:
        builds = [Build(a.workspace, os.path.relpath(a.workspace))]
    play(builds, a.moves)
    return 0


if __name__ == "__main__":
    sys.exit(main())
