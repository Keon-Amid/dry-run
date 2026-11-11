import io
import json
import os
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from builder import llm


class FakeResp:
    def __init__(self, body: dict):
        self._b = json.dumps(body).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, body, retry_after=None):
    h = Message()
    if retry_after is not None:
        h["retry-after"] = str(retry_after)
    return urllib.error.HTTPError(llm.API_URL, code, "err", h, io.BytesIO(json.dumps(body).encode()))


OK = {"content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn",
      "usage": {"input_tokens": 3, "output_tokens": 1}}


class Opener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return FakeResp(o)


class TestLLM(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        p = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"})
        p.start()
        self.addCleanup(p.stop)

    def make(self, outcomes, **kw):
        op = Opener(outcomes)
        return llm.AnthropicLLM(model="m-test", sleep=self.sleeps.append, urlopen=op, **kw), op

    def test_default_model_and_env_override(self):
        self.assertTrue(llm.DEFAULT_MODEL.startswith("claude-sonnet"))
        with mock.patch.dict(os.environ, {"DRYRUN_MODEL": ""}):
            self.assertEqual(llm.model_name(), llm.DEFAULT_MODEL)
        with mock.patch.dict(os.environ, {"DRYRUN_MODEL": "x-model"}):
            self.assertEqual(llm.model_name(), "x-model")
            self.assertEqual(llm.AnthropicLLM(urlopen=None).model, "x-model")

    def test_request_shape(self):
        c, op = self.make([OK])
        sysb = [{"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}]
        msgs = [{"role": "user", "content": "Do step 1."}]
        tools = [{"name": "bash", "description": "d", "input_schema": {"type": "object"}}]
        r = c.create(sysb, msgs, tools)
        self.assertEqual(r["stop_reason"], "end_turn")
        req = op.requests[0]
        self.assertEqual(req.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(req.get_method(), "POST")
        hdrs = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(hdrs["x-api-key"], "sk-test")
        self.assertEqual(hdrs["anthropic-version"], llm.API_VERSION)
        self.assertEqual(hdrs["content-type"], "application/json")
        body = json.loads(req.data)
        self.assertEqual(body["model"], "m-test")
        self.assertEqual(body["system"], sysb)
        self.assertEqual(body["messages"], msgs)
        self.assertEqual(body["tools"], tools)
        for k in ("temperature", "top_p", "top_k"):
            self.assertNotIn(k, body)
        self.assertEqual(self.sleeps, [])

    def test_tools_none_omits_tools(self):
        c, op = self.make([OK])
        c.create([], [{"role": "user", "content": "x"}], None)
        self.assertNotIn("tools", json.loads(op.requests[0].data))

    def test_key_read_at_call_time(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            c, op = self.make([OK])   # construction must not need the key
            with self.assertRaises(RuntimeError):
                c.create([], [], None)
            self.assertEqual(op.requests, [])
        c2, op2 = self.make([OK])
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-later"}):
            c2.create([], [], None)
        self.assertEqual(dict((k.lower(), v) for k, v in op2.requests[0].header_items())["x-api-key"], "sk-later")

    def test_retry_429_honours_retry_after(self):
        c, op = self.make([http_error(429, {"error": {"type": "rate_limit_error"}}, retry_after=7), OK],
                          base_delay=0.01)
        self.assertEqual(c.create([], [], None)["stop_reason"], "end_turn")
        self.assertEqual(len(op.requests), 2)
        self.assertEqual(len(self.sleeps), 1)
        self.assertGreaterEqual(self.sleeps[0], 7.0)

    def test_retry_529_500_and_overloaded_with_backoff(self):
        outcomes = [http_error(529, {"error": {"type": "overloaded_error"}}),
                    http_error(500, {"error": {"type": "api_error"}}),
                    http_error(400, {"error": {"type": "overloaded_error"}}),  # retry by error type
                    OK]
        c, op = self.make(outcomes, base_delay=1.0, max_delay=100)
        c.create([], [], None)
        self.assertEqual(len(op.requests), 4)
        self.assertEqual(len(self.sleeps), 3)
        self.assertEqual(c.retries, 3)
        # jittered exponential: attempt n in [0.5, 1.0] * 2**n
        for n, d in enumerate(self.sleeps):
            self.assertGreaterEqual(d, 0.5 * 2 ** n)
            self.assertLessEqual(d, 1.0 * 2 ** n)

    def test_non_retryable_raises_with_body(self):
        body = {"error": {"type": "invalid_request_error", "message": "bad field xyz"}}
        c, op = self.make([http_error(400, body), OK])
        with self.assertRaises(llm.APIError) as cm:
            c.create([], [], None)
        self.assertEqual(cm.exception.status, 400)
        self.assertIn("bad field xyz", str(cm.exception))
        self.assertEqual(len(op.requests), 1)
        self.assertEqual(self.sleeps, [])

    def test_gives_up_after_max_retries(self):
        errs = [http_error(529, {"error": {"type": "overloaded_error"}}) for _ in range(4)]
        c, op = self.make(errs, max_retries=3, base_delay=0.01)
        with self.assertRaises(llm.APIError) as cm:
            c.create([], [], None)
        self.assertEqual(cm.exception.status, 529)
        self.assertEqual(len(op.requests), 4)
        self.assertEqual(len(self.sleeps), 3)

    def test_params(self):
        c, _ = self.make([])
        p = c.params
        self.assertEqual(p["temperature"], "api-default")
        self.assertEqual(p["max_tokens"], 8192)
        json.dumps(p)


if __name__ == "__main__":
    unittest.main()
