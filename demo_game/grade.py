"""The demo's grader (P2). Deterministic checks only, never an LLM. Standard library only.

Two modes, one set of checks:

  orchestrator:  python3 grade.py --disk DIR --at-step K   ->  {"check_name": true|false, ...}
                 (only checks with from_step <= K; the workspace is DIR/workspace)
                 python3 grade.py --meta                   ->  {"check_name": {"from_step", "file", "heldout"}, ...}
  flip:          python3 grade.py WORKSPACE                ->  {"checks": {"check_name": {"pass": bool, "msg": str}}}

  bundle:        python3 grade.py --bundle OUT.py  writes one self-contained grader with every check embedded, for
                 orchestrator/wave.py, which copies a single file into the sandbox after the builder exits.

A check is one file: demo/checks/<name>.py (visible) or demo/checks_heldout/<name>.py (held out: graded, never shown
to the rewrite step). Neither folder is ever on the agent's disk. Each check file holds

    META = {"from_step": 2, "file": "workspace/app.py"}     # a literal; read with ast, never executed by the grader
    def check(ws):                                         # ws is on sys.path and is the cwd
        from app import make_code
        assert len(make_code()) == 6, "codes are not 6 digits"
        return "6 digits"                                  # optional pass message

check() passes unless it raises (AssertionError -> its message; anything else -> "<Type>: <msg>"). It may also
return (False, "msg") to fail explicitly.

Isolation: each check runs in its own subprocess (python -I -B, clean env, own process group, timeout) against its
own temp copy of the workspace, so a broken, hanging or file-writing build fails that check and nothing else, and
grading never writes to the agent's disk. The check source goes in over stdin; it is never written into the copy.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS_DIR = os.path.join(HERE, "checks")
HELDOUT_DIR = os.path.join(HERE, "checks_heldout")
TIMEOUT_S = 10
WORKSPACE = "workspace"
COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".venv")

# Replaced by --bundle with {name: {"src": str, "heldout": bool}}. None = read the check folders.
EMBEDDED = None

# Runs inside the check subprocess. The real stdout is kept on a private fd for the one result line; fd 1 is pointed
# at stderr so prints from the built code can't forge a result.
RUNNER = r"""
import json, os, sys
_out = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
ws, name = sys.argv[1], sys.argv[2]
src = sys.stdin.read()
sys.stdin = open(os.devnull)
sys.path.insert(0, ws)
os.chdir(ws)
def _res(ok, msg):
    _out.write(json.dumps({"pass": bool(ok), "msg": str(msg)[:500]}) + "\n"); _out.flush()
try:
    ns = {"__name__": "check_" + name}
    exec(compile(src, name + ".py", "exec"), ns)
    r = ns["check"](ws)
    if isinstance(r, tuple):
        _res(r[0], r[1] if len(r) > 1 else "")
    else:
        _res(True, "ok" if r is None else r)
except AssertionError as e:
    _res(False, str(e) or "assertion failed")
except BaseException as e:
    _res(False, type(e).__name__ + ": " + str(e))
"""


def read_meta(src: str, name: str) -> dict:
    """The META literal from a check's source, without running it."""
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "META" for t in node.targets):
            meta = ast.literal_eval(node.value)
            if not isinstance(meta.get("from_step"), int) or not isinstance(meta.get("file"), str):
                raise ValueError(f"check {name}: META needs int from_step and str file")
            return meta
    raise ValueError(f"check {name}: no META")


def load_checks(checks_dir: str = CHECKS_DIR, heldout_dir: str = HELDOUT_DIR) -> dict:
    """{name: {"src", "heldout", "from_step", "file"}}, sorted by name. Names must be unique across both folders."""
    found = {}
    if EMBEDDED is not None:
        found = {n: dict(c) for n, c in EMBEDDED.items()}
    else:
        for d, heldout in ((checks_dir, False), (heldout_dir, True)):
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".py") or fn.startswith(("_", ".")):
                    continue
                name = fn[:-3]
                if name in found:
                    raise ValueError(f"check {name} is defined twice")
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    found[name] = {"src": f.read(), "heldout": heldout}
    for name, c in found.items():
        m = read_meta(c["src"], name)
        c.update(from_step=m["from_step"], file=m["file"])
    return dict(sorted(found.items()))


