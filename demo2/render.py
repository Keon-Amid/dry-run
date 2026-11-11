"""Turn a Dungeon Painter workspace into one picture. Standard library only.

  python3 demo2/render.py WORKSPACE OUT.svg
      runs the workspace's scene.render_demo() in a subprocess (python -I -B, cwd = a temp copy, timeout) and writes
      the SVG, or a "build failed" placeholder SVG if it raises, hangs or returns something that isn't SVG.
  python3 demo2/render.py --side-by-side BASE_WS FIXED_WS OUT.html
      one standalone HTML page: the two pictures next to each other, captioned "base run" / "after Banzai", each with
      its failing and passing checks (from demo2/grade.py).

The workspace is copied first, so rendering never writes to it. Built SVG is shown through <img src="data:...">, so
any script inside it never runs.
"""
from __future__ import annotations

import base64
import html
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT_S = 20
RUN = "import sys, scene; sys.stdout.write(scene.render_demo())"


def placeholder(reason: str) -> str:
    """A visible 'build failed' picture carrying the reason."""
    lines = [reason[i:i + 60] for i in range(0, min(len(reason), 300), 60)] or [""]
    body = "".join(f'<text x="16" y="{70 + 18 * i}" fill="#f5c6cb" font-family="monospace" font-size="13">'
                   f"{html.escape(ln)}</text>" for i, ln in enumerate(lines))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="368" height="180">'
            '<rect x="0" y="0" width="368" height="180" fill="#3b0d12"/>'
            '<text x="16" y="40" fill="#ffffff" font-family="monospace" font-size="20">build failed</text>'
            f"{body}</svg>\n")


def render(workspace: str, timeout: float = TIMEOUT_S) -> tuple:
    """(svg_text, ok). Never raises: a broken build gives (placeholder, False)."""
    if not os.path.isdir(workspace):
        return placeholder(f"no workspace at {workspace}"), False
    tmp = tempfile.mkdtemp(prefix="render-")
    try:
        ws = os.path.join(tmp, "workspace")
        shutil.copytree(workspace, ws, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
        code = f"import sys; sys.path.insert(0, {ws!r}); " + RUN
        try:
            p = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ws, env=env, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return placeholder(f"timeout after {timeout}s"), False
        if p.returncode != 0:
            tail = (p.stderr.strip().splitlines() or [f"exit {p.returncode}"])[-1]
            return placeholder(tail), False
        try:
            root = ET.fromstring(p.stdout)
        except ET.ParseError as e:
            return placeholder(f"not valid SVG: {e}"), False
        if root.tag.split("}")[-1] != "svg":
            return placeholder(f"root element is <{root.tag}>, not <svg>"), False
        return p.stdout, True
    except Exception as e:  # copy failed etc.
        return placeholder(f"{type(e).__name__}: {e}"), False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _panel(caption: str, svg: str, checks: dict) -> str:
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    fails = sorted(n for n, r in checks.items() if not r["pass"])
    passes = sorted(n for n, r in checks.items() if r["pass"])
    items = "".join(f'<li class="fail"><b>{html.escape(n)}</b> {html.escape(checks[n]["msg"][:160])}</li>'
                    for n in fails)
    items += "".join(f'<li class="pass">{html.escape(n)}</li>' for n in passes)
    return (f'<figure><figcaption>{html.escape(caption)} &middot; {len(passes)}/{len(checks)} checks pass'
            f'</figcaption><img alt="{html.escape(caption)}" src="{uri}"><ul>{items}</ul></figure>')


def side_by_side(base_ws: str, fixed_ws: str, out: str) -> str:
    """Write the comparison page; return its path."""
    sys.path.insert(0, os.path.dirname(HERE))
    from demo2 import grade as g
    checks = g.load_checks()
    panels = []
    for caption, ws in (("base run", base_ws), ("after Banzai", fixed_ws)):
        svg, _ = render(ws)
        panels.append(_panel(caption, svg, g.grade(ws, checks)))
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dungeon Painter: before and after</title>
<style>
body {{ margin: 0; padding: 16px; background: #111318; color: #e8e8ec; font: 14px/1.4 system-ui, sans-serif; }}
main {{ display: flex; flex-wrap: wrap; gap: 24px; }}
figure {{ flex: 1 1 360px; margin: 0; min-width: 0; }}
figcaption {{ font-size: 18px; font-weight: 600; margin-bottom: 8px; }}
img {{ width: 100%; height: auto; image-rendering: pixelated; border: 1px solid #333; }}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 2px 0; overflow-wrap: anywhere; }}
.fail {{ color: #ff8a80; }} .fail::before {{ content: "FAIL "; }}
.pass {{ color: #8fd19e; }} .pass::before {{ content: "pass "; }}
</style></head><body><main>{"".join(panels)}</main></body></html>
"""
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 4 and argv[0] == "--side-by-side":
        print(side_by_side(argv[1], argv[2], argv[3]))
        return 0
    if len(argv) == 2:
        svg, ok = render(argv[0])
        with open(argv[1], "w", encoding="utf-8") as f:
            f.write(svg)
        print(("rendered " if ok else "build failed, placeholder written to ") + argv[1])
        return 0 if ok else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
