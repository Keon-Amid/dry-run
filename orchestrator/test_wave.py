"""The whole pipeline on LocalStore (plain folders, fake builder, fake checks). No Archil, no API."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import orchestrator.wave as wave_mod

from orchestrator.archil_log import ArchilLog
from orchestrator.pipeline import pipeline
from orchestrator.stores import LocalStore
from orchestrator.wave import GUARD_EXIT, HERE, Kit, install_builder, outcome, parse_result, run_builder, run_wave


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
        self.assertIn("Confirmed: a fresh build from step 0 with it passes.", t["card"])

    def test_confirm_is_a_fresh_build_with_the_shortest_winner(self):
        sw = self.files["swarm"]["swarms"][0]
        self.assertEqual(sw["confirm"]["route"], "rw1")  # rw1 is shorter than rw4
        self.assertTrue(sw["confirm"]["passed"])
        cw = next(w for w in self.files["results"]["waves"] if w["purpose"] == "confirm")
        self.assertEqual((cw["fork_step"], cw["n"]), (0, 1))
        self.assertEqual(cw["copies"][0]["builder"]["built"], [1, 2, 3, 4, 5, 6, 7])  # from step 0, all 7 steps

    def test_run_files(self):
        purposes = [w["purpose"] for w in self.files["results"]["waves"]]
        self.assertEqual(purposes, ["triage", "triage", "suspects", "swarm", "confirm", "baseline"])  # decoy: no wave
        self.assertEqual(len(self.files["archil"]["waves"]), 6)
        self.assertEqual(self.files["archil"]["spent"]["total"]["model_calls"], "unknown")  # stub: no model calls
        self.assertIn("build", self.files["archil"]["stages_s"])
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


class BaselineTest(unittest.TestCase):
    def test_stub_fixer_baseline_and_report(self):
        tmp = Path(tempfile.mkdtemp())
        pipeline(LocalStore(tmp / "store"), tmp / "run")
        b = json.loads((tmp / "run" / "baseline.json").read_text())["baselines"][0]
        self.assertEqual((b["fixer"], b["visible"], b["heldout"], b["call"]["model_calls"]), ("stub-fixer", "0/3", "0/3", 0))
        report = (tmp / "run" / "report.md").read_text()
        self.assertIn("| Before: control branches (no change) | 0/3 | 0/3 |", report)
        self.assertIn('| After: swarm rw1 "Links expire 30 days after their last click." | 3/3 | 3/3 |', report)
        self.assertIn("| Baseline: one stub-fixer call fixes the spec, built from step 0 | 0/3 | 0/3 |", report)

    def test_a_fixer_that_fixes_the_spec_builds_from_step_0_three_times(self):
        class Fixer:
            model = "fake-fixer"

            def create(self, system, messages, tools):
                spec = messages[0]["content"].split("<spec>\n", 1)[1].split("\n</spec>", 1)[0]
                fixed = spec.replace("Links expire after 30 days.", "Links expire 30 days after their last click.")
                return {"model": self.model, "content": [{"type": "text", "text": f"<spec>\n{fixed}\n</spec>"}],
                        "usage": {"input_tokens": 10, "output_tokens": 5}}
        tmp = Path(tempfile.mkdtemp())
        pipeline(LocalStore(tmp / "store"), tmp / "run", fixer=Fixer())
        b = json.loads((tmp / "run" / "baseline.json").read_text())["baselines"][0]
        self.assertEqual((b["visible"], b["heldout"], b["regressions"], b["passes_all"]), ("3/3", "3/3", [], True))
        self.assertIn("+Links expire 30 days after their last click.", b["diff"])
        w = next(w for w in json.loads((tmp / "run" / "results.json").read_text())["waves"] if w["purpose"] == "baseline")
        self.assertEqual((w["fork_step"], w["n"]), (0, 3))
        self.assertTrue(all(c["builder"]["built"] == list(range(1, 8)) for c in w["copies"]))

    def test_a_reply_that_changes_the_steps_is_rejected(self):
        from orchestrator.baseline import extract_spec
        with self.assertRaisesRegex(ValueError, "steps"):
            extract_spec("<spec>\n## Step 1\nx\n</spec>", "## Step 1\na\n## Step 2\nb\n")


class BrendanPatchTest(unittest.TestCase):
    def test_every_patch_the_pipeline_sends_passes_brendans_validator(self):
        from builder.patch import load_patch
        tmp = Path(tempfile.mkdtemp())
        store, run_dir = LocalStore(tmp / "store"), tmp / "run"
        pipeline(store, run_dir)
        sent = list(store.root.rglob("patch.json"))
        self.assertGreater(len(sent), 20)
        for p in sent:
            load_patch(str(p))  # raises PatchError on any field it rejects (e.g. a control patch without a step)


class SecretsTest(unittest.TestCase):
    def test_key_reaches_the_builder_env_but_never_a_file(self):
        secret = "sk-ant-test-NEVER-ON-DISK-1234"
        tmp = Path(tempfile.mkdtemp())
        pkg = tmp / "pkg" / "builder"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        digest = hashlib.sha256(secret.encode()).hexdigest()  # the fake builder knows only the hash
        (pkg / "run.py").write_text(
            "import hashlib,json,os\nk=os.environ.get('ANTHROPIC_API_KEY','').encode()\n"
            "print('RESULT ' + json.dumps({'ok': hashlib.sha256(k).hexdigest() == %r}))\n" % digest)
        store = LocalStore(tmp / "store")
        w = store.start_build("sec")
        install_builder(w, pkg)
        res = run_builder(w, 1, 1, "build", kit=Kit(builder_src=pkg, env={"ANTHROPIC_API_KEY": secret}))
        self.assertTrue(res["ok"])  # the builder saw the key
        for f in tmp.rglob("*"):
            if f.is_file():
                self.assertNotIn(secret, f.read_text(errors="ignore"), f)


class ConcurrencyAndRateLimitTest(unittest.TestCase):
    def _pkg(self, tmp: Path, body: str) -> Path:
        pkg = tmp / "pkg" / "builder"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "run.py").write_text(body)
        return pkg

    def test_max_builders_caps_concurrent_builder_processes(self):
        tmp = Path(tempfile.mkdtemp())
        log_path = tmp / "spans.log"
        pkg = self._pkg(tmp, "import json,os,time\nf=os.environ['SPANS']\nopen(f,'a').write(f'+ {time.time()}\\n')\n"
                             "time.sleep(0.3)\nopen(f,'a').write(f'- {time.time()}\\n')\n"
                             "print('RESULT ' + json.dumps({'ok': True}))\n")
        checks = tmp / "nochecks.py"
        checks.write_text("import json\nprint(json.dumps({}))\n")
        store = LocalStore(tmp / "store")
        w = store.start_build("cap")
        w.put(f"{w.mnt}/state.json", "{}")
        ck = store.save(0)
        kit = Kit(builder_src=pkg, checks_src=checks, env={"SPANS": str(log_path)}, max_builders=2)
        log = ArchilLog(None, tmp / "archil.json")
        rec = run_wave(store, ck, [{"route": "x", "kind": "none"}], 6, wave="cap", to_step=1, run_dir=tmp,
                       log=log, targets=[], purpose="test", kit=kit)
        self.assertTrue(all(c["ok"] for c in rec["copies"]), [c.get("error") for c in rec["copies"]])
        running = peak = 0
        events = sorted((float(l.split()[1]), l.split()[0]) for l in log_path.read_text().splitlines())
        for _, kind in events:
            running += 1 if kind == "+" else -1
            peak = max(peak, running)
        self.assertEqual(peak, 2)

    def test_rate_limited_copy_backs_off_and_resumes_from_its_last_step(self):
        calls = []
        replies = [{"ok": False, "error": "APIError: 429 rate_limit_error", "last_done": 3, "steps": [{"step": 3}]},
                   {"ok": True, "last_done": 7, "steps": [{"step": s} for s in range(4, 8)]}]

        def fake_run_builder(w, frm, to, route, patch, env, kit, max_calls=None):
            calls.append((frm, to, patch))
            return replies[len(calls) - 1]

        sleeps = []
        with mock.patch.object(wave_mod, "run_builder", fake_run_builder):
            res = wave_mod.run_steps(None, 3, 7, "r", {"kind": "spec_line"}, Kit(), sleep=sleeps.append)
        self.assertEqual(calls, [(3, 7, {"kind": "spec_line"}), (4, 7, None)])  # resumed at 4, patch not resent
        self.assertEqual((res["ok"], res["rate_limit_resumes"], len(sleeps)), (True, 1, 1))
        self.assertEqual([s["step"] for s in res["steps"]], [3, 4, 5, 6, 7])


class AssertChecksAdapterTest(unittest.TestCase):
    def test_toy_canaries_become_checks(self):
        from orchestrator.assert_checks import build_checks_file
        from orchestrator.pipeline import TOY
        tmp = Path(tempfile.mkdtemp())
        f = build_checks_file(TOY, tmp / "toy_checks.py")
        ws = tmp / "disk" / "workspace"
        ws.mkdir(parents=True)
        (ws / "hello.py").write_text('print("hello")\n')
        run = lambda *a: json.loads(subprocess.run([sys.executable, str(f), *a], capture_output=True, text=True,
                                                   check=True).stdout)
        self.assertEqual(run("--disk", str(tmp / "disk"), "--at-step", "1"), {})  # make_code not defined yet
        (ws / "code.py").write_text("def make_code() -> str:\n    return '123456'\n")
        self.assertEqual(run("--disk", str(tmp / "disk"), "--at-step", "2"), {"CHECK-SOURCE-91bc": True})
        (ws / "code.py").write_text("def make_code() -> str:\n    return '123'\n")
        self.assertEqual(run("--disk", str(tmp / "disk"), "--at-step", "2"), {"CHECK-SOURCE-91bc": False})
        self.assertEqual(list((tmp / "disk").rglob("__pycache__")), [])  # grading imported code.py, wrote nothing
        meta = run("--meta")
        self.assertFalse(meta["HELDOUT-SECRET-7f3a"]["supported"])  # prose, not an assert: never graded
        self.assertTrue(meta["HELDOUT-SECRET-7f3a"]["heldout"])


class SafeNameTest(unittest.TestCase):
    def test_archil_name_rules(self):
        import re
        from orchestrator.stores import safe_name
        for raw in ("suspects-expiry_from_last_click-rule-short-answers-r3", "A__B", "-x-", "_" * 80):
            n = safe_name(raw)
            self.assertRegex(n, r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", raw)
        self.assertNotEqual(safe_name("same"), safe_name("same"))
