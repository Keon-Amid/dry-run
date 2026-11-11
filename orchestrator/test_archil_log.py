"""Run: .venv/bin/python -m unittest orchestrator/test_archil_log.py  (fake run files, no Archil, no API)."""
import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.archil_log import ArchilLog, Copy, Wave, usage_usd

RUN = {  # fake run.json: 2 steps on Opus 5.5
    "model": "claude-opus-5-5",
    "steps": [
        {"step": 1, "wall_s": 30.0, "model_calls": 4,
         "usage": {"input_tokens": 100_000, "output_tokens": 10_000, "cache_read_input_tokens": 0}},
        {"step": 2, "wall_s": 50.0, "model_calls": 6,
         "usage": {"input_tokens": 50_000, "output_tokens": 20_000, "cache_creation_input_tokens": 40_000,
                   "cache_read_input_tokens": 200_000}},
    ],
}
SPIKE = {"timings_s": {"branch_create": 0.15, "branch_mount_b": 2.0}, "baseline": {"timings_s": {"total": 32.15}}}


class ArchilLogTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "run.json").write_text(json.dumps(RUN))
        (self.dir / "spike.json").write_text(json.dumps(SPIKE))
        self.out = self.dir / "archil.json"
        self.log = ArchilLog(self.dir / "run.json", self.out, self.dir / "spike.json")

    def test_usage_usd(self):
        # step 1: 0.1M in * $4 + 0.01M out * $20 = 0.40 + 0.20
        self.assertAlmostEqual(usage_usd("claude-opus-5-5", RUN["steps"][0]["usage"]), 0.60)
        # step 2: 0.05*4 + 0.02*20 + 0.04*4*1.25 + 0.2*0.20 = 0.2 + 0.4 + 0.2 + 0.04
        self.assertAlmostEqual(usage_usd("claude-opus-5-5", RUN["steps"][1]["usage"]), 0.84)

    def test_wave_and_totals(self):
        copies = [Copy(f"triage-r{i}", branch_ms=40, mount_ms=1100, wall_s=60) for i in range(3)]
        rec = self.log.wave(Wave("triage", fork_step=2, wall_s=75, copies=copies))
        self.assertEqual(rec["steps_reused"], 6)            # 2 steps x 3 copies
        self.assertEqual(rec["sum_copy_s"], 180)
        self.assertEqual(rec["parallel_speedup"], 2.4)      # 180 / 75
        self.assertEqual(rec["saved"]["minutes"], 4.0)      # 6 x 40 s avg
        self.assertEqual(rec["saved"]["model_calls"], 30)   # 6 x 5 avg
        self.assertAlmostEqual(rec["saved"]["usd"], 6 * 0.72)
        self.assertEqual(rec["saved"]["restore_minutes_vs_git"], 1.5)  # (32.15 - 2.15) s x 3 copies

        self.log.wave(Wave("suspects", fork_step=1, wall_s=50, copies=copies[:2]))
        doc = json.loads(self.out.read_text())
        t = doc["totals_saved"]
        self.assertEqual(t["steps"], 8)
        self.assertEqual(t["copies"], 5)
        self.assertEqual(t["model_calls"], 40)
        self.assertEqual([w["wave"] for w in doc["waves"]], ["triage", "suspects"])
        self.assertEqual(doc["waves"][0]["copies"][0]["branch_ms"], 40)

    def test_no_spike_means_no_restore_numbers(self):
        log = ArchilLog(self.dir / "run.json", self.out)
        rec = log.wave(Wave("swarm", fork_step=1, wall_s=10, copies=[Copy("s1", 30, 900, 10)]))
        self.assertNotIn("restore_minutes_vs_git", rec["saved"])
        self.assertIsNone(json.loads(self.out.read_text())["restore_baseline"])


    def test_missing_run_fields_are_unknown(self):
        partial = {"steps": [{"step": 1, "wall_s": 30.0}, {"step": 2, "wall_s": 90.0}]}  # no model, calls or usage
        (self.dir / "partial.json").write_text(json.dumps(partial))
        log = ArchilLog(self.dir / "partial.json", self.out)
        rec = log.wave(Wave("swarm", fork_step=2, wall_s=10, copies=[Copy("s1", 30, 900, 10)]))
        self.assertEqual(rec["saved"]["minutes"], 2.0)          # 2 steps x 60 s avg: wall_s is there
        self.assertEqual(rec["saved"]["model_calls"], "unknown")
        self.assertEqual(rec["saved"]["usd"], "unknown")
        self.assertEqual(log.totals()["usd"], "unknown")

    def test_no_run_json_at_all(self):
        log = ArchilLog(self.dir / "missing.json", self.out)
        rec = log.wave(Wave("swarm", fork_step=1, wall_s=10, copies=[Copy("s1", 30, 900, 10)]))
        self.assertEqual(rec["saved"]["steps"], 1)               # steps reused never needs run.json
        self.assertEqual(rec["saved"]["minutes"], "unknown")


if __name__ == "__main__":
    unittest.main()
