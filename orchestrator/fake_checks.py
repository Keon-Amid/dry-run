"""STUB checks standing in for P2's, until they land. Graded from outside the agent's disk.

    python3 fake_checks.py --disk DIR [--steps 7]   ->  prints {"check_name": true|false, ...}

`expiry_from_last_click` plays the planted ambiguity: the stock spec line "Links expire after 30 days." fails it, and
only rewrites that say "last click" pass. Standard library only: it runs inside the sandbox.
"""
import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk", required=True)
    ap.add_argument("--steps", type=int, default=7)
    a = ap.parse_args()
    disk = Path(a.disk)

    def step(k: int) -> str:
        p = disk / "workspace" / f"step_{k}.txt"
        return p.read_text() if p.exists() else ""

    conv = [json.loads(l) for l in (disk / "conversation.jsonl").read_text().splitlines() if l.strip()] \
        if (disk / "conversation.jsonl").exists() else []
    print(json.dumps({
        "all_steps_built": all(step(k) for k in range(1, a.steps + 1)),
        "conversation_intact": [m["step"] for m in conv] == [k for k in range(1, a.steps + 1) for _ in (0, 1)],
        "codes_6_digits": "6 digits" in step(2),
        "expiry_from_last_click": "last click" in step(3).lower(),
    }))


if __name__ == "__main__":
    main()
