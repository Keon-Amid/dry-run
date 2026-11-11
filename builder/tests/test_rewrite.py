import glob
import json
import os
import re
import tempfile
import unittest

from builder import rewrite

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "toy")
CULPRIT = "Codes are 6 digits."
STEP = "Codes are 6 digits. Add `code.py` with a function `make_code()` returning a 6-digit string."


def good(orig=CULPRIT):
    return [
        {"text": "Codes are six-digit strings, leading zeros allowed.", "kind": "disambiguate"},
        {"text": "", "kind": "delete"},
        {"text": "Codes have 6 digits.", "kind": "rephrase"},
        {"text": "6-digit codes.", "kind": "shorten"},
        {"text": "Each code is exactly 6 decimal digits.", "kind": "rephrase"},
    ]


class FakeLLM:
    def __init__(self, text):
        self.text, self.calls = text, []

    def create(self, system, messages, tools):
        self.calls.append((system, messages, tools))
        return {"content": [{"type": "text", "text": self.text}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}


class TestPrompt(unittest.TestCase):
    def secret_strings(self):
        files = glob.glob(os.path.join(FIX, "heldout", "*")) + glob.glob(os.path.join(FIX, "checks", "*"))
        self.assertTrue(files)
        out = []
        for p in files:
            with open(p) as f:
                txt = f.read()
            out += re.findall(r"[A-Z]+-[A-Z]+-[0-9a-f]{4}", txt)  # marker tokens
            out += [ln.strip() for ln in txt.splitlines() if len(ln.strip()) > 8]  # every non-trivial line
        self.assertIn("HELDOUT-SECRET-7f3a", out)
        self.assertIn("CHECK-SOURCE-91bc", out)
        return out

    def test_no_heldout_or_check_source_in_prompt(self):
        secrets = self.secret_strings()
        for mode in ("fix", "ambiguity"):
            p = rewrite.build_prompt(CULPRIT, STEP, "test_code_length", "make_code() returned '12345'", mode)
            self.assertIn(CULPRIT, p)
            self.assertIn("test_code_length", p)
            for s in secrets:
                self.assertNotIn(s, p, f"leaked {s!r} in {mode} prompt")

    def test_generate_sends_no_secrets(self):
        secrets = self.secret_strings()
        llm = FakeLLM(json.dumps({"rewrites": good()}))
        with tempfile.TemporaryDirectory() as d:
            rewrite.generate(llm, CULPRIT, STEP, "test_code_length", "bad length", out=os.path.join(d, "r.json"))
        sent = json.dumps(llm.calls)
        for s in secrets:
            self.assertNotIn(s, sent)

    def test_signature_has_no_extra_inputs(self):
        import inspect
        params = list(inspect.signature(rewrite.build_prompt).parameters)
        self.assertEqual(params, ["culprit", "step_text", "check_name", "check_msg", "mode"])

    def test_modes(self):
        self.assertIn('"rewrites"', rewrite.build_prompt("a", "b", "c", "d", "fix"))
        self.assertIn('"readings"', rewrite.build_prompt("a", "b", "c", "d", "ambiguity"))
        with self.assertRaises(ValueError):
            rewrite.build_prompt("a", "b", "c", "d", "nope")


class TestValidate(unittest.TestCase):
    def test_sorted_shortest_first(self):
        out = rewrite.validate(CULPRIT, good())
        self.assertEqual(len(out), 5)
        lens = [len(r["text"]) for r in out]
        self.assertEqual(lens, sorted(lens))
        self.assertEqual(out[0], {"text": "", "kind": "delete"})

    def test_wrong_count(self):
        with self.assertRaises(ValueError):
            rewrite.validate(CULPRIT, good()[:4])
        with self.assertRaises(ValueError):
            rewrite.validate(CULPRIT, good() + [{"text": "x", "kind": "shorten"}])

    def test_duplicates_normalized(self):
        rs = good()
        rs[4] = {"text": "  codes HAVE   6 digits. ", "kind": "rephrase"}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            rewrite.validate(CULPRIT, rs)

    def test_equal_to_original(self):
        rs = good()
        rs[0] = {"text": "codes are 6  DIGITS.", "kind": "rephrase"}
        with self.assertRaisesRegex(ValueError, "original"):
            rewrite.validate(CULPRIT, rs)

    def test_needs_delete_or_shorter(self):
        long = [{"text": CULPRIT + " " + w, "kind": "disambiguate"} for w in ("a1", "b2", "c3", "d4", "e5")]
        with self.assertRaisesRegex(ValueError, "delete or shorter"):
            rewrite.validate(CULPRIT, long)
        long[2] = {"text": "Six digits.", "kind": "shorten"}
        self.assertEqual(rewrite.validate(CULPRIT, long)[0]["text"], "Six digits.")

    def test_bad_kind_and_entry(self):
        rs = good()
        rs[0] = {"text": "zzz", "kind": "expand"}
        with self.assertRaises(ValueError):
            rewrite.validate(CULPRIT, rs)
        rs[0] = "just a string"
        with self.assertRaises(ValueError):
            rewrite.validate(CULPRIT, rs)
        with self.assertRaises(ValueError):
            rewrite.validate(CULPRIT, None)


class TestGenerate(unittest.TestCase):
    def test_writes_file_from_fenced_reply(self):
        reply = "Here you go:\n```json\n" + json.dumps({"rewrites": good()}) + "\n```\n"
        llm = FakeLLM(reply)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rewrites.json")
            res = rewrite.generate(llm, CULPRIT, STEP, "test_code_length", "bad length", out=out)
            with open(out) as f:
                disk = json.load(f)
        self.assertEqual(res, disk)
        self.assertEqual(disk["culprit"], CULPRIT)
        self.assertEqual(disk["check"], "test_code_length")
        self.assertEqual(disk["mode"], "fix")
        self.assertEqual([r["text"] for r in disk["rewrites"]],
                         [r["text"] for r in rewrite.validate(CULPRIT, good())])
        system, messages, tools = llm.calls[0]
        self.assertIsNone(tools)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn(CULPRIT, messages[0]["content"])
        self.assertEqual(system[0]["type"], "text")

    def test_plain_json_reply(self):
        llm = FakeLLM(json.dumps({"rewrites": good()}))
        with tempfile.TemporaryDirectory() as d:
            res = rewrite.generate(llm, CULPRIT, STEP, "c", "m", out=os.path.join(d, "r.json"))
        self.assertEqual(len(res["rewrites"]), 5)

    def test_invalid_reply_writes_nothing(self):
        llm = FakeLLM(json.dumps({"rewrites": good()[:3]}))
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            with self.assertRaises(ValueError):
                rewrite.generate(llm, CULPRIT, STEP, "c", "m", out=out)
            self.assertFalse(os.path.exists(out))
            with self.assertRaises(ValueError):
                rewrite.generate(FakeLLM("not json at all"), CULPRIT, STEP, "c", "m", out=out)
            self.assertFalse(os.path.exists(out))

    def test_ambiguity_mode(self):
        llm = FakeLLM(json.dumps({"readings": ["exactly six digit characters", "a number below 10^6",
                                               "Exactly six digit characters "]}))
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            res = rewrite.generate(llm, CULPRIT, STEP, "c", "m", out=out, mode="ambiguity")
            with open(out) as f:
                self.assertEqual(json.load(f), res)
            with self.assertRaises(ValueError):
                rewrite.generate(FakeLLM('{"readings":["one"]}'), CULPRIT, STEP, "c", "m",
                                 out=os.path.join(d, "y"), mode="ambiguity")
        self.assertEqual(res["mode"], "ambiguity")
        self.assertEqual(res["readings"], ["exactly six digit characters", "a number below 10^6"])


if __name__ == "__main__":
    unittest.main()
