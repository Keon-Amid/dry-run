"""Build with a checkpoint per step, then waves of branches from a checkpoint.

build(store, spec, rules, steps, run_dir, kit)              -> run.json (checkpoints, per-step time, checks, usage)
run_wave(store, checkpoint_id, edits, n, ..., kit=kit)      -> one wave appended to results.json, logged to archil.json

Each copy: resume (branch + sandbox + mount) -> builder with its edit -> grade -> delete the sandbox.
Checks never sit where the agent can read them: they are copied into the sandbox only after the builder exits,
removed right after grading, and every builder run starts behind a guard that fails if any check is visible.
Secrets (ANTHROPIC_API_KEY) reach the builder only through the exec environment (Kit.env), never a file.
Model calls: at most Kit.max_builders builder processes run at once across all waves (each makes its calls one at a
time); the builder retries 429s itself, and a copy that still dies on a rate limit is resumed from its last step.
"""
from __future__ import annotations

import base64
import json
import os
import random
import shlex
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.archil_log import ArchilLog, Copy, Wave

HERE = Path(__file__).resolve().parent
STUB_BUILDER = HERE / "stub_builder" / "builder"     # same CLI and RESULT line as brendan's builder/
REAL_BUILDER = HERE.parent / "builder"               # brendan's package, used with --builder real
STUB_CHECKS = HERE / "fake_checks.py"                # swap for P2's checks when they land
GUARD_EXIT = 97
RATE_LIMIT_RETRIES = 3


@dataclass
class Kit:
    builder_src: Path = STUB_BUILDER
    checks_src: Path = STUB_CHECKS
    env: dict = field(default_factory=dict, repr=False)  # exec env for the builder only (keys); never written
    max_builders: int = 64                               # builder processes running at once, across all waves
    branch_max_calls: int | None = None                  # --max-calls for wave copies (brendan: 8-12); None = default
    _sem: threading.BoundedSemaphore = field(init=False, repr=False)

    def __post_init__(self):
        self._sem = threading.BoundedSemaphore(self.max_builders)

    @property
    def checks_name(self) -> str:
        return Path(self.checks_src).name

    @property
    def builder_label(self) -> str:
        return "stub" if Path(self.builder_src) == STUB_BUILDER else "builder/ (real)"


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
                env: dict | None = None, kit: Kit | None = None, max_calls: int | None = None) -> dict:
    """Run steps from_step..to_step (from_step runs first; steps 1..from_step-1 must already be on the disk).
    Behind a guard: no checks dir, and no check file anywhere on the agent's disk.
    Returns the builder's RESULT json whatever the exit code (brendan's: 0 ok, 2 capped/invalid, 1 error);
    raises only when there is no RESULT line."""
    kit = kit or Kit()
    patch_arg = ""
    if patch and patch.get("kind", "none") != "none":
        w.put(f"{w.tools}/patch.json", json.dumps(patch))
        patch_arg = f" --patch {w.tools}/patch.json"
    if max_calls:
        patch_arg += f" --max-calls {max_calls}"
    guard = (f"if [ -e {checks_dir(w)} ] || find {w.mnt} -name {kit.checks_name} -print 2>/dev/null | grep -q .; "
             f"then echo 'checks visible to the builder' >&2; exit {GUARD_EXIT}; fi")
    with kit._sem:  # caps concurrent model-calling processes
        code, out, err = w.exec(f"{guard}; cd {pkg_dir(w)} && python3 -m builder.run --disk {w.mnt}"
                                f" --from-step {from_step} --to-step {to_step} --route {route}{patch_arg}",
                                env={**kit.env, **(env or {})} or None)
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


def rate_limited(res: dict) -> bool:
    e = str(res.get("error") or "").lower()
    return outcome(res) == "error" and ("429" in e or "rate_limit" in e or "rate limit" in e or "529" in e)


