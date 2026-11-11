"""C3: builder.patch tests. Run on a tempdir copy of the toy fixture disk."""
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from builder import patch
from builder.types import Patch, PatchError

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "toy", "disk")

SPEC_DUP = (
    "# Toy spec\n\n"
    "## Step 1\nCodes are 6 digits.\nCreate `hello.py`.\n\n"
    "## Step 2\nCodes are 6 digits. Add `code.py`.\n\n"
    "## Step 3\nAdd `README.md`. Add `README.md`.\n"
)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def P(**kw):
    d = dict(route="r1", kind="spec_line", step=None, old=None, new=None, rule=None, hypothesis="h")
    d.update(kw)
    return Patch(**d)


class PatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.disk = os.path.join(self.tmp, "disk")
        shutil.copytree(FIXTURE, self.disk)
        self.spec = os.path.join(self.disk, "spec.md")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def read(self, rel="spec.md"):
        with open(os.path.join(self.disk, rel), "rb") as f:
            return f.read()

    def write_spec(self, s):
        with open(self.spec, "w", encoding="utf-8") as f:
            f.write(s)

    def walk_files(self):
        out = []
        for root, dirs, files in os.walk(self.disk):
            out += [os.path.join(root, x) for x in dirs + files]
        return out

    # spec_sha / load_patch
    def test_spec_sha_is_sha256_of_bytes(self):
        self.assertEqual(patch.spec_sha(self.disk), sha(self.read()))

    def test_load_patch(self):
        pf = os.path.join(self.tmp, "p.json")
        with open(pf, "w") as f:
            json.dump({"route": "s2-a1", "kind": "spec_line", "step": 2, "old": "6", "new": "4",
                       "rule": None, "hypothesis": "hyp"}, f)
        p = patch.load_patch(pf)
        self.assertEqual((p.route, p.kind, p.step, p.old, p.new, p.hypothesis),
                         ("s2-a1", "spec_line", 2, "6", "4", "hyp"))
        with open(pf, "w") as f:
            json.dump({"route": "x", "kind": "bogus"}, f)
        with self.assertRaises(PatchError):
            patch.load_patch(pf)

    # spec_line
    def test_spec_line_edits_only_named_step(self):
        self.write_spec(SPEC_DUP)
        before = sha(self.read())
        b, a = patch.apply(self.disk, P(step=2, old="Codes are 6 digits.", new="Codes are 4 digits."))
        got = self.read().decode()
        self.assertEqual(got, SPEC_DUP.replace("Codes are 6 digits. Add", "Codes are 4 digits. Add"))
        self.assertIn("## Step 1\nCodes are 6 digits.", got)  # same text in step 1 untouched
        self.assertEqual(b, before)
        self.assertEqual(a, sha(self.read()))
        self.assertNotEqual(a, b)

    def test_spec_line_on_real_fixture(self):
        b, a = patch.apply(self.disk, P(step=2, old="Codes are 6 digits. ", new=""))
        self.assertNotIn(b"Codes are 6 digits", self.read())
        self.assertEqual(a, patch.spec_sha(self.disk))

    def test_spec_line_zero_matches_in_section(self):
        self.write_spec(SPEC_DUP)
        orig = self.read()
        # text exists in step 1 but not in step 3 -> 0 matches in the section
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(step=3, old="Codes are 6 digits.", new="x"))
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(step=2, old="nowhere at all", new="x"))
        self.assertEqual(self.read(), orig)
        self.assertFalse(os.path.exists(os.path.join(self.disk, "routes")))

    def test_spec_line_two_matches_in_section(self):
        self.write_spec(SPEC_DUP)
        orig = self.read()
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(step=3, old="Add `README.md`.", new="x"))
        self.assertEqual(self.read(), orig)

    def test_spec_line_missing_step(self):
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(step=9, old="hello", new="x"))

    def test_step_1_does_not_match_step_10(self):
        s = "## Step 1\nalpha\n\n## Step 10\nbeta\n"
        self.write_spec(s)
        patch.apply(self.disk, P(step=1, old="alpha", new="gamma"))
        self.assertEqual(self.read().decode(), "## Step 1\ngamma\n\n## Step 10\nbeta\n")
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(step=1, old="beta", new="x"))

    def test_new_empty_deletes(self):
        self.write_spec(SPEC_DUP)
        patch.apply(self.disk, P(step=2, old="Codes are 6 digits. ", new=""))
        self.assertEqual(self.read().decode(), SPEC_DUP.replace("Codes are 6 digits. Add", "Add"))

    def test_spec_line_noop_rejected(self):
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(step=2, old="6 digits", new="6 digits"))

    # landed-assert
    def test_landed_assert_spec_line(self):
        orig = self.read()
        with mock.patch.object(patch, "_write_bytes", lambda path, data: None):
            with self.assertRaises(PatchError):
                patch.apply(self.disk, P(step=2, old="6 digits", new="4 digits"))
        self.assertEqual(self.read(), orig)
        self.assertFalse(os.path.exists(os.path.join(self.disk, "routes")))

    def test_landed_assert_rule_off(self):
        with mock.patch.object(patch, "_remove", lambda path: None):
            with self.assertRaises(PatchError):
                patch.apply(self.disk, P(kind="rule_off", rule="style.md"))

    # rule_off
    def test_rule_off_deletes_without_copy(self):
        content = self.read("rules/style.md")
        b, a = patch.apply(self.disk, P(kind="rule_off", rule="style.md", route="rule-style"))
        self.assertFalse(os.path.lexists(os.path.join(self.disk, "rules", "style.md")))
        self.assertEqual(b, a)
        for path in self.walk_files():
            self.assertNotIn(".off", os.path.basename(path))
            if os.path.isfile(path) and not path.endswith(os.path.join("routes", "rule-style.md")):
                with open(path, "rb") as f:
                    self.assertNotIn(content.strip(), f.read(), path)
        names = sorted(os.path.relpath(x, self.disk) for x in self.walk_files())
        self.assertEqual(names, ["routes", os.path.join("routes", "rule-style.md"), "rules", "spec.md"])

    def test_rule_off_missing(self):
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(kind="rule_off", rule="nope.md"))

    def test_rule_off_rejects_paths(self):
        for bad in ("../spec.md", "sub/style.md", "..", ".", "a\\b", "", "/etc/passwd", "..style.md"):
            with self.assertRaises(PatchError, msg=bad):
                patch.apply(self.disk, P(kind="rule_off", rule=bad))
        self.assertTrue(os.path.exists(self.spec))
        self.assertTrue(os.path.exists(os.path.join(self.disk, "rules", "style.md")))

    # control
    def test_control_rewrites_identical_bytes_same_path(self):
        orig = self.read()
        calls = []
        real = patch._write_bytes

        def spy(path, data):
            calls.append((path, data))
            real(path, data)

        with mock.patch.object(patch, "_write_bytes", spy):
            b, a = patch.apply(self.disk, P(kind="control", route="ctl", step=2, old="6 digits"))
        self.assertEqual(b, a)
        self.assertEqual(b, sha(orig))
        self.assertEqual(self.read(), orig)
        self.assertEqual(calls[0], (self.spec, orig))  # went through the spec writer
        self.assertTrue(os.path.exists(os.path.join(self.disk, "routes", "ctl.md")))

    def test_control_without_old(self):
        orig = self.read()
        b, a = patch.apply(self.disk, P(kind="control", route="ctl2"))
        self.assertEqual((b, a), (sha(orig), sha(orig)))

    def test_control_validates_match(self):
        with self.assertRaises(PatchError):
            patch.apply(self.disk, P(kind="control", step=2, old="not there"))

    # routes
    def test_route_file_written(self):
        p = P(route="s2-a1", step=2, old="6 digits", new="4 digits", hypothesis="six vs four confuses it")
        b, a = patch.apply(self.disk, p)
        md = self.read("routes/s2-a1.md").decode()
        self.assertIn("six vs four confuses it", md)
        self.assertIn(b, md)
        self.assertIn(a, md)
        blob = md.split("```json\n", 1)[1].split("\n```", 1)[0]
        d = json.loads(blob)
        self.assertEqual(d, {"route": "s2-a1", "kind": "spec_line", "step": 2, "old": "6 digits",
                             "new": "4 digits", "rule": None, "hypothesis": "six vs four confuses it"})
        self.assertEqual(Patch.from_dict(d), p)

    def test_route_rejects_paths(self):
        orig = self.read()
        for bad in ("../x", "a/b", "..", "a\\b", "", "/abs"):
            with self.assertRaises(PatchError, msg=bad):
                patch.apply(self.disk, P(route=bad, step=2, old="6 digits", new="4 digits"))
        self.assertEqual(self.read(), orig)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x.md")))


if __name__ == "__main__":
    unittest.main()
