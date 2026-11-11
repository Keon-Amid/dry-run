import os
import tempfile
import time
import unittest
from unittest import mock

from builder import tools
from builder.tools import MAX_OUT, TOOL_SCHEMAS, LocalExec, PathEscape, dispatch


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.ws = os.path.join(self.root, "workspace")
        self.outside = os.path.join(self.root, "outside")
        os.makedirs(self.ws)
        os.makedirs(self.outside)
        with open(os.path.join(self.outside, "secret.txt"), "w") as f:
            f.write("SECRET")
        self.ex = LocalExec(self.ws)

    def tearDown(self):
        self.tmp.cleanup()


class TestPaths(Base):
    def test_dotdot_rejected_read_and_write(self):
        with self.assertRaises(PathEscape):
            self.ex.read_file("../outside/secret.txt")
        with self.assertRaises(PathEscape):
            self.ex.write_file("../x", "nope")
        self.assertFalse(os.path.exists(os.path.join(self.root, "x")))
        with self.assertRaises(PathEscape):
            self.ex.list_files("..")

    def test_absolute_outside_rejected(self):
        with self.assertRaises(PathEscape):
            self.ex.read_file(os.path.join(self.outside, "secret.txt"))
        with self.assertRaises(PathEscape):
            self.ex.write_file(os.path.join(self.outside, "new.txt"), "nope")
        self.assertFalse(os.path.exists(os.path.join(self.outside, "new.txt")))
        with self.assertRaises(PathEscape):
            self.ex.read_file("/etc/passwd")

    def test_absolute_inside_allowed(self):
        self.ex.write_file(os.path.join(self.ws, "a.txt"), "hi")
        self.assertEqual(self.ex.read_file("a.txt"), "hi")

    def test_symlink_file_out_rejected(self):
        os.symlink(os.path.join(self.outside, "secret.txt"), os.path.join(self.ws, "link"))
        with self.assertRaises(PathEscape):
            self.ex.read_file("link")
        with self.assertRaises(PathEscape):
            self.ex.write_file("link", "overwritten")
        with open(os.path.join(self.outside, "secret.txt")) as f:
            self.assertEqual(f.read(), "SECRET")

    def test_symlink_dir_out_rejected(self):
        os.symlink(self.outside, os.path.join(self.ws, "dirlink"))
        with self.assertRaises(PathEscape):
            self.ex.read_file("dirlink/secret.txt")
        with self.assertRaises(PathEscape):
            self.ex.write_file("dirlink/new.txt", "nope")
        self.assertFalse(os.path.exists(os.path.join(self.outside, "new.txt")))
        with self.assertRaises(PathEscape):
            self.ex.list_files("dirlink")
        # Listing the root must not walk through the link either.
        self.assertNotIn("secret.txt", self.ex.list_files("."))

    def test_dangling_symlink_out_rejected_on_write(self):
        os.symlink(os.path.join(self.outside, "ghost.txt"), os.path.join(self.ws, "ghost"))
        with self.assertRaises(PathEscape):
            self.ex.write_file("ghost", "nope")
        self.assertFalse(os.path.exists(os.path.join(self.outside, "ghost.txt")))

    def test_sibling_prefix_not_confused(self):
        # /root/workspace2 shares a string prefix with /root/workspace but is outside.
        os.makedirs(self.ws + "2")
        with self.assertRaises(PathEscape):
            self.ex.write_file(self.ws + "2/x", "nope")


class TestFiles(Base):
    def test_write_creates_parents_and_reads_back(self):
        msg = self.ex.write_file("a/b/c.txt", "hello")
        self.assertIn("5 bytes", msg)
        with open(os.path.join(self.ws, "a", "b", "c.txt")) as f:
            self.assertEqual(f.read(), "hello")
        self.assertEqual(self.ex.read_file("a/b/c.txt"), "hello")

    def test_read_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.ex.read_file("nope.txt")

    def test_read_truncated(self):
        self.ex.write_file("big.txt", "x" * 10000)
        out = self.ex.read_file("big.txt")
        self.assertLessEqual(len(out), MAX_OUT)
        self.assertIn("truncated", out)
        self.assertTrue(out.startswith("x" * 100))

    def test_list_skips_git_and_is_relative(self):
        self.ex.write_file("src/main.py", "")
        self.ex.write_file("README.md", "")
        self.ex.write_file(".git/HEAD", "ref")
        self.ex.write_file(".git/objects/ab", "")
        out = self.ex.list_files()
        lines = out.splitlines()
        self.assertIn("README.md", lines)
        self.assertIn(os.path.join("src", "main.py"), lines)
        self.assertNotIn(".git", out)
        self.assertEqual(self.ex.list_files("src").splitlines(), [os.path.join("src", "main.py")])

    def test_list_truncated(self):
        for i in range(400):
            self.ex.write_file(f"file_with_a_longish_name_{i:04d}.txt", "")
        out = self.ex.list_files()
        self.assertLessEqual(len(out), MAX_OUT)
        self.assertIn("truncated", out)


