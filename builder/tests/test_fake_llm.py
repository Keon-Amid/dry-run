import json
import os
import shutil
import tempfile
import unittest

from builder.fake_llm import FakeLLM
from builder.types import USAGE_KEYS

TOOLS = [{"name": "write_file", "input_schema": {"type": "object"}}]


def tool_use(path, content="x"):
    return {"content": [{"type": "tool_use", "name": "write_file", "input": {"path": path, "content": content}}],
            "stop_reason": "tool_use"}


def user(k):
    return [{"role": "user", "content": f"Do step {k}."}]


class TestFakeLLM(unittest.TestCase):
    def test_tool_use_turn_then_end_turn(self):
        script = {"steps": {"1": [tool_use("hello.py", "print('hello')"),
                                  {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn",
                                   "usage": {"input_tokens": 5}}]}}
        f = FakeLLM(script)
        r1 = f.create([], user(1), TOOLS)
        self.assertEqual(r1["stop_reason"], "tool_use")
        blk = r1["content"][0]
        self.assertEqual(blk["input"]["path"], "hello.py")
        self.assertTrue(blk["id"])
        self.assertEqual(set(r1["usage"]), set(USAGE_KEYS))
        msgs = user(1) + [{"role": "assistant", "content": r1["content"]},
                          {"role": "user", "content": [{"type": "tool_result", "tool_use_id": blk["id"],
                                                        "content": "ok"}]}]
        r2 = f.create([], msgs, TOOLS)  # step still found from earlier user message
        self.assertEqual(r2["stop_reason"], "end_turn")
        self.assertEqual(r2["usage"]["input_tokens"], 5)
        self.assertEqual(r2["usage"]["cache_read_input_tokens"], 0)
        r3 = f.create([], msgs, TOOLS)  # list exhausted
        self.assertEqual(r3["stop_reason"], "end_turn")
        self.assertEqual(len(f.calls), 3)
        self.assertEqual(f.calls[0][1], user(1))
        self.assertEqual(f.calls[0][2], TOOLS)

    def test_over_budget(self):
        script = {"steps": {"2": [tool_use(f"f{i}.py") for i in range(10)]}}
        f = FakeLLM(script)
        budget = 3
        ids = set()
        for _ in range(budget):
            r = f.create([], user(2), TOOLS)
            self.assertEqual(r["stop_reason"], "tool_use")
            ids.add(r["content"][0]["id"])
        self.assertEqual(len(ids), budget)  # distinct tool_use ids
        final = f.create([], user(2), None)
        self.assertEqual(final["stop_reason"], "end_turn")
        self.assertEqual(final["content"][0]["type"], "text")
        self.assertIsNone(f.calls[-1][2])

    def test_steps_independent_and_default(self):
        script = {"steps": {"1": [tool_use("a.py")]},
                  "default": [tool_use("d.py"), {"content": [{"type": "text", "text": "d"}],
                                                 "stop_reason": "end_turn"}]}
        f = FakeLLM(script)
        self.assertEqual(f.create([], user(1), TOOLS)["content"][0]["input"]["path"], "a.py")
        self.assertEqual(f.create([], user(3), TOOLS)["content"][0]["input"]["path"], "d.py")
        self.assertEqual(f.create([], user(3), TOOLS)["stop_reason"], "end_turn")
        # default replays from the start for another step
        self.assertEqual(f.create([], user(4), TOOLS)["content"][0]["input"]["path"], "d.py")
        # step 1 exhausted
        self.assertEqual(f.create([], user(1), TOOLS)["stop_reason"], "end_turn")

    def test_script_not_mutated_and_recorded_calls_copied(self):
        script = {"steps": {"1": [tool_use("a.py")]}}
        f = FakeLLM(script)
        msgs = user(1)
        f.create([], msgs, TOOLS)
        self.assertNotIn("id", script["steps"]["1"][0]["content"][0])
        msgs.append({"role": "assistant", "content": "later"})
        self.assertEqual(len(f.calls[0][1]), 1)

    def test_from_file_and_params(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        p = os.path.join(tmp, "s.json")
        with open(p, "w") as fh:
            json.dump({"steps": {"1": [tool_use("z.py")]}}, fh)
        f = FakeLLM.from_file(p)
        self.assertEqual(f.create([], user(1), TOOLS)["stop_reason"], "tool_use")
        self.assertEqual(f.params["temperature"], "api-default")


if __name__ == "__main__":
    unittest.main()
