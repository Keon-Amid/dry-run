"""Tests for the dungeon demo: golden passes all but the decoy, plant patches land, plants own their checks."""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
from demo_game import grade  # noqa: E402  (this folder's copy: checks from demo_game/)


def plants():
    with open(os.path.join(HERE, "plants.json")) as f:
        return json.load(f)


class DungeonDemoTest(unittest.TestCase):
    def test_grader_reads_this_folder(self):
        self.assertEqual(grade.CHECKS_DIR, os.path.join(HERE, "checks"))

    def test_golden_passes_all_but_decoy(self):
        res = grade.grade(os.path.join(HERE, "golden", "workspace"), grade.load_checks())
        self.assertEqual(sorted(n for n, r in res.items() if not r["pass"]), ["actions_uppercase"], res)

    def test_each_plant_owns_one_visible_check_and_one_heldout(self):
        checks = grade.load_checks()
        ps = plants()
        self.assertEqual(len({p["check"] for p in ps}), len(ps))
        for p in ps:
            self.assertFalse(checks[p["check"]]["heldout"])
            f = checks[p["check"]]["file"]
            held = [n for n, c in checks.items() if c["heldout"] and c["file"] == f]
            self.assertEqual(len(held), 1, (p["id"], held))

    def test_each_plant_patch_lands(self):
        from builder import patch as bpatch
        from builder.types import Patch
        for p in plants():
            tmp = tempfile.mkdtemp(prefix="test-dplant-")
            try:
                disk = os.path.join(tmp, "disk")
                shutil.copytree(os.path.join(HERE, "disk"), disk)
                before, after = bpatch.apply(disk, Patch.from_dict(p["patch"]), write_route=False)
                if p["patch"]["kind"] == "spec_line":
                    self.assertNotEqual(before, after, p["id"])
                else:
                    self.assertFalse(os.path.exists(os.path.join(disk, "rules", p["patch"]["rule"])))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    def test_no_check_on_the_agent_disk(self):
        names = set(grade.load_checks())
        for d, _, fs in os.walk(os.path.join(HERE, "disk")):
            for f in fs:
                self.assertNotIn(f[:-3], names)


if __name__ == "__main__":
    unittest.main()
