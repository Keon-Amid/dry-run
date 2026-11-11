"""The whole pipeline on LocalStore (plain folders, fake builder, fake checks). No Archil, no API."""
import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.archil_log import ArchilLog
from orchestrator.pipeline import pipeline
from orchestrator.stores import LocalStore
from orchestrator.wave import GUARD_EXIT, build, install_builder, run_builder, HERE


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp())
        cls.store, cls.run_dir = LocalStore(tmp / "store"), tmp / "run"
        cls.out = pipeline(cls.store, cls.run_dir)
        cls.files = {n: json.loads((cls.run_dir / f"{n}.json").read_text())
                     for n in ("run", "triage", "results", "swarm", "archil")}

    def test_verdicts(self):
        v = {t["check"]: t["verdict"] for t in self.files["triage"]["checks"]}
        self.assertEqual(v, {"expiry_from_last_click": "real_problem", "redirect_counts_click": "model_slip",
                             "stats_returns_json": "test_wrong"})

    def test_locate_suspects_swarm(self):
        t = next(t for t in self.files["triage"]["checks"] if t["check"] == "expiry_from_last_click")
        self.assertEqual((t["surfaced_step"], t["origin_step"]), (3, 3))
        self.assertTrue(t["fork_checkpoint_id"].endswith("/c2"))
        self.assertEqual(t["culprit"]["route"], "spec-step3")
        self.assertEqual((t["culprit"]["score"], t["suspects"]["control"]), ("3/3", "0/3"))
        self.assertEqual({s["route"]: s["score"] for s in t["suspects"]["suspects"]},
                         {"spec-step3": "3/3", "rule-short-answers": "0/3"})
        sw = self.files["swarm"]["swarms"][0]
        self.assertEqual(sw["winners"], ["rw1", "rw4"])
        rw3 = next(r for r in sw["rewrites"] if r["route"] == "rw3")
        self.assertEqual((rw3["visible"], rw3["heldout"], rw3["winner"]), ("3/3", "0/3", False))  # held-out stops it
        self.assertIn("Swarm: 15 branches tried 5 rewrites, 2 pass 3/3 + held-out.", t["card"])

    def test_run_files(self):
        purposes = [w["purpose"] for w in self.files["results"]["waves"]]
        self.assertEqual(purposes, ["triage", "triage", "suspects", "swarm"])  # the decoy needs no wave
        self.assertEqual(len(self.files["archil"]["waves"]), 4)
        self.assertTrue(all(c["ok"] for w in self.files["results"]["waves"] for c in w["copies"]))
        self.assertEqual(self.files["run"]["simulated_slip"]["step"], 4)

    def test_checks_hidden_from_every_builder_run(self):
        self.assertTrue(all(s["checks_hidden_during_build"] for s in self.files["run"]["steps"]))
        copies = [c for w in self.files["results"]["waves"] for c in w["copies"]]
        self.assertTrue(copies and all(c["builder"]["checks_hidden_during_build"] for c in copies))
        # no check file left in any branch or in any tools folder after the run
        self.assertEqual(list(self.store.root.rglob("fake_checks.py")), [])

    def test_guard_refuses_when_checks_are_visible(self):
        store = LocalStore(Path(tempfile.mkdtemp()))
        w = store.start_build("guard")
        install_builder(w)
        w.put(f"{w.mnt}/state.json", '{"last_done": 0, "steps": []}')
        w.put(f"{w.mnt}/spec.md", (HERE / "fake_spec.md").read_text())
        w.put(f"{w.tools}/checks/fake_checks.py", "planted")
        with self.assertRaisesRegex(RuntimeError, f"exit {GUARD_EXIT}"):
            run_builder(w, 0, 1, "build")
        w.put(f"{w.mnt}/workspace/fake_checks.py", "planted on the disk")
        Path(w.tools, "checks", "fake_checks.py").unlink()
        Path(w.tools, "checks").rmdir()
        with self.assertRaisesRegex(RuntimeError, f"exit {GUARD_EXIT}"):
            run_builder(w, 0, 1, "build")


if __name__ == "__main__":
    unittest.main()


class SafeNameTest(unittest.TestCase):
    def test_archil_name_rules(self):
        import re
        from orchestrator.stores import safe_name
        for raw in ("suspects-expiry_from_last_click-rule-short-answers-r3", "A__B", "-x-", "_" * 80):
            n = safe_name(raw)
            self.assertRegex(n, r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", raw)
        self.assertNotEqual(safe_name("same"), safe_name("same"))
