"""Baseline arm: what one plain Claude call does with the same failure, no branching and no swarm.

fix_spec(llm, spec, check, message) sends the original spec plus the failing visible check's name and message in one
request (no tools, same model as the swarm's builder) and returns the complete fixed spec. The pipeline then builds
that spec from step 0 three times and grades visible + held-out checks, next to the swarm's numbers (report.md).
StubFixer stands in when the builder is the stub: it makes no call and returns the spec unchanged.
"""
from __future__ import annotations

import difflib
import re
import time

PROMPT = """A program is built from the spec below, one "## Step N" section per step. The finished build fails one \
check.

<spec>
{spec}
</spec>

Failing check: {check}
Check message: {message}

Rewrite the spec so a build from it passes this check. Keep the same "## Step N" sections in the same order, and \
change as little as you need. Reply with the complete fixed spec inside <spec></spec> tags and nothing else."""


def _steps(spec: str) -> list[str]:
    return re.findall(r"^## Step \d+", spec, re.M)


def extract_spec(text: str, original: str) -> str:
    m = re.search(r"<spec>\s*(.*?)\s*</spec>", text, re.S)
    if not m:
        raise ValueError("reply has no <spec>...</spec> block")
    fixed = m.group(1).strip() + "\n"
    if _steps(fixed) != _steps(original):
        raise ValueError(f"fixed spec has steps {_steps(fixed)}, the original has {_steps(original)}")
    return fixed


def fix_spec(llm, spec: str, check: str, message: str) -> dict:
    prompt = PROMPT.format(spec=spec.strip(), check=check, message=message)
    t0 = time.perf_counter()
    resp = llm.create(system=[{"type": "text", "text": "You fix software build specs."}],
                      messages=[{"role": "user", "content": prompt}], tools=None)
    wall = round(time.perf_counter() - t0, 3)
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    out = {"model": resp.get("model") or getattr(llm, "model", None), "prompt": prompt, "reply": text,
           "usage": resp.get("usage") or {}, "wall_s": wall, "stop_reason": resp.get("stop_reason")}
    try:
        out["fixed_spec"] = extract_spec(text, spec)
        out["diff"] = "".join(difflib.unified_diff(spec.splitlines(True), out["fixed_spec"].splitlines(True),
                                                   "spec.md (original)", "spec.md (baseline fix)"))
    except ValueError as e:
        out["fixed_spec"], out["error"] = None, str(e)
    return out


class StubFixer:
    """No model call: returns the spec unchanged, so the stub pipeline exercises the arm end to end."""
    model = "stub-fixer"

    def create(self, system, messages, tools):
        spec = re.search(r"<spec>\n(.*?)\n</spec>", messages[0]["content"], re.S).group(1)
        return {"model": self.model, "content": [{"type": "text", "text": f"<spec>\n{spec}\n</spec>"}],
                "usage": {}, "stop_reason": "end_turn"}


class UsageRecorder:
    """Wraps an llm with .create(): records each call's model and usage, so orchestrator-side calls (rewrites,
    baseline) are counted in archil.json's spent."""

    def __init__(self, llm):
        self.llm, self.calls = llm, []
        self.model = getattr(llm, "model", None)

    def create(self, system, messages, tools):
        t0 = time.perf_counter()
        resp = self.llm.create(system, messages, tools)
        self.calls.append({"model": resp.get("model") or self.model, "usage": resp.get("usage") or {},
                           "wall_s": round(time.perf_counter() - t0, 3)})
        return resp
