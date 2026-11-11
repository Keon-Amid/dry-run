"""Build with a checkpoint per step, then run waves of branches from a checkpoint.

build(store, spec, steps, run_dir)              -> run.json (checkpoint ids, per-step wall time)
run_wave(store, checkpoint_id, edits, n, ...)   -> one wave in results.json and archil.json

Each copy: resume (branch + sandbox + mount) -> apply its edit -> builder to the last step -> checks -> delete.
The builder and checks are copied into each worker's tools folder, outside the agent's disk.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orchestrator.archil_log import ArchilLog, Copy, Wave

HERE = Path(__file__).resolve().parent
BUILDER, CHECKS = "fake_builder.py", "fake_checks.py"  # swap for the real builder and P2's checks when they land


def _write_json(path: Path, doc) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    os.replace(tmp, path)


def _install_tools(w) -> None:
    for f in (BUILDER, CHECKS):
        w.put(f"{w.tools}/{f}", (HERE / f).read_text())


def _last_json_line(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def build(store, spec: str, steps: int, run_dir: Path, name: str = "build") -> dict:
    """Step-by-step build: one builder process per step, save(k) between turns. Writes run.json."""
    run_dir.mkdir(parents=True, exist_ok=True)
    w = store.start_build(f"{name}-{int(time.time())}")
    try:
        _install_tools(w)
        w.put(f"{w.mnt}/spec.md", spec)
        w.put(f"{w.mnt}/state.json", json.dumps({"last_done": 0, "steps": []}))
        run = {"disk_id": store.disk_id, "store": store.kind, "builder": BUILDER, "n_steps": steps,
               "checkpoints": {"0": store.save(0)}, "steps": []}
        for k in range(1, steps + 1):
            t0 = time.perf_counter()
            w.must(f"python3 {w.tools}/{BUILDER} --disk {w.mnt} --from-step {k - 1} --to-step {k} --route build")
            wall = time.perf_counter() - t0
            t0 = time.perf_counter()
            run["checkpoints"][str(k)] = store.save(k)
            run["steps"].append({"step": k, "wall_s": round(wall, 3),
                                 "checkpoint_ms": round((time.perf_counter() - t0) * 1000, 1)})
            _write_json(run_dir / "run.json", run)
        run["checks"] = json.loads(w.must(f"python3 {w.tools}/{CHECKS} --disk {w.mnt} --steps {steps}"))
        _write_json(run_dir / "run.json", run)
        return run
    finally:
        w.delete()


def run_wave(store, checkpoint_id: str, edits: list[dict], n: int, *, wave: str, to_step: int,
             run_dir: Path, log: ArchilLog) -> dict:
    """Branch n copies of checkpoint_id in parallel; copy i applies edits[i % len(edits)]."""
    fork_step = int(checkpoint_id.rsplit("/c", 1)[1])

    def one(i: int) -> dict:
        edit = edits[i % len(edits)]
        rid = f"{wave}-{edit['route']}-r{i // len(edits) + 1}"
        rec = {"id": rid, "route": edit["route"], "kind": edit["kind"], "edit": edit.get("new"), "ok": False}
        t0 = time.perf_counter()
        w = None
        try:
            w = store.resume(checkpoint_id, rid)
            rec["branch"] = w.branch
            _install_tools(w)
            w.put(f"{w.tools}/patch.json", json.dumps({**edit, "route": rid}))
            rec["builder"] = _last_json_line(w.must(
                f"python3 {w.tools}/{BUILDER} --disk {w.mnt} --from-step {fork_step} --to-step {to_step}"
                f" --patch {w.tools}/patch.json --route {rid}"))
            rec["checks"] = json.loads(w.must(f"python3 {w.tools}/{CHECKS} --disk {w.mnt} --steps {to_step}"))
            rec["passed"] = all(rec["checks"].values())
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
        r = by_route.setdefault(c["route"], {"route": c["route"], "edit": c["edit"], "runs": 0, "passed": 0,
                                             "errors": 0})
        r["runs"] += 1
        r["passed"] += int(bool(c.get("passed")))
        r["errors"] += int(not c["ok"])
    for r in by_route.values():
        r["score"] = f"{r['passed']}/{r['runs']}"

    rec = {"wave": wave, "checkpoint_id": checkpoint_id, "fork_step": fork_step, "to_step": to_step, "n": n,
           "wall_s": wall, "routes": list(by_route.values()), "copies": copies}
    res_path = run_dir / "results.json"
    results = json.loads(res_path.read_text()) if res_path.exists() else {"waves": []}
    results["waves"].append(rec)
    _write_json(res_path, results)

    log.wave(Wave(wave=wave, fork_step=fork_step, wall_s=wall, copies=[
        Copy(c["id"], c["timings_ms"].get("branch", 0.0), c["timings_ms"].get("mount", 0.0), c["wall_s"],
             c["timings_ms"].get("sandbox", 0.0)) for c in copies if c["ok"]]))
    return rec
