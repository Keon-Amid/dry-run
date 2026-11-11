"""A whole build + wave on LocalStore (plain folders, fake builder, fake checks). No Archil, no API."""
import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.archil_log import ArchilLog
from orchestrator.run_demo import EDITS
from orchestrator.stores import LocalStore
from orchestrator.wave import HERE, build, run_wave


class WaveTest(unittest.TestCase):
    def test_build_then_swarm(self):
        tmp = Path(tempfile.mkdtemp())
        store, run_dir = LocalStore(tmp / "store"), tmp / "run"
        run = build(store, (HERE / "fake_spec.md").read_text(), 7, run_dir)
        self.assertEqual(sorted(run["checkpoints"], key=int), [str(k) for k in range(8)])
        self.assertFalse(run["checks"]["expiry_from_last_click"])  # the planted check fails on the stock spec
        self.assertTrue(run["checks"]["conversation_intact"])

        log = ArchilLog(run_dir / "run.json", run_dir / "archil.json")
        rec = run_wave(store, run["checkpoints"]["2"], EDITS, 10, wave="swarm", to_step=7, run_dir=run_dir, log=log)
        scores = {r["route"]: r["score"] for r in rec["routes"]}
        self.assertEqual(scores, {"rw1": "2/2", "rw2": "0/2", "rw3": "0/2", "rw4": "2/2", "rw5": "0/2"})
        self.assertTrue(all(c["ok"] for c in rec["copies"]), [c.get("error") for c in rec["copies"]])

        # each branch resumed at step 2: steps 1-2 kept from the checkpoint, 3-7 rebuilt with the edit
        c = rec["copies"][0]
        self.assertEqual(c["builder"]["built"], [3, 4, 5, 6, 7])
        branch = store.root / "branches" / c["branch"]
        self.assertIn("last click", (branch / "workspace" / "step_3.txt").read_text())
        self.assertNotIn("last click", (store.root / "checkpoints" / "c2" / "spec.md").read_text())  # source untouched

        doc = json.loads((run_dir / "archil.json").read_text())
        self.assertEqual(doc["waves"][0]["steps_reused"], 20)  # 2 steps x 10 copies
        self.assertEqual(doc["totals_saved"]["model_calls"], "unknown")  # the fake builder logs no model calls
        self.assertEqual(json.loads((run_dir / "results.json").read_text())["waves"][0]["n"], 10)


if __name__ == "__main__":
    unittest.main()
