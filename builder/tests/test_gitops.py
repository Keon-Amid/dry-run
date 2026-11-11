import os
import subprocess
import tempfile
import unittest
from unittest import mock

from builder import convo, gitops
from builder.types import WORKSPACE, ResumeError


class GitopsTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.disk = self._td.name
        self.ws = os.path.join(self.disk, WORKSPACE)

    def tearDown(self):
        self._td.cleanup()

    def git(self, *a):
        return gitops._git(self.disk, *a).stdout.strip()

    def write(self, rel, s):
        p = os.path.join(self.ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(s)

    def build(self, n):
        gitops.init_workspace(self.disk)
        for k in range(1, n + 1):
            self.write(f"f{k}.txt", str(k))
            gitops.commit_step(self.disk, k)
            convo.append_step(self.disk, k, [{"role": "user", "content": f"s{k}"}])

    def test_init_creates_and_is_idempotent(self):
        self.assertFalse(os.path.exists(self.ws))
        sha = gitops.init_workspace(self.disk)
        self.assertTrue(os.path.isdir(os.path.join(self.ws, ".git")))
        self.assertEqual(gitops.tag_sha(self.disk, 0), sha)
        self.assertEqual(self.git("log", "--format=%s"), "step 0")
        self.assertEqual(gitops.init_workspace(self.disk), sha)
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")

    def test_identity_ignores_user_config(self):
        home = os.path.join(self.disk, "home")
        os.makedirs(home)
        with open(os.path.join(home, ".gitconfig"), "w") as f:
            f.write("[user]\n\tname = Someone Else\n\temail = x@y\n[commit]\n\tgpgsign = true\n")
        with mock.patch.dict(os.environ, {"HOME": home, "GIT_AUTHOR_NAME": "evil"}):
            gitops.init_workspace(self.disk)
            gitops.commit_step(self.disk, 1)
        self.assertEqual(self.git("log", "-1", "--format=%an <%ae> | %cn <%ce>"),
                         "builder <builder@dryrun.local> | builder <builder@dryrun.local>")

    def test_commit_step_and_tags(self):
        self.build(2)
        self.assertEqual(gitops.tag_sha(self.disk, 2), gitops.head(self.disk))
        self.assertEqual(self.git("log", "--format=%s"), "step 2\nstep 1\nstep 0")
        self.assertIsNone(gitops.tag_sha(self.disk, 3))
        # empty step still makes a commit
        sha = gitops.commit_step(self.disk, 3)
        self.assertEqual(gitops.tag_sha(self.disk, 3), sha)
        self.assertNotEqual(sha, gitops.tag_sha(self.disk, 2))

    def test_delete_tags_after_and_reset_to(self):
        self.build(3)
        self.write("junk/x.pyc", "j")
        gitops.reset_to(self.disk, 1)
        self.assertEqual(gitops.head(self.disk), gitops.tag_sha(self.disk, 1))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "f2.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "junk")))
        self.assertEqual(self.git("tag", "--list"), "step-0\nstep-1")
        self.assertEqual(gitops.delete_tags_after(self.disk, 1), [])

    def test_delete_tags_numeric_not_lexical(self):
        gitops.init_workspace(self.disk)
        for k in (1, 2, 10):
            gitops.commit_step(self.disk, k)
        self.assertEqual(gitops.delete_tags_after(self.disk, 2), ["step-10"])

    def test_repair_consistent_returns_empty(self):
        self.build(2)
        self.assertEqual(gitops.repair(self.disk, 2), [])
        self.assertEqual(convo.max_step(self.disk), 2)

    def test_repair_log_ahead_of_state(self):
        self.build(2)
        convo.append_step(self.disk, 3, [{"role": "user", "content": "s3"}, {"role": "assistant", "content": "x"}])
        actions = gitops.repair(self.disk, 2)
        self.assertEqual(len(actions), 1)
        self.assertIn("truncated", actions[0])
        self.assertEqual(convo.max_step(self.disk), 2)
        self.assertEqual(gitops.head(self.disk), gitops.tag_sha(self.disk, 2))

    def test_repair_head_ahead_of_tag(self):
        self.build(2)
        good = gitops.tag_sha(self.disk, 2)
        # crash after commit+tag of step 3, before log append and state save
        self.write("f3.txt", "3")
        gitops.commit_step(self.disk, 3)
        self.write("untracked.txt", "u")
        self.write("build/out.o", "o")
        with open(os.path.join(self.ws, ".gitignore"), "w") as f:
            f.write("build/\n")
        actions = gitops.repair(self.disk, 2)
        self.assertTrue(any("reset --hard" in a for a in actions), actions)
        self.assertTrue(any("step-3" in a and "stale" in a for a in actions), actions)
        self.assertEqual(gitops.head(self.disk), good)
        self.assertIsNone(gitops.tag_sha(self.disk, 3))
        for gone in ("f3.txt", "untracked.txt", "build", ".gitignore"):
            self.assertFalse(os.path.exists(os.path.join(self.ws, gone)), gone)
        self.assertEqual(self.git("status", "--porcelain", "--ignored"), "")
        self.assertEqual(gitops.repair(self.disk, 2), [])

    def test_repair_both_crashes(self):
        self.build(1)
        self.write("f2.txt", "2")
        gitops.commit_step(self.disk, 2)
        convo.append_step(self.disk, 2, [{"role": "user", "content": "s2"}])
        actions = gitops.repair(self.disk, 1)
        self.assertEqual(len(actions), 3, actions)
        self.assertEqual(convo.max_step(self.disk), 1)
        self.assertEqual(gitops.head(self.disk), gitops.tag_sha(self.disk, 1))

    def test_repair_dirty_tree_at_right_head(self):
        self.build(1)
        self.write("f1.txt", "edited")
        self.write("new.txt", "n")
        actions = gitops.repair(self.disk, 1)
        self.assertEqual(len(actions), 1, actions)
        with open(os.path.join(self.ws, "f1.txt")) as f:
            self.assertEqual(f.read(), "1")
        self.assertFalse(os.path.exists(os.path.join(self.ws, "new.txt")))

    def test_repair_missing_tag_raises(self):
        self.build(1)
        with self.assertRaises(ResumeError):
            gitops.repair(self.disk, 2)
        self.git("tag", "-d", "step-1")
        with self.assertRaises(ResumeError):
            gitops.repair(self.disk, 1)

    def test_repair_no_repo_raises(self):
        with self.assertRaises(ResumeError):
            gitops.repair(self.disk, 0)


if __name__ == "__main__":
    unittest.main()
