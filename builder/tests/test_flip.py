import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("flip", os.path.join(REPO, "scripts", "flip.py"))
flip = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flip)

TOY_DISK = os.path.join(REPO, "builder", "tests", "fixtures", "toy", "disk")

# Grader: reads workspace/code.txt; "code_len" passes iff it holds 6 chars; "readme" passes iff README exists.
# A workspace containing GARBAGE makes the grader print non-JSON.
GRADER = textwrap.dedent('''
    import json, os, sys
    ws = sys.argv[-1]
    if os.path.exists(os.path.join(ws, "GARBAGE")):
        print("Traceback: boom"); sys.exit(1)
    code = open(os.path.join(ws, "code.txt")).read().strip()
    print(json.dumps({"checks": {
        "code_len": {"pass": len(code) == 6, "msg": "len=%d" % len(code)},
        "readme": {"pass": os.path.exists(os.path.join(ws, "README.md")), "msg": ""}}}))
''')

PLANT = {"id": "p-five", "check": "code_len",
         "patch": {"route": "p-five", "kind": "spec_line", "step": 2, "old": "5 digits", "new": "6 digits",
                   "hypothesis": "plant"}}


class FakeRunner:
    """Stands in for builder.run: writes a 5-char code with the plant, 6 chars when the patch is applied."""

    def __init__(self, out=None, script=None):
        self.calls, self.out, self.script = [], out, script or {}
        self.seen_counts = []

    def __call__(self, disk, to_step, patch_path, fake_llm):
        n = len(self.calls)
        patch = None
        if patch_path:
            with open(patch_path) as f:
                patch = json.load(f)
        self.calls.append({"disk": disk, "to_step": to_step, "patch": patch, "fake_llm": fake_llm,
                           "has_spec": os.path.exists(os.path.join(disk, "spec.md"))})
        if self.out:
            with open(self.out) as f:
                self.seen_counts.append(len(json.load(f)["runs"]))
        ws = os.path.join(disk, "workspace")
        os.makedirs(ws, exist_ok=True)
        with open(os.path.join(ws, "code.txt"), "w") as f:
            f.write("123456" if patch else "12345")
        action = self.script.get(n)
        if action == "capped":
            return 2, {"capped": True}, "capped"
        if action == "capped_flag":
            return 0, {"capped": True}, ""
        if action == "error":
            return 1, {"error": "PatchError"}, "boom"
        if action == "noresult":
            return 0, None, ""
        if action == "raise":
            raise RuntimeError("runner died")
        if action == "garbage":
            open(os.path.join(ws, "GARBAGE"), "w").close()
        return 0, {"capped": False, "last_done": to_step}, ""


class FlipBase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        g = os.path.join(self.d, "grade.py")
        with open(g, "w") as f:
            f.write(GRADER)
        self.check_cmd = f"{sys.executable} {g}"
        self.out = os.path.join(self.d, "flip.json")

    def run_flip(self, runner, plants=(PLANT,), **kw):
        return flip.run_flip(list(plants), TOY_DISK, 3, self.out, check_cmd=self.check_cmd, runner=runner, **kw)

    def load(self):
        with open(self.out) as f:
            return json.load(f)

    def table(self):
        buf = io.StringIO()
        flip.print_table(self.out, file=buf)
        return buf.getvalue()


