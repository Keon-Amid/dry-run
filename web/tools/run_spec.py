"""Run the pipeline on an uploaded spec.

Same as `python -m orchestrator.pipeline ...`, with one difference: the chosen fixture's spec text is replaced by the
file given with --spec. Rules, checks, held-out checks and golden stay the fixture's, so the uploaded spec has to be a
spec for that same project. The fixture's pre-registered suspects are edits to its own spec, so they are dropped and
the pipeline derives suspects from the uploaded spec instead.

  python web/tools/run_spec.py --spec my-spec.md --fixture demo --builder real [--local] [--smoke] ...
"""
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import orchestrator.pipeline as P  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    if "--spec" not in args:
        raise SystemExit("usage: run_spec.py --spec FILE [pipeline options]")
    i = args.index("--spec")
    text = Path(args[i + 1]).read_text()
    del args[i:i + 2]
    original = P.load_fixture

    def with_uploaded_spec(name, scratch):
        fx = original(name, scratch)
        return dataclasses.replace(fx, spec=text, suspects=None)

    P.load_fixture = with_uploaded_spec
    sys.argv = ["orchestrator.pipeline", *args]
    print(f"uploaded spec: {len(text)} chars, {text.count(chr(10) + '## Step ') + text.startswith('## Step ')} steps", flush=True)
    P.main()


if __name__ == "__main__":
    main()
