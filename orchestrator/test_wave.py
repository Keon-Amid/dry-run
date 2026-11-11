"""The whole pipeline on LocalStore (plain folders, fake builder, fake checks). No Archil, no API."""
import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.archil_log import ArchilLog
from orchestrator.pipeline import pipeline
from orchestrator.stores import LocalStore
from orchestrator.wave import GUARD_EXIT, HERE, install_builder, outcome, parse_result, run_builder


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
            run_builder(w, 1, 1, "build")
        w.put(f"{w.mnt}/workspace/fake_checks.py", "planted on the disk")
        Path(w.tools, "checks", "fake_checks.py").unlink()
        Path(w.tools, "checks").rmdir()
        with self.assertRaisesRegex(RuntimeError, f"exit {GUARD_EXIT}"):
            run_builder(w, 1, 1, "build")


if __name__ == "__main__":
    unittest.main()


class BuilderHandoffTest(unittest.TestCase):
    """The contract with brendan's builder: RESULT line, --from-step = first step to run, a package run with -m."""

    def test_parse_result_takes_the_last_result_line(self):
        out = 'step 1\nRESULT {"n": 1}\nnoise {"n": 9}\nRESULT {"n": 2}\ntrailing log line'
        self.assertEqual(parse_result(out), {"n": 2})
        with self.assertRaisesRegex(RuntimeError, "no RESULT line.*just logs"):
            parse_result("just logs\n{\"n\": 3}")

    def _worker(self):
        w = LocalStore(Path(tempfile.mkdtemp())).start_build("h")
        install_builder(w)
        w.put(f"{w.mnt}/spec.md", (HERE / "fake_spec.md").read_text())
        w.put(f"{w.mnt}/state.json", '{"last_done": 0, "steps": []}')
        return w

    def test_from_step_is_the_first_step_run(self):
        w = self._worker()
        self.assertEqual(run_builder(w, 1, 1, "build")["built"], [1])     # build mode: one step per process
        self.assertEqual(run_builder(w, 2, 2, "build")["built"], [2])
        self.assertEqual(run_builder(w, 3, 5, "copy")["built"], [3, 4, 5])  # resume from c2 = --from-step 3
        res = run_builder(w, 5, 7, "copy")                                 # off by one is refused, not silent
        self.assertEqual((res["ok"], res["exit_code"], outcome(res)), (False, 1, "error"))
        self.assertIn("last_done=5, asked to run step 5 first", res["error"])

    def test_builder_runs_as_a_package(self):
        w = self._worker()
        self.assertTrue(Path(w.tools, "pkg", "builder", "run.py").exists())
        code, out, _ = w.exec(f"cd {w.tools}/pkg && python3 -m builder.run --help")
        self.assertEqual(code, 0)
        self.assertIn("--from-step", out)

    def test_no_result_line_is_an_error_with_stdout_tail(self):
        w = self._worker()
        Path(w.tools, "pkg", "builder", "run.py").write_text("print('working...')\n")
        with self.assertRaisesRegex(RuntimeError, "no RESULT line.*working"):
            run_builder(w, 1, 1, "build")


    def test_capped_copy_is_invalid_not_failed(self):
        w = self._worker()
        Path(w.tools, "pkg", "builder", "run.py").write_text(
            "import json,sys\nprint('RESULT ' + json.dumps({'ok': False, 'capped': True, 'invalid': True}))\n"
            "sys.exit(2)\n")
        res = run_builder(w, 1, 1, "copy")
        self.assertEqual((res["exit_code"], outcome(res)), (2, "invalid"))


class SafeNameTest(unittest.TestCase):
    def test_archil_name_rules(self):
        import re
        from orchestrator.stores import safe_name
        for raw in ("suspects-expiry_from_last_click-rule-short-answers-r3", "A__B", "-x-", "_" * 80):
            n = safe_name(raw)
            self.assertRegex(n, r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", raw)
        self.assertNotEqual(safe_name("same"), safe_name("same"))
