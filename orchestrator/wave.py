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
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orchestrator.archil_log import ArchilLog, Copy, Wave

HERE = Path(__file__).resolve().parent
STUB_BUILDER = HERE / "stub_builder" / "builder"     # same CLI and RESULT line as brendan's builder/
REAL_BUILDER = HERE.parent / "builder"               # brendan's package, used with --builder real
CHECKS = "fake_checks.py"                            # swap for P2's checks when they land
GUARD_EXIT = 97


def _write_json(path: Path, doc) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    os.replace(tmp, path)


def parse_result(out: str) -> dict:
    """The builder's answer is the LAST stdout line starting with "RESULT "; everything else is ignored."""
    lines = [l for l in out.splitlines() if l.startswith("RESULT ")]
    if not lines:
        raise RuntimeError(f"builder printed no RESULT line; stdout tail: {out[-500:]!r}")
    return json.loads(lines[-1][len("RESULT "):])


def pkg_dir(w) -> str:
    return f"{w.tools}/pkg"  # holds builder/; the builder runs as `python3 -m builder.run` from here


def install_builder(w, src: Path = STUB_BUILDER) -> None:
    """Copy the whole builder/ package in, and install its requirements.txt if it has one."""
    w.put_tree(src, pkg_dir(w))
    if (src / "requirements.txt").exists():
        w.must(f"python3 -m pip install -q --disable-pip-version-check -r {pkg_dir(w)}/builder/requirements.txt")


def checks_dir(w) -> str:
    return f"{w.tools}/checks"


def run_builder(w, from_step: int, to_step: int, route: str, patch: dict | None = None,
                env: dict | None = None) -> dict:
    """Run steps from_step..to_step (from_step runs first; steps 1..from_step-1 must already be on the disk).
    Behind a guard: no checks dir, and no check file anywhere on the agent's disk.
    Returns the builder's RESULT json whatever the exit code (brendan's: 0 ok, 2 capped/invalid, 1 error);
    raises only when there is no RESULT line."""
    patch_arg = ""
    if patch and patch.get("kind", "none") != "none":
        w.put(f"{w.tools}/patch.json", json.dumps(patch))
        patch_arg = f" --patch {w.tools}/patch.json"
    guard = (f"if [ -e {checks_dir(w)} ] || find {w.mnt} -name {CHECKS} -print 2>/dev/null | grep -q .; "
             f"then echo 'checks visible to the builder' >&2; exit {GUARD_EXIT}; fi")
    code, out, err = w.exec(f"{guard}; cd {pkg_dir(w)} && python3 -m builder.run --disk {w.mnt}"
                            f" --from-step {from_step} --to-step {to_step} --route {route}{patch_arg}", env=env)
    if code == GUARD_EXIT:
        raise RuntimeError(f"exit {GUARD_EXIT}: checks visible to the builder")
    try:
        res = parse_result(out)
    except RuntimeError as e:
        raise RuntimeError(f"builder exit {code}, {e}; stderr tail: {err[-300:]!r}") from None
    return {**res, "exit_code": code, "checks_hidden_during_build": True}


def outcome(res: dict) -> str:
    """ok | invalid (capped: never counted as a fail) | error."""
    if res.get("ok"):
        return "ok"
    return "invalid" if res.get("invalid") or res.get("capped") else "error"


SNAPSHOT = ("import hashlib,json,os,sys;r=sys.argv[1];o={}\n"
            "for d,ds,fs in os.walk(r):\n"
            " ds[:]=[x for x in ds if x!='.git']\n"
            " for f in fs:\n"
            "  p=os.path.join(d,f);o[os.path.relpath(p,r)]=hashlib.sha1(open(p,'rb').read()).hexdigest()\n"
            "print(json.dumps(o))")


def snapshot(w) -> dict:
    """Hash of every file on the agent's disk (minus .git), to see which files a step wrote, with any builder."""
    return json.loads(w.must(f"python3 -c {shlex.quote(SNAPSHOT)} {w.mnt}"))


def grade(w, at_step: int) -> dict:
    """Copy the checks in (builder has exited), grade, remove them, all in one exec."""
    d, b64 = checks_dir(w), base64.b64encode((HERE / CHECKS).read_text().encode()).decode()
    out = w.must(f"mkdir -p {d} && echo {b64} | base64 -d > {d}/{CHECKS} && "
                 f"python3 {d}/{CHECKS} --disk {w.mnt} --at-step {at_step}; rc=$?; rm -rf {d}; exit $rc")
    return json.loads(out)


