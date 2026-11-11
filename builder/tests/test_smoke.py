"""Smoke: `python -m builder.run` with FakeLLM on the toy spec, steps 1..3 in one process."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(REPO, "builder", "tests", "fixtures", "toy")


class Smoke(unittest.TestCase):
    def test_run_cli(self):
        tmp = tempfile.mkdtemp()
        try:
            disk = os.path.join(tmp, "disk")
            shutil.copytree(os.path.join(FIX, "disk"), disk)
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            p = subprocess.run([sys.executable, "-m", "builder.run", "--disk", disk, "--from-step", "1",
                                "--to-step", "3", "--fake-llm", os.path.join(FIX, "fake_script.json")],
                               cwd=REPO, capture_output=True, text=True, timeout=120, env=env)
            self.assertEqual(p.returncode, 0, p.stderr[-2000:])
            last = p.stdout.strip().splitlines()[-1]
            self.assertTrue(last.startswith("RESULT "))
            res = json.loads(last[7:])
            self.assertTrue(res["ok"])
            self.assertEqual(res["last_done"], 3)
            self.assertEqual(len(res["steps"]), 3)
            st = json.load(open(os.path.join(disk, "state.json")))
            for s in st["steps"]:
                self.assertEqual(set(s["usage"]), {"input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                   "cache_read_input_tokens"})
                self.assertIn("wall_s", s)
                self.assertIn("model_calls", s)
            self.assertTrue(st["model"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
