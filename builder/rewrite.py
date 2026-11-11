"""Swarm rewrite generator. Owner: C5.
Input: culprit line, its step text, visible check name + message. NEVER held-out checks or check source."""
from __future__ import annotations


def build_prompt(culprit: str, step_text: str, check_name: str, check_msg: str, mode: str = "fix") -> str:
    """mode 'fix' -> 5 rewrites; 'ambiguity' -> readings."""
    raise NotImplementedError


def validate(original: str, rewrites: list) -> list:
    """5 distinct, all != original, >=1 delete/shorten. Return sorted shortest first. Raise ValueError otherwise."""
    raise NotImplementedError


def generate(llm, culprit: str, step_text: str, check_name: str, check_msg: str, out: str = "rewrites.json",
             mode: str = "fix") -> dict:
    """Call llm, parse, validate, write rewrites.json. Return the written dict."""
    raise NotImplementedError
