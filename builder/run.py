"""CLI. Owner: lead (Phase 2).

python -m builder.run --disk DIR --from-step K --to-step N [--patch patch.json] [--route ID]
                      [--max-calls 25] [--drop-conversation] [--fake-llm script.json]

Logs go to stderr. The last stdout line is always `RESULT {json}`.
Exit: 0 ok, 2 capped/invalid branch (budget hit, max_tokens, refusal; sticky across processes), 1 error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback

from builder import gitops, loop, patch as patchmod, state as statemod
from builder.tools import LocalExec
from builder.types import PatchError, ResumeError, WORKSPACE, ROUTES, SPEC

EXIT_OK, EXIT_ERROR, EXIT_CAPPED = 0, 1, 2
_STEP_HDR = re.compile(r"^##\s+Step\s+(\d+)\b", re.M)
# Never visible to the agent's tools (bash env is already minimal; this also hides them from `ps eww $PPID`).
_SECRET_ENV = re.compile(r"(^ANTHROPIC_|_KEY$|_TOKEN$|_SECRET$|^DRYRUN_CHECK_CMD$)")


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):   # argparse would exit 2, which means "capped" here
        raise UsageError(f"usage: {message}")


def make_llm(fake_script: str | None):
    if fake_script:
        from builder.fake_llm import FakeLLM
        return FakeLLM.from_file(fake_script)
    from builder.llm import AnthropicLLM
    return AnthropicLLM()


def scrub_env(llm) -> None:
    if hasattr(llm, "capture_key"):
        llm.capture_key()
    for k in list(os.environ):
        if _SECRET_ENV.search(k):
            del os.environ[k]


def check_spec_steps(disk: str, to_step: int) -> None:
    with open(os.path.join(disk, SPEC), encoding="utf-8") as f:
        nums = [int(n) for n in _STEP_HDR.findall(f.read())]
    missing = [k for k in range(1, to_step + 1) if nums.count(k) != 1]
    if missing:
        raise ResumeError(f"spec.md needs exactly one '## Step k' header for k=1..{to_step}; bad: {missing}")


def _model_of(llm) -> str:
    return getattr(llm, "model", None) or type(llm).__name__


def _route_note(disk: str, route: str, p, result: dict) -> None:
    os.makedirs(os.path.join(disk, ROUTES), exist_ok=True)
    path = os.path.join(disk, ROUTES, f"{route}.md")
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8") as f:
        if p is not None and new:
            f.write(patchmod.route_md(p, result.get("spec_sha_before") or "", result.get("spec_sha_after") or ""))
        f.write("\n## Result\n\n```json\n" + json.dumps(result, indent=2) + "\n```\n")


def _apply_patch(disk: str, st, p, a, result: dict) -> None:
    if a.route and a.route != p.route:
        raise PatchError(f"--route {a.route} != patch route {p.route}")
    if p.step is not None and p.step > a.to_step:
        raise PatchError(f"patch edits step {p.step}, beyond --to-step {a.to_step}: it would never be built")
    if (p.step is not None and p.step < a.from_step) or (p.kind == "rule_off" and a.from_step > 1):
        result["patch_warning"] = (f"steps 1..{a.from_step - 1} were built before this {p.kind} edit; "
                                   "it only affects later steps")
        loop.log(result["patch_warning"])
    if st.patch_id not in (None, p.route):
        raise PatchError(f"disk already carries patch {st.patch_id}")
    if st.patch_id == p.route and st.patch_applied:
        loop.log(f"patch {p.route} already applied; not re-applying")
        return
    cur = patchmod.spec_sha(disk)
    if st.patch_id == p.route:
        # pending marker from a crashed run: the edit may already be on disk; never apply it twice
        landed = None
        if p.kind == "spec_line" and cur != st.spec_sha_before:
            landed = True
        elif p.kind == "rule_off" and not os.path.exists(os.path.join(disk, "rules", p.rule or "")):
            landed = cur == st.spec_sha_before or None
        elif cur != st.spec_sha_before:
            raise PatchError(f"pending {p.kind} patch but spec.md changed since it was started")
        if landed:
            st.patch_applied, st.spec_sha_after = True, cur
            statemod.save(disk, st)
            result["repairs"].append(f"patch {p.route} had landed before a crash; recorded, not re-applied")
            return
    st.patch_id, st.patch_applied, st.spec_sha_before = p.route, False, cur   # pending marker
    statemod.save(disk, st)
    before, after = patchmod.apply(disk, p, write_route=False)
    st.patch_applied, st.spec_sha_before, st.spec_sha_after = True, before, after
    statemod.save(disk, st)
    loop.log(f"patch {p.route} ({p.kind}) applied: {before[:10]} -> {after[:10]}")


def main(argv=None) -> int:
    ap = _Parser(prog="builder.run")
    ap.add_argument("--disk", required=True)
    ap.add_argument("--from-step", type=int, required=True)
    ap.add_argument("--to-step", type=int, required=True)
    ap.add_argument("--patch")
    ap.add_argument("--route")
    ap.add_argument("--max-calls", type=int, default=25)
    ap.add_argument("--drop-conversation", action="store_true")
    ap.add_argument("--fake-llm")
    try:
        a = ap.parse_args(argv)
    except UsageError as e:
        print("RESULT " + json.dumps({"ok": False, "invalid": False, "capped": False, "error": str(e)}), flush=True)
        return EXIT_ERROR

    disk = os.path.abspath(a.disk)
    result = {"ok": False, "disk": disk, "route": a.route, "from_step": a.from_step, "to_step": a.to_step,
              "last_done": None, "capped": False, "invalid": False, "patch_applied": False,
              "spec_sha_before": None, "spec_sha_after": None, "repairs": [], "steps": [],
              "drop_conversation": a.drop_conversation, "model": None, "error": None}
    code = EXIT_ERROR
    p = None
    try:
        if a.from_step < 1 or a.to_step < a.from_step:
            raise ResumeError(f"bad step range {a.from_step}..{a.to_step}")
        llm = make_llm(a.fake_llm)
        scrub_env(llm)
        check_spec_steps(disk, a.to_step)
        gitops.init_workspace(disk)
        st = statemod.load(disk)
        if a.from_step != st.last_done + 1:
            raise ResumeError(f"--from-step {a.from_step} but state.last_done={st.last_done}")
        result["repairs"] = gitops.repair(disk, st.last_done)
        for r in result["repairs"]:
            loop.log(f"repair: {r}")

        prior_capped = [s.step for s in st.steps if s.capped]
        if prior_capped:
            result["capped"] = result["invalid"] = True
            result["error"] = f"disk carries capped step(s) {prior_capped}: branch is invalid, not run"
            loop.log(result["error"])
            code = EXIT_CAPPED
        else:
            if a.patch:
                p = patchmod.load_patch(a.patch)
                result["route"] = p.route
                _apply_patch(disk, st, p, a, result)
            elif st.patch_id and not st.patch_applied:
                raise PatchError(f"patch {st.patch_id} is pending on this disk; rerun with --patch")

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
            _route_note(disk, result["route"], p, result)
        except Exception as e:
            loop.log(f"could not write route note: {e}")
    sys.stdout.flush()
    print("RESULT " + json.dumps(result), flush=True)
    return code


_KEEP_ENV = ("PATH", "HOME", "LANG", "TMPDIR", "DRYRUN_MODEL")


def reexec_clean() -> None:
    """Re-exec this CLI with a minimal environment, passing ANTHROPIC_API_KEY through a one-shot pipe.

    Deleting from os.environ is not enough: `ps eww $PPID` (macOS) and /proc/<pid>/environ (Linux) show the
    environment a process was exec'd with, and the agent's bash runs as our child. After execve the initial
    environment holds no secrets (no key, no DRYRUN_CHECK_CMD, no *_TOKEN)."""
    if os.environ.get("DRYRUN_CLEAN") == "1":
        fd = os.environ.pop("DRYRUN_KEY_FD", None)
        if fd is not None:
            with os.fdopen(int(fd), "rb") as f:
                os.environ["ANTHROPIC_API_KEY"] = f.read().decode()   # captured + popped again by scrub_env
        return
    env = {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}
    env["DRYRUN_CLEAN"] = "1"
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        r, w = os.pipe()
        os.write(w, key.encode())
        os.close(w)
        os.set_inheritable(r, True)
        env["DRYRUN_KEY_FD"] = str(r)
    sys.stdout.flush()
    sys.stderr.flush()
    os.execve(sys.executable, [sys.executable, "-m", "builder.run", *sys.argv[1:]], env)


if __name__ == "__main__":
    reexec_clean()
    sys.exit(main())
