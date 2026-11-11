"""STUB builder with the worker CLI from docs/plan-builder.md, until Brendan's builder/ lands.

    python3 fake_builder.py --disk DIR --from-step K --to-step N [--patch patch.json] --route ID

No model calls. For each step k in K+1..N it copies spec step k's text into workspace/step_k.txt, appends a user and an
assistant line to conversation.jsonl, and writes state.json. The patch is applied once, before the first step:
  spec_line (replace `old` with `new`, exactly one match) | rule_off (delete rules/<rule>) | control (rewrite `old`
  with itself, same code path) | none.
SIMULATED SLIP: with FAKE_SLIP_STEP=k in the environment and --route build, step k drops its last clause, standing in
for a one-off model mistake (a rebuild of that step doesn't repeat it).
Prints one JSON result line. Standard library only: it runs inside the sandbox.
"""
import argparse
import json
import os
import re
from pathlib import Path


def spec_step(spec: str, k: int) -> str:
    m = re.search(rf"^## Step {k}\b.*?\n(.*?)(?=^## Step |\Z)", spec, re.S | re.M)
    if not m:
        raise SystemExit(f"spec has no '## Step {k}'")
    return m.group(1).strip()


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def apply_patch(disk: Path, patch: dict) -> None:
    kind = patch.get("kind", "none")
    if kind in ("spec_line", "control"):
        spec_path = disk / "spec.md"
        spec = spec_path.read_text()
        n = spec.count(patch["old"])
        if n != 1:
            raise SystemExit(f"patch {patch['route']}: 'old' matches {n} times, need exactly 1")
        new = patch["old"] if kind == "control" else patch["new"]
        write_atomic(spec_path, spec.replace(patch["old"], new))
    elif kind == "rule_off":
        rule = disk / "rules" / patch["rule"]
        if not rule.exists():
            raise SystemExit(f"patch {patch['route']}: no rule {patch['rule']}")
        rule.unlink()
        assert not rule.exists()
    elif kind != "none":
        raise SystemExit(f"unknown patch kind {kind}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk", required=True)
    ap.add_argument("--from-step", type=int, required=True)
    ap.add_argument("--to-step", type=int, required=True)
    ap.add_argument("--patch")
    ap.add_argument("--route", required=True)
    a = ap.parse_args()
    disk = Path(a.disk)
    state_path, spec_path = disk / "state.json", disk / "spec.md"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"last_done": 0, "steps": []}
    if state["last_done"] != a.from_step:
        raise SystemExit(f"state says last_done={state['last_done']}, asked to resume from {a.from_step}")

    patch = json.loads(Path(a.patch).read_text()) if a.patch else None
    if patch:
        apply_patch(disk, patch)
        state["patch_id"], state["patch_kind"], state["patch_applied"] = patch["route"], patch.get("kind"), True

    slip = int(os.environ.get("FAKE_SLIP_STEP", "0")) if a.route == "build" else 0
    rules = sorted(p.name for p in (disk / "rules").glob("*.md")) if (disk / "rules").exists() else []
    (disk / "workspace").mkdir(exist_ok=True)
    built, slipped = [], None
    for k in range(a.from_step + 1, a.to_step + 1):
        text = spec_step(spec_path.read_text(), k)
        if k == slip:
            text, slipped = re.sub(r"\s+and [^.]*\.$", ".", text), k  # the simulated slip
        (disk / "workspace" / f"step_{k}.txt").write_text(text + "\n")
        with open(disk / "conversation.jsonl", "a") as f:
            f.write(json.dumps({"step": k, "msg": {"role": "user", "content": f"Do step {k}."}}) + "\n")
            f.write(json.dumps({"step": k, "msg": {"role": "assistant", "content": f"wrote step_{k}.txt"}}) + "\n")
            f.flush()
            os.fsync(f.fileno())
        state["last_done"] = k
        state["steps"].append({"step": k, "route": a.route, "rules_active": rules})
        write_atomic(state_path, json.dumps(state, indent=1))
        built.append(k)

    routes = disk / "routes"
    routes.mkdir(exist_ok=True)
    (routes / f"{a.route}.md").write_text(
        f"# {a.route}\n\nhypothesis: {(patch or {}).get('hypothesis', 'none')}\n"
        f"edit: {json.dumps({k: v for k, v in (patch or {}).items() if k != 'hypothesis'})}\nbuilt steps: {built}\n")
    print(json.dumps({"route": a.route, "from_step": a.from_step, "to_step": a.to_step, "built": built,
                      "wrote": [f"workspace/step_{k}.txt" for k in built], "patch_applied": bool(patch),
                      "simulated_slip_step": slipped, "builder": "fake"}))


if __name__ == "__main__":
    main()
