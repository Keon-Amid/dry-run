"""Archil benefit log: writes archil.json, what each wave got from branching instead of rebuilding.

The orchestrator calls `ArchilLog.wave(...)` once per finished wave. Every number comes from a run file:
  - per-step averages (wall time, model calls, tokens) from run.json, written by the build
  - per-copy branch/mount times and wall times, measured by the orchestrator during the wave
  - the no-Archil restore baseline (git clone + dependency install) from spikes/disk_spike.json

Two counterfactuals, kept apart:
  - rebuild: without a checkpoint, each copy replays steps 1..fork_step (minutes, model calls, dollars)
  - restore: git clone + install gets the code back (not the conversation); compared with branch + mount
Only the token prices below are typed in (Anthropic list prices, per million tokens).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

# $ per million tokens. Cache write = 1.25 x input (5-minute cache). HARDCODED; update if the model or price changes.
PRICES = {
    "claude-fable-5-2": {"input": 8.00, "output": 40.00, "cache_read": 0.20},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.10},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01},
}
CACHE_WRITE_MULT = 1.25


def usage_usd(model: str, usage: dict) -> float:
    """Dollars for one API `usage` object (or a sum of them)."""
    p = PRICES[model]
    return (usage.get("input_tokens", 0) * p["input"]
            + usage.get("output_tokens", 0) * p["output"]
            + usage.get("cache_creation_input_tokens", 0) * p["input"] * CACHE_WRITE_MULT
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1e6


UNKNOWN = "unknown"


def _mean(steps: list[dict], fn) -> float | str:
    """Mean of fn(step) over all steps, or "unknown" if any step lacks the fields fn needs."""
    try:
        vals = [fn(s) for s in steps]
    except (KeyError, TypeError):
        return UNKNOWN
    return round(sum(vals) / len(vals), 6) if vals else UNKNOWN


def step_averages(run: dict | None) -> dict:
    """Mean wall seconds, model calls and dollars per build step, from run.json.

    Every run.json field is optional: an average whose fields are missing on any step is "unknown"."""
    steps = (run or {}).get("steps") or []
    model = (run or {}).get("model")
    return {
        "steps_in_run": len(steps),
        "wall_s": _mean(steps, lambda s: s["wall_s"]),
        "model_calls": _mean(steps, lambda s: s["model_calls"]),
        "usd": _mean(steps, lambda s: usage_usd(s.get("model") or model, s["usage"])),
    }


def _times(n: int, avg: float | str, digits: int) -> float | str:
    return UNKNOWN if avg == UNKNOWN else round(n * avg, digits)


def restore_baseline(spike: dict) -> dict:
    """No-Archil restore (git clone + install) vs Archil restore (branch + mount), from the spike's JSON."""
    b, t = spike["baseline"]["timings_s"], spike["timings_s"]
    archil_s = t["branch_create"] + t["branch_mount_b"]
    return {"git_clone_plus_install_s": b["total"], "branch_plus_mount_s": round(archil_s, 3),
            "source": "spikes/disk_spike.json"}


@dataclass
class Copy:
    id: str             # branch name, e.g. "triage-c3-r1"
    branch_ms: float    # create_branch call
    mount_ms: float     # mount in its sandbox until the files are readable
    wall_s: float       # resume -> graded, this copy alone
    sandbox_ms: float = 0.0  # sandbox create, between the branch and the mount


@dataclass
class Wave:
    wave: str           # "triage" | "suspects" | "swarm" | ...
    fork_step: int      # checkpoint branched from: steps 1..fork_step are reused, not rebuilt
    wall_s: float       # whole wave, first branch to last grade
    copies: list[Copy] = field(default_factory=list)


class ArchilLog:
    def __init__(self, run_json: Path | None, out: Path, spike_json: Path | None = None):
        self.out = Path(out)
        run = json.loads(Path(run_json).read_text()) if run_json and Path(run_json).exists() else None
        self.avg = step_averages(run)
        self.restore = restore_baseline(json.loads(Path(spike_json).read_text())) if spike_json else None
        self.waves: list[dict] = []

    def wave(self, w: Wave) -> dict:
        n = len(w.copies)
        reused = w.fork_step * n
        sum_copy = sum(c.wall_s for c in w.copies)
        rec = {
            **asdict(w),
            "n_copies": n,
            "steps_reused_per_copy": w.fork_step,
            "steps_reused": reused,
            "sum_copy_s": round(sum_copy, 3),
            "parallel_speedup": round(sum_copy / w.wall_s, 2) if w.wall_s else None,
            "saved": {
                "steps": reused,
                "minutes": _times(reused, self.avg["wall_s"] if self.avg["wall_s"] == UNKNOWN
                                  else self.avg["wall_s"] / 60, 2),
                "model_calls": _times(reused, self.avg["model_calls"], 1),
                "usd": _times(reused, self.avg["usd"], 4),
            },
        }
        if self.restore:  # each copy's own branch + mount, against the one-time git clone + install baseline
            git_s = self.restore["git_clone_plus_install_s"]
            saved_s = sum(git_s - (c.branch_ms + c.mount_ms) / 1000 for c in w.copies)
            rec["saved"]["restore_minutes_vs_git"] = round(saved_s / 60, 2)
        self.waves.append(rec)
        self.write()
        return rec

    def totals(self) -> dict:
        keys = ["steps", "minutes", "model_calls", "usd"] + (["restore_minutes_vs_git"] if self.restore else [])
        t = {}
        for k in keys:
            vals = [w["saved"][k] for w in self.waves]
            t[k] = UNKNOWN if UNKNOWN in vals else round(sum(vals), 4)
        t["copies"] = sum(w["n_copies"] for w in self.waves)
        t["wall_s"] = round(sum(w["wall_s"] for w in self.waves), 3)
        t["sum_copy_s"] = round(sum(w["sum_copy_s"] for w in self.waves), 3)
        return t

    def write(self) -> None:
        doc = {
            "counterfactuals": {
                "rebuild": "without a checkpoint, each copy replays steps 1..fork_step",
                "restore": "git clone + dependency install restores code only, not the conversation",
            },
            "per_step_avg": self.avg,
            "restore_baseline": self.restore,
            "prices_per_mtok": PRICES,
            "waves": self.waves,
            "totals_saved": self.totals(),
        }
        tmp = self.out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=2) + "\n")
        os.replace(tmp, self.out)  # atomic: the page never reads half a file


def relog(run_dir: Path, spike_json: Path | None = None) -> dict:
    """Rebuild run_dir/archil.json from run_dir/run.json + results.json (the run files), e.g. after a formula fix."""
    run_dir = Path(run_dir)
    log = ArchilLog(run_dir / "run.json", run_dir / "archil.json", spike_json)
    for wv in json.loads((run_dir / "results.json").read_text())["waves"]:
        log.wave(Wave(wave=wv["wave"], fork_step=wv["fork_step"], wall_s=wv["wall_s"], copies=[
            Copy(c["id"], c["timings_ms"].get("branch", 0.0), c["timings_ms"].get("mount", 0.0), c["wall_s"],
                 c["timings_ms"].get("sandbox", 0.0)) for c in wv["copies"] if c["ok"]]))
    return json.loads((run_dir / "archil.json").read_text())


if __name__ == "__main__":  # python -m orchestrator.archil_log RUN_DIR
    import sys
    doc = relog(Path(sys.argv[1]), Path(__file__).resolve().parent.parent / "spikes" / "disk_spike.json")
    print(json.dumps(doc["totals_saved"], indent=1))
