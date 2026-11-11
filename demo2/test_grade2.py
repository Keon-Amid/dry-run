"""Tests for demo2 (Dungeon Painter): checks, golden, flawed workspaces, plants, bundle, render. Stdlib, no API."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from demo2 import grade as g  # noqa: E402
from demo2 import render as rd  # noqa: E402

GOLDEN = os.path.join(HERE, "golden", "workspace")
DECOY = "hero_is_yellow"
REAL = ("ambiguity", "contradiction", "bad_rule")
HELDOUT_OF = {"ambiguity": "heldout_torch_light_corner", "contradiction": "heldout_cave_ring",
              "bad_rule": "heldout_hud_text_other"}

with open(os.path.join(HERE, "plants.json")) as f:
    PLANTS = json.load(f)
BY_ID = {p["id"]: p for p in PLANTS}
CHECKS = g.load_checks()
_cache = {}


def graded(ws):
    if ws not in _cache:
        _cache[ws] = g.grade(ws, CHECKS)
    return _cache[ws]


def failing(ws):
    return sorted(n for n, r in graded(ws).items() if not r["pass"])


def svg_root(text):
    root = ET.fromstring(text)
    for e in root.iter():
        e.tag = e.tag.split("}")[-1]
    return root


class ChecksTest(unittest.TestCase):
    def test_counts_and_meta(self):
        visible = [n for n, c in CHECKS.items() if not c["heldout"]]
        held = [n for n, c in CHECKS.items() if c["heldout"]]
        self.assertGreaterEqual(len(visible), 10)
        self.assertEqual(sorted(held), sorted(HELDOUT_OF.values()))
        for n, c in CHECKS.items():
            self.assertTrue(1 <= c["from_step"] <= 7, n)
            self.assertTrue(c["file"].startswith("workspace/"), n)

    def test_golden_passes_all_but_decoy(self):
        self.assertEqual(failing(GOLDEN), [DECOY], graded(GOLDEN))

    def test_decoy_fails_on_golden(self):
        self.assertFalse(graded(GOLDEN)[DECOY]["pass"])

    def test_empty_workspace_fails_every_check(self):
        tmp = tempfile.mkdtemp(prefix="demo2-empty-")
        try:
            res = g.grade(tmp, CHECKS)
            self.assertEqual(set(res), set(CHECKS))
            self.assertFalse([n for n, r in res.items() if r["pass"]])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_each_flawed_workspace_fails_exactly_its_own_checks(self):
        """The plant matrix is diagonal: each literal (flawed) reading breaks its check + held-out, nothing else."""
        for pid in REAL:
            ws = os.path.join(HERE, "flawed", pid)
            self.assertEqual(failing(ws), sorted([BY_ID[pid]["check"], HELDOUT_OF[pid], DECOY]), pid)

    def test_grading_steps(self):
        """Orchestrator mode on a disk holding golden: only checks checkable by step K run."""
        tmp = tempfile.mkdtemp(prefix="demo2-disk-")
        try:
            shutil.copytree(GOLDEN, os.path.join(tmp, "workspace"))
            out = subprocess.run([sys.executable, os.path.join(HERE, "grade.py"), "--disk", tmp, "--at-step", "1"],
                                 capture_output=True, text=True, timeout=120, check=True).stdout
            self.assertEqual(json.loads(out), {"parse_map_rows": True})
            meta = json.loads(subprocess.run([sys.executable, os.path.join(HERE, "grade.py"), "--meta"],
                                             capture_output=True, text=True, timeout=60, check=True).stdout)
            self.assertEqual(meta["cave_keeps_shape"], {"from_step": 5, "file": "workspace/tiles.py",
                                                        "heldout": False})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bundle_is_standalone(self):
        tmp = tempfile.mkdtemp(prefix="demo2-bundle-")
        try:
            out = os.path.join(tmp, "elsewhere", "checks_bundle.py")
            os.makedirs(os.path.dirname(out))
            subprocess.run([sys.executable, os.path.join(HERE, "grade.py"), "--bundle", out], check=True,
                           capture_output=True, timeout=60)
            disk = os.path.join(tmp, "disk")
            shutil.copytree(GOLDEN, os.path.join(disk, "workspace"))
            run = lambda *a: json.loads(subprocess.run([sys.executable, out, *a], capture_output=True, text=True,
                                                       cwd=tmp, timeout=120, check=True).stdout)
            res = run("--disk", disk, "--at-step", "7")
            self.assertEqual(set(res), set(CHECKS))
            self.assertEqual(sorted(n for n, ok in res.items() if not ok), [DECOY])
            self.assertEqual(run("--meta"), g.meta(CHECKS))
            self.assertEqual(sorted(os.listdir(os.path.join(disk, "workspace"))), sorted(os.listdir(GOLDEN)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_check_on_the_agent_disk(self):
        for d, _, fs in os.walk(os.path.join(HERE, "disk")):
            for f in fs:
                self.assertNotIn(f[:-3], CHECKS, os.path.join(d, f))
                self.assertFalse(f.startswith("test_") or f.endswith(".py"), os.path.join(d, f))


class PlantsTest(unittest.TestCase):
    def test_shape(self):
        for p in PLANTS:
            self.assertTrue({"id", "check", "patch"} <= set(p) <= {"id", "check", "patch", "expect"}, p)
            self.assertEqual(set(p["patch"]), {"route", "kind", "step", "old", "new", "rule", "hypothesis"})
            self.assertIn(p["check"], CHECKS)
            self.assertFalse(CHECKS[p["check"]]["heldout"], p["id"])
        self.assertEqual({p["id"] for p in PLANTS}, set(REAL) | {"control", "placebo"})

    def test_no_two_plants_share_a_check(self):
        checks = [p["check"] for p in PLANTS] + [DECOY]
        self.assertEqual(len(set(checks)), len(checks))

    def test_real_plants_pair_with_one_heldout_by_file(self):
        for pid in REAL:
            f_ = CHECKS[BY_ID[pid]["check"]]["file"]
            held = [n for n, c in CHECKS.items() if c["heldout"] and c["file"] == f_]
            self.assertEqual(held, [HELDOUT_OF[pid]], pid)

    def test_each_patch_applies_and_lands(self):
        from builder import patch as bpatch
        from builder.types import Patch
        for p in PLANTS:
            tmp = tempfile.mkdtemp(prefix="demo2-plant-")
            try:
                disk = os.path.join(tmp, "disk")
                shutil.copytree(os.path.join(HERE, "disk"), disk)
                kind = p["patch"]["kind"]
                before, after = bpatch.apply(disk, Patch.from_dict(p["patch"]), write_route=False)
                if kind == "spec_line":
                    self.assertNotEqual(before, after, p["id"])
                    with open(os.path.join(disk, "spec.md")) as f:
                        self.assertIn(p["patch"]["new"], f.read())
                elif kind == "rule_off":
                    self.assertEqual(before, after)
                    self.assertFalse(os.path.exists(os.path.join(disk, "rules", p["patch"]["rule"])))
                else:
                    self.assertEqual(before, after, p["id"])
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    def test_spec_has_seven_steps(self):
        import re
        with open(os.path.join(HERE, "disk", "spec.md")) as f:
            spec = f.read()
        self.assertEqual(re.findall(r"^## Step (\d+)", spec, re.M), [str(i) for i in range(1, 8)])
        self.assertEqual(sorted(os.listdir(os.path.join(HERE, "disk", "rules"))), ["portable.md", "style.md"])


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svg = {"golden": rd.render(GOLDEN)}
        for pid in REAL:
            cls.svg[pid] = rd.render(os.path.join(HERE, "flawed", pid))

    def test_everything_renders(self):
        for name, (svg, ok) in self.svg.items():
            self.assertTrue(ok, (name, svg[:300]))
            root = svg_root(svg)
            self.assertEqual((root.get("width"), root.get("height")), ("368", "180"), name)

    def _rects(self, name):
        return {(e.get("x"), e.get("y"), e.get("width"), e.get("fill")) for e in svg_root(self.svg[name][0]).iter("rect")}

    def test_each_plant_differs_visibly_from_golden(self):
        gold = self._rects("golden")
        # ambiguity: some floor behind the wall is lit
        lit = lambda n: {(x, y) for x, y, w, f in self._rects(n) if f == "#8a6d2f"}
        self.assertTrue(lit("ambiguity") - lit("golden"), "flawed light lights nothing extra")
        self.assertIn(("240", "64"), lit("ambiguity") - lit("golden"))  # (15, 4): the room behind the torch's wall
        # contradiction: the cave walls moved
        self.assertNotEqual(self._rects("contradiction"), gold)
        self.assertNotIn(("0", "0", "16", "#5b5b6b"), gold)
        self.assertIn(("0", "0", "16", "#5b5b6b"), self._rects("contradiction"))
        # bad rule: the label is gone
        texts = lambda n: ["".join(e.itertext()) for e in svg_root(self.svg[n][0]).iter("text")]
        self.assertEqual(len(texts("golden")), 1)
        self.assertEqual(texts("bad_rule"), [])

    def test_broken_build_gives_placeholder(self):
        tmp = tempfile.mkdtemp(prefix="demo2-broken-")
        try:
            with open(os.path.join(tmp, "scene.py"), "w") as f:
                f.write("def render_demo():\n    raise RuntimeError('boom')\n")
            svg, ok = rd.render(tmp)
            self.assertFalse(ok)
            self.assertIn("build failed", svg)
            self.assertIn("boom", svg)
            svg_root(svg)
            self.assertEqual(os.listdir(tmp), ["scene.py"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_side_by_side_html(self):
        tmp = tempfile.mkdtemp(prefix="demo2-sbs-")
        try:
            out = os.path.join(tmp, "out.html")
            p = subprocess.run([sys.executable, os.path.join(HERE, "render.py"), "--side-by-side",
                                os.path.join(HERE, "flawed", "ambiguity"), GOLDEN, out],
                               capture_output=True, text=True, timeout=180)
            self.assertEqual(p.returncode, 0, p.stderr)
            with open(out) as f:
                page = f.read()
            self.assertIn("base run", page)
            self.assertIn("after Banzai", page)
            self.assertEqual(page.count("data:image/svg+xml;base64,"), 2)
            self.assertIn("<b>torch_light_stops_at_walls</b>", page)  # failing in the base panel
            self.assertIn("12/15 checks pass", page)
            self.assertIn("14/15 checks pass", page)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
