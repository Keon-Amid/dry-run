"""Frozen shared types for the builder. Coders: do NOT edit; report needed changes to the lead.

Python 3.10 compatible (./check runs system python3 = 3.10).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional, Protocol

PatchKind = Literal["spec_line", "rule_off", "control"]

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def empty_usage() -> dict:
    return {k: 0 for k in USAGE_KEYS}


@dataclass
class Patch:
    route: str
    kind: PatchKind
    step: Optional[int]          # spec step whose section spec_line edits; None for rule_off
    old: Optional[str]           # spec_line: exact text to replace (must match once in step section)
    new: Optional[str]           # spec_line: replacement ("" = delete)
    rule: Optional[str]          # rule_off: filename under rules/, e.g. "style.md"
    hypothesis: str

    @staticmethod
    def from_dict(d: dict) -> "Patch":
        return Patch(route=d["route"], kind=d["kind"], step=d.get("step"), old=d.get("old"),
                     new=d.get("new"), rule=d.get("rule"), hypothesis=d.get("hypothesis", ""))


@dataclass
class StepResult:
    step: int
    commit: str                  # git sha of the "step k" commit
    tool_calls: int
    capped: bool
    wall_s: float
    model_calls: int
    usage: dict = field(default_factory=empty_usage)   # sum of API usage objects, keys = USAGE_KEYS

    @staticmethod
    def from_dict(d: dict) -> "StepResult":
        return StepResult(**d)


@dataclass
class State:
    last_done: int
    patch_id: Optional[str] = None
    patch_applied: bool = False
    spec_sha_before: Optional[str] = None
    spec_sha_after: Optional[str] = None
    model: str = ""
    params: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)          # list[StepResult]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "State":
        d = dict(d)
        d["steps"] = [StepResult.from_dict(s) for s in d.get("steps", [])]
        return State(**d)


class LLM(Protocol):
    def create(self, system: list, messages: list, tools: Optional[list]) -> dict:
        """Return a raw Messages API response dict (content, stop_reason, usage, ...)."""
        ...


class Exec(Protocol):
    def read_file(self, p: str) -> str: ...
    def write_file(self, p: str, s: str) -> str: ...
    def list_files(self, p: str = ".") -> str: ...
    def bash(self, cmd: str, timeout: int = 30) -> str: ...


class PatchError(Exception):
    """Patch could not be applied or did not land."""


class ResumeError(Exception):
    """Disk state is inconsistent with the requested resume and cannot be repaired."""


# Disk layout (relative to --disk DIR)
WORKSPACE = "workspace"
SPEC = "spec.md"
RULES = "rules"
CONVERSATION = "conversation.jsonl"
STATE = "state.json"
ROUTES = "routes"
