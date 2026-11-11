"""Two extra commands on a finished demo run (real builder, the run's own Archil disk and checkpoints).

  python -m orchestrator.live both RUN_DIR   combined CONFIRM: fresh build from c0 with spec.fixed.md's changes
                                             (CONFIRMed rewrite applied AND every culprit rule off), all checks
  python -m orchestrator.live wave RUN_DIR   judges' table: 3 copies branched from c3, the winning rewrite on step 4,
                                             rebuild step 4, grade; prints branch / sandbox / mount / copy times
Model: the run's model (run.json). Keys from .env / the environment; ANTHROPIC_API_KEY goes to the builder's exec env.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

from orchestrator.archil_log import ArchilLog, spent
from orchestrator.pipeline import ROOT, _load_env, _replace_in_step, load_fixture, write_report
from orchestrator.stores import ArchilStore
from orchestrator.wave import REAL_BUILDER, Kit, _write_json, run_wave


def _setup(run_dir: Path):
    import archil
    _load_env()
    run = json.loads((run_dir / "run.json").read_text())
    region = os.environ.get("ARCHIL_REGION", "aws-us-east-1")
    client = archil.Archil(api_key=os.environ["ARCHIL_API_KEY"], region=region)
    store = ArchilStore.attach(client, region, run["disk_id"])
    fx = load_fixture("demo", Path(tempfile.mkdtemp(prefix="dryrun-scratch-")))
    kit = Kit(builder_src=REAL_BUILDER, checks_src=fx.checks_src, max_builders=8,
              env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"], "DRYRUN_MODEL": run["model"]})
    return client, store, fx, kit, run


def both(run_dir: Path) -> None:
    client, store, fx, kit, run = _setup(run_dir)
    try:
        specs = json.loads((run_dir / "specs.json").read_text())
        fixed, off = fx.spec, []
        for c in specs["culprits"]:
            if c["kind"] == "spec_line" and c.get("fix") is not None:
                fixed = _replace_in_step(fixed, c["step"], c["line"], c["fix"])
            elif c["kind"] == "rule":
                off.append(c["rule"])
        arch = json.loads((run_dir / "archil.json").read_text())
        log = ArchilLog(run_dir / "run.json", run_dir / "archil.json", ROOT / "spikes" / "disk_spike.json")
        log.waves, log.spent, log.stages_s = arch["waves"], arch.get("spent"), arch.get("stages_s") or {}
        t0 = time.perf_counter()
        w = run_wave(store, run["checkpoints"]["0"], [{"route": "both-fixes", "kind": "spec_replace", "spec": fixed,
                                                       "rules_off": off}], 1, wave="confirm-both", to_step=fx.steps,
                     run_dir=run_dir, log=log, targets=[], purpose="confirm_both", kit=kit)
        cp = w["copies"][0]
        print(f"confirm-both: {time.perf_counter() - t0:.1f}s ok={cp['ok']} checks={cp.get('checks')} {cp.get('error') or ''}")
        sp = spent(run, json.loads((run_dir / "results.json").read_text()))
        oc = (arch.get("spent") or {}).get("orchestrator_calls")
        if oc:
            sp["orchestrator_calls"] = oc
            sp["total"] = {k: round(sp["total"][k] + oc[k], 4) for k in sp["total"]}
        log.set_spent(sp, log.stages_s)
        print(write_report(run_dir))
    finally:
        client.close()


def wave(run_dir: Path, copies: int = 3) -> None:
    client, store, fx, kit, run = _setup(run_dir)
    try:
        sw = json.loads((run_dir / "swarm.json").read_text())["swarms"][0]
        win = next(r for r in sw["rewrites"] if r["route"] == sw["confirm"]["route"])
        step, c = sw["culprit"]["step"], sw["check"]
        out = ROOT / "orchestrator" / "runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-live"
        out.mkdir(parents=True)
        log = ArchilLog(None, out / "archil.json")
        print(f"branching {copies} copies of the agent's disk at step {step - 1} ({run['disk_id']}), "
              f"fix on step {step}: {win['text']!r}", flush=True)
        t0 = time.perf_counter()
        w = run_wave(store, run["checkpoints"][str(step - 1)],
                     [{"route": "live", "kind": "spec_line", "step": step, "old": sw["culprit"]["old"],
                       "new": win["text"], "hypothesis": "the winning rewrite"}], copies, wave="live", to_step=step,
                     run_dir=out, log=log, targets=[c], purpose="live", check=c, kit=kit)
        for cp in w["copies"]:
            t = cp["timings_ms"]
            print(f"  {cp['id']:<12} branch {t.get('branch', 0):6.0f} ms  sandbox {t.get('sandbox', 0):6.0f} ms  "
                  f"mount {t.get('mount', 0):6.0f} ms  copy {cp['wall_s']:5.1f} s  "
                  f"{c}: {'PASS' if cp.get('passed') else 'FAIL'}{'  ' + cp['error'] if cp.get('error') else ''}")
        r = w["routes"][0]
        print(f"wave: {w['wall_s']:.1f} s wall, {r['score']} pass, total {time.perf_counter() - t0:.1f} s -> {out}")
    finally:
        client.close()


if __name__ == "__main__":
    cmd, rd = sys.argv[1], Path(sys.argv[2])
    both(rd) if cmd == "both" else wave(rd)