def run_steps(w, from_step: int, to_step: int, route: str, patch: dict | None, kit: Kit,
              env: dict | None = None, sleep=time.sleep, max_calls: int | None = None) -> dict:
    """run_builder, plus: if the builder still dies on a rate limit after its own retries, back off and resume
    from its last finished step (the patch has landed by then, so it isn't sent again). `retries` is recorded."""
    res = run_builder(w, from_step, to_step, route, patch, env, kit, max_calls)
    retries, steps = 0, list(res.get("steps") or [])
    while rate_limited(res) and retries < RATE_LIMIT_RETRIES:
        retries += 1
        sleep(min(60.0, 5.0 * 2 ** retries) * (0.5 + random.random() / 2))
        nxt = (res.get("last_done") or from_step - 1) + 1
        if nxt > to_step:
            break
        res = run_builder(w, nxt, to_step, route, None, env, kit, max_calls)
        steps += list(res.get("steps") or [])
    return {**res, "steps": steps, "rate_limit_resumes": retries}


SNAPSHOT = ("import hashlib,json,os,sys;r=sys.argv[1];o={}\n"
            "for d,ds,fs in os.walk(r):\n"
            " ds[:]=[x for x in ds if x!='.git']\n"
            " for f in fs:\n"
            "  p=os.path.join(d,f);o[os.path.relpath(p,r)]=hashlib.sha1(open(p,'rb').read()).hexdigest()\n"
            "print(json.dumps(o))")


def snapshot(w) -> dict:
    """Hash of every file on the agent's disk (minus .git), to see which files a step wrote, with any builder."""
    return json.loads(w.must(f"python3 -c {shlex.quote(SNAPSHOT)} {w.mnt}"))


def grade(w, at_step: int, kit: Kit | None = None) -> dict:
    """Copy the checks in (builder has exited), grade, remove them, all in one exec. Grading must leave the agent's
    disk byte-identical (no __pycache__ from importing its code), or the builder sees a dirty workspace."""
    kit = kit or Kit()
    d, name = checks_dir(w), kit.checks_name
    b64 = base64.b64encode(Path(kit.checks_src).read_bytes()).decode()
    out = w.must(f"mkdir -p {d} && echo {b64} | base64 -d > {d}/{name} && "
                 f"PYTHONDONTWRITEBYTECODE=1 python3 {d}/{name} --disk {w.mnt} --at-step {at_step}; rc=$?; "
                 f"rm -rf {d}; exit $rc")
    return json.loads(out)


def grade_messages(w, at_step: int, kit: Kit | None = None) -> dict | None:
    """Failure messages per check, from a grader that has a flip mode (`checks.py WORKSPACE` ->
    {"checks": {name: {"pass", "msg"}}}). None if the grader has no such mode (the stub checks)."""
    kit = kit or Kit()
    d, name = checks_dir(w), kit.checks_name
    b64 = base64.b64encode(Path(kit.checks_src).read_bytes()).decode()
    code, out, _ = w.exec(f"mkdir -p {d} && echo {b64} | base64 -d > {d}/{name} && "
                          f"PYTHONDONTWRITEBYTECODE=1 python3 {d}/{name} {w.mnt}/workspace --at-step {at_step}; "
                          f"rc=$?; rm -rf {d}; exit $rc")
    try:
        res = json.loads(out)["checks"] if code == 0 else None
    except (ValueError, KeyError, TypeError):
        return None
    return {n: r.get("msg") for n, r in res.items() if not r.get("pass")} if res else None


def build(store, spec: str, rules: dict[str, str], steps: int, run_dir: Path, *,
          slip_step: int | None = None, name: str = "build", kit: Kit | None = None,
          export_dir: Path | None = None) -> dict:
    """One builder process per step, graded after each step, save(k) between turns. Writes run.json."""
    kit = kit or Kit()
    run_dir.mkdir(parents=True, exist_ok=True)
    w = store.start_build(f"{name}-{int(time.time())}")
    try:
        install_builder(w, kit.builder_src)
        w.put(f"{w.mnt}/spec.md", spec)
        for fname, text in rules.items():
            w.put(f"{w.mnt}/rules/{fname}", text)
        w.put(f"{w.mnt}/state.json", json.dumps({"last_done": 0, "steps": []}))
        run = {"run_id": run_dir.name, "disk_id": store.disk_id, "store": store.kind, "builder": kit.builder_label,
               "checks_source": kit.checks_name, "n_steps": steps, "model": None,
               "simulated_slip": {"step": slip_step, "label": "simulated model slip (stub builder)"}
               if slip_step else None,
               "checkpoints": {"0": store.save(0)}, "steps": []}
        env = {"FAKE_SLIP_STEP": str(slip_step)} if slip_step else None
        before = snapshot(w)
        for k in range(1, steps + 1):
            t0 = time.perf_counter()
            res = run_steps(w, k, k, "build", None, kit, env)  # one step per process, then save(k)
            wall = time.perf_counter() - t0
            if outcome(res) != "ok":
                raise RuntimeError(f"build step {k} {outcome(res)}: {res.get('error')}")
            after = snapshot(w)
            wrote = sorted(f for f in after if after[f] != before.get(f))
            before = after
            checks = grade(w, k, kit)
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
        run["final_messages"] = grade_messages(w, steps, kit)  # why each failing check failed (visible + held-out)
        if export_dir:  # the finished workspace, for scripts/before_after.py (the sandbox is deleted next)
            try:
                w.get_tree(f"{w.mnt}/workspace", export_dir)
                run["workspace_export"] = str(export_dir.relative_to(run_dir))
            except Exception as e:  # never sink a run over an export
                run["workspace_export_error"] = f"{type(e).__name__}: {e}"[:300]
        _write_json(run_dir / "run.json", run)
        return run
    finally:
        w.delete()