def build(store, spec: str, rules: dict[str, str], steps: int, run_dir: Path, *,
          slip_step: int | None = None, name: str = "build", builder_src: Path = STUB_BUILDER) -> dict:
    """One builder process per step, graded after each step, save(k) between turns. Writes run.json."""
    run_dir.mkdir(parents=True, exist_ok=True)
    w = store.start_build(f"{name}-{int(time.time())}")
    try:
        install_builder(w, builder_src)
        w.put(f"{w.mnt}/spec.md", spec)
        for fname, text in rules.items():
            w.put(f"{w.mnt}/rules/{fname}", text)
        w.put(f"{w.mnt}/state.json", json.dumps({"last_done": 0, "steps": []}))
        run = {"run_id": run_dir.name, "disk_id": store.disk_id, "store": store.kind,
               "builder": "stub" if builder_src == STUB_BUILDER else str(builder_src),
               "checks_source": CHECKS, "n_steps": steps, "model": None,
               "simulated_slip": {"step": slip_step, "label": "simulated model slip (fake builder)"}
               if slip_step else None,
               "checkpoints": {"0": store.save(0)}, "steps": []}
        env = {"FAKE_SLIP_STEP": str(slip_step)} if slip_step else None
        before = snapshot(w)
        for k in range(1, steps + 1):
            t0 = time.perf_counter()
            res = run_builder(w, k, k, "build", env=env)  # one step per process, then save(k)
            wall = time.perf_counter() - t0
            if outcome(res) != "ok":
                raise RuntimeError(f"build step {k} {outcome(res)}: {res.get('error')}")
            after = snapshot(w)
            wrote = sorted(f for f in after if after[f] != before.get(f))
            before = after
            checks = grade(w, k)
            t0 = time.perf_counter()
            run["checkpoints"][str(k)] = store.save(k)
            rec = {"step": k, "wall_s": round(wall, 3), "wrote": wrote, "checks": checks,
                   "checks_hidden_during_build": res["checks_hidden_during_build"],
                   "checkpoint_ms": round((time.perf_counter() - t0) * 1000, 1)}
            sr = next((x for x in res.get("steps") or [] if x.get("step") == k), None)
            if sr:  # brendan's StepResult: the optional run.json fields
                rec.update({f: sr[f] for f in ("model_calls", "usage", "tool_calls", "commit") if f in sr})
            run["model"] = res.get("model") or run["model"]
            run["steps"].append(rec)
            _write_json(run_dir / "run.json", run)
        run["final_checks"] = run["steps"][-1]["checks"]
        _write_json(run_dir / "run.json", run)
        return run
    finally:
        w.delete()


def run_wave(store, checkpoint_id: str, edits: list[dict], n: int, *, wave: str, to_step: int, run_dir: Path,
             log: ArchilLog, targets: list[str], purpose: str, check: str | None = None,
             builder_src: Path = STUB_BUILDER) -> dict:
    """Branch n copies of checkpoint_id = c_{k-1} in parallel; each runs steps k..to_step with
    edits[i % len(edits)] applied first. A copy `passed` when every check in `targets` is true at to_step."""
    fork_step = int(checkpoint_id.rsplit("/c", 1)[1])  # steps 1..fork_step are on the branch already

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
            install_builder(w, builder_src)
            rec["builder"] = run_builder(w, fork_step + 1, to_step, rid, {**edit, "route": rid})
            out = outcome(rec["builder"])
            if out == "invalid":
                rec["invalid"] = True  # capped: reported as invalid, never graded, never a fail
            elif out == "error":
                rec["error"] = f"builder: {rec['builder'].get('error')}"[:600]
            else:
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
                                             "passed": 0, "errors": 0, "invalid": 0})
        r["runs"] += 1
        r["passed"] += int(bool(c.get("passed")))
        r["invalid"] += int(bool(c.get("invalid")))
        r["errors"] += int(not c["ok"] and not c.get("invalid"))
    for r in by_route.values():
        r["graded"] = r["runs"] - r["errors"] - r["invalid"]
        r["score"] = f"{r['passed']}/{r['graded']}"  # only graded copies count; invalid/errored shown separately

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
