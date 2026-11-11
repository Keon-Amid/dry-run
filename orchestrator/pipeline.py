"""One entry point: build -> grade -> triage -> locate -> suspects -> swarm -> confirm, per CONTRACT.md.

    .venv/bin/python -m orchestrator.pipeline [--local] [--builder stub|real] [--fixture stub|toy] [--smoke]
                                              [--copies 3] [--max-builders N]

Writes orchestrator/runs/<stamp>/: run.json, triage.json, results.json (every wave), swarm.json, archil.json,
baseline.json (one plain Claude call fixes the spec; 3 fresh builds of it) and report.md (before/after/baseline).
--fixture stub: the stub spec/checks/golden/rules/rewrites in orchestrator/ (all three verdicts planted).
--fixture demo2: brendan's visual demo (demo2/, Dungeon Painter SVG; side-by-side via demo2/render.py).
--fixture toy:  brendan's builder/tests/fixtures/toy (spec, rules, canary checks via orchestrator/assert_checks.py).
--smoke: build + triage only (or, if nothing fails, one 3-copy rebuild of the last step), to exercise the real builder.
--builder real: ANTHROPIC_API_KEY (and DRYRUN_MODEL if set) go to each builder process through the exec env only.
On Archil every sandbox is deleted (inside build and run_wave); the disk, checkpoints and branches stay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.archil_log import ArchilLog, spent, usage_usd
from orchestrator.baseline import StubFixer, UsageRecorder, fix_spec
from orchestrator.assert_checks import build_checks_file
from orchestrator.stores import ArchilStore, LocalStore
from orchestrator.wave import HERE, REAL_BUILDER, STUB_BUILDER, STUB_CHECKS, Kit, _write_json, build, run_wave

ROOT = HERE.parent
N_COPIES = 3  # per hypothesis: verdicts are counts (3/3 vs 0/3), never one run
TOY = ROOT / "builder" / "tests" / "fixtures" / "toy"
DEMO = ROOT / "demo"

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
    rewrites: dict = field(default_factory=dict)   # culprit line -> rewrites; used when rewriter == "table"
    rewriter: str = "table"                        # "table" (hand-written, stubs) | "generator" (builder/rewrite.py)
    suspects: list | None = None                   # fixed suspect edits; None = mechanical (spec lines + every rule)
    natural: int = 0                               # fresh builds of the original spec from c0 ("before" arm)

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
    if name == "demo":  # P2's Shortlink: spec + rules from demo/disk, checks bundled from demo/grade.py
        scratch.mkdir(parents=True, exist_ok=True)
        bundle = scratch / "demo_checks.py"
        subprocess.run([sys.executable, str(DEMO / "grade.py"), "--bundle", str(bundle)], check=True,
                       capture_output=True)
        plants = json.loads((DEMO / "plants.json").read_text())
        suspects = []
        for p in plants:  # the kept plants' edits are the suspects (CONTRACT.md 8f8b1a4: contradiction dropped)
            e = {k: v for k, v in p["patch"].items() if v is not None}
            e["route"] = f"spec-step{e['step']}" if e["kind"] == "spec_line" else f"rule-{Path(e['rule']).stem}"
            suspects.append(e)
        return Fixture("demo", (DEMO / "disk" / "spec.md").read_text(),
                       {p.name: p.read_text() for p in sorted((DEMO / "disk" / "rules").glob("*.md"))}, bundle,
                       golden=DEMO / "golden", rewriter="generator", suspects=suspects, natural=3)
    if name == "demo2":
        return demo2_fixture(scratch)
    raise SystemExit(f"unknown fixture {name}")


DEMO2 = ROOT / "demo2"


def demo2_fixture(scratch: Path) -> Fixture:
    """brendan's visual demo (Dungeon Painter, SVG), wired like the Shortlink `demo` fixture: suspects are the
    plants' own edits (ambiguity, contradiction, bad rule, plus the placebo that must not flip), rewrites come live
    from builder/rewrite.py, and 3 natural builds give the "before" arm. Side by side: demo2/render.py."""
    scratch.mkdir(parents=True, exist_ok=True)
    bundle = scratch / "demo2_checks.py"
    subprocess.run([sys.executable, str(DEMO2 / "grade.py"), "--bundle", str(bundle)], check=True,
                   capture_output=True)
    suspects = []
    for p in json.loads((DEMO2 / "plants.json").read_text()):
        if p["patch"]["kind"] == "control":
            continue   # the pipeline adds its own control branch
        e = {k: v for k, v in p["patch"].items() if v is not None}
        e["route"] = f"spec-step{e['step']}" if e["kind"] == "spec_line" else f"rule-{Path(e['rule']).stem}"
        suspects.append(e)
    return Fixture("demo2", (DEMO2 / "disk" / "spec.md").read_text(),
                   {p.name: p.read_text() for p in sorted((DEMO2 / "disk" / "rules").glob("*.md"))}, bundle,
                   golden=DEMO2 / "golden", rewriter="generator", suspects=suspects, natural=3)


def spec_line(spec: str, k: int) -> str:
    return re.search(rf"^## Step {k}\b.*?\n(.*?)(?=^## Step |\Z)", spec, re.S | re.M).group(1).strip()


def local_checks(checks_src: Path, *args: str) -> dict:
    out = subprocess.run([sys.executable, str(checks_src), *args], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _route(wave: dict, route: str) -> dict:
    return next(r for r in wave["routes"] if r["route"] == route)


def _score(cps: list[dict], c: str, heldout: list[str], ctrl_green) -> dict:
    """Visible and held-out pass counts for a set of copies, and checks that were green in every control copy
    but went red here."""
    ok = [cp for cp in cps if cp["ok"]]
    visible = sum(cp["checks"].get(c, False) for cp in ok)
    held = sum(all(cp["checks"].get(h, False) for h in heldout) for cp in ok)
    regress = sorted({k for cp in ok for k in ctrl_green if k != c and not cp["checks"].get(k)})
    return {"visible": f"{visible}/{len(cps)}", "heldout": f"{held}/{len(cps)}", "regressions": regress,
            "errors": len(cps) - len(ok), "_all": len(ok) == len(cps) and visible == held == len(cps) and not regress}


def _verdict(fails: int, runs: int, errors: int) -> str:
    if errors or runs == 0:
        return "inconclusive"
    return {0: "model_slip", runs: "real_problem"}.get(fails, "inconclusive")


def _usd(model, usage, fixer):
    if isinstance(fixer, StubFixer):
        return 0.0
    try:
        return round(usage_usd(model, usage), 6)
    except KeyError:
        return "unknown"


def pipeline(store, run_dir: Path, *, fixture: Fixture | None = None, kit: Kit | None = None,
             copies: int = N_COPIES, smoke: bool = False, baseline: bool = True, fixer=None) -> dict:
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
    run = build(store, fx.spec, fx.rules, steps, run_dir, slip_step=fx.slip_step, kit=kit,
                export_dir=run_dir / "workspaces" / "build")
    stage("build")
    ckpt = run["checkpoints"]
    log = ArchilLog(run_dir / "run.json", run_dir / "archil.json", ROOT / "spikes" / "disk_spike.json")
    meta = local_checks(fx.checks_src, "--meta")
    golden = local_checks(fx.checks_src, "--disk", str(fx.golden), "--at-step", str(steps)) if fx.golden else {}
    failing = [c for c, ok in run["final_checks"].items() if not ok and not meta[c]["heldout"]]
    messages = run.get("final_messages") or {}
    msg_of = lambda c: messages.get(c) or meta[c].get("message", "")
    heldout_of = lambda c: [h for h, m in meta.items() if m["heldout"] and m.get("file") == meta[c].get("file")]
    print(f"build: {steps} steps, failing {failing}", flush=True)
    recorder = None
    if kit.builder_label != "stub" and (fx.rewriter == "generator" or baseline):
        from builder.llm import AnthropicLLM
        recorder = UsageRecorder(AnthropicLLM(model=run["model"]))  # same model as the builder

    # NATURAL: the original spec built from step 0 n times, "what Claude builds naturally"
    if fx.natural:
        run_wave(store, ckpt["0"], [{"route": "natural", "kind": "none"}], fx.natural, wave="natural", to_step=steps,
                 run_dir=run_dir, log=log, targets=[], purpose="natural", kit=kit)
        stage("natural")

    # TRIAGE each failing check, LOCATE the real ones
    triage = []
    for c in failing:
        surfaced = next(s["step"] for s in run["steps"] if s["checks"].get(c) is False)
        f = meta[c].get("file")
        origin = next((s["step"] for s in run["steps"] if f and f in s["wrote"]), surfaced) \
            if f != "conversation.jsonl" else surfaced
        t_ = {"check": c, "surfaced_step": surfaced, "origin_step": origin, "heldout_checks": heldout_of(c),
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
        if fx.suspects is not None:
            edits = [dict(e) for e in fx.suspects]
        else:
            edits = [{"route": f"spec-step{k}", "kind": "spec_line", "step": k, "old": spec_line(fx.spec, k),
                      "new": fx.disambiguate.get(spec_line(fx.spec, k), ""), "hypothesis": f"spec step {k} is the cause"}
                     for k in ks]
            edits += [{"route": f"rule-{Path(r).stem}", "kind": "rule_off", "rule": r,
                       "hypothesis": f"rule {r} is the cause"} for r in fx.rules]
        anchor = next((e for e in edits if e["kind"] == "spec_line"), None)
        cstep, cold = (anchor["step"], anchor["old"]) if anchor else (ks[0], spec_line(fx.spec, ks[0]))
        edits.append({"route": "control", "kind": "control", "step": cstep, "old": cold, "hypothesis": "no change"})
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
        t_["control_green"] = sorted(k for k in run["final_checks"] if all(
            cp["checks"].get(k) for cp in sv["copies"] if cp["route"] == "control" and cp["ok"]))
        if not t_["culprit"] or t_["culprit"]["kind"] != "spec_line":
            continue  # a harness culprit or no unique culprit: no swarm
        old = t_["culprit"]["old"]
        if fx.rewriter == "generator" and recorder:
            from builder.rewrite import generate
            g = generate(recorder, old, spec_line(fx.spec, t_["culprit"]["step"]), c, msg_of(c),
                         out=str(run_dir / f"rewrites-{c}.json"))
            texts = [r["text"] for r in g["rewrites"]]
        else:
            texts = fx.rewrites.get(old, [])
        if not texts:
            continue

        # SWARM: rewrites of the culprit line x copies, from the same checkpoint
        heldout = heldout_of(c)
        ctrl_green = {k for k in run["final_checks"] if all(cp["checks"].get(k) for cp in sv["copies"]
                                                             if cp["route"] == "control" and cp["ok"])}
        rws = [{"route": f"rw{i + 1}", "kind": "spec_line", "step": t_["culprit"]["step"], "old": old, "new": new,
                "hypothesis": "rewrite of the culprit line"} for i, new in enumerate(texts)]
        ww = run_wave(store, fork, rws, copies * len(rws), wave=f"swarm-{c}", to_step=steps, run_dir=run_dir, log=log,
                      targets=[c], purpose="swarm", check=c, kit=kit)
        rewrites = []
        for e in rws:
            sc = _score([cp for cp in ww["copies"] if cp["route"] == e["route"]], c, heldout, ctrl_green)
            rewrites.append({"route": e["route"], "text": e["new"], **{k: v for k, v in sc.items() if k != "_all"},
                             "winner": sc["_all"]})
        winners = [r for r in rewrites if r["winner"]]
        sw = {"check": c, "culprit": t_["culprit"], "fork_checkpoint_id": fork, "wave": ww["wave"],
              "heldout_checks": heldout, "n_branches": ww["n"], "n_rewrites": len(rws),
              "rewrites": rewrites, "winners": [r["route"] for r in winners], "confirm": None,
              "control_green": sorted(ctrl_green)}
        t_["swarm"] = {"branches": ww["n"], "rewrites": len(rws), "winners": len(winners)}
        print(f"swarm {c}: winners {[r['text'] for r in winners]}", flush=True)
        stage("swarm")

        # CONFIRM: one fresh build from step 0 with the winning fix (shortest winner: the plan prefers removal)
        if winners:
            win = min(winners, key=lambda r: (len(r["text"]), r["route"]))
            edit = next(e for e in rws if e["route"] == win["route"])
            cv = run_wave(store, ckpt["0"], [{**edit, "route": f"confirm-{win['route']}"}], 1, wave=f"confirm-{c}",
                          to_step=steps, run_dir=run_dir, log=log, targets=[c, *heldout], purpose="confirm", check=c,
                          kit=kit, export_dir=run_dir / "workspaces" / f"confirm-{c}")
            cp = cv["copies"][0]
            regress = sorted(k for k in ctrl_green if k != c and cp["ok"] and not cp["checks"].get(k))
            sw["confirm"] = {"wave": cv["wave"], "route": win["route"], "text": win["text"], "ok": cp["ok"],
                             "passed": bool(cp.get("passed")) and not regress, "regressions": regress,
                             "checks": cp.get("checks"), "error": cp.get("error")}
            t_["confirm"] = {"passed": sw["confirm"]["passed"], "text": win["text"]}
            print(f"confirm {c}: {'passes' if sw['confirm']['passed'] else 'FAILS'} with {win['text']!r}", flush=True)
            stage("confirm")
        swarm.append(sw)

    # BASELINE: one plain Claude call fixes the whole spec from the failing check alone; 3 fresh builds of it
    baselines = []
    real = [x for x in triage if x["verdict"] == "real_problem" and x.get("suspects")]
    if baseline and real:
        if fixer is None:
            fixer = StubFixer() if kit.builder_label == "stub" else recorder
        for t_ in real:
            c, heldout = t_["check"], heldout_of(t_["check"])
            out = fix_spec(fixer, fx.spec, c, msg_of(c))
            b = {"check": c, "fixer": out["model"], "message": msg_of(c), "call": {
                "model_calls": 0 if isinstance(fixer, StubFixer) else 1, "usage": out["usage"], "wall_s": out["wall_s"],
                "stop_reason": out["stop_reason"], "usd": _usd(out["model"], out["usage"], fixer)},
                 "diff": out.get("diff"), "fixed_spec": out["fixed_spec"], "error": out.get("error"),
                 "prompt": out["prompt"], "reply": out["reply"]}
            if out["fixed_spec"]:
                bv = run_wave(store, ckpt["0"], [{"route": "baseline", "kind": "spec_replace", "spec": out["fixed_spec"]}],
                              copies, wave=f"baseline-{c}", to_step=steps, run_dir=run_dir, log=log,
                              targets=[c, *heldout], purpose="baseline", check=c, kit=kit,
                              export_dir=run_dir / "workspaces" / f"baseline-{c}")
                sc = _score(bv["copies"], c, heldout, set(t_.get("control_green", [])))
                b.update(wave=bv["wave"], n_builds=len(bv["copies"]), **{k: v for k, v in sc.items() if k != "_all"},
                         passes_all=sc["_all"])
            baselines.append(b)
            print(f"baseline {c}: visible {b.get('visible')}, held-out {b.get('heldout')} ({b['fixer']})", flush=True)
        stage("baseline")
    _write_json(run_dir / "baseline.json", {"run_id": run_dir.name, "baselines": baselines})

    for t_ in triage:
        t_["card"] = card(t_)
    _write_json(run_dir / "triage.json", {"run_id": run_dir.name, "checks": triage})
    _write_json(run_dir / "swarm.json", {"run_id": run_dir.name, "swarms": swarm})
    results = json.loads((run_dir / "results.json").read_text()) if (run_dir / "results.json").exists() else {}
    stages["total"] = round(time.perf_counter() - t_start, 3)
    sp = spent(json.loads((run_dir / "run.json").read_text()), results)
    if recorder:  # orchestrator-side calls: rewrite generator + baseline (all through the recorder)
        usd = [_usd(x["model"], x["usage"], None) for x in recorder.calls]
        sp["orchestrator_calls"] = {"model_calls": len(recorder.calls),
                                    "usd": "unknown" if "unknown" in usd else round(sum(usd), 4)}
        if recorder.calls:
            sp["total"] = {k: ("unknown" if "unknown" in (sp["total"][k], sp["orchestrator_calls"][k])
                               else round(sp["total"][k] + sp["orchestrator_calls"][k], 4)) for k in sp["total"]}
    elif baselines:
        calls = sum(b["call"]["model_calls"] for b in baselines)
        usd = [b["call"]["usd"] for b in baselines]
        sp["baseline_calls"] = {"model_calls": calls, "usd": "unknown" if "unknown" in usd else round(sum(usd), 4)}
        if calls:
            sp["total"] = {k: ("unknown" if "unknown" in (sp["total"][k], sp["baseline_calls"][k])
                               else round(sp["total"][k] + sp["baseline_calls"][k], 4)) for k in sp["total"]}
    log.set_spent(sp, stages)
    finish(run_dir, fx.spec, fx.rules)
    print(f"pipeline done in {stages['total']:.1f}s -> {run_dir}", flush=True)
    return {"triage": triage, "swarm": swarm}


def finish(run_dir: Path, spec: str, rules: dict) -> Path:
    """The files after the waves: spec.original.md, spec.fixed.md, specs.json, before_after.json, report.md/json."""
    _write_json(run_dir / "specs.json", write_specs(run_dir, spec, rules))
    write_before_after(run_dir)
    return write_report(run_dir)


def write_report(run_dir: Path) -> Path:
    """report.md: verdicts, then before / after / baseline pass rates side by side, read back from the run files."""
    load = lambda n: json.loads((run_dir / f"{n}.json").read_text()) if (run_dir / f"{n}.json").exists() else {}
    run, results, tri, sw_doc, bl_doc, arch = (load(n) for n in ("run", "results", "triage", "swarm", "baseline",
                                                                  "archil"))
    waves = results.get("waves", [])
    spent_w = (arch.get("spent") or {}).get("waves", {})
    cost = lambda wave: (lambda x: f"{x.get('model_calls')} calls, ${x.get('usd')}")(spent_w.get(wave, {}))
    swarms = {sw["check"]: sw for sw in sw_doc.get("swarms", [])}
    baselines = {b["check"]: b for b in bl_doc.get("baselines", [])}
    natural = next((w for w in waves if w["purpose"] == "natural"), None)
    final = run.get("final_checks", {})
    lines = [f"# Banzai report: {run.get('run_id')}", "",
             f"Builder: {run.get('builder')} · model: {run.get('model')} · disk: `{run.get('disk_id')}`. "
             "Every number below is read from this folder's run files.", "",
             "## Verdicts", "", "| Failing check | Verdict | Surfaced / origin step | Card |", "|---|---|---|---|"]
    for t in tri.get("checks", []):
        lines.append(f"| `{t['check']}` | {t['verdict']} | {t['surfaced_step']} / {t['origin_step']} | "
                     f"{t.get('card', '').replace('|', '/')} |")
    lines.append("")
    rj = {"run_id": run.get("run_id"), "model": run.get("model"), "builder": run.get("builder"),
          "disk_id": run.get("disk_id"), "verdicts": [{k: t.get(k) for k in ("check", "verdict", "surfaced_step",
                                                                          "origin_step", "card")}
                                                      for t in tri.get("checks", [])],
          "checks": {}, "winning_rewrites": [], "archil_totals": arch.get("totals_saved"), "spent": arch.get("spent"),
          "stages_s": arch.get("stages_s"), "source": "built from run.json, results.json, triage.json, swarm.json, "
                                                      "baseline.json and archil.json in this folder"}

    def frac(cps, name, held):
        sc = _score(cps, name, held, set())
        return sc["visible"], sc["heldout"]

    for t in tri.get("checks", []):
        if t["verdict"] != "real_problem":
            continue
        c = t["check"]
        held = t.get("heldout_checks") or []
        rows = [("Before: the checkpointed build", f"{int(bool(final.get(c)))}/1",
                 f"{int(all(final.get(h, False) for h in held))}/1" if held else "n/a", "build")]
        if natural:
            v, h = frac(natural["copies"], c, held)
            rows.append((f"Before: original spec, {natural['n']} fresh builds from step 0", v, h if held else "n/a",
                         cost(natural["wave"])))
        sus = next((w for w in waves if w["purpose"] == "suspects" and w["check"] == c), None)
        if sus:
            v, h = frac([cp for cp in sus["copies"] if cp["route"] == "control"], c, held)
            rows.append(("Before: control branches (no change)", v, h if held else "n/a", cost(sus["wave"])))
            cul = t.get("culprit")
            if cul:
                v, h = frac([cp for cp in sus["copies"] if cp["route"] == cul["route"]], c, held)
                what = f"rule {cul['rule']} off" if cul["kind"] == "rule_off" else f"step {cul['step']} edit"
                rows.append((f"After: the culprit's suspect edit ({what})", v, h if held else "n/a", cost(sus["wave"])))
        sw = swarms.get(c)
        if sw:
            best = [r for r in sw["rewrites"] if r["winner"]] or sorted(sw["rewrites"], key=lambda r: r["visible"])[-1:]
            for r in best:
                rows.append((f"After: swarm {r['route']} \"{r['text']}\"" + ("" if r["winner"] else " (best, not a winner)"),
                             r["visible"], r["heldout"], cost(sw["wave"])))
            if sw.get("confirm"):
                cf = sw["confirm"]
                v = cf.get("checks") or {}
                rows.append((f"After: CONFIRM, fresh build from step 0 with {cf['route']}", f"{int(bool(v.get(c)))}/1",
                             f"{int(all(v.get(h, False) for h in held))}/1", cost(cf["wave"])))
        b = baselines.get(c)
        if b:
            label = f"Baseline: one {b['fixer']} call rewrites the spec, built from step 0"
            if b.get("wave"):
                rows.append((label, b["visible"], b["heldout"] if held else "n/a",
                             f"{cost(b['wave'])} + fix call ${b['call']['usd']}"))
            else:
                rows.append((label + f" (no usable spec: {b.get('error')})", "n/a", "n/a", f"${b['call']['usd']}"))
        keys = ["before_build", "before_natural", "before_control", "after_culprit_edit", "after_swarm",
                "after_confirm", "baseline"]
        rj["checks"][c] = {"heldout_checks": held, "arms": [
            {"arm": next((k for k in keys if _arm_key(a_) == k), _arm_key(a_)), "label": a_, "visible": v_,
             "heldout": h_, "cost": k_} for a_, v_, h_, k_ in rows]}
        if sw and sw.get("confirm"):
            win = next(r for r in sw["rewrites"] if r["route"] == sw["confirm"]["route"])
            rj["winning_rewrites"].append({"check": c, "culprit": sw["culprit"].get("old"), "route": win["route"],
                                           "text": win["text"], "visible": win["visible"], "heldout": win["heldout"],
                                           "confirm_passed": sw["confirm"]["passed"],
                                           "all_winners": sw["winners"]})
        lines += [f"## `{c}`", "", f"Held-out checks: {', '.join(f'`{h}`' for h in held) or 'none'}.", "",
                  "| Arm | Visible check | Held-out | Cost |", "|---|---|---|---|"]
        lines += [f"| {a_} | {v_} | {h_} | {k_} |" for a_, v_, h_, k_ in rows]
        if sw:
            lines += ["", "All swarm rewrites (losers included):", "", "| Rewrite | Visible | Held-out | Regressions | Winner |",
                      "|---|---|---|---|---|"]
            lines += [f"| {r['route']} \"{r['text']}\" | {r['visible']} | {r['heldout']} | "
                      f"{', '.join(r['regressions']) or '-'} | {'yes' if r['winner'] else 'no'} |" for r in sw["rewrites"]]
        if b and b.get("diff"):
            lines += ["", "<details><summary>Baseline's spec change</summary>", "", "```diff", b["diff"].rstrip(),
                      "```", "</details>"]
        lines.append("")
    sp, st, tot = arch.get("spent") or {}, arch.get("stages_s") or {}, arch.get("totals_saved") or {}
    lines += ["## Cost and Archil", "",
              f"- Spent: {sp.get('total', {}).get('model_calls')} model calls, ${sp.get('total', {}).get('usd')} "
              f"(build {sp.get('build')}; orchestrator calls {sp.get('orchestrator_calls')}).",
              f"- Wall: {st.get('total')} s; stages {st}.",
              f"- Branching saved (archil.json totals): {tot}.", ""]
    specs = load("specs")  # written by write_specs via finish(): spec_files + culprits
    if specs:
        rj["spec_files"] = specs.get("spec_files")
        rj["culprits"] = specs.get("culprits")
        rj["culprit_lines"] = [c["line"] for c in specs.get("culprits", []) if c["kind"] == "spec_line"]
    if (run_dir / "before_after.json").exists():
        rj["before_after"] = "before_after.json"
    out = run_dir / "report.md"
    out.write_text("\n".join(lines))
    _write_json(run_dir / "report.json", rj)  # the same numbers for Keon's page (final screen)
    return out


def _replace_in_step(spec: str, step: int, old: str, new: str) -> str:
    m = re.search(rf"^## Step {step}\b.*?(?=^## Step |\Z)", spec, re.S | re.M)
    section = m.group(0)
    assert section.count(old) == 1, f"culprit line not found once in step {step}"
    return spec[:m.start()] + section.replace(old, new) + spec[m.end():]


def write_specs(run_dir: Path, spec: str, rules: dict) -> dict:
    """spec.original.md (the spec as built + the harness rules it ran with) and spec.fixed.md (each CONFIRMed
    winning rewrite applied in its step, each culprit rule marked switched off). From triage.json + swarm.json."""
    load = lambda n: json.loads((run_dir / f"{n}.json").read_text()) if (run_dir / f"{n}.json").exists() else {}
    tri, sw_doc = load("triage"), load("swarm")
    swarms = {sw["check"]: sw for sw in sw_doc.get("swarms", [])}
    fixed, off, culprits = spec, {}, []
    for t in tri.get("checks", []):
        cul = t.get("culprit")
        if t["verdict"] != "real_problem" or not cul:
            continue
        sus = t.get("suspects", {})
        if cul["kind"] == "rule_off":
            off[cul["rule"]] = f"{t['check']}: {cul['score']} with it off vs control {sus.get('control')}"
            culprits.append({"check": t["check"], "kind": "rule", "rule": cul["rule"],
                             "rule_text": rules.get(cul["rule"], "").strip(), "fix": "switch the rule off"})
            continue
        sw = swarms.get(t["check"]) or {}
        win = (sw.get("confirm") or {}) if (sw.get("confirm") or {}).get("passed") else {}
        culprits.append({"check": t["check"], "kind": "spec_line", "step": cul["step"], "line": cul["old"],
                         "fix": win.get("text"), "fix_route": win.get("route")})
        if win:
            fixed = _replace_in_step(fixed, cul["step"], cul["old"], win["text"])

    def rules_md(mark: bool) -> str:
        out = ["", "## Harness rules (rules/, read by the builder every turn; not part of spec.md)", ""]
        for name, text in sorted(rules.items()):
            if mark and name in off:
                out += [f"### ~~{name}~~ SWITCHED OFF (culprit, {off[name]})", "", f"~~{text.strip()}~~", ""]
            else:
                out += [f"### {name}", "", text.strip(), ""]
        return "\n".join(out)

    (run_dir / "spec.original.md").write_text(spec.rstrip() + "\n" + rules_md(False))
    (run_dir / "spec.fixed.md").write_text(fixed.rstrip() + "\n" + rules_md(True))
    return {"spec_files": {"original": "spec.original.md", "fixed": "spec.fixed.md"}, "culprits": culprits}


def write_before_after(run_dir: Path) -> str | None:
    if not (run_dir / "workspaces").is_dir():
        return None
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "before_after.py"), str(run_dir), "--json",
                        str(run_dir / "before_after.json")], capture_output=True, text=True)
    return "before_after.json" if r.returncode == 0 else None


def _arm_key(label: str) -> str:
    for prefix, key in (("Before: the checkpointed", "before_build"), ("Before: original spec", "before_natural"),
                        ("Before: control", "before_control"), ("After: the culprit", "after_culprit_edit"),
                        ("After: swarm", "after_swarm"), ("After: CONFIRM", "after_confirm"),
                        ("Baseline", "baseline")):
        if label.startswith(prefix):
            return key
    return label


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
    if not (ROOT / ".env").exists():   # keys may come from the environment instead
        return
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
    ap.add_argument("--fixture", choices=["stub", "toy", "demo", "demo2"], default="stub")
    ap.add_argument("--model", help="DRYRUN_MODEL for the builder (the rewrite and baseline calls use the same)")
    ap.add_argument("--smoke", action="store_true", help="build + triage (or one 3-copy rebuild) only")
    ap.add_argument("--no-baseline", action="store_true", help="skip the one-call baseline arm")
    ap.add_argument("--max-builders", type=int, default=None,
                    help="builder processes at once across all waves (default 8 for real, 64 for stub)")
    ap.add_argument("--report", metavar="RUN_DIR", help="only regenerate report.md + report.json from a run folder")
    a = ap.parse_args()
    if a.report:  # regenerate the after-wave files of an existing run, with the fixture it was run with
        rd = Path(a.report)
        fx = load_fixture(a.fixture, Path(tempfile.mkdtemp(prefix="dryrun-scratch-")))
        shas = {(c.get("builder") or {}).get("spec_sha_before") for w in json.loads(
            (rd / "results.json").read_text())["waves"] if w["purpose"] in ("suspects", "swarm")
            for c in w["copies"]} - {None}
        mine = hashlib.sha256(fx.spec.encode()).hexdigest()
        if shas and shas != {mine}:
            raise SystemExit(f"--fixture {a.fixture} spec sha {mine[:12]} != the run's spec_sha_before {shas}")
        print(f"spec verified against the run's spec_sha_before: {bool(shas)}")
        print(finish(rd, fx.spec, fx.rules))
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "runs" / f"{stamp}-{a.fixture}-{a.builder}{'-local' if a.local else ''}"
    _load_env()
    env = {}
    if a.builder == "real":
        env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]  # exec env only; never written anywhere
        if a.model or os.environ.get("DRYRUN_MODEL"):
            env["DRYRUN_MODEL"] = a.model or os.environ["DRYRUN_MODEL"]
    kit = Kit(builder_src=REAL_BUILDER if a.builder == "real" else STUB_BUILDER, env=env,
              max_builders=a.max_builders or (8 if a.builder == "real" else 64),
              branch_max_calls=10 if a.builder == "real" and a.fixture == "toy" else None)
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
        out = pipeline(store, run_dir, fixture=fx, kit=kit, copies=a.copies, smoke=a.smoke,
                       baseline=not a.no_baseline)
        for t_ in out["triage"]:
            print(" ", t_["card"])
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
