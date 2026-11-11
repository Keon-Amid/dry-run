"""Build the stub spec with a checkpoint per step, then run one swarm wave: 5 rewrites of step 3 x copies/5.

    .venv/bin/python -m orchestrator.run_demo [--local] [--copies 15]

Writes orchestrator/runs/<stamp>/{run.json, results.json, archil.json}. On Archil, every sandbox is deleted
(the copies inside run_wave, the build sandbox inside build); the disk and its checkpoints/branches stay.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from orchestrator.archil_log import ArchilLog
from orchestrator.stores import ArchilStore, LocalStore
from orchestrator.wave import HERE, build, run_wave

ROOT = HERE.parent
OLD = "Links expire after 30 days."
REWRITES = [  # STUB rewrites (hand-written) of the planted ambiguous line; the real ones come from the rewrite step
    ("rw1", "Links expire 30 days after their last click."),
    ("rw2", "Links expire 30 days after they are created."),
    ("rw3", "A link expires when 30 days pass without a click."),
    ("rw4", "Links expire after 30 days, counted from the last click."),
    ("rw5", "Links never expire."),
]
EDITS = [{"route": r, "kind": "spec_line", "step": 3, "old": OLD, "new": new,
          "hypothesis": "step 3's expiry rule is ambiguous"} for r, new in REWRITES]


def load_env() -> None:
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="plain folders instead of Archil")
    ap.add_argument("--copies", type=int, default=15)
    ap.add_argument("--steps", type=int, default=7)
    a = ap.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "runs" / f"{stamp}{'-local' if a.local else ''}"
    client = None
    if a.local:
        store = LocalStore(Path(tempfile.mkdtemp(prefix="dryrun-")))
    else:
        import archil
        load_env()
        region = os.environ.get("ARCHIL_REGION", "aws-us-east-1")
        client = archil.Archil(api_key=os.environ["ARCHIL_API_KEY"], region=region)
        store = ArchilStore.new(client, region, f"dryrun-run-{stamp}")
    try:
        print(f"run dir: {run_dir}\ndisk: {store.disk_id}", flush=True)
        t0 = time.perf_counter()
        run = build(store, (HERE / "fake_spec.md").read_text(), a.steps, run_dir)
        print(f"build: {a.steps} steps + checkpoints in {time.perf_counter() - t0:.1f}s, checks {run['checks']}",
              flush=True)
        log = ArchilLog(run_dir / "run.json", run_dir / "archil.json", ROOT / "spikes" / "disk_spike.json")
        fork = run["checkpoints"]["2"]  # the edit is at step 3, so branch the checkpoint just before it
        rec = run_wave(store, fork, EDITS, a.copies, wave="swarm", to_step=a.steps, run_dir=run_dir, log=log)
        print(f"wave: {a.copies} copies in {rec['wall_s']}s")
        for r in rec["routes"]:
            print(f"  {r['route']}: {r['score']} pass  errors={r['errors']}  {r['edit']}")
        print(json.dumps(json.loads((run_dir / "archil.json").read_text())["totals_saved"], indent=1))
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
