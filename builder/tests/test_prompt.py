import os
import shutil
import tempfile
import unittest

from builder import prompt

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "toy", "disk")
SPEC = """# Toy spec
Intro text.

## Step 1
Create hello.py.

## Step 2
Codes are 6 digits.

## Step 3
Add README.md describing both files.
"""


class TestPrompt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.disk = os.path.join(self.tmp, "disk")
        shutil.copytree(FIXTURE, self.disk)

    def test_spec_steps_filters(self):
        s2 = prompt.spec_steps(SPEC, 2)
        self.assertIn("Intro text.", s2)
        self.assertIn("Create hello.py.", s2)
        self.assertIn("Codes are 6 digits.", s2)
        self.assertNotIn("README", s2)
        self.assertNotIn("## Step 3", s2)
        s1 = prompt.spec_steps(SPEC, 1)
        self.assertNotIn("6 digits", s1)
        self.assertIn("README", prompt.spec_steps(SPEC, 3))

    def test_spec_steps_double_digit(self):
        spec = "## Step 1\na\n## Step 10\nten\n## Step 2\nb\n"
        out = prompt.spec_steps(spec, 2)
        self.assertNotIn("ten", out)
        self.assertIn("b", out)

    def test_active_rules_sorted_and_deleted_absent(self):
        with open(os.path.join(self.disk, "rules", "a_first.md"), "w") as f:
            f.write("Rule A.")
        rules = prompt.active_rules(self.disk)
        self.assertEqual([n for n, _ in rules], ["a_first.md", "style.md"])
        self.assertIn("4-space", dict(rules)["style.md"])
        os.remove(os.path.join(self.disk, "rules", "style.md"))
        self.assertEqual([n for n, _ in prompt.active_rules(self.disk)], ["a_first.md"])
        shutil.rmtree(os.path.join(self.disk, "rules"))
        self.assertEqual(prompt.active_rules(self.disk), [])

    def test_preamble_on_fixture(self):
        p = prompt.preamble(self.disk, 2)
        self.assertIn("workspace/", p)
        self.assertIn("6 digits", p)
        self.assertNotIn("describing both files", p)  # step 3 text
        self.assertIn("4-space indentation", p)
        os.remove(os.path.join(self.disk, "rules", "style.md"))
        self.assertNotIn("4-space indentation", prompt.preamble(self.disk, 2))
        self.assertIn("describing both files", prompt.preamble(self.disk, 3))

    def test_system_blocks(self):
        b = prompt.system_blocks(self.disk, 1)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["type"], "text")
        self.assertEqual(b[0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(b[0]["text"], prompt.preamble(self.disk, 1))

    def test_with_cache_breakpoint_string_content(self):
        msgs = [{"role": "user", "content": "Do step 1."}]
        out = prompt.with_cache_breakpoint(msgs)
        self.assertEqual(msgs, [{"role": "user", "content": "Do step 1."}])  # input untouched
        self.assertEqual(out[0]["content"],
                         [{"type": "text", "text": "Do step 1.", "cache_control": {"type": "ephemeral"}}])

    def test_with_cache_breakpoint_strips_old(self):
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "Do step 1.",
                                          "cache_control": {"type": "ephemeral"}}]},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"},
                                              {"type": "tool_use", "id": "t1", "name": "bash", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "a",
                                          "cache_control": {"type": "ephemeral"}},
                                         {"type": "tool_result", "tool_use_id": "t2", "content": "b"}]},
        ]
        out = prompt.with_cache_breakpoint(msgs)
        count = sum(1 for m in out for b in m["content"] if "cache_control" in b)
        self.assertEqual(count, 1)
        self.assertEqual(out[-1]["content"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertIn("cache_control", msgs[0]["content"][0])  # original not mutated
        self.assertNotIn("cache_control", msgs[2]["content"][1])
        self.assertEqual(prompt.with_cache_breakpoint([]), [])

    def test_step_user_message(self):
        self.assertEqual(prompt.step_user_message(3), {"role": "user", "content": "Do step 3."})


if __name__ == "__main__":
    unittest.main()
