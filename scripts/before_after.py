"""Before / after, in the built code itself: the original build vs the CONFIRM build (and the baseline, if exported).

    python3 scripts/before_after.py orchestrator/runs/<run> [--json OUT]

Loads the workspaces the pipeline exported into <run>/workspaces/ (build, confirm-<check>, baseline-<check>) and runs
the same probes against each, side by side:
  1. shorten a URL at day 0, resolve it at day 25 (a click), resolve it again at day 31
  2. normalize("not a url")
Each workspace runs in its own `python -I -B` subprocess with the workspace as cwd, so nothing is written into it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DAY = 86400
PROBE = r'''
import json, sys
sys.path.insert(0, ".")
out = {}
def run(label, fn):
    try:
        out[label] = repr(fn())
    except Exception as e:
        out[label] = f"raises {type(e).__name__}: {e}"
try:
    from links import Shortlink
    s = Shortlink()
    code = {}
    run("shorten(url, now=day 0)", lambda: code.setdefault("c", s.shorten("https://Example.com/a?b=1", now=0)))
    run("resolve(code, now=day 25)", lambda: s.resolve(code.get("c"), now=25 * %(day)d))
    run("resolve(code, now=day 31)", lambda: s.resolve(code.get("c"), now=31 * %(day)d))
except Exception as e:
    out["links.Shortlink"] = f"import failed: {type(e).__name__}: {e}"
try:
    from urls import normalize
    run('normalize("not a url")', lambda: normalize("not a url"))
except Exception as e:
    out["urls.normalize"] = f"import failed: {type(e).__name__}: {e}"
print(json.dumps(out))
''' % {"day": DAY}


def probe(ws: Path) -> dict:
    r = subprocess.run([sys.executable, "-I", "-B", "-c", PROBE], cwd=ws, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout).strip()[-300:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> int:
    args = sys.argv[1:]
    out_json = None
    if "--json" in args:
        i = args.index("--json")
        out_json = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    run = Path(args[0])
    wss = run / "workspaces"
    cols = [("before (original build)", wss / "build")]
    cols += [(f"after ({p.name})", p) for p in sorted(wss.glob("confirm-*"))]
    cols += [(f"baseline ({p.name})", p) for p in sorted(wss.glob("baseline-*"))]
    cols = [(name, p) for name, p in cols if p.is_dir()]
    if not cols:
        print(f"no exported workspaces in {wss}")
        return 1
    results = [(name, probe(p)) for name, p in cols]
    if out_json:
        out_json.write_text(json.dumps({"probes": ["shorten at day 0, resolve at day 25 (a click), resolve at day 31",
                                                   'normalize("not a url")'],
                                        "columns": [{"name": name, "workspace": str(p.relative_to(run)), "results": r}
                                                    for (name, r), (_, p) in zip(results, cols)]}, indent=2) + "\n")
    rows = list(dict.fromkeys(k for _, r in results for k in r))
    w0 = max(len(r) for r in rows)
    widths = [max(len(name), *(len(str(r.get(k, ""))) for k in rows)) for name, r in results]
    print(" " * w0 + " | " + " | ".join(n.ljust(w) for (n, _), w in zip(results, widths)))
    print("-" * w0 + "-+-" + "-+-".join("-" * w for w in widths))
    for k in rows:
        print(k.ljust(w0) + " | " + " | ".join(str(r.get(k, "")).ljust(w) for (_, r), w in zip(results, widths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
