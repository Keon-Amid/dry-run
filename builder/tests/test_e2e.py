"""End-to-end FakeLLM runs of builder.run: build, save at c_1, patch + resume, blind arm, capped turn."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from builder import convo, gitops, local, run, state
from builder.fake_llm import FakeLLM

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(REPO, "builder", "tests", "fixtures", "toy")
SCRIPT = os.path.join(FIX, "fake_script.json")


def run_proc(*args):
    p = subprocess.run([sys.executable, "-m", "builder.run", *args], cwd=REPO, capture_output=True, text=True,
                       timeout=120)
    last = [ln for ln in p.stdout.splitlines() if ln.strip()][-1]
    assert last.startswith("RESULT "), p.stdout + p.stderr
    return p.returncode, json.loads(last[len("RESULT "):]), p.stderr


def run_inproc(llm, *args):
    """Run builder.run.main in-process with a given LLM object; return (code, result, llm)."""
    orig = run.make_llm
    run.make_llm = lambda _s: llm
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = run.main(list(args))
    finally:
        run.make_llm = orig
    last = out.getvalue().strip().splitlines()[-1]
    return code, json.loads(last[len("RESULT "):])


def git(disk, *a):
    return subprocess.run(["git", "-C", os.path.join(disk, "workspace"), *a], capture_output=True, text=True,
                          check=True).stdout.strip()


class E2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.disk = os.path.join(self.tmp, "disk")
        shutil.copytree(os.path.join(FIX, "disk"), self.disk)
        self.c1 = os.path.join(self.tmp, "c1")
        # build: one process per step, save c_1 after step 1 (what P1's save(k) does)
        for k in (1, 2, 3):
            code, res, _ = run_proc("--disk", self.disk, "--from-step", str(k), "--to-step", str(k),
                                    "--fake-llm", SCRIPT)
            self.assertEqual(code, 0, res)
            if k == 1:
                local.save(self.disk, self.c1)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_three_steps(self):
        st = state.load(self.disk)
        self.assertEqual(st.last_done, 3)
        self.assertEqual([s.step for s in st.steps], [1, 2, 3])
        self.assertEqual(convo.max_step(self.disk), 3)
        self.assertEqual(gitops.head(self.disk), gitops.tag_sha(self.disk, 3))
        self.assertEqual(git(self.disk, "log", "--format=%s"), "step 3\nstep 2\nstep 1\nstep 0")
        for f in ("hello.py", "code.py", "README.md"):
            self.assertTrue(os.path.exists(os.path.join(self.disk, "workspace", f)))
        s1 = st.steps[0]
        self.assertEqual((s1.tool_calls, s1.model_calls, s1.capped), (2, 3, False))
        self.assertEqual(s1.usage, {"input_tokens": 120, "output_tokens": 30, "cache_creation_input_tokens": 50,
                                    "cache_read_input_tokens": 310})
        self.assertGreaterEqual(s1.wall_s, 0)
        self.assertTrue(st.model)
        # the read of ../spec.md was refused, as an is_error tool_result, not a crash
        log = open(os.path.join(self.disk, "conversation.jsonl")).read()
        self.assertIn('"is_error": true', log)
        # preamble (spec text) is never written to the log
        self.assertNotIn("Codes are 6 digits", log)

    def test_patch_and_resume_from_c1(self):
        b = os.path.join(self.tmp, "b")
        local.resume(self.c1, b)
        patch = os.path.join(self.tmp, "p.json")
        json.dump({"route": "s2-a1", "kind": "spec_line", "step": 2, "old": "Codes are 6 digits.",
                   "new": "Codes are 8 digits.", "rule": None, "hypothesis": "6 vs alias"}, open(patch, "w"))
        llm = FakeLLM.from_file(SCRIPT)
        code, res = run_inproc(llm, "--disk", b, "--from-step", "2", "--to-step", "3", "--patch", patch,
                               "--route", "s2-a1")
        self.assertEqual(code, 0, res)
        self.assertTrue(res["patch_applied"])
        self.assertNotEqual(res["spec_sha_before"], res["spec_sha_after"])
        self.assertEqual(res["last_done"], 3)
        # step 2's system prompt carries the new wording; history carries step 1 messages
        sys2, msgs2, _ = llm.calls[0]
        self.assertIn("Codes are 8 digits.", sys2[0]["text"])
        self.assertNotIn("6 digits", json.dumps(llm.calls))
        self.assertEqual(msgs2[0]["content"], "Do step 1.")
        self.assertEqual(convo.max_step(b), 3)
        self.assertEqual(gitops.head(b), gitops.tag_sha(b, 3))
        st = state.load(b)
        self.assertEqual((st.patch_id, st.patch_applied), ("s2-a1", True))
        self.assertEqual([s.step for s in st.steps], [1, 2, 3])
        self.assertTrue(os.path.exists(os.path.join(b, "routes", "s2-a1.md")))
        # the original build disk is untouched
        self.assertIn("Codes are 6 digits.", open(os.path.join(self.disk, "spec.md")).read())

    def test_patch_zero_matches_is_exit_1(self):
        b = os.path.join(self.tmp, "b")
        local.resume(self.c1, b)
        patch = os.path.join(self.tmp, "p.json")
        json.dump({"route": "bad", "kind": "spec_line", "step": 2, "old": "no such text", "new": "x",
                   "rule": None, "hypothesis": ""}, open(patch, "w"))
        code, res, _ = run_proc("--disk", b, "--from-step", "2", "--to-step", "3", "--patch", patch,
                                "--fake-llm", SCRIPT)
        self.assertEqual(code, 1)
        self.assertIn("PatchError", res["error"])
        self.assertEqual(res["last_done"], 1)

    def test_wrong_from_step_is_exit_1(self):
        b = os.path.join(self.tmp, "b")
        local.resume(self.c1, b)
        code, res, _ = run_proc("--disk", b, "--from-step", "3", "--to-step", "3", "--fake-llm", SCRIPT)
        self.assertEqual(code, 1)
        self.assertIn("ResumeError", res["error"])

    def test_blind_arm_drops_history_keeps_files(self):
        b = os.path.join(self.tmp, "b")
        local.resume(self.c1, b)
        llm = FakeLLM.from_file(SCRIPT)
        code, res = run_inproc(llm, "--disk", b, "--from-step", "2", "--to-step", "3", "--drop-conversation")
        self.assertEqual(code, 0, res)
        _, msgs, _ = llm.calls[0]
        self.assertEqual(msgs, [{"role": "user", "content": [{"type": "text", "text": "Do step 2.",
                                                              "cache_control": {"type": "ephemeral"}}]}])
        self.assertTrue(os.path.exists(os.path.join(b, "workspace", "hello.py")))
        # step 3 in the same process sees step 2 but still not step 1
        step3 = [c for c in llm.calls if "Do step 3." in json.dumps(c[1])][0][1]
        self.assertNotIn("Do step 1.", json.dumps(step3))
        self.assertIn("Do step 2.", json.dumps(step3))

    def test_crash_after_commit_before_state_is_repaired(self):
        b = os.path.join(self.tmp, "b")
        local.resume(self.c1, b)
        # simulate: step 2 committed + tagged and logged, but state.json still says last_done=1
        open(os.path.join(b, "workspace", "junk.txt"), "w").write("x")
        gitops.commit_step(b, 2)
        convo.append_step(b, 2, [{"role": "user", "content": "Do step 2."},
                                 {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}])
        code, res, _ = run_proc("--disk", b, "--from-step", "2", "--to-step", "2", "--fake-llm", SCRIPT)
        self.assertEqual(code, 0, res)
        self.assertTrue(res["repairs"])
        self.assertFalse(os.path.exists(os.path.join(b, "workspace", "junk.txt")))
        self.assertEqual(git(b, "log", "--format=%s"), "step 2\nstep 1\nstep 0")
        step2 = [r["msg"] for r in convo.load(b) if r["step"] == 2]
        self.assertEqual(len(step2), 6)  # user, 2 x (tool turn + results), final turn; stale record dropped
        self.assertNotIn('"text": "ok"', json.dumps(step2))


class Capped(unittest.TestCase):
    def test_capped_step_exit_2_and_valid_log(self):
        tmp = tempfile.mkdtemp()
        try:
            disk = os.path.join(tmp, "d")
            shutil.copytree(os.path.join(FIX, "disk"), disk)
            spin = {"content": [{"type": "tool_use", "name": "bash", "input": {"command": "true"}},
                                {"type": "tool_use", "name": "list_files", "input": {}}],
                    "stop_reason": "tool_use"}
            script = os.path.join(tmp, "s.json")
            json.dump({"steps": {"1": [spin] * 10}}, open(script, "w"))
            code, res, _ = run_proc("--disk", disk, "--from-step", "1", "--to-step", "2", "--max-calls", "3",
                                    "--fake-llm", script)
            self.assertEqual(code, 2)
            self.assertTrue(res["capped"] and res["invalid"])
            self.assertEqual(res["last_done"], 1)          # stopped after the capped step
            sr = state.load(disk).steps[0]
            self.assertEqual((sr.tool_calls, sr.capped), (3, True))
            # every tool_use has a matching tool_result in the next message; log ends on an assistant turn
            msgs = convo.messages(disk)
            for i, m in enumerate(msgs):
                ids = [b["id"] for b in m["content"] if isinstance(m["content"], list) and b.get("type") == "tool_use"]
                if ids:
                    got = [b["tool_use_id"] for b in msgs[i + 1]["content"] if b.get("type") == "tool_result"]
                    self.assertEqual(ids, got)
            self.assertEqual(msgs[-1]["role"], "assistant")
            self.assertIn("budget reached", json.dumps(msgs))
            self.assertEqual(gitops.head(disk), gitops.tag_sha(disk, 1))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
