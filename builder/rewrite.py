"""Swarm rewrite generator. Owner: C5.
Input: culprit line, its step text, visible check name + message. NEVER held-out checks or check source.

build_prompt only sees its four string arguments, so nothing else (held-out checks, check source, golden files)
can reach the model through this module.
"""
from __future__ import annotations

import json
import os
import re
import tempfile

N_REWRITES = 5
KINDS = ("delete", "shorten", "disambiguate", "rephrase")
MIN_READINGS = 2

SYSTEM = ("You edit one line of a build spec. Reply with strict JSON only: no prose, no markdown, no code fences.")


def build_prompt(culprit: str, step_text: str, check_name: str, check_msg: str, mode: str = "fix") -> str:
    """mode 'fix' -> 5 rewrites; 'ambiguity' -> readings."""
    head = (
        "A coding agent built software from a spec. One spec line is suspected of causing a failed check.\n\n"
        f"Suspect line:\n<<<\n{culprit}\n>>>\n\n"
        f"The spec step that contains it:\n<<<\n{step_text}\n>>>\n\n"
        f"Failed check: {check_name}\n"
        f"Check message: {check_msg}\n\n"
    )
    if mode == "fix":
        return head + (
            f"Propose exactly {N_REWRITES} distinct replacements for the suspect line. Prefer removing words over "
            "adding constraints: include at least one deletion (empty text) or a shorter version. Every replacement "
            "must differ from the original line. Do not add new requirements.\n"
            'Reply as JSON: {"rewrites":[{"text":"...","kind":"delete|shorten|disambiguate|rephrase"}, ...]}\n'
            'A delete has "text": "".'
        )
    if mode == "ambiguity":
        return head + (
            "List the distinct ways a careful reader could interpret the suspect line. One short sentence each.\n"
            'Reply as JSON: {"readings":["...", "..."]}'
        )
    raise ValueError(f"unknown mode {mode!r}")


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def validate(original: str, rewrites: list) -> list:
    """5 distinct, all != original, >=1 delete/shorten. Return sorted shortest first. Raise ValueError otherwise."""
    if not isinstance(rewrites, list):
        raise ValueError("rewrites must be a list")
    if len(rewrites) != N_REWRITES:
        raise ValueError(f"need exactly {N_REWRITES} rewrites, got {len(rewrites)}")
    orig = _norm(original)
    seen = set()
    clean = []
    for r in rewrites:
        if not isinstance(r, dict) or not isinstance(r.get("text"), str):
            raise ValueError(f"bad rewrite entry: {r!r}")
        text = r["text"].strip()
        kind = r.get("kind")
        if kind not in KINDS:
            raise ValueError(f"bad kind {kind!r}")
        n = _norm(text)
        if n == orig:
            raise ValueError(f"rewrite equals the original: {text!r}")
        if n in seen:
            raise ValueError(f"duplicate rewrite: {text!r}")
        seen.add(n)
        clean.append({"text": text, "kind": kind})
    if not any(r["text"] == "" or len(r["text"]) < len(original.strip()) for r in clean):
        raise ValueError("need at least one delete or shorter-than-original rewrite")
    return sorted(clean, key=lambda r: (len(r["text"]), r["text"]))


def validate_readings(readings: list) -> list:
    if not isinstance(readings, list) or not all(isinstance(x, str) for x in readings):
        raise ValueError("readings must be a list of strings")
    out, seen = [], set()
    for x in readings:
        x = x.strip()
        n = _norm(x)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(x)
    if len(out) < MIN_READINGS:
        raise ValueError(f"need at least {MIN_READINGS} distinct readings, got {len(out)}")
    return out


def extract_text(resp: dict) -> str:
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json(text: str) -> dict:
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1])
        raise ValueError(f"model reply is not JSON: {text[:200]!r}")


def _write_atomic(path: str, obj: dict) -> None:
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".rewrites.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def generate(llm, culprit: str, step_text: str, check_name: str, check_msg: str, out: str = "rewrites.json",
             mode: str = "fix") -> dict:
    """Call llm, parse, validate, write rewrites.json. Return the written dict."""
    prompt = build_prompt(culprit, step_text, check_name, check_msg, mode)
    resp = llm.create([{"type": "text", "text": SYSTEM}], [{"role": "user", "content": prompt}], None)
    data = parse_json(extract_text(resp))
    result = {"culprit": culprit, "check": check_name, "mode": mode}
    if mode == "fix":
        result["rewrites"] = validate(culprit, data.get("rewrites"))
    else:
        result["readings"] = validate_readings(data.get("readings"))
    _write_atomic(out, result)
    return result
