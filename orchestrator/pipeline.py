"""One entry point: build -> grade -> triage -> locate -> suspects -> swarm, per CONTRACT.md "How it works".

    .venv/bin/python -m orchestrator.pipeline [--local] [--swarm-copies 3]

Writes orchestrator/runs/<stamp>/: run.json, triage.json, results.json (every wave), swarm.json, archil.json.
Uses the STUB builder, checks, spec, rules, golden/ and rewrites in orchestrator/ until the real ones land.
On Archil every sandbox is deleted (inside build and run_wave); the disk, checkpoints and branches stay.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from orchestrator.archil_log import ArchilLog
from orchestrator.stores import ArchilStore, LocalStore
from orchestrator.wave import CHECKS, HERE, _write_json, build, run_wave

ROOT = HERE.parent
N_COPIES = 3  # per hypothesis: verdicts are counts (3/3 vs 0/3), never one run

# STUBS until P2 / brendan land theirs. Suspect edits are minimal disambiguations (docs/plan-builder.md change C);
# swarm rewrites stand in for the rewrite generator. rw3 passes the visible check but fails the held-out one.
DISAMBIGUATE = {"Links expire after 30 days.": "Links expire 30 days after the last click."}
REWRITES = {"Links expire after 30 days.": [
    "Links expire 30 days after their last click.",
    "Links expire 30 days after they are created.",
    "Links expire at the last click.",
    "Links expire after 30 days, counted from the last click.",
    "Links never expire.",
]}


def spec_line(spec: str, k: int) -> str:
    return re.search(rf"^## Step {k}\b.*?\n(.*?)(?=^## Step |\Z)", spec, re.S | re.M).group(1).strip()


def local_checks(*args: str) -> dict:
    out = subprocess.run([sys.executable, str(HERE / CHECKS), *args], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _route(wave: dict, route: str) -> dict:
    return next(r for r in wave["routes"] if r["route"] == route)


def _verdict(fails: int, runs: int, errors: int) -> str:
    if errors or runs == 0:
        return "inconclusive"
    return {0: "model_slip", runs: "real_problem"}.get(fails, "inconclusive")


def pipeline(store, run_dir: Path, *, steps: int = 7, slip_step: int | None = 4, copies: int = N_COPIES) -> dict:
    spec = (HERE / "fake_spec.md").read_text()
    rules = {p.name: p.read_text() for p in sorted((HERE / "fake_rules").glob("*.md"))}
    t_start = time.perf_counter()

    # BUILD + GRADE (checks after every step, from outside the agent's disk)
    run = build(store, spec, rules, steps, run_dir, slip_step=slip_step)
    ckpt = run["checkpoints"]
    log = ArchilLog(run_dir / "run.json", run_dir / "archil.json", ROOT / "spikes" / "disk_spike.json")
    meta = local_checks("--meta")
    golden = local_checks("--disk", str(HERE / "fake_golden"), "--at-step", str(steps))  # never on an agent disk
    failing = [c for c, ok in run["final_checks"].items() if not ok and not meta[c]["heldout"]]
    print(f"build: failing {failing}", flush=True)

    # TRIAGE each failing check, LOCATE the real ones
    triage = []
    for c in failing:
        surfaced = next(s["step"] for s in run["steps"] if s["checks"].get(c) is False)
        origin = next(s["step"] for s in run["steps"] if meta[c]["file"] in s["wrote"] or
                      (meta[c]["file"] == "conversation.jsonl"))
        t = {"check": c, "surfaced_step": surfaced, "origin_step": origin, "fails_on_golden": not golden.get(c, True)}
        if t["fails_on_golden"]:
            t.update(verdict="test_wrong", rebuild=None)
        else:
            wv = run_wave(store, ckpt[str(surfaced - 1)], [{"route": "rebuild", "kind": "none"}], copies,
                          wave=f"triage-{c}", to_step=surfaced, run_dir=run_dir, log=log, targets=[c],
                          purpose="triage", check=c)
            r = _route(wv, "rebuild")
            fails = r["runs"] - r["passed"] - r["errors"]
            t["rebuild"] = {"checkpoint_id": wv["checkpoint_id"], "step": surfaced, "fails": f"{fails}/{r['runs']}",
                            "errors": r["errors"], "wave": wv["wave"]}
            t["verdict"] = _verdict(fails, r["runs"], r["errors"])
        if t["verdict"] == "real_problem":
            t["fork_checkpoint_id"] = ckpt[str(origin - 1)]  # LOCATE: the checkpoint just before the origin step
        triage.append(t)
        print(f"triage {c}: {t['verdict']}", flush=True)
    _write_json(run_dir / "triage.json", {"run_id": run_dir.name, "checks": triage})

    # SUSPECTS + SWARM for each real problem
    swarm = []
    for t in (t for t in triage if t["verdict"] == "real_problem"):
        c, fork = t["check"], t["fork_checkpoint_id"]
        lines = list(dict.fromkeys(spec_line(spec, k) for k in (t["origin_step"], t["surfaced_step"])))
        edits = [{"route": f"spec-step{k}", "kind": "spec_line", "step": k, "old": spec_line(spec, k),
                  "new": DISAMBIGUATE.get(spec_line(spec, k), ""), "hypothesis": f"spec step {k} is the cause"}
                 for k in dict.fromkeys((t["origin_step"], t["surfaced_step"]))]
        edits += [{"route": f"rule-{Path(r).stem}", "kind": "rule_off", "rule": r,
                   "hypothesis": f"rule {r} is the cause"} for r in rules]
        edits.append({"route": "control", "kind": "control", "old": lines[0], "hypothesis": "no change"})
        sv = run_wave(store, fork, edits, copies * len(edits), wave=f"suspects-{c}", to_step=steps, run_dir=run_dir,
                      log=log, targets=[c], purpose="suspects", check=c)
        ctrl = _route(sv, "control")
        suspects = [{**{k: e.get(k) for k in ("route", "kind", "step", "old", "new", "rule")},
                     "score": _route(sv, e["route"])["score"]} for e in edits if e["route"] != "control"]
        flips = [s for s in suspects if s["score"] == f"{copies}/{copies}" and ctrl["passed"] == 0
                 and ctrl["errors"] == 0]
        t["suspects"] = {"wave": sv["wave"], "control": ctrl["score"], "suspects": suspects}
        t["culprit"] = flips[0] if len(flips) == 1 else None
        print(f"suspects {c}: control {ctrl['score']}, " + ", ".join(f"{s['route']} {s['score']}" for s in suspects),
              flush=True)
        if not t["culprit"] or t["culprit"]["kind"] != "spec_line":
            continue  # a harness culprit has no swarm; no unique culprit means no swarm either

        # SWARM: rewrites of the culprit line x copies, from the same checkpoint
        old = t["culprit"]["old"]
        heldout = [h for h, m in meta.items() if m["heldout"] and m["file"] == meta[c]["file"]]
        ctrl_green = {k for k in run["final_checks"] if all(cp["checks"].get(k) for cp in sv["copies"]
                                                             if cp["route"] == "control" and cp["ok"])}
        rws = [{"route": f"rw{i + 1}", "kind": "spec_line", "step": t["culprit"]["step"], "old": old, "new": new,
                "hypothesis": "rewrite of the culprit line"} for i, new in enumerate(REWRITES.get(old, []))]
        ww = run_wave(store, fork, rws, copies * len(rws), wave=f"swarm-{c}", to_step=steps, run_dir=run_dir, log=log,
                      targets=[c], purpose="swarm", check=c)
        rewrites = []
        for e in rws:
            cps = [cp for cp in ww["copies"] if cp["route"] == e["route"]]
            ok = [cp for cp in cps if cp["ok"]]
            visible = sum(cp["checks"].get(c, False) for cp in ok)
            held = sum(all(cp["checks"].get(h, False) for h in heldout) for cp in ok)
            regress = sorted({k for cp in ok for k in ctrl_green if k != c and not cp["checks"].get(k)})
            rewrites.append({"route": e["route"], "text": e["new"], "visible": f"{visible}/{len(cps)}",
                             "heldout": f"{held}/{len(cps)}", "regressions": regress, "errors": len(cps) - len(ok),
                             "winner": len(ok) == len(cps) and visible == held == len(cps) and not regress})
        winners = [r for r in rewrites if r["winner"]]
        swarm.append({"check": c, "culprit": t["culprit"], "fork_checkpoint_id": fork, "wave": ww["wave"],
                      "heldout_checks": heldout, "n_branches": ww["n"], "n_rewrites": len(rws),
                      "rewrites": rewrites, "winners": [r["route"] for r in winners]})
        t["swarm"] = {"branches": ww["n"], "rewrites": len(rws), "winners": len(winners)}
        print(f"swarm {c}: winners {[r['text'] for r in winners]}", flush=True)

    for t in triage:
        t["card"] = card(t)
    _write_json(run_dir / "triage.json", {"run_id": run_dir.name, "checks": triage})
    _write_json(run_dir / "swarm.json", {"run_id": run_dir.name, "swarms": swarm})
    print(f"pipeline done in {time.perf_counter() - t_start:.1f}s -> {run_dir}", flush=True)
    return {"triage": triage, "swarm": swarm}


def card(t: dict) -> str:
    """The one-line card, built only from the run-file fields above."""
    if t["verdict"] == "test_wrong":
        return f"{t['check']}: your test is wrong (it fails on golden/ too). The spec wasn't touched."
    if t["verdict"] == "model_slip":
        return (f"{t['check']}: the model slipped. Rebuilding step {t['surfaced_step']} 3 times fails "
                f"{t['rebuild']['fails']}.")
    if t["verdict"] != "real_problem":
        return f"{t['check']}: inconclusive ({t.get('rebuild') or 'no rebuild'})."
    cul = t.get("culprit")
    if not cul:
        return f"{t['check']}: real problem, no single suspect flipped it (control {t['suspects']['control']})."
    cause = f"spec step {cul['step']}, \"{cul['old']}\"" if cul["kind"] == "spec_line" else f"rule {cul['rule']}"
    s = (f"Cause: {cause}. Surfaced at step {t['surfaced_step']}, origin step {t['origin_step']}. "
         f"Suspect test: {cul['score']} vs control {t['suspects']['control']}.")
    if t.get("swarm"):
        sw = t["swarm"]
        s += f" Swarm: {sw['branches']} branches tried {sw['rewrites']} rewrites, {sw['winners']} pass 3/3 + held-out."
    return s


def _load_env() -> None:
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="plain folders instead of Archil")
    ap.add_argument("--copies", type=int, default=N_COPIES, help="copies per hypothesis")
    a = ap.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "runs" / f"{stamp}{'-local' if a.local else ''}"
    client = None
    if a.local:
        store = LocalStore(Path(tempfile.mkdtemp(prefix="dryrun-")))
    else:
        import archil
        _load_env()
        region = os.environ.get("ARCHIL_REGION", "aws-us-east-1")
        client = archil.Archil(api_key=os.environ["ARCHIL_API_KEY"], region=region)
        store = ArchilStore.new(client, region, f"dryrun-run-{stamp}")
    try:
        print(f"run dir: {run_dir}\ndisk: {store.disk_id}", flush=True)
        out = pipeline(store, run_dir, copies=a.copies)
        for t in out["triage"]:
            print(" ", t["card"])
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
