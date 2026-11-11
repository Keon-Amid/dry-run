"""Flip test (1:25 gate). Owner: C5.

For each plant, build N disks "with" the plant (template as-is) and N "without" it (the plant's patch applied via
`python -m builder.run --patch`), grade each workspace with $DRYRUN_CHECK_CMD, and append every run to flip.json.
The table is printed only by re-reading flip.json (print_table), never from in-memory numbers.

Capped (exit 2 / RESULT.capped) and errored runs are recorded as invalid: never a pass or a fail.

Usage:
  DRYRUN_CHECK_CMD="python3 grade.py" python3 scripts/flip.py --plants plants.json --disk-template DIR \
      --to-step 3 [--runs 3] [--out flip.json] [--matrix] [--fake-llm script.json]
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ("with", "without")
WORKSPACE = "workspace"  # same as builder.types.WORKSPACE; not imported so this script runs standalone


def parse_result(stdout: str):
    """Return the dict from the last non-empty stdout line if it is `RESULT {json}`, else None."""
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if not lines or not lines[-1].startswith("RESULT "):
        return None
    try:
        return json.loads(lines[-1][len("RESULT "):])
    except json.JSONDecodeError:
        return None


def subprocess_runner(disk: str, to_step: int, patch_path, fake_llm) -> tuple:
    """Run builder.run as a subprocess. Return (exit_code, result_dict_or_None, stderr_tail)."""
    cmd = [sys.executable, "-m", "builder.run", "--disk", disk, "--from-step", "1", "--to-step", str(to_step)]
    if patch_path:
        cmd += ["--patch", patch_path]
    if fake_llm:
        cmd += ["--fake-llm", fake_llm]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return p.returncode, parse_result(p.stdout), p.stderr[-2000:]


def grade(workspace: str, check_cmd: str) -> dict:
    """Run the grader with the workspace path appended. Return {"name": {"pass": bool, "msg": str}}."""
    p = subprocess.run(shlex.split(check_cmd) + [workspace], capture_output=True, text=True)
    data = json.loads(p.stdout)
    checks = data["checks"]
    for name, c in checks.items():
        if not isinstance(c.get("pass"), bool):
            raise ValueError(f"check {name}: 'pass' is not a bool")
    return checks


def write_json_atomic(path: str, obj) -> None:
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".flip.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def one_run(plant: dict, arm: str, i: int, template: str, to_step: int, check_cmd: str, matrix: bool,
            fake_llm, runner) -> dict:
    rec = {"plant": plant["id"], "arm": arm, "run": i, "check": plant["check"], "valid": False, "pass": None,
           "exit": None, "capped": None, "reason": None, "checks": {}}
    tmp = tempfile.mkdtemp(prefix="flip-")
    try:
        disk = os.path.join(tmp, "disk")
        shutil.copytree(template, disk, symlinks=True)
        patch_path = None
        if arm == "without":
            patch_path = os.path.join(tmp, "patch.json")
            with open(patch_path, "w") as f:
                json.dump(plant["patch"], f)
        t0 = time.time()
        try:
            code, result, err = runner(disk, to_step, patch_path, fake_llm)
        except Exception as e:  # runner crashed: invalid, never a fail
            code, result, err = None, None, repr(e)
        rec["wall_s"] = round(time.time() - t0, 3)
        rec["exit"] = code
        rec["result"] = result
        capped = code == 2 or bool(result and result.get("capped"))
        rec["capped"] = capped
        if capped:
            rec["reason"] = "capped"
            return rec
        if code != 0 or result is None:
            rec["reason"] = f"error exit={code}: {(err or '')[-300:]}"
            return rec
        try:
            checks = grade(os.path.join(disk, WORKSPACE), check_cmd)
        except Exception as e:
            rec["reason"] = f"grader error: {e!r}"
            return rec
        if plant["check"] not in checks:
            rec["reason"] = f"grader did not report check {plant['check']!r}"
            return rec
        rec["checks"] = checks if matrix else {plant["check"]: checks[plant["check"]]}
        rec["pass"] = checks[plant["check"]]["pass"]
        rec["valid"] = True
        return rec
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_flip(plants: list, template: str, to_step: int, out: str, runs: int = 3, matrix: bool = False,
             fake_llm=None, check_cmd=None, runner=subprocess_runner) -> str:
    check_cmd = check_cmd or os.environ.get("DRYRUN_CHECK_CMD")
    if not check_cmd:
        raise SystemExit("DRYRUN_CHECK_CMD is not set")
    doc = {"params": {"runs": runs, "to_step": to_step, "matrix": matrix, "template": os.path.abspath(template),
                      "fake_llm": fake_llm, "check_cmd": check_cmd,
                      "plants": [{"id": p["id"], "check": p["check"]} for p in plants]},
           "runs": []}
    write_json_atomic(out, doc)
    for plant in plants:
        for arm in ARMS:
            for i in range(1, runs + 1):
                doc["runs"].append(one_run(plant, arm, i, template, to_step, check_cmd, matrix, fake_llm, runner))
                write_json_atomic(out, doc)
    return out


def verdict(w: dict, wo: dict, runs: int) -> str:
    """Team item B: only all-fail with the plant vs all-pass without it names a culprit."""
    if w["fail"] == runs and wo["pass"] == runs:
        return "FLIP"
    if w["invalid"] or wo["invalid"]:
        return "inconclusive"
    if (w["pass"] == runs and wo["pass"] == runs) or (w["fail"] == runs and wo["fail"] == runs):
        return "no flip"
    return "inconclusive"


def print_table(path: str, file=None) -> str:
    """Read flip.json from disk and print the table. Every number comes from the file."""
    file = file or sys.stdout
    with open(path) as f:
        doc = json.load(f)
    runs = doc["params"]["runs"]
    lines = [f"flip table from {path} (runs per arm: {runs})",
             f"{'plant':<20} {'check':<20} {'with p/f/inv':>13} {'without p/f/inv':>16}  verdict"]
    counts = {}
    for r in doc["runs"]:
        c = counts.setdefault((r["plant"], r["arm"]), {"pass": 0, "fail": 0, "invalid": 0})
        if not r["valid"]:
            c["invalid"] += 1
        elif r["pass"]:
            c["pass"] += 1
        else:
            c["fail"] += 1
    zero = {"pass": 0, "fail": 0, "invalid": 0}
    for p in doc["params"]["plants"]:
        w = counts.get((p["id"], "with"), zero)
        wo = counts.get((p["id"], "without"), zero)
        fmt = lambda c: f"{c['pass']}/{c['fail']}/{c['invalid']}"
        lines.append(f"{p['id']:<20} {p['check']:<20} {fmt(w):>13} {fmt(wo):>16}  {verdict(w, wo, runs)}")
    if doc["params"].get("matrix"):
        lines.append("")
        lines.append("matrix: passes per check (valid runs only)")
        mat = {}
        for r in doc["runs"]:
            if not r["valid"]:
                continue
            for name, c in r["checks"].items():
                m = mat.setdefault((r["plant"], r["arm"], name), [0, 0])
                m[0] += 1 if c["pass"] else 0
                m[1] += 1
        for (plant, arm, name), (ok, n) in sorted(mat.items()):
            lines.append(f"  {plant:<20} {arm:<8} {name:<24} {ok}/{n}")
    text = "\n".join(lines)
    print(text, file=file)
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plants", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--disk-template", required=True)
    ap.add_argument("--to-step", type=int, required=True)
    ap.add_argument("--out", default="flip.json")
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--fake-llm", default=None)
    a = ap.parse_args(argv)
    with open(a.plants) as f:
        plants = json.load(f)
    fake = os.path.abspath(a.fake_llm) if a.fake_llm else None
    run_flip(plants, a.disk_template, a.to_step, a.out, runs=a.runs, matrix=a.matrix, fake_llm=fake)
    print_table(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
