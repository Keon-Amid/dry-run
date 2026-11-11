"""Regression tests for the Phase 3 red-team findings (R1 plan-vs-code, R2 gaming)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from builder import convo, gitops, local, state
from builder.types import State

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(REPO, "builder", "tests", "fixtures", "toy")
SCRIPT = os.path.join(FIX, "fake_script.json")


def tu(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def turn(*blocks, stop="tool_use"):
    return {"content": list(blocks), "stop_reason": stop}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.disk = os.path.join(self.tmp, "disk")
        shutil.copytree(os.path.join(FIX, "disk"), self.disk)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def script(self, steps):
        path = os.path.join(self.tmp, f"s{len(os.listdir(self.tmp))}.json")
        with open(path, "w") as f:
            json.dump({"steps": {str(k): v for k, v in steps.items()}}, f)
        return path

    def run_cli(self, *args, env=None, disk=None):
        p = subprocess.run([sys.executable, "-m", "builder.run", "--disk", disk or self.disk, *args], cwd=REPO,
                           capture_output=True, text=True, timeout=120, env=env)
        lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
        self.assertTrue(lines and lines[-1].startswith("RESULT "), p.stdout + p.stderr)
        return p.returncode, json.loads(lines[-1][7:])

    def patch_file(self, **kw):
        d = {"route": "r1", "kind": "spec_line", "step": 2, "old": None, "new": None, "rule": None,
             "hypothesis": "h"}
        d.update(kw)
        path = os.path.join(self.tmp, "patch.json")
        with open(path, "w") as f:
            json.dump(d, f)
        return path

    def log_text(self, disk=None):
        with open(os.path.join(disk or self.disk, "conversation.jsonl")) as f:
            return f.read()


class Secrets(Base):
    def test_secrets_not_visible_to_agent_bash_or_parent_env(self):
        out = "env.txt"
        s = self.script({1: [turn(tu("bash", command=f"env > {out}; ps eww -o command= -p $PPID >> {out}; "
                                                  f"git config --list >> {out} 2>&1; true"))]})
        env = dict(os.environ, ANTHROPIC_API_KEY="sk-SECRET-1", DRYRUN_CHECK_CMD="grader-SECRET-2",
                   FOO_TOKEN="tok-SECRET-3")
        code, res = self.run_cli("--from-step", "1", "--to-step", "1", "--fake-llm", s, env=env)
        self.assertEqual(code, 0, res)
        with open(os.path.join(self.disk, "workspace", out)) as f:
            text = f.read()
        self.assertTrue(text.strip())
        for secret in ("SECRET-1", "SECRET-2", "SECRET-3"):
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, self.log_text())

    def test_git_env_minimal(self):
        os.environ["ZZZ_API_KEY"] = "leak"
        try:
            self.assertNotIn("ZZZ_API_KEY", gitops._env())
        finally:
            del os.environ["ZZZ_API_KEY"]


class Invalid(Base):
    def test_max_tokens_and_refusal_mark_step_invalid(self):
        for stop in ("max_tokens", "refusal"):
            d = os.path.join(self.tmp, stop)
            shutil.copytree(os.path.join(FIX, "disk"), d)
            s = self.script({1: [turn({"type": "thinking", "thinking": "", "signature": "x"},
                                      tu("write_file", path="half.py", content="x"), stop=stop)]})
            code, res = self.run_cli("--from-step", "1", "--to-step", "2", "--fake-llm", s, disk=d)
            self.assertEqual(code, 2, (stop, res))
            self.assertTrue(res["capped"] and res["invalid"])
            self.assertFalse(os.path.exists(os.path.join(d, "workspace", "half.py")))   # truncated call not run
            self.assertNotIn("tool_use", self.log_text(d))

    def test_capped_is_sticky_across_processes(self):
        spin = turn(tu("bash", command="true"))
        s = self.script({1: [spin] * 6})
        code, _ = self.run_cli("--from-step", "1", "--to-step", "1", "--max-calls", "2", "--fake-llm", s)
        self.assertEqual(code, 2)
        code, res = self.run_cli("--from-step", "2", "--to-step", "3", "--fake-llm", SCRIPT)
        self.assertEqual(code, 2)
        self.assertTrue(res["invalid"])
        self.assertEqual(res["last_done"], 1)   # nothing more was built on the capped disk

    def test_usage_error_is_exit_1_with_result(self):
        code, res = self.run_cli("--from-step", "1")
        self.assertEqual(code, 1)
        self.assertIn("usage", res["error"])
        self.assertFalse(res["capped"])


class Patches(Base):
    def setUp(self):
        super().setUp()
        code, _ = self.run_cli("--from-step", "1", "--to-step", "1", "--fake-llm", SCRIPT)
        self.assertEqual(code, 0)

    def test_patch_beyond_to_step_rejected(self):
        p = self.patch_file(step=3, old="Add `README.md`", new="Add `NOTES.md`")
        code, res = self.run_cli("--from-step", "2", "--to-step", "2", "--patch", p, "--fake-llm", SCRIPT)
        self.assertEqual(code, 1)
        self.assertIn("beyond --to-step", res["error"])

    def test_patch_before_from_step_warns(self):
        p = self.patch_file(step=1, old='prints "hello"', new='prints "hi"')
        code, res = self.run_cli("--from-step", "2", "--to-step", "2", "--patch", p, "--fake-llm", SCRIPT)
        self.assertEqual(code, 0, res)
        self.assertIn("patch_warning", res)

    def test_crash_between_patch_and_state_does_not_double_apply(self):
        from builder import patch as patchmod
        p = self.patch_file(old="Codes are 6 digits.", new="Codes are exactly 6 digits.")
        st = state.load(self.disk)
        st.patch_id, st.patch_applied, st.spec_sha_before = "r1", False, patchmod.spec_sha(self.disk)
        state.save(self.disk, st)                                      # pending marker written ...
        patchmod.apply(self.disk, patchmod.load_patch(p), write_route=False)   # ... edit landed, then crash
        code, res = self.run_cli("--from-step", "2", "--to-step", "2", "--patch", p, "--fake-llm", SCRIPT)
        self.assertEqual(code, 0, res)
        with open(os.path.join(self.disk, "spec.md")) as f:
            spec = f.read()
        self.assertIn("Codes are exactly 6 digits.", spec)
        self.assertNotIn("exactly exactly", spec)
        self.assertTrue(res["patch_applied"])
        self.assertTrue(any("not re-applied" in r for r in res["repairs"]))

    def test_route_note_not_on_disk_while_agent_runs(self):
        s = self.script({2: [turn(tu("bash", command="ls ../routes 2>&1; cat ../routes/*.md 2>&1; true"))]})
        p = self.patch_file(old="Codes are 6 digits.", new="Codes are 8 digits.", hypothesis="HYPO-SECRET")
        code, res = self.run_cli("--from-step", "2", "--to-step", "2", "--patch", p, "--fake-llm", s)
        self.assertEqual(code, 0, res)
        self.assertNotIn("HYPO-SECRET", self.log_text())
        self.assertNotIn("6 digits", self.log_text())
        with open(os.path.join(self.disk, "routes", "r1.md")) as f:
            note = f.read()
        self.assertIn("HYPO-SECRET", note)       # written after the run
        self.assertIn("## Result", note)


class Spec(Base):
    def test_bad_step_headers_rejected(self):
        path = os.path.join(self.disk, "spec.md")
        with open(path) as f:
            text = f.read()
        with open(path, "w") as f:
            f.write(text.replace("## Step 2", "### Step 2"))
        code, res = self.run_cli("--from-step", "1", "--to-step", "3", "--fake-llm", SCRIPT)
        self.assertEqual(code, 1)
        self.assertIn("[2]", res["error"])


class Git(Base):
    def test_ignored_files_are_not_a_false_repair(self):
        s = self.script({1: [turn(tu("write_file", path=".gitignore", content="build/\n"),
                                  tu("bash", command="mkdir -p build && echo x > build/out.bin"))]})
        self.run_cli("--from-step", "1", "--to-step", "1", "--fake-llm", s)
        code, res = self.run_cli("--from-step", "2", "--to-step", "2", "--fake-llm", SCRIPT)
        self.assertEqual(code, 0, res)
        self.assertEqual(res["repairs"], [])
        self.assertTrue(os.path.exists(os.path.join(self.disk, "workspace", "build", "out.bin")))

    def test_agent_git_commits_and_nested_repo_squashed(self):
        cmd = ("echo a > a.txt && git add a.txt && git -c user.name=x -c user.email=x@x commit -qm mine && "
               "git tag step-7 && mkdir sub && cd sub && git init -q && echo b > b.txt")
        s = self.script({1: [turn(tu("bash", command=cmd))]})
        code, res = self.run_cli("--from-step", "1", "--to-step", "1", "--fake-llm", s)
        self.assertEqual(code, 0, res)
        ws = os.path.join(self.disk, "workspace")
        log = subprocess.run(["git", "-C", ws, "log", "--format=%s"], capture_output=True, text=True).stdout
        self.assertEqual(log.split(), ["step", "1", "step", "0"])
        tags = subprocess.run(["git", "-C", ws, "tag"], capture_output=True, text=True).stdout.split()
        self.assertEqual(sorted(tags), ["step-0", "step-1"])
        files = subprocess.run(["git", "-C", ws, "ls-files"], capture_output=True, text=True).stdout.split()
        self.assertIn("sub/b.txt", files)

    def test_preexisting_workspace_files_are_in_c0(self):
        os.makedirs(os.path.join(self.disk, "workspace"))
        with open(os.path.join(self.disk, "workspace", "starter.py"), "w") as f:
            f.write("x = 1\n")
        gitops.init_workspace(self.disk)
        self.assertEqual(gitops.repair(self.disk, 0), [])
        files = subprocess.run(["git", "-C", os.path.join(self.disk, "workspace"), "ls-files", "--with-tree",
                                "step-0"], capture_output=True, text=True).stdout.split()
        self.assertIn("starter.py", files)


def _load_flip():
    spec = importlib.util.spec_from_file_location("flip", os.path.join(REPO, "scripts", "flip.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Flip(Base):
    def test_zero_runs_is_never_flip(self):
        flip = _load_flip()
        z = {"pass": 0, "fail": 0, "invalid": 0}
        self.assertEqual(flip.verdict(z, z, 0), "inconclusive")
        with self.assertRaises(ValueError):
            flip.run_flip([], self.disk, 1, os.path.join(self.tmp, "f.json"), runs=0, check_cmd="x")

    def test_real_subprocess_runner_with_fake_llm(self):
        flip = _load_flip()
        grader = os.path.join(self.tmp, "grade.py")
        with open(grader, "w") as f:
            f.write("import json,os,sys\nws=sys.argv[1]\n"
                    "ok=os.path.exists(os.path.join(ws,'hello.py'))\n"
                    "print(json.dumps({'checks':{'hello':{'pass':ok,'msg':''}}}))\n")
        plants = [{"id": "p1", "check": "hello",
                   "patch": {"route": "p1", "kind": "control", "step": 1, "old": None, "new": None,
                             "rule": None, "hypothesis": "control"}}]
        out = os.path.join(self.tmp, "flip.json")
        flip.run_flip(plants, self.disk, 1, out, runs=1, fake_llm=SCRIPT,
                      check_cmd=f"{sys.executable} {grader}")
        with open(out) as f:
            doc = json.load(f)
        self.assertEqual(len(doc["runs"]), 2)
        self.assertTrue(all(r["valid"] and r["pass"] for r in doc["runs"]), doc["runs"])


if __name__ == "__main__":
    unittest.main()


class KeyHandoff(unittest.TestCase):
    def test_child_reads_key_from_pipe_into_llm_and_env_is_cleared(self):
        from builder import run
        from builder.llm import AnthropicLLM
        r, w = os.pipe()
        os.write(w, b"sk-pipe-key")
        os.close(w)
        saved = dict(os.environ)
        try:
            os.environ.update(DRYRUN_CLEAN="1", DRYRUN_KEY_FD=str(r))
            os.environ.pop("ANTHROPIC_API_KEY", None)
            run.reexec_clean()
            llm = AnthropicLLM(model="m")
            run.scrub_env(llm)
            self.assertEqual(llm._key, "sk-pipe-key")
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
            self.assertNotIn("DRYRUN_KEY_FD", os.environ)
        finally:
            os.environ.clear()
            os.environ.update(saved)
