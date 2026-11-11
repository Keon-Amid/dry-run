"""One entry point: build -> grade -> triage -> locate -> suspects -> swarm -> confirm, per CONTRACT.md.

    .venv/bin/python -m orchestrator.pipeline [--local] [--builder stub|real] [--fixture stub|toy] [--smoke]
                                              [--copies 3] [--max-builders N]

Writes orchestrator/runs/<stamp>/: run.json, triage.json, results.json (every wave), swarm.json, archil.json.
--fixture stub: the stub spec/checks/golden/rules/rewrites in orchestrator/ (all three verdicts planted).
--fixture toy:  brendan's builder/tests/fixtures/toy (spec, rules, canary checks via orchestrator/assert_checks.py).
--smoke: build + triage only (or, if nothing fails, one 3-copy rebuild of the last step), to exercise the real builder.
--builder real: ANTHROPIC_API_KEY (and DRYRUN_MODEL if set) go to each builder process through the exec env only.
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
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.archil_log import ArchilLog, spent
from orchestrator.assert_checks import build_checks_file
from orchestrator.stores import ArchilStore, LocalStore
from orchestrator.wave import HERE, REAL_BUILDER, STUB_BUILDER, STUB_CHECKS, Kit, _write_json, build, run_wave

ROOT = HERE.parent
N_COPIES = 3  # per hypothesis: verdicts are counts (3/3 vs 0/3), never one run
TOY = ROOT / "builder" / "tests" / "fixtures" / "toy"

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


@dataclass
class Fixture:
    name: str
    spec: str
    rules: dict
    checks_src: Path
    golden: Path | None = None
    slip_step: int | None = None
    disambiguate: dict = field(default_factory=dict)
    rewrites: dict = field(default_factory=dict)

    @property
    def steps(self) -> int:
        return len(re.findall(r"^## Step \d+", self.spec, re.M))


def load_fixture(name: str, scratch: Path) -> Fixture:
    if name == "stub":
        return Fixture("stub", (HERE / "fake_spec.md").read_text(),
                       {p.name: p.read_text() for p in sorted((HERE / "fake_rules").glob("*.md"))}, STUB_CHECKS,
                       golden=HERE / "fake_golden", slip_step=4, disambiguate=DISAMBIGUATE, rewrites=REWRITES)
    if name == "toy":
        scratch.mkdir(parents=True, exist_ok=True)
        return Fixture("toy", (TOY / "disk" / "spec.md").read_text(),
                       {p.name: p.read_text() for p in sorted((TOY / "disk" / "rules").glob("*.md"))},
                       build_checks_file(TOY, scratch / "toy_checks.py"))
    raise SystemExit(f"unknown fixture {name}")


def spec_line(spec: str, k: int) -> str:
    return re.search(rf"^## Step {k}\b.*?\n(.*?)(?=^## Step |\Z)", spec, re.S | re.M).group(1).strip()


def local_checks(checks_src: Path, *args: str) -> dict:
    out = subprocess.run([sys.executable, str(checks_src), *args], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _route(wave: dict, route: str) -> dict:
    return next(r for r in wave["routes"] if r["route"] == route)


def _verdict(fails: int, runs: int, errors: int) -> str:
    if errors or runs == 0:
        return "inconclusive"
    return {0: "model_slip", runs: "real_problem"}.get(fails, "inconclusive")


def pipeline(store, run_dir: Path, *, fixture: Fixture | None = None, kit: Kit | None = None,
             copies: int = N_COPIES, smoke: bool = False) -> dict:
    fx = fixture or load_fixture("stub", run_dir / "_scratch")
    kit = kit or Kit()
    kit.checks_src = fx.checks_src
    steps = fx.steps
    stages: dict[str, float] = {}
    t_start = t = time.perf_counter()

    def stage(name: str) -> None:
        nonlocal t
        stages[name] = round(stages.get(name, 0) + time.perf_counter() - t, 3)
        t = time.perf_counter()

    # BUILD + GRADE (checks after every step, from outside the agent's disk)
    run = build(store, fx.spec, fx.rules, steps, run_dir, slip_step=fx.slip_step, kit=kit)
    stage("build")
    ckpt = run["checkpoints"]
    log = ArchilLog(run_dir / "run.json", run_dir / "archil.json", ROOT / "spikes" / "disk_spike.json")
    meta = local_checks(fx.checks_src, "--meta")
    golden = local_checks(fx.checks_src, "--disk", str(fx.golden), "--at-step", str(steps)) if fx.golden else {}
    failing = [c for c, ok in run["final_checks"].items() if not ok and not meta[c]["heldout"]]
    print(f"build: {steps} steps, final checks {run['final_checks']}", flush=True)

    # TRIAGE each failing check, LOCATE the real ones
    triage = []
    for c in failing:
        surfaced = next(s["step"] for s in run["steps"] if s["checks"].get(c) is False)
        f = meta[c].get("file")
        origin = next((s["step"] for s in run["steps"] if f and f in s["wrote"]), surfaced) \
            if f != "conversation.jsonl" else surfaced
        t_ = {"check": c, "surfaced_step": surfaced, "origin_step": origin,
              "fails_on_golden": (not golden.get(c, True)) if fx.golden else None}
        if t_["fails_on_golden"]:
            t_.update(verdict="test_wrong", rebuild=None)
        else:
            wv = run_wave(store, ckpt[str(surfaced - 1)], [{"route": "rebuild", "kind": "none"}], copies,
                          wave=f"triage-{c}", to_step=surfaced, run_dir=run_dir, log=log, targets=[c],
                          purpose="triage", check=c, kit=kit)
            r = _route(wv, "rebuild")
            fails = r["graded"] - r["passed"]
            t_["rebuild"] = {"checkpoint_id": wv["checkpoint_id"], "step": surfaced, "fails": f"{fails}/{r['runs']}",
                             "errors": r["errors"], "invalid": r["invalid"], "wave": wv["wave"]}
            t_["verdict"] = _verdict(fails, r["runs"], r["errors"] + r["invalid"])
        if t_["verdict"] == "real_problem":
            t_["fork_checkpoint_id"] = ckpt[str(origin - 1)]  # LOCATE: the checkpoint just before the origin step
        triage.append(t_)
        print(f"triage {c}: {t_['verdict']}", flush=True)
    _write_json(run_dir / "triage.json", {"run_id": run_dir.name, "checks": triage})
    stage("triage")

    if smoke and not any(t_.get("rebuild") for t_ in triage):  # nothing to triage: still exercise one wave
        run_wave(store, ckpt[str(steps - 1)], [{"route": "rebuild", "kind": "none"}], copies, wave="smoke-rebuild",
                 to_step=steps, run_dir=run_dir, log=log, targets=[], purpose="smoke", kit=kit)
        stage("smoke_wave")

    swarm = []
    for t_ in ([] if smoke else [x for x in triage if x["verdict"] == "real_problem"]):
        # SUSPECTS
        c, fork = t_["check"], t_["fork_checkpoint_id"]
        ks = list(dict.fromkeys((t_["origin_step"], t_["surfaced_step"])))
        edits = [{"route": f"spec-step{k}", "kind": "spec_line", "step": k, "old": spec_line(fx.spec, k),
                  "new": fx.disambiguate.get(spec_line(fx.spec, k), ""), "hypothesis": f"spec step {k} is the cause"}
                 for k in ks]
        edits += [{"route": f"rule-{Path(r).stem}", "kind": "rule_off", "rule": r,
                   "hypothesis": f"rule {r} is the cause"} for r in fx.rules]
        edits.append({"route": "control", "kind": "control", "step": ks[0], "old": spec_line(fx.spec, ks[0]),
                      "hypothesis": "no change"})
        sv = run_wave(store, fork, edits, copies * len(edits), wave=f"suspects-{c}", to_step=steps, run_dir=run_dir,
                      log=log, targets=[c], purpose="suspects", check=c, kit=kit)
        ctrl = _route(sv, "control")
        suspects = [{**{k: e.get(k) for k in ("route", "kind", "step", "old", "new", "rule")},
                     "score": _route(sv, e["route"])["score"]} for e in edits if e["route"] != "control"]
        flips = [s for s in suspects if s["score"] == f"{copies}/{copies}" and ctrl["score"] == f"0/{copies}"]
        t_["suspects"] = {"wave": sv["wave"], "control": ctrl["score"], "suspects": suspects}
        t_["culprit"] = flips[0] if len(flips) == 1 else None
        print(f"suspects {c}: control {ctrl['score']}, " + ", ".join(f"{s['route']} {s['score']}" for s in suspects),
              flush=True)
        stage("suspects")
        if not t_["culprit"] or t_["culprit"]["kind"] != "spec_line" or not fx.rewrites.get(t_["culprit"]["old"]):
            continue  # a harness culprit, no unique culprit, or no rewrites: no swarm

        # SWARM: rewrites of the culprit line x copies, from the same checkpoint
        old = t_["culprit"]["old"]
        heldout = [h for h, m in meta.items() if m["heldout"] and m.get("file") == meta[c].get("file")]
        ctrl_green = {k for k in run["final_checks"] if all(cp["checks"].get(k) for cp in sv["copies"]
                                                             if cp["route"] == "control" and cp["ok"])}
        rws = [{"route": f"rw{i + 1}", "kind": "spec_line", "step": t_["culprit"]["step"], "old": old, "new": new,
                "hypothesis": "rewrite of the culprit line"} for i, new in enumerate(fx.rewrites[old])]
        ww = run_wave(store, fork, rws, copies * len(rws), wave=f"swarm-{c}", to_step=steps, run_dir=run_dir, log=log,
                      targets=[c], purpose="swarm", check=c, kit=kit)
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
        sw = {"check": c, "culprit": t_["culprit"], "fork_checkpoint_id": fork, "wave": ww["wave"],
              "heldout_checks": heldout, "n_branches": ww["n"], "n_rewrites": len(rws),
              "rewrites": rewrites, "winners": [r["route"] for r in winners], "confirm": None}
        t_["swarm"] = {"branches": ww["n"], "rewrites": len(rws), "winners": len(winners)}
        print(f"swarm {c}: winners {[r['text'] for r in winners]}", flush=True)
        stage("swarm")

        # CONFIRM: one fresh build from step 0 with the winning fix (shortest winner: the plan prefers removal)
        if winners:
            win = min(winners, key=lambda r: (len(r["text"]), r["route"]))
            edit = next(e for e in rws if e["route"] == win["route"])
            cv = run_wave(store, ckpt["0"], [{**edit, "route": f"confirm-{win['route']}"}], 1, wave=f"confirm-{c}",
                          to_step=steps, run_dir=run_dir, log=log, targets=[c, *heldout], purpose="confirm", check=c,
                          kit=kit)
            cp = cv["copies"][0]
            regress = sorted(k for k in ctrl_green if k != c and cp["ok"] and not cp["checks"].get(k))
            sw["confirm"] = {"wave": cv["wave"], "route": win["route"], "text": win["text"], "ok": cp["ok"],
                             "passed": bool(cp.get("passed")) and not regress, "regressions": regress,
                             "checks": cp.get("checks"), "error": cp.get("error")}
            t_["confirm"] = {"passed": sw["confirm"]["passed"], "text": win["text"]}
            print(f"confirm {c}: {'passes' if sw['confirm']['passed'] else 'FAILS'} with {win['text']!r}", flush=True)
            stage("confirm")
        swarm.append(sw)

    for t_ in triage:
        t_["card"] = card(t_)
    _write_json(run_dir / "triage.json", {"run_id": run_dir.name, "checks": triage})
    _write_json(run_dir / "swarm.json", {"run_id": run_dir.name, "swarms": swarm})
    results = json.loads((run_dir / "results.json").read_text()) if (run_dir / "results.json").exists() else {}
    stages["total"] = round(time.perf_counter() - t_start, 3)
    log.set_spent(spent(json.loads((run_dir / "run.json").read_text()), results), stages)
    print(f"pipeline done in {stages['total']:.1f}s -> {run_dir}", flush=True)
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
        sus = t.get("suspects")
        return (f"{t['check']}: real problem, no single suspect flipped it"
                + (f" (control {sus['control']})." if sus else "."))
    cause = f"spec step {cul['step']}, \"{cul['old']}\"" if cul["kind"] == "spec_line" else f"rule {cul['rule']}"
    s = (f"Cause: {cause}. Surfaced at step {t['surfaced_step']}, origin step {t['origin_step']}. "
         f"Suspect test: {cul['score']} vs control {t['suspects']['control']}.")
    if t.get("swarm"):
        sw = t["swarm"]
        s += f" Swarm: {sw['branches']} branches tried {sw['rewrites']} rewrites, {sw['winners']} pass 3/3 + held-out."
    if t.get("confirm"):
        s += (" Confirmed: a fresh build from step 0 with it passes." if t["confirm"]["passed"]
              else " CONFIRM failed: a fresh build from step 0 with it does not pass.")
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
    ap.add_argument("--builder", choices=["stub", "real"], default="stub",
                    help="stub = orchestrator/stub_builder/builder; real = brendan's builder/ at the repo root")
    ap.add_argument("--fixture", choices=["stub", "toy"], default="stub")
    ap.add_argument("--smoke", action="store_true", help="build + triage (or one 3-copy rebuild) only")
    ap.add_argument("--max-builders", type=int, default=None,
                    help="builder processes at once across all waves (default 8 for real, 64 for stub)")
    a = ap.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "runs" / f"{stamp}-{a.fixture}-{a.builder}{'-local' if a.local else ''}"
    _load_env()
    env = {}
    if a.builder == "real":
        env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]  # exec env only; never written anywhere
        if os.environ.get("DRYRUN_MODEL"):
            env["DRYRUN_MODEL"] = os.environ["DRYRUN_MODEL"]
    kit = Kit(builder_src=REAL_BUILDER if a.builder == "real" else STUB_BUILDER, env=env,
              max_builders=a.max_builders or (8 if a.builder == "real" else 64),
              branch_max_calls=10 if a.builder == "real" else None)
    scratch = Path(tempfile.mkdtemp(prefix="dryrun-scratch-"))
    fx = load_fixture(a.fixture, scratch)
    client = None
    if a.local:
        store = LocalStore(Path(tempfile.mkdtemp(prefix="dryrun-")))
    else:
        import archil
        region = os.environ.get("ARCHIL_REGION", "aws-us-east-1")
        client = archil.Archil(api_key=os.environ["ARCHIL_API_KEY"], region=region)
        store = ArchilStore.new(client, region, f"dryrun-run-{stamp}")
    try:
        print(f"run dir: {run_dir}\ndisk: {store.disk_id}\nbuilder: {kit.builder_label}, fixture: {fx.name}, "
              f"max builders: {kit.max_builders}", flush=True)
        out = pipeline(store, run_dir, fixture=fx, kit=kit, copies=a.copies, smoke=a.smoke)
        for t_ in out["triage"]:
            print(" ", t_["card"])
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