def run_wave(store, checkpoint_id: str, edits: list[dict], n: int, *, wave: str, to_step: int, run_dir: Path,
             log: ArchilLog, targets: list[str], purpose: str, check: str | None = None,
             kit: Kit | None = None, export_dir: Path | None = None) -> dict:
    """Branch n copies of checkpoint_id = c_{k-1} in parallel; each runs steps k..to_step with
    edits[i % len(edits)] applied first. A copy `passed` when every check in `targets` is true at to_step."""
    kit = kit or Kit()
    fork_step = int(checkpoint_id.rsplit("/c", 1)[1])  # steps 1..fork_step are on the branch already

    def one(i: int) -> dict:
        edit = edits[i % len(edits)]
        rid = f"{wave}-{edit['route']}-r{i // len(edits) + 1}"
        rec = {"id": rid, "route": edit["route"], "kind": edit.get("kind", "none"),
               "edit": edit.get("new") or edit.get("rule") or (f"whole spec, {len(edit['spec'])} chars"
                                                                if edit.get("spec") else None), "ok": False}
        t0 = time.perf_counter()
        w = None
        try:
            w = store.resume(checkpoint_id, rid)
            rec["branch"] = w.branch
            install_builder(w, kit.builder_src)
            patch = {**edit, "route": rid}
            if edit.get("kind") == "spec_replace":  # a whole new spec (baseline arm): written before the builder
                w.put(f"{w.mnt}/spec.md", edit["spec"])  # starts; the builder's patch kinds only edit one step
                patch = None
            rec["builder"] = run_steps(w, fork_step + 1, to_step, rid, patch, kit,
                                       max_calls=kit.branch_max_calls)
            out = outcome(rec["builder"])
            if out == "invalid":
                rec["invalid"] = True  # capped: reported as invalid, never graded, never a fail
            elif out == "error":
                rec["error"] = f"builder: {rec['builder'].get('error')}"[:600]
            else:
                rec["checks"] = grade(w, to_step, kit)
                rec["passed"] = all(rec["checks"].get(t, False) for t in targets)
                rec["ok"] = True
                if export_dir and i == 0:  # first copy's finished workspace, before its sandbox is deleted
                    try:
                        w.get_tree(f"{w.mnt}/workspace", export_dir)
                        rec["workspace_export"] = str(export_dir.relative_to(run_dir))
                    except Exception as e:
                        rec["workspace_export_error"] = f"{type(e).__name__}: {e}"[:300]
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
           "fork_step": fork_step, "to_step": to_step, "n": n, "wall_s": wall, "max_builders": kit.max_builders,
           "routes": list(by_route.values()), "copies": copies}
    res_path = run_dir / "results.json"
    results = json.loads(res_path.read_text()) if res_path.exists() else {"run_id": run_dir.name, "waves": []}
    results["waves"].append(rec)
    _write_json(res_path, results)

    log.wave(Wave(wave=wave, fork_step=fork_step, wall_s=wall, copies=[
        Copy(c["id"], c["timings_ms"].get("branch", 0.0), c["timings_ms"].get("mount", 0.0), c["wall_s"],
             c["timings_ms"].get("sandbox", 0.0)) for c in copies if c["ok"]]))
    return rec
