"""Turn construction. Owner: C4."""
from __future__ import annotations


def spec_steps(spec_text: str, k: int) -> str:
    """Return the spec text containing only '## Step j' sections for j <= k (plus any preamble before Step 1)."""
    raise NotImplementedError


def active_rules(disk: str) -> list:
    """[(name, text)] for files in DISK/rules, sorted."""
    raise NotImplementedError


def preamble(disk: str, k: int) -> str:
    """Harness instructions + spec steps 1..k + active rules."""
    raise NotImplementedError


def system_blocks(disk: str, k: int) -> list:
    """[{"type":"text","text":preamble,"cache_control":{"type":"ephemeral"}}]"""
    raise NotImplementedError


def with_cache_breakpoint(messages: list) -> list:
    """Deep copy of messages with cache_control on the last content block of the last message
    (string content converted to a text block). No other cache_control left in history."""
    raise NotImplementedError


def step_user_message(k: int) -> dict:
    """{"role":"user","content":"Do step k."}"""
    raise NotImplementedError
