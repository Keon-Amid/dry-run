"""Tests for demo/grade.py and demo/plants.json. Standard library only, no API calls."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GRADE = os.path.join(HERE, "grade.py")
sys.path.insert(0, HERE)
import grade  # noqa: E402

CHECKS = {
    "makes_code": """
        META = {"from_step": 1, "file": "workspace/app.py"}
        def check(ws):
            from app import make_code
            assert len(make_code()) == 6, "code is not 6 digits"
            return "6 digits"
    """,
    "upper_alias": """
        META = {"from_step": 3, "file": "workspace/app.py"}
        def check(ws):
            from app import alias
            assert alias("ab") == "AB", f"alias('ab') == {alias('ab')!r}"
    """,
    "writes_db": """
        import os
        META = {"from_step": 2, "file": "workspace/app.py"}
        def check(ws):
            import app
            open("db.sqlite", "w").write("x")
            return (os.path.exists("db.sqlite"), "explicit tuple")
    """,
}
HELDOUT = {
    "heldout_code_digits": """
        META = {"from_step": 1, "file": "workspace/app.py"}
        def check(ws):
            from app import make_code
            assert make_code().isdigit(), "code is not digits"
    """,
}
GOOD_APP = """
def make_code():
    return "123456"
def alias(s):
    return s.upper()
