"""Turn construction. Owner: C4."""
from __future__ import annotations

import copy
import os
import re

from builder.types import RULES, SPEC

HARNESS = """You are a coding agent building a small project, one spec step at a time.
- You work in the directory workspace/. All file paths you pass to tools are relative to workspace/.
- Use the tools (read_file, write_file, list_files, bash) to inspect and change files; do not just describe changes.
- Do only the step the user asks for in this turn ("Do step k."), then stop and reply with a one-line summary.
- Follow the spec and the rules below exactly."""

_STEP_RE = re.compile(r"^##\s+Step\s+(\d+)\b", re.IGNORECASE)
_H2_RE = re.compile(r"^##\s")


def spec_steps(spec_text: str, k: int) -> str:
    """Return the spec text containing only '## Step j' sections for j <= k (plus any preamble before Step 1)."""
    out, keep = [], True
    for line in spec_text.splitlines(keepends=True):
        m = _STEP_RE.match(line)
        if m:
            keep = int(m.group(1)) <= k
        elif _H2_RE.match(line):
            pass  # a non-step H2 inherits the current keep state (belongs to the preceding step)
        if keep:
            out.append(line)
    return "".join(out).rstrip() + "\n"


def active_rules(disk: str) -> list:
    """[(name, text)] for files in DISK/rules, sorted."""
    d = os.path.join(disk, RULES)
    if not os.path.isdir(d):
        return []
    rules = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if name.startswith(".") or not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8") as f:
            rules.append((name, f.read()))
    return rules


def preamble(disk: str, k: int) -> str:
    """Harness instructions + spec steps 1..k + active rules."""
    with open(os.path.join(disk, SPEC), encoding="utf-8") as f:
        spec = spec_steps(f.read(), k)
    parts = [HARNESS, "", "<spec>", spec.rstrip(), "</spec>"]
    rules = active_rules(disk)
    if rules:
        parts += ["", "<rules>"]
        for name, text in rules:
            parts += [f'<rule file="{name}">', text.rstrip(), "</rule>"]
        parts.append("</rules>")
    return "\n".join(parts) + "\n"


def system_blocks(disk: str, k: int) -> list:
    """[{"type":"text","text":preamble,"cache_control":{"type":"ephemeral"}}]"""
    return [{"type": "text", "text": preamble(disk, k), "cache_control": {"type": "ephemeral"}}]


def with_cache_breakpoint(messages: list) -> list:
    """Deep copy of messages with cache_control on the last content block of the last message
    (string content converted to a text block). No other cache_control left in history."""
    msgs = copy.deepcopy(messages)
    for m in msgs:
        if isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict):
                    b.pop("cache_control", None)
    if not msgs:
        return msgs
    last = msgs[-1]
    c = last.get("content")
    if isinstance(c, str):
        last["content"] = [{"type": "text", "text": c, "cache_control": {"type": "ephemeral"}}]
    elif isinstance(c, list) and c:
        c[-1]["cache_control"] = {"type": "ephemeral"}
    return msgs


def step_user_message(k: int) -> dict:
    """{"role":"user","content":"Do step k."}"""
    return {"role": "user", "content": f"Do step {k}."}