class TestFlipRuns(FlipBase):
    def test_flip_detected_and_recorded(self):
        r = FakeRunner()
        self.run_flip(r, fake_llm="/abs/script.json")
        doc = self.load()
        self.assertEqual(len(doc["runs"]), 6)
        w = [x for x in doc["runs"] if x["arm"] == "with"]
        wo = [x for x in doc["runs"] if x["arm"] == "without"]
        self.assertTrue(all(x["valid"] and x["pass"] is False for x in w))
        self.assertTrue(all(x["valid"] and x["pass"] is True for x in wo))
        self.assertEqual(w[0]["checks"], {"code_len": {"pass": False, "msg": "len=5"}})
        # arms: with = no patch, without = the plant's patch, every run on a fresh copy of the template
        self.assertEqual([c["patch"] for c in r.calls[:3]], [None] * 3)
        self.assertEqual([c["patch"] for c in r.calls[3:]], [PLANT["patch"]] * 3)
        self.assertEqual(len({c["disk"] for c in r.calls}), 6)
        self.assertTrue(all(c["has_spec"] and c["to_step"] == 3 for c in r.calls))
        self.assertTrue(all(c["fake_llm"] == "/abs/script.json" for c in r.calls))
        self.assertFalse(os.path.exists(os.path.join(TOY_DISK, "workspace")))  # template untouched
        self.assertFalse(any(os.path.exists(c["disk"]) for c in r.calls))       # temp disks cleaned
        t = self.table()
        self.assertIn("p-five", t)
        self.assertIn("0/3/0", t)
        self.assertIn("3/0/0", t)
        self.assertIn("FLIP", t)

    def test_appends_as_it_goes(self):
        r = FakeRunner(out=self.out)
        self.run_flip(r)
        self.assertEqual(r.seen_counts, [0, 1, 2, 3, 4, 5])

    def test_capped_and_errors_are_invalid_never_pass_or_fail(self):
        r = FakeRunner(script={0: "capped", 1: "capped_flag", 2: "error", 3: "noresult", 4: "raise",
                               5: "garbage"})
        self.run_flip(r)
        doc = self.load()
        self.assertEqual(len(doc["runs"]), 6)
        for x in doc["runs"]:
            self.assertFalse(x["valid"], x)
            self.assertIsNone(x["pass"], x)
        self.assertTrue(doc["runs"][0]["capped"] and doc["runs"][1]["capped"])
        self.assertIn("grader error", doc["runs"][5]["reason"])
        t = self.table()
        self.assertIn("0/0/3", t)
        self.assertNotIn("FLIP", t)
        self.assertIn("inconclusive", t)

    def test_one_capped_run_blocks_flip(self):
        self.run_flip(FakeRunner(script={1: "capped"}))
        t = self.table()
        self.assertIn("0/2/1", t)
        self.assertIn("inconclusive", t)
        self.assertNotIn("FLIP", t)

    def test_matrix_records_all_checks(self):
        self.run_flip(FakeRunner(), matrix=True)
        doc = self.load()
        self.assertTrue(all(set(x["checks"]) == {"code_len", "readme"} for x in doc["runs"]))
        t = self.table()
        self.assertIn("matrix", t)
        self.assertIn("readme", t)

    def test_missing_check_name_is_invalid(self):
        plant = dict(PLANT, check="not_a_check")
        self.run_flip(FakeRunner(), plants=[plant])
        self.assertTrue(all(not x["valid"] for x in self.load()["runs"]))

    def test_needs_check_cmd(self):
        old = os.environ.pop("DRYRUN_CHECK_CMD", None)
        try:
            with self.assertRaises(SystemExit):
                flip.run_flip([PLANT], TOY_DISK, 3, self.out, runner=FakeRunner())
        finally:
            if old is not None:
                os.environ["DRYRUN_CHECK_CMD"] = old


class TestPrintTable(FlipBase):
    def test_table_reads_only_the_file(self):
        self.run_flip(FakeRunner())
        self.assertIn("FLIP", self.table())
        # Edit the file on disk: the table must follow the file, not any memory of the run.
        doc = self.load()
        for x in doc["runs"]:
            x["pass"] = True
        with open(self.out, "w") as f:
            json.dump(doc, f)
        t = self.table()
        self.assertNotIn("FLIP", t)
        self.assertIn("3/0/0", t)
        self.assertNotIn("0/3/0", t)

    def test_table_from_handwritten_file_without_running(self):
        doc = {"params": {"runs": 2, "matrix": False, "plants": [{"id": "zz", "check": "c"}]},
               "runs": [{"plant": "zz", "arm": "with", "valid": True, "pass": True, "checks": {}},
                        {"plant": "zz", "arm": "with", "valid": True, "pass": True, "checks": {}},
                        {"plant": "zz", "arm": "without", "valid": True, "pass": True, "checks": {}},
                        {"plant": "zz", "arm": "without", "valid": True, "pass": True, "checks": {}}]}
        with open(self.out, "w") as f:
            json.dump(doc, f)
        t = self.table()
        self.assertIn("runs per arm: 2", t)
        self.assertIn("no flip", t)
        self.assertIn("2/0/0", t)

    def test_main_prints_via_print_table(self):
        calls = []
        orig_pt, orig_rf = flip.print_table, flip.run_flip
        flip.print_table = lambda path, file=None: calls.append(("print", path))
        flip.run_flip = lambda *a, **k: calls.append(("run", a[3])) or a[3]
        try:
            plants = os.path.join(self.d, "plants.json")
            with open(plants, "w") as f:
                json.dump([PLANT], f)
            flip.main(["--plants", plants, "--disk-template", TOY_DISK, "--to-step", "3", "--out", self.out])
        finally:
            flip.print_table, flip.run_flip = orig_pt, orig_rf
        self.assertEqual(calls, [("run", self.out), ("print", self.out)])


class TestParseResult(unittest.TestCase):
    def test_last_line_only(self):
        self.assertEqual(flip.parse_result('noise\nRESULT {"a": 1}\n\n'), {"a": 1})
        self.assertIsNone(flip.parse_result('RESULT {"a": 1}\nlater line'))
        self.assertIsNone(flip.parse_result("RESULT {bad"))
        self.assertIsNone(flip.parse_result(""))


if __name__ == "__main__":
    unittest.main()