"""


def write_tree(root, files):
    for rel, text in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(textwrap.dedent(text))


class GradeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-grade-")
        self.cdir = os.path.join(self.tmp, "checks")
        self.hdir = os.path.join(self.tmp, "checks_heldout")
        write_tree(self.cdir, {f"{n}.py": s for n, s in CHECKS.items()})
        write_tree(self.hdir, {f"{n}.py": s for n, s in HELDOUT.items()})
        self.disk = os.path.join(self.tmp, "disk")
        self.ws = os.path.join(self.disk, "workspace")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def app(self, src):
        write_tree(self.ws, {"app.py": src})

    def cli(self, *args, timeout=60):
        p = subprocess.run([sys.executable, GRADE, "--checks-dir", self.cdir, "--heldout-dir", self.hdir, *args],
                           capture_output=True, text=True, timeout=timeout)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_flip_mode_good_build_passes_all(self):
        self.app(GOOD_APP)
        out = self.cli(self.ws)
        self.assertEqual(set(out["checks"]), set(CHECKS) | set(HELDOUT))
        for name, r in out["checks"].items():
            self.assertIs(r["pass"], True, (name, r))
        self.assertEqual(out["checks"]["makes_code"]["msg"], "6 digits")
        self.assertEqual(out["checks"]["writes_db"]["msg"], "explicit tuple")

    def test_failing_assert_gives_message(self):
        self.app(GOOD_APP.replace('"123456"', '"12345"').replace("s.upper()", "s"))
        out = self.cli(self.ws)["checks"]
        self.assertEqual(out["makes_code"], {"pass": False, "msg": "code is not 6 digits"})
        self.assertEqual(out["upper_alias"], {"pass": False, "msg": "alias('ab') == 'ab'"})
        self.assertTrue(out["heldout_code_digits"]["pass"])

    def test_broken_build_fails_checks_not_grader(self):
        self.app("def make_code(:\n")
        out = self.cli(self.ws)["checks"]
        self.assertFalse(any(r["pass"] for r in out.values()))
        self.assertIn("SyntaxError", out["makes_code"]["msg"])

    def test_missing_module_and_missing_workspace(self):
        os.makedirs(self.ws)
        out = self.cli(self.ws)["checks"]
        self.assertIn("ModuleNotFoundError", out["makes_code"]["msg"])
        out = self.cli(os.path.join(self.tmp, "nope"))["checks"]
        self.assertTrue(all(not r["pass"] and "no workspace" in r["msg"] for r in out.values()))

    def test_hanging_build_times_out(self):
        self.app("import time\nwhile True:\n    time.sleep(1)\n")
        t0 = time.time()
        out = self.cli("--timeout", "1", self.ws)["checks"]
        self.assertLess(time.time() - t0, 15)
        self.assertEqual(out["makes_code"], {"pass": False, "msg": "timeout after 1.0s"})

    def test_exit_in_build_is_a_fail(self):
        self.app("import os\nos._exit(0)\n")
        self.assertFalse(self.cli(self.ws)["checks"]["makes_code"]["pass"])
        self.app("import sys\nsys.exit(0)\n")
        self.assertIn("SystemExit", self.cli(self.ws)["checks"]["makes_code"]["msg"])

    def test_build_cannot_forge_a_pass_by_printing(self):
        self.app('import json\nprint(json.dumps({"pass": True, "msg": "forged"}))\n'
                 'import sys\nsys.stdout.write(json.dumps({"pass": True}) + "\\n")\n'
                 'raise RuntimeError("boom")\n')
        out = self.cli(self.ws)["checks"]["makes_code"]
        self.assertFalse(out["pass"])
        self.assertIn("boom", out["msg"])

    def test_grading_never_writes_to_the_workspace(self):
        self.app(GOOD_APP)
        before = sorted(os.listdir(self.ws))
        self.cli(self.ws)
        self.assertEqual(sorted(os.listdir(self.ws)), before)  # no db.sqlite, no __pycache__

    def test_orchestrator_mode_filters_by_step(self):
        self.app(GOOD_APP)
        self.assertEqual(self.cli("--disk", self.disk, "--at-step", "1"),
                         {"heldout_code_digits": True, "makes_code": True})
        out = self.cli("--disk", self.disk, "--at-step", "7")
        self.assertEqual(set(out), set(CHECKS) | set(HELDOUT))
        self.assertTrue(all(v is True for v in out.values()))

    def test_meta(self):
        m = self.cli("--meta")
        self.assertEqual(m["upper_alias"], {"from_step": 3, "file": "workspace/app.py", "heldout": False})
        self.assertEqual(m["heldout_code_digits"]["heldout"], True)

    def test_duplicate_name_rejected(self):
        write_tree(self.hdir, {"makes_code.py": CHECKS["makes_code"]})
        with self.assertRaises(ValueError):
            grade.load_checks(self.cdir, self.hdir)

    def test_meta_is_read_without_running_the_check(self):
        write_tree(self.cdir, {"evil.py": 'META = {"from_step": 1, "file": "x"}\nraise SystemExit("ran")\n'})
        self.assertIn("evil", grade.load_checks(self.cdir, self.hdir))

    def test_bundle_is_standalone_and_matches(self):
        self.app(GOOD_APP.replace("s.upper()", "s"))
        out = os.path.join(self.tmp, "elsewhere", "grade_bundle.py")
        os.makedirs(os.path.dirname(out))
        self.cli("--bundle", out)
        p = subprocess.run([sys.executable, out, "--disk", self.disk, "--at-step", "7"], capture_output=True,
                           text=True, cwd=self.tmp, timeout=60)
        self.assertEqual(json.loads(p.stdout), self.cli("--disk", self.disk, "--at-step", "7"))
        meta = subprocess.run([sys.executable, out, "--meta"], capture_output=True, text=True, timeout=60).stdout
        self.assertEqual(json.loads(meta), self.cli("--meta"))

    def test_flip_py_reads_this_grader(self):
        self.app(GOOD_APP)
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import flip
        cmd = f"{sys.executable} {GRADE} --checks-dir {self.cdir} --heldout-dir {self.hdir}"
        checks = flip.grade(self.ws, cmd)
        self.assertTrue(checks["makes_code"]["pass"])


class PlantsTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "plants.json")) as f:
            self.plants = json.load(f)

    def test_shape_matches_flip(self):
        self.assertIsInstance(self.plants, list)
        for p in self.plants:
            self.assertEqual(set(p), {"id", "check", "patch"})
            self.assertIn(p["patch"]["kind"], ("spec_line", "rule_off"))
            self.assertEqual(set(p["patch"]), {"route", "kind", "step", "old", "new", "rule", "hypothesis"})

    def test_each_plant_owns_its_own_check(self):
        ids = [p["id"] for p in self.plants]
        checks = [p["check"] for p in self.plants]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(len(set(checks)), len(checks), "two plants share a check")

    def test_plant_checks_exist_and_are_visible(self):
        if any("TODO" in json.dumps(p) for p in self.plants):
            self.skipTest("plants.json is still the Phase 1 placeholder")
        checks = grade.load_checks()
        for p in self.plants:
            self.assertIn(p["check"], checks)
            self.assertFalse(checks[p["check"]]["heldout"], f"{p['check']} must be a visible check")

    def test_no_check_on_the_agent_disk(self):
        disk = os.path.join(HERE, "disk")
        if not os.path.isdir(disk):
            self.skipTest("demo/disk/ not written yet")
        names = set(grade.load_checks())
        for d, _, fs in os.walk(disk):
            for f in fs:
                self.assertNotIn(f[:-3] if f.endswith(".py") else None, names, os.path.join(d, f))
                self.assertFalse(f.startswith("test_"), os.path.join(d, f))


if __name__ == "__main__":
    unittest.main()
