"""STUB builder with the worker CLI from docs/plan-builder.md, until the real builder lands.

    python3 fake_builder.py --disk DIR --from-step K --to-step N [--patch patch.json] --route ID

No model calls. For each step k in K+1..N it copies spec step k's text into workspace/step_k.txt, appends a user and an
assistant line to conversation.jsonl, and writes state.json. The patch (spec_line | control) is applied once, before
the first step. Prints one JSON result line. Standard library only: it runs inside the sandbox.
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
        spec = spec_path.read_text()
        if spec.count(patch["old"]) != 1:
            raise SystemExit(f"patch {patch['route']}: 'old' matches {spec.count(patch['old'])} times, need 1")
        write_atomic(spec_path, spec.replace(patch["old"], patch["new"]))
        state["patch_id"], state["patch_applied"] = patch["route"], True

    (disk / "workspace").mkdir(exist_ok=True)
    built = []
    for k in range(a.from_step + 1, a.to_step + 1):
        text = spec_step(spec_path.read_text(), k)
        (disk / "workspace" / f"step_{k}.txt").write_text(text + "\n")
        with open(disk / "conversation.jsonl", "a") as f:
            f.write(json.dumps({"step": k, "msg": {"role": "user", "content": f"Do step {k}."}}) + "\n")
            f.write(json.dumps({"step": k, "msg": {"role": "assistant", "content": f"wrote step_{k}.txt"}}) + "\n")
            f.flush()
            os.fsync(f.fileno())
        state["last_done"] = k
        state["steps"].append({"step": k, "route": a.route})
        write_atomic(state_path, json.dumps(state, indent=1))
        built.append(k)

    routes = disk / "routes"
    routes.mkdir(exist_ok=True)
    (routes / f"{a.route}.md").write_text(
        f"# {a.route}\n\nhypothesis: {(patch or {}).get('hypothesis', 'none')}\n"
        f"edit: {(patch or {}).get('new', 'none')}\nbuilt steps: {built}\n")
    print(json.dumps({"route": a.route, "from_step": a.from_step, "to_step": a.to_step, "built": built,
                      "patch_applied": bool(patch), "builder": "fake"}))


if __name__ == "__main__":
    main()
