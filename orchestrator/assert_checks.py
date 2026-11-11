"""Adapter: fixture check files -> our checks interface (--disk DIR --at-step K | --meta).

Brendan's toy fixture keeps its checks as one-line canaries, e.g.
    checks/test_code.py:            # CHECK-SOURCE-91bc: assert len(make_code()) == 6
    heldout/test_code_heldout.py:   # HELDOUT-SECRET-7f3a: make_code() must never start with zero
Each `# NAME: assert EXPR` line becomes a check named NAME, evaluated against the names defined by the top-level
*.py files in the agent's workspace. A line without `assert` is prose: listed in --meta as unsupported, never graded.
A check whose names don't exist yet (NameError) isn't checkable at that step and is left out, like `from_step`.

build_checks_file(fixture_dir, out_path) writes a self-contained grader (this file + the parsed lines), which is what
gets copied into the sandbox after the builder exits. Standard library only.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import re
import signal
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # importing the agent's code must not write __pycache__ onto its disk
LINE = re.compile(r"^#\s*([A-Za-z0-9_-]+):\s*(.+?)\s*$")
CHECK_LINES: list = []  # filled in by build_checks_file


def parse_fixture(fixture_dir: Path) -> list[dict]:
    out = []
    for sub, heldout in (("checks", False), ("heldout", True)):
        for f in sorted((Path(fixture_dir) / sub).glob("*.py")):
            for line in f.read_text().splitlines():
                m = LINE.match(line.strip())
                if m:
                    body = m.group(2)
                    expr = body[len("assert "):].strip() if body.startswith("assert ") else None
                    out.append({"name": m.group(1), "expr": expr, "heldout": heldout, "source": f"{sub}/{f.name}",
                                "text": body})
    return out


def build_checks_file(fixture_dir: Path, out_path: Path) -> Path:
    lines = json.dumps(parse_fixture(fixture_dir))
    src = Path(__file__).read_text().replace("CHECK_LINES: list = []  # filled in by build_checks_file",
                                             f"CHECK_LINES: list = json.loads({lines!r})", 1)  # the definition only
    Path(out_path).write_text(src)
    return Path(out_path)


def _namespace(ws: Path) -> dict:
    ns: dict = {}
    sys.path.insert(0, str(ws))
    for f in sorted(ws.glob("*.py")):
        if f.name.startswith("test"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            mod = importlib.util.module_from_spec(spec)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                spec.loader.exec_module(mod)  # the agent's code: its prints must not reach our JSON
            ns.update({k: v for k, v in vars(mod).items() if not k.startswith("_")})
        except Exception:
            pass
    return ns


def grade(disk: Path, at_step: int) -> dict:
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("check timed out")))
    signal.alarm(20)
    ns = _namespace(Path(disk) / "workspace")
    out = {}
    for c in CHECK_LINES:
        if c["expr"] is None:
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                out[c["name"]] = bool(eval(c["expr"], dict(ns)))
        except NameError:
            continue  # not checkable yet
        except Exception:
            out[c["name"]] = False
    signal.alarm(0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk")
    ap.add_argument("--at-step", type=int, default=0)
    ap.add_argument("--meta", action="store_true")
    a = ap.parse_args()
    if a.meta:
        print(json.dumps({c["name"]: {"from_step": 1, "file": None, "heldout": c["heldout"], "source": c["source"],
                                      "supported": c["expr"] is not None, "text": c["text"],
                                      "message": f"failed: {c['text']}"} for c in CHECK_LINES}))
        return
    print(json.dumps(grade(Path(a.disk), a.at_step)))


if __name__ == "__main__":
    main()