class TestBash(Base):
    def test_cwd_is_workspace(self):
        out = self.ex.bash("pwd")
        self.assertEqual(os.path.realpath(out.splitlines()[0]), self.ws)
        self.assertIn("[exit code 0]", out)

    def test_stdout_stderr_and_exit_code(self):
        out = self.ex.bash("echo out; echo err 1>&2; exit 3")
        self.assertIn("out", out)
        self.assertIn("err", out)
        self.assertTrue(out.endswith("[exit code 3]"))

    def test_runs_in_new_session(self):
        # start_new_session=True: the shell is its own process group leader.
        out = self.ex.bash('ps -o pgid= -p $$; echo $$')
        pgid, pid = out.split()[:2]
        self.assertEqual(pgid, pid)
        self.assertNotEqual(int(pgid), os.getpgrp())

    def test_env_scrubbed(self):
        fake = {"ANTHROPIC_API_KEY": "sk-leak", "FOO_TOKEN": "tok-leak", "BAR_KEY": "key-leak",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/home/x", "LANG": "C"}
        with mock.patch.dict(os.environ, fake):
            out = self.ex.bash("env")
        names = {line.split("=", 1)[0] for line in out.splitlines() if "=" in line}
        for leak in ("ANTHROPIC_API_KEY", "FOO_TOKEN", "BAR_KEY"):
            self.assertNotIn(leak, names)
        self.assertNotIn("leak", out)
        self.assertIn("HOME", names)
        self.assertIn("PATH", names)
        # bash itself adds PWD, SHLVL and _; nothing else from the parent env survives.
        self.assertTrue(names <= {"PATH", "HOME", "LANG", "TMPDIR", "PWD", "SHLVL", "_", "OLDPWD"},
                        names)

    def test_timeout_kills_process_group(self):
        pidfile = os.path.join(self.root, "child.pid")
        t0 = time.time()
        out = self.ex.bash(f"sleep 60 & echo $! > {pidfile}; sleep 60", timeout=1)
        self.assertLess(time.time() - t0, 10)
        self.assertIn("timeout", out)
        with open(pidfile) as f:
            child = int(f.read().strip())
        deadline = time.time() + 3
        while pid_alive(child) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(pid_alive(child), "background child survived the timeout")

    def test_timeout_keeps_partial_output(self):
        out = self.ex.bash("echo before; sleep 60", timeout=1)
        self.assertIn("before", out)
        self.assertIn("timeout after 1s", out)

    def test_output_truncated_with_marker_keeps_exit_code(self):
        out = self.ex.bash("head -c 20000 /dev/zero | tr '\\0' 'a'; exit 7")
        self.assertLessEqual(len(out), MAX_OUT)
        self.assertIn("truncated", out)
        self.assertTrue(out.endswith("[exit code 7]"))

    def test_leftover_background_child_reaped(self):
        pidfile = os.path.join(self.root, "bg.pid")
        out = self.ex.bash(f"sleep 60 >/dev/null 2>&1 & echo $! > {pidfile}; echo ok")
        self.assertIn("[exit code 0]", out)
        with open(pidfile) as f:
            child = int(f.read().strip())
        deadline = time.time() + 3
        while pid_alive(child) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(pid_alive(child), "background child outlived the bash call")


class TestTruncate(unittest.TestCase):
    def test_short_unchanged(self):
        self.assertEqual(tools.truncate("abc"), "abc")

    def test_exact_limit(self):
        s = "a" * MAX_OUT
        self.assertEqual(tools.truncate(s), s)
        out = tools.truncate(s + "b")
        self.assertLessEqual(len(out), MAX_OUT)
        self.assertIn("truncated", out)


class TestDispatch(Base):
    def test_schemas(self):
        by_name = {t["name"]: t for t in TOOL_SCHEMAS}
        self.assertEqual(set(by_name), {"read_file", "write_file", "list_files", "bash"})
        for t in TOOL_SCHEMAS:
            self.assertEqual(t["input_schema"]["type"], "object")
            self.assertTrue(t["description"])
        self.assertEqual(by_name["read_file"]["input_schema"]["required"], ["path"])
        self.assertEqual(set(by_name["write_file"]["input_schema"]["required"]), {"path", "content"})
        self.assertEqual(by_name["list_files"]["input_schema"]["required"], [])
        self.assertEqual(by_name["bash"]["input_schema"]["required"], ["command"])

    def test_routes_each_tool(self):
        self.assertIn("bytes", dispatch(self.ex, "write_file", {"path": "d/f.txt", "content": "zz"}))
        self.assertEqual(dispatch(self.ex, "read_file", {"path": "d/f.txt"}), "zz")
        self.assertIn(os.path.join("d", "f.txt"), dispatch(self.ex, "list_files", {}))
        self.assertIn(os.path.join("d", "f.txt"), dispatch(self.ex, "list_files", {"path": "d"}))
        self.assertIn("hi", dispatch(self.ex, "bash", {"command": "echo hi"}))

    def test_unknown_tool(self):
        with self.assertRaises(ValueError):
            dispatch(self.ex, "rm_rf", {})

    def test_missing_or_bad_args(self):
        with self.assertRaises(ValueError):
            dispatch(self.ex, "read_file", {})
        with self.assertRaises(ValueError):
            dispatch(self.ex, "write_file", {"path": "x"})
        with self.assertRaises(ValueError):
            dispatch(self.ex, "bash", {})
        with self.assertRaises(ValueError):
            dispatch(self.ex, "bash", {"command": 5})
        with self.assertRaises(ValueError):
            dispatch(self.ex, "bash", None)
        self.assertFalse(os.path.exists(os.path.join(self.ws, "x")))

    def test_escape_surfaces_as_error(self):
        with self.assertRaises(ValueError):   # PathEscape is a ValueError
            dispatch(self.ex, "read_file", {"path": "../outside/secret.txt"})


if __name__ == "__main__":
    unittest.main()
