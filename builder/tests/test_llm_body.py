import unittest

from builder.llm import AnthropicLLM
from builder.tools import TOOL_SCHEMAS


class Body(unittest.TestCase):
    def test_tools_none_with_tool_history_sends_tool_choice_none(self):
        msgs = [{"role": "user", "content": "Do step 1."},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "bash", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]}]
        b = AnthropicLLM(model="m")._body([], msgs, None)
        self.assertEqual(b["tool_choice"], {"type": "none"})
        self.assertEqual(b["tools"], TOOL_SCHEMAS)

    def test_tools_none_plain_history_sends_no_tools(self):
        b = AnthropicLLM(model="m")._body([], [{"role": "user", "content": "hi"}], None)
        self.assertNotIn("tools", b)
        self.assertNotIn("tool_choice", b)
