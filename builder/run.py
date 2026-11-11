"""CLI. Owner: lead (Phase 2).

python -m builder.run --disk DIR --from-step K --to-step N [--patch patch.json] [--route ID]
                      [--max-calls 25] [--drop-conversation] [--fake-llm script.json]

Logs go to stderr. The last stdout line is `RESULT {json}`. Exit: 0 ok, 2 capped (invalid branch), 1 error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from builder import gitops, loop, patch as patchmod, state as statemod
from builder.tools import LocalExec
from builder.types import PatchError, ResumeError, WORKSPACE, ROUTES

EXIT_OK, EXIT_ERROR, EXIT_CAPPED = 0, 1, 2


def make_llm(fake_script: str | None):
    if fake_script:
        from builder.fake_llm import FakeLLM
        return FakeLLM.from_file(fake_script)
    from builder.llm import AnthropicLLM
    return AnthropicLLM()


def _model_of(llm) -> str:
    return getattr(llm, "model", None) or type(llm).__name__


def _route_note(disk: str, route: str, result: dict) -> None:
    os.makedirs(os.path.join(disk, ROUTES), exist_ok=True)
    with open(os.path.join(disk, ROUTES, f"{route}.md"), "a") as f:
        f.write("\n## Result\n\n```json\n" + json.dumps(result, indent=2) + "\n```\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="builder.run")
    ap.add_argument("--disk", required=True)
    ap.add_argument("--from-step", type=int, required=True)
    ap.add_argument("--to-step", type=int, required=True)
    ap.add_argument("--patch")
    ap.add_argument("--route")
    ap.add_argument("--max-calls", type=int, default=25)
    ap.add_argument("--drop-conversation", action="store_true")
    ap.add_argument("--fake-llm")
    a = ap.parse_args(argv)

    disk = os.path.abspath(a.disk)
    result = {"ok": False, "disk": disk, "route": a.route, "from_step": a.from_step, "to_step": a.to_step,
              "last_done": None, "capped": False, "invalid": False, "patch_applied": False,
              "spec_sha_before": None, "spec_sha_after": None, "repairs": [], "steps": [],
              "drop_conversation": a.drop_conversation, "model": None, "error": None}
    code = EXIT_ERROR
    try:
        if a.from_step < 1 or a.to_step < a.from_step:
            raise ResumeError(f"bad step range {a.from_step}..{a.to_step}")
        llm = make_llm(a.fake_llm)
        gitops.init_workspace(disk)
        st = statemod.load(disk)
        if a.from_step != st.last_done + 1:
            raise ResumeError(f"--from-step {a.from_step} but state.last_done={st.last_done}")
        result["repairs"] = gitops.repair(disk, st.last_done)
        for r in result["repairs"]:
            loop.log(f"repair: {r}")

        if a.patch:
            p = patchmod.load_patch(a.patch)
            if a.route and a.route != p.route:
                raise PatchError(f"--route {a.route} != patch route {p.route}")
            result["route"] = p.route
            if st.patch_applied and st.patch_id == p.route:
                loop.log(f"patch {p.route} already applied; not re-applying")
            else:
                if st.patch_applied:
                    raise PatchError(f"disk already carries patch {st.patch_id}")
                before, after = patchmod.apply(disk, p)
                st.patch_id, st.patch_applied = p.route, True
                st.spec_sha_before, st.spec_sha_after = before, after
                statemod.save(disk, st)
                loop.log(f"patch {p.route} ({p.kind}) applied: {before[:10]} -> {after[:10]}")

        st.model = _model_of(llm)
        st.params = dict(getattr(llm, "params", {}) or {}, max_calls=a.max_calls)
        result["model"] = st.model
        ex = LocalExec(os.path.join(disk, WORKSPACE))
        hist_min = a.from_step if a.drop_conversation else 1
        for k in range(a.from_step, a.to_step + 1):
            sr = loop.run_step(disk, k, llm, ex, a.max_calls, history_min_step=hist_min)
            st.steps.append(sr)
            st.last_done = k
            statemod.save(disk, st)
            result["steps"].append(sr.__dict__)
            if sr.capped:
                result["capped"] = result["invalid"] = True
                loop.log(f"step {k} capped: branch is invalid, stopping")
                break
        result["ok"] = not result["capped"]
        code = EXIT_CAPPED if result["capped"] else EXIT_OK
    except (PatchError, ResumeError) as e:
        result["error"] = f"{type(e).__name__}: {e}"
        loop.log(result["error"])
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
    try:
        st = statemod.load(disk)
        result.update(last_done=st.last_done, patch_applied=st.patch_applied,
                      spec_sha_before=st.spec_sha_before, spec_sha_after=st.spec_sha_after)
    except Exception:
        pass
    if result["route"]:
        try:
            _route_note(disk, result["route"], result)
        except Exception as e:
            loop.log(f"could not write route note: {e}")
    sys.stdout.flush()
    print("RESULT " + json.dumps(result), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
