"""Scripted LLM for tests. Owner: C4.

Script JSON: {"steps": {"1": [resp, resp, ...], "2": [...]}, "default": [resp]}
Each resp is a partial Messages response: {"content":[...], "stop_reason":"tool_use"|"end_turn", "usage":{...}}.
The step is read from the last user message text "Do step k." found in messages.
When a step's list runs out, it returns an end_turn text response. If tools is None it always returns end_turn.
"""
from __future__ import annotations


class FakeLLM:
    def __init__(self, script: dict):
        raise NotImplementedError

    @staticmethod
    def from_file(path: str) -> "FakeLLM":
        raise NotImplementedError

    def create(self, system: list, messages: list, tools: list | None) -> dict:
        raise NotImplementedError

    calls: list   # recorded (system, messages, tools) per call, for assertions

    @property
    def params(self) -> dict:
        raise NotImplementedError
