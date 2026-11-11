"""C3: builder.local tests (copytree save/resume keeps git intact)."""
import os
import shutil
import subprocess
import tempfile
import unittest

from builder import local
from builder.types import ResumeError

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def git(cwd, *args):
    return subprocess.run(GIT + list(args), cwd=cwd, check=True, capture_output=True, text=True).stdout


class LocalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.disk = os.path.join(self.tmp, "disk")
        ws = os.path.join(self.disk, "workspace")
        os.makedirs(ws)
        with open(os.path.join(self.disk, "spec.md"), "w") as f:
            f.write("## Step 1\nx\n")
        git(ws, "init", "-q")
        with open(os.path.join(ws, "a.txt"), "w") as f:
            f.write("one\n")
        os.symlink("a.txt", os.path.join(ws, "link"))
        git(ws, "add", "-A")
        git(ws, "commit", "-q", "-m", "step 1")
        git(ws, "tag", "step-1")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_save_keeps_git_and_is_independent(self):
        dest = local.save(self.disk, os.path.join(self.tmp, "c1"))
        ws2 = os.path.join(dest, "workspace")
        self.assertEqual(git(ws2, "log", "--format=%s").strip(), "step 1")
        self.assertEqual(git(ws2, "rev-parse", "step-1"), git(os.path.join(self.disk, "workspace"), "rev-parse", "HEAD"))
        self.assertEqual(git(ws2, "status", "--porcelain"), "")
        self.assertTrue(os.path.islink(os.path.join(ws2, "link")))
        self.assertEqual(os.readlink(os.path.join(ws2, "link")), "a.txt")
        # independence: commit in the copy, original unchanged
        with open(os.path.join(ws2, "b.txt"), "w") as f:
            f.write("two\n")
        git(ws2, "add", "-A")
        git(ws2, "commit", "-q", "-m", "step 2")
        self.assertEqual(git(os.path.join(self.disk, "workspace"), "log", "--format=%s").strip(), "step 1")
        self.assertFalse(os.path.exists(os.path.join(self.disk, "workspace", "b.txt")))
        self.assertEqual(git(ws2, "log", "--format=%s").split(), ["step", "2", "step", "1"])

    def test_resume_fresh_copy(self):
        saved = local.save(self.disk, os.path.join(self.tmp, "c1"))
        r1 = local.resume(saved, os.path.join(self.tmp, "run1"))
        empty = os.path.join(self.tmp, "run2")
        os.makedirs(empty)
        r2 = local.resume(saved, empty)  # empty dest is allowed
        for r in (r1, r2):
            self.assertEqual(git(os.path.join(r, "workspace"), "log", "--format=%s").strip(), "step 1")
        with open(os.path.join(r1, "spec.md"), "w") as f:
            f.write("changed\n")
        with open(os.path.join(r2, "spec.md")) as f:
            self.assertEqual(f.read(), "## Step 1\nx\n")
        with open(os.path.join(saved, "spec.md")) as f:
            self.assertEqual(f.read(), "## Step 1\nx\n")

    def test_resume_refuses_nonempty_dest(self):
        dest = os.path.join(self.tmp, "busy")
        os.makedirs(dest)
        with open(os.path.join(dest, "keep"), "w") as f:
            f.write("k")
        with self.assertRaises(ResumeError):
            local.resume(self.disk, dest)
        self.assertEqual(os.listdir(dest), ["keep"])

    def test_save_refuses_nonempty_dest_and_missing_src(self):
        dest = local.save(self.disk, os.path.join(self.tmp, "c1"))
        with self.assertRaises(FileExistsError):
            local.save(self.disk, dest)
        with self.assertRaises(FileNotFoundError):
            local.save(os.path.join(self.tmp, "nope"), os.path.join(self.tmp, "c2"))

    def test_save_refuses_dest_inside_src(self):
        with self.assertRaises(ValueError):
            local.save(self.disk, os.path.join(self.disk, "inner"))


if __name__ == "__main__":
    unittest.main()
