"""Scripted LLM for tests. Owner: C4.

Script JSON: {"steps": {"1": [resp, resp, ...], "2": [...]}, "default": [resp]}
Each resp is a partial Messages response: {"content":[...], "stop_reason":"tool_use"|"end_turn", "usage":{...}}.
The step is read from the last user message text "Do step k." found in messages.
When a step's list runs out, it returns an end_turn text response. If tools is None it always returns end_turn.
"""
from __future__ import annotations

import copy
import json
import re

from builder.types import USAGE_KEYS

_STEP_RE = re.compile(r"Do step (\d+)\.")


def _texts(content) -> list:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return []


def step_of(messages: list):
    """k from the last user message whose text is 'Do step k.', else None."""
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        for t in reversed(_texts(m.get("content"))):
            mm = _STEP_RE.search(t)
            if mm:
                return int(mm.group(1))
    return None


class FakeLLM:
    def __init__(self, script: dict):
        self.script = script
        self.calls = []
        self._pos = {}       # (script key, step) -> next index
        self._ids = 0

    @staticmethod
    def from_file(path: str) -> "FakeLLM":
        with open(path, encoding="utf-8") as f:
            return FakeLLM(json.load(f))

    def _end_turn(self, text: str) -> dict:
        return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}

    def _finish(self, resp: dict) -> dict:
        resp = copy.deepcopy(resp)
        resp.setdefault("id", f"msg_fake_{len(self.calls)}")
        resp.setdefault("type", "message")
        resp.setdefault("role", "assistant")
        resp.setdefault("model", "fake")
        resp.setdefault("content", [])
        resp.setdefault("stop_reason", "end_turn")
        usage = resp.get("usage") or {}
        resp["usage"] = {k: int(usage.get(k, 0)) for k in USAGE_KEYS}
        for b in resp["content"]:
            if b.get("type") == "tool_use":
                if not b.get("id"):
                    self._ids += 1
                    b["id"] = f"toolu_fake_{self._ids}"
                b.setdefault("input", {})
        return resp

    def create(self, system: list, messages: list, tools: list | None) -> dict:
        self.calls.append((copy.deepcopy(system), copy.deepcopy(messages), copy.deepcopy(tools)))
        if tools is None:
            return self._finish(self._end_turn("Budget reached; stopping."))
        k = step_of(messages)
        steps = self.script.get("steps", {})
        key = str(k) if k is not None and str(k) in steps else "default"
        seq = steps.get(key) if key != "default" else self.script.get("default", [])
        seq = seq or []
        pos_key = (key, k)   # "default" replays from the start for each step
        i = self._pos.get(pos_key, 0)
        if i >= len(seq):
            return self._finish(self._end_turn(f"Step {k} done."))
        self._pos[pos_key] = i + 1
        return self._finish(seq[i])

    @property
    def params(self) -> dict:
        return {"max_tokens": 0, "temperature": "api-default", "fake": True}
