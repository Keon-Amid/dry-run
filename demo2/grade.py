"""demo2's grader (Dungeon Painter): demo/grade.py's logic, pointed at demo2's check folders. Standard library only.

Same CLI as demo/grade.py:
  python3 demo2/grade.py WORKSPACE                      -> {"checks": {name: {"pass", "msg"}}}   (flip mode)
  python3 demo2/grade.py --disk DIR --at-step K         -> {name: bool}                          (orchestrator)
  python3 demo2/grade.py --meta                         -> {name: {"from_step", "file", "heldout"}}
  python3 demo2/grade.py --bundle OUT.py                -> one standalone grader with demo2's checks embedded
--checks-dir / --heldout-dir still override the folders. Nothing under demo/ is changed.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from demo import grade as _g  # noqa: E402

CHECKS_DIR = os.path.join(HERE, "checks")
HELDOUT_DIR = os.path.join(HERE, "checks_heldout")
TIMEOUT_S = _g.TIMEOUT_S
run_check = _g.run_check
grade = _g.grade
meta = _g.meta


def load_checks(checks_dir: str = CHECKS_DIR, heldout_dir: str = HELDOUT_DIR) -> dict:
    """demo2's checks: {name: {"src", "heldout", "from_step", "file"}}."""
    return _g.load_checks(checks_dir, heldout_dir)


def bundle(out: str, checks: dict | None = None) -> None:
    """A standalone copy of demo/grade.py with demo2's checks embedded."""
    _g.bundle(out, load_checks() if checks is None else checks)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not any(a == "--checks-dir" or a.startswith("--checks-dir=") for a in argv):
        argv = ["--checks-dir", CHECKS_DIR] + argv
    if not any(a == "--heldout-dir" or a.startswith("--heldout-dir=") for a in argv):
        argv = ["--heldout-dir", HELDOUT_DIR] + argv
    return _g.main(argv)


if __name__ == "__main__":
    sys.exit(main())
