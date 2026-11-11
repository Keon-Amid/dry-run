"""Step loop. Owner: lead (Phase 2).

One step = preamble (spec 1..k + active rules, never logged) + replayed history + "Do step k." + tool loop,
then: git commit + tag step-k, then one fsynced append of the step's messages to conversation.jsonl.
The caller (run.py) writes state.json last, so a crash anywhere leaves something gitops.repair can fix.
"""
from __future__ import annotations

import json
import sys
import time

from builder import convo, gitops, prompt, tools
from builder.types import StepResult, USAGE_KEYS, empty_usage

BUDGET_MSG = "budget reached, finish now"


def log(msg: str) -> None:
    print(f"[builder] {msg}", file=sys.stderr, flush=True)


def _add_usage(total: dict, resp: dict) -> None:
    u = resp.get("usage") or {}
    for key in USAGE_KEYS:
        total[key] += int(u.get(key) or 0)


def _assistant_msg(resp: dict, strip_tool_use: bool = False) -> dict:
    content = list(resp.get("content") or [])
    if strip_tool_use:
        content = [b for b in content if b.get("type") != "tool_use"]
    if not content:
        content = [{"type": "text", "text": "(no text)"}]
    return {"role": "assistant", "content": content}


def history(disk: str, history_min_step: int = 1) -> list:
    """Prior messages from the log, only records with step >= history_min_step (blind arm drops older ones)."""
    return [r["msg"] for r in convo.load(disk) if r["step"] >= history_min_step]


def run_step(disk: str, k: int, llm, ex, max_calls: int = 25, history_min_step: int = 1) -> StepResult:
    t0 = time.monotonic()
    system = prompt.system_blocks(disk, k)
    prior = history(disk, history_min_step)
    step_msgs: list = [prompt.step_user_message(k)]
    usage = empty_usage()
    model_calls = 0
    tool_calls = 0
    capped = False

    while True:
        resp = llm.create(system, prompt.with_cache_breakpoint(prior + step_msgs), tools.TOOL_SCHEMAS)
        model_calls += 1
        _add_usage(usage, resp)
        uses = [b for b in (resp.get("content") or []) if b.get("type") == "tool_use"]
        step_msgs.append(_assistant_msg(resp))
        if not uses:
            break  # end_turn (or max_tokens / stop_sequence with no pending tool call)

        results = []
        for b in uses:
            if tool_calls >= max_calls:
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": BUDGET_MSG,
                                "is_error": True})
                capped = True
                continue
            tool_calls += 1
            try:
                out = tools.dispatch(ex, b.get("name", ""), b.get("input") or {})
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": out})
            except Exception as e:  # a tool error never escapes the loop
                results.append({"type": "tool_result", "tool_use_id": b["id"],
                                "content": f"{type(e).__name__}: {e}", "is_error": True})
        step_msgs.append({"role": "user", "content": results})

        if capped:
            # One final call with tools disabled; any tool_use it still emits is dropped so the log stays valid.
            resp = llm.create(system, prompt.with_cache_breakpoint(prior + step_msgs), None)
            model_calls += 1
            _add_usage(usage, resp)
            step_msgs.append(_assistant_msg(resp, strip_tool_use=True))
            break

    sha = gitops.commit_step(disk, k)
    convo.append_step(disk, k, step_msgs)
    wall = round(time.monotonic() - t0, 3)
    log(f"step {k}: {tool_calls} tool calls, {model_calls} model calls, capped={capped}, {wall}s, "
        f"usage={json.dumps(usage)}")
    return StepResult(step=k, commit=sha, tool_calls=tool_calls, capped=capped, wall_s=wall,
                      model_calls=model_calls, usage=usage)
