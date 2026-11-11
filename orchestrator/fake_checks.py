"""STUB checks standing in for P2's, until they land. Graded from outside: copied into the sandbox only after the
builder exits, and removed right after grading.

    python3 fake_checks.py --disk DIR --at-step K   ->  {"check_name": true|false, ...} (checks checkable by step K)
    python3 fake_checks.py --meta                   ->  {"check_name": {"from_step", "file", "heldout"}, ...}

Each failing check plays one verdict:
  expiry_from_last_click   a real spec problem ("Links expire after 30 days." is ambiguous)
  redirect_counts_click    a simulated model slip at step 4 in the build
  stats_returns_json       a bad check (decoy): it fails on golden/ too
Held-out checks (heldout=True) are graded but never shown to the rewrite step. Standard library only.
"""
import argparse
import json
from pathlib import Path


def _step(disk: Path, k: int) -> str:
    p = disk / "workspace" / f"step_{k}.txt"
    return p.read_text().lower() if p.exists() else ""


def _conv_ok(disk: Path, k: int) -> bool:
    p = disk / "conversation.jsonl"
    if not p.exists():
        return k == 0
    steps = [json.loads(l)["step"] for l in p.read_text().splitlines() if l.strip()]
    return steps == [s for s in range(1, k + 1) for _ in (0, 1)]


MESSAGES = {  # what a failing check says (the visible message the swarm and the baseline get)
    "conversation_intact": "conversation.jsonl is missing steps or out of order",
    "codes_6_digits": "generated codes are not 6 digits",
    "expiry_from_last_click": "a link clicked yesterday expired 30 days after it was created",
    "redirect_counts_click": "GET /<code> redirected but the click count did not go up",
    "stats_returns_json": "GET /links/<code>/stats did not return JSON",
    "all_steps_built": "not every step produced its file",
    "heldout_expiry_keeps_30_days": "held out",
}

# name: (checkable from step, file it reads, held out?, test)
CHECKS = {
    "conversation_intact": (1, "conversation.jsonl", False, lambda d, k: _conv_ok(d, k)),
    "codes_6_digits": (2, "workspace/step_2.txt", False, lambda d, k: "6 digits" in _step(d, 2)),
    "expiry_from_last_click": (3, "workspace/step_3.txt", False, lambda d, k: "last click" in _step(d, 3)),
    "redirect_counts_click": (4, "workspace/step_4.txt", False, lambda d, k: "counts the click" in _step(d, 4)),
    "stats_returns_json": (6, "workspace/step_6.txt", False, lambda d, k: "json" in _step(d, 6)),
    "all_steps_built": (7, "workspace/step_7.txt", False, lambda d, k: all(_step(d, s) for s in range(1, 8))),
    "heldout_expiry_keeps_30_days": (3, "workspace/step_3.txt", True,
                                     lambda d, k: "30 days" in _step(d, 3) and "last click" in _step(d, 3)),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk")
    ap.add_argument("--at-step", type=int, default=7)
    ap.add_argument("--meta", action="store_true")
    a = ap.parse_args()
    if a.meta:
        print(json.dumps({n: {"from_step": s, "file": f, "heldout": h, "message": MESSAGES.get(n, "")}
                          for n, (s, f, h, _) in CHECKS.items()}))
        return
    disk = Path(a.disk)
    print(json.dumps({n: bool(fn(disk, a.at_step)) for n, (s, _, _, fn) in CHECKS.items() if s <= a.at_step}))


if __name__ == "__main__":
    main()
