"""Build with a checkpoint per step, then waves of branches from a checkpoint.

build(store, spec, rules, steps, run_dir)        -> run.json (checkpoint ids, per-step wall time and checks)
run_wave(store, checkpoint_id, edits, n, ...)    -> one wave appended to results.json, logged to archil.json

Each copy: resume (branch + sandbox + mount) -> builder with its edit -> grade -> delete the sandbox.
Checks never sit where the agent can read them: they are copied into the sandbox only after the builder exits,
removed right after grading, and every builder run starts behind a guard that fails if any check is visible.
"""
from __future__ import annotations

import base64
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orchestrator.archil_log import ArchilLog, Copy, Wave

HERE = Path(__file__).resolve().parent
BUILDER, CHECKS = "fake_builder.py", "fake_checks.py"  # swap for builder/ (brendan) and P2's checks when they land
GUARD_EXIT = 97


def _write_json(path: Path, doc) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    os.replace(tmp, path)


def _last_json_line(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def install_builder(w) -> None:
    w.put(f"{w.tools}/builder/{BUILDER}", (HERE / BUILDER).read_text())


def checks_dir(w) -> str:
    return f"{w.tools}/checks"


def run_builder(w, from_step: int, to_step: int, route: str, patch: dict | None = None,
                env: dict | None = None) -> dict:
    """Run the builder behind a guard: no checks dir, and no check file anywhere on the agent's disk."""
    patch_arg = ""
    if patch and patch.get("kind", "none") != "none":
        w.put(f"{w.tools}/patch.json", json.dumps(patch))
        patch_arg = f" --patch {w.tools}/patch.json"
    guard = (f"if [ -e {checks_dir(w)} ] || find {w.mnt} -name {CHECKS} -print 2>/dev/null | grep -q .; "
             f"then echo 'checks visible to the builder' >&2; exit {GUARD_EXIT}; fi")
    out = w.must(f"{guard}; python3 {w.tools}/builder/{BUILDER} --disk {w.mnt} --from-step {from_step}"
                 f" --to-step {to_step} --route {route}{patch_arg}", env=env)
    return {**_last_json_line(out), "checks_hidden_during_build": True}


def grade(w, at_step: int) -> dict:
    """Copy the checks in (builder has exited), grade, remove them, all in one exec."""
    d, b64 = checks_dir(w), base64.b64encode((HERE / CHECKS).read_text().encode()).decode()
    out = w.must(f"mkdir -p {d} && echo {b64} | base64 -d > {d}/{CHECKS} && "
                 f"python3 {d}/{CHECKS} --disk {w.mnt} --at-step {at_step}; rc=$?; rm -rf {d}; exit $rc")
    return json.loads(out)


def build(store, spec: str, rules: dict[str, str], steps: int, run_dir: Path, *,
          slip_step: int | None = None, name: str = "build") -> dict:
    """One builder process per step, graded after each step, save(k) between turns. Writes run.json."""
    run_dir.mkdir(parents=True, exist_ok=True)
    w = store.start_build(f"{name}-{int(time.time())}")
    try:
        install_builder(w)
        w.put(f"{w.mnt}/spec.md", spec)
        for fname, text in rules.items():
            w.put(f"{w.mnt}/rules/{fname}", text)
        w.put(f"{w.mnt}/state.json", json.dumps({"last_done": 0, "steps": []}))
        run = {"run_id": run_dir.name, "disk_id": store.disk_id, "store": store.kind, "builder": BUILDER,
               "checks_source": CHECKS, "n_steps": steps, "model": None,
               "simulated_slip": {"step": slip_step, "label": "simulated model slip (fake builder)"}
               if slip_step else None,
               "checkpoints": {"0": store.save(0)}, "steps": []}
        env = {"FAKE_SLIP_STEP": str(slip_step)} if slip_step else None
        for k in range(1, steps + 1):
            t0 = time.perf_counter()
            res = run_builder(w, k - 1, k, "build", env=env)
            wall = time.perf_counter() - t0
            checks = grade(w, k)
            t0 = time.perf_counter()
            run["checkpoints"][str(k)] = store.save(k)
            run["steps"].append({"step": k, "wall_s": round(wall, 3), "wrote": res["wrote"],
                                 "checks": checks, "checks_hidden_during_build": res["checks_hidden_during_build"],
                                 "checkpoint_ms": round((time.perf_counter() - t0) * 1000, 1)})
            _write_json(run_dir / "run.json", run)
        run["final_checks"] = run["steps"][-1]["checks"]
        _write_json(run_dir / "run.json", run)
        return run
    finally:
        w.delete()


def run_wave(store, checkpoint_id: str, edits: list[dict], n: int, *, wave: str, to_step: int, run_dir: Path,
             log: ArchilLog, targets: list[str], purpose: str, check: str | None = None) -> dict:
    """Branch n copies of checkpoint_id in parallel; copy i applies edits[i % len(edits)].
    A copy `passed` when every check in `targets` is true after it rebuilds to `to_step`."""
    fork_step = int(checkpoint_id.rsplit("/c", 1)[1])

    def one(i: int) -> dict:
        edit = edits[i % len(edits)]
        rid = f"{wave}-{edit['route']}-r{i // len(edits) + 1}"
        rec = {"id": rid, "route": edit["route"], "kind": edit.get("kind", "none"),
               "edit": edit.get("new") or edit.get("rule"), "ok": False}
        t0 = time.perf_counter()
        w = None
        try:
            w = store.resume(checkpoint_id, rid)
            rec["branch"] = w.branch
            install_builder(w)
            rec["builder"] = run_builder(w, fork_step, to_step, rid, {**edit, "route": rid})
            rec["checks"] = grade(w, to_step)
            rec["passed"] = all(rec["checks"].get(t, False) for t in targets)
            rec["ok"] = True
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:600]
        finally:
            rec["wall_s"] = round(time.perf_counter() - t0, 3)
            rec["timings_ms"] = dict(w.timings_ms) if w else {}
            if w:
                w.delete()
        return rec

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as ex:
        copies = list(ex.map(one, range(n)))
    wall = round(time.perf_counter() - t0, 3)

    by_route: dict[str, dict] = {}
    for c in copies:
        r = by_route.setdefault(c["route"], {"route": c["route"], "kind": c["kind"], "edit": c["edit"], "runs": 0,
                                             "passed": 0, "errors": 0})
        r["runs"] += 1
        r["passed"] += int(bool(c.get("passed")))
        r["errors"] += int(not c["ok"])
    for r in by_route.values():
        r["score"] = f"{r['passed']}/{r['runs']}"

    rec = {"wave": wave, "purpose": purpose, "check": check, "targets": targets, "checkpoint_id": checkpoint_id,
           "fork_step": fork_step, "to_step": to_step, "n": n, "wall_s": wall, "routes": list(by_route.values()),
           "copies": copies}
    res_path = run_dir / "results.json"
    results = json.loads(res_path.read_text()) if res_path.exists() else {"run_id": run_dir.name, "waves": []}
    results["waves"].append(rec)
    _write_json(res_path, results)

    log.wave(Wave(wave=wave, fork_step=fork_step, wall_s=wall, copies=[
        Copy(c["id"], c["timings_ms"].get("branch", 0.0), c["timings_ms"].get("mount", 0.0), c["wall_s"],
             c["timings_ms"].get("sandbox", 0.0)) for c in copies if c["ok"]]))
    return rec