def _clean_env() -> dict:
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    return env


def run_check(name: str, src: str, workspace: str, timeout: float = TIMEOUT_S) -> dict:
    """{"pass": bool, "msg": str}. Never raises: any failure of the build or the check is a fail with a reason."""
    if not os.path.isdir(workspace):
        return {"pass": False, "msg": f"no workspace at {workspace}"}
    tmp = tempfile.mkdtemp(prefix=f"grade-{name}-")
    try:
        ws = os.path.join(tmp, WORKSPACE)
        shutil.copytree(workspace, ws, symlinks=True, ignore=COPY_IGNORE)
        p = subprocess.Popen([sys.executable, "-I", "-B", "-c", RUNNER, ws, name], cwd=ws, env=_clean_env(),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
        try:
            out, err = p.communicate(src, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill(p)
            return {"pass": False, "msg": f"timeout after {timeout}s"}
        finally:
            _kill(p)  # anything the build left running in the group (a server, a child) dies with the check
        lines = [ln for ln in out.splitlines() if ln.strip()]
        try:
            res = json.loads(lines[-1])
            return {"pass": res["pass"] is True, "msg": str(res.get("msg", ""))}
        except (IndexError, ValueError, KeyError, TypeError):
            tail = err.strip().splitlines()[-1:] or [f"exit {p.returncode}"]
            return {"pass": False, "msg": f"no result: {tail[0][:300]}"}
    except Exception as e:  # copy failed etc.: still a fail, never a grader crash
        return {"pass": False, "msg": f"grader: {type(e).__name__}: {e}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _kill(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def grade(workspace: str, checks: dict, timeout: float = TIMEOUT_S, at_step: int | None = None) -> dict:
    """{name: {"pass", "msg"}} for every check (or those with from_step <= at_step), run in parallel."""
    names = [n for n, c in checks.items() if at_step is None or c["from_step"] <= at_step]
    with ThreadPoolExecutor(max_workers=min(8, len(names) or 1)) as ex:
        results = list(ex.map(lambda n: run_check(n, checks[n]["src"], workspace, timeout), names))
    return dict(zip(names, results))


def meta(checks: dict) -> dict:
    return {n: {"from_step": c["from_step"], "file": c["file"], "heldout": c["heldout"]} for n, c in checks.items()}


def bundle(out: str, checks: dict) -> None:
    """Write a standalone copy of this grader with every check embedded (EMBEDDED = {...})."""
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        me = f.read()
    emb = {n: {"src": c["src"], "heldout": c["heldout"]} for n, c in checks.items()}
    marker = "\nEMBEDDED = None\n"
    assert me.count(marker) == 1
    with open(out, "w", encoding="utf-8") as f:
        f.write(me.replace(marker, f"\nEMBEDDED = {emb!r}\n"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", nargs="?", help="flip mode: grade this workspace, every check")
    ap.add_argument("--disk", help="orchestrator mode: grade DIR/workspace")
    ap.add_argument("--at-step", type=int, default=None, help="only checks checkable by this step")
    ap.add_argument("--meta", action="store_true")
    ap.add_argument("--bundle", metavar="OUT")
    ap.add_argument("--checks-dir", default=CHECKS_DIR)
    ap.add_argument("--heldout-dir", default=HELDOUT_DIR)
    ap.add_argument("--timeout", type=float, default=TIMEOUT_S, help="seconds per check")
    a = ap.parse_args(argv)
    checks = load_checks(a.checks_dir, a.heldout_dir)
    if a.bundle:
        bundle(a.bundle, checks)
        print(json.dumps({"bundle": a.bundle, "checks": len(checks)}))
        return 0
    if a.meta:
        print(json.dumps(meta(checks)))
        return 0
    if a.disk:
        res = grade(os.path.join(a.disk, WORKSPACE), checks, a.timeout, a.at_step)
        print(json.dumps({n: r["pass"] for n, r in res.items()}))
        return 0
    if a.workspace:
        print(json.dumps({"checks": grade(a.workspace, checks, a.timeout, a.at_step)}))
        return 0
    ap.error("give a WORKSPACE, --disk DIR, --meta or --bundle OUT")
    return 2


if __name__ == "__main__":
    sys.exit(main())
