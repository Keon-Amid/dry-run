"""Apply a Patch to the disk's spec.md / rules/. Owner: C3.

Every kind goes through `apply`:
- spec_line: replace `old` with `new` inside the `## Step k` section only (exactly one match there).
- rule_off: delete rules/<rule> outright (no `.off/` copy anywhere on the disk).
- control: same write path as spec_line, but writes back identical bytes (sha unchanged).
After the edit, a landed-assert re-reads the disk and raises PatchError if the edit didn't take.
Then routes/<route>.md records the patch JSON, the hypothesis and both spec shas.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile

from builder.types import Patch, PatchError, RULES, ROUTES, SPEC

KINDS = ("spec_line", "rule_off", "control")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def spec_sha(disk: str) -> str:
    """sha256 hex of spec.md bytes."""
    with open(os.path.join(disk, SPEC), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_patch(path: str) -> Patch:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        raise PatchError(f"patch file {path} is not a JSON object")
    try:
        p = Patch.from_dict(d)
    except KeyError as e:
        raise PatchError(f"patch file {path} missing field {e}") from None
    _validate(p)
    return p


def _safe_name(name, what: str) -> str:
    """A bare file name: no path separators, no '..', no leading dot."""
    if not isinstance(name, str) or not name:
        raise PatchError(f"{what} must be a non-empty string")
    if "/" in name or "\\" in name or os.sep in name or (os.altsep and os.altsep in name):
        raise PatchError(f"{what} {name!r} contains a path separator")
    if name in (".", "..") or ".." in name or not _NAME_RE.match(name):
        raise PatchError(f"{what} {name!r} is not a plain file name")
    return name


def _validate(p: Patch) -> None:
    if p.kind not in KINDS:
        raise PatchError(f"unknown patch kind {p.kind!r}")
    _safe_name(p.route, "route")
    if p.kind == "spec_line":
        if not isinstance(p.step, int) or isinstance(p.step, bool):
            raise PatchError("spec_line needs an integer step")
        if not isinstance(p.old, str) or not p.old:
            raise PatchError("spec_line needs a non-empty old")
        if not isinstance(p.new, str):
            raise PatchError("spec_line needs new (a string; '' deletes)")
    elif p.kind == "rule_off":
        _safe_name(p.rule, "rule")
    elif p.kind == "control":
        if p.old is not None and (not isinstance(p.step, int) or isinstance(p.step, bool)):
            raise PatchError("control with old needs an integer step")


def _write_bytes(path: str, data: bytes) -> None:
    """Atomic write: tmp file in the same dir, fsync, os.replace, dir fsync."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    try:
        dfd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def _section_bounds(text: str, step: int) -> tuple:
    """(start, end) char offsets of the body of `## Step <step>` (after its heading line, up to the
    next heading of level 1 or 2, or EOF). PatchError if the heading is missing or duplicated."""
    head = re.compile(r"^##[ \t]+Step[ \t]+" + str(step) + r"\b.*$", re.MULTILINE)
    heads = list(head.finditer(text))
    if len(heads) != 1:
        raise PatchError(f"spec has {len(heads)} '## Step {step}' headings (need exactly 1)")
    start = heads[0].end()
    nxt = re.compile(r"^#{1,2}[ \t]", re.MULTILINE).search(text, start)
    end = nxt.start() if nxt else len(text)
    return start, end


def _replace_in_step(text: str, step: int, old: str, new: str) -> str:
    start, end = _section_bounds(text, step)
    section = text[start:end]
    n = section.count(old)
    if n != 1:
        raise PatchError(f"old text matches {n} times in step {step} (need exactly 1): {old!r}")
    return text[:start] + section.replace(old, new, 1) + text[end:]


def _read_spec(disk: str) -> tuple:
    path = os.path.join(disk, SPEC)
    if not os.path.isfile(path):
        raise PatchError(f"no {SPEC} on disk {disk}")
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return path, raw, raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise PatchError(f"{SPEC} is not utf-8: {e}") from None


def _apply_spec(disk: str, p: Patch) -> None:
    path, raw, text = _read_spec(disk)
    if p.kind == "spec_line":
        want = _replace_in_step(text, p.step, p.old, p.new).encode("utf-8")
        if want == raw:
            raise PatchError("spec_line edit is a no-op (old == new); use kind=control")
    else:  # control: same path, identical bytes
        if p.old is not None:
            want = _replace_in_step(text, p.step, p.old, p.old).encode("utf-8")
        else:
            want = raw
    _write_bytes(path, want)
    with open(path, "rb") as f:
        got = f.read()
    if got != want:
        raise PatchError(f"{p.kind} edit did not land in {SPEC}")
    if p.kind == "spec_line" and got == raw:
        raise PatchError("spec_line edit did not change spec.md")


def _apply_rule_off(disk: str, p: Patch) -> None:
    rules_dir = os.path.join(disk, RULES)
    path = os.path.join(rules_dir, p.rule)
    if not os.path.lexists(path):
        raise PatchError(f"rule {p.rule!r} not found in {RULES}/")
    if os.path.isdir(path) and not os.path.islink(path):
        raise PatchError(f"rule {p.rule!r} is a directory")
    _remove(path)
    if os.path.lexists(path):
        raise PatchError(f"rule_off did not land: {RULES}/{p.rule} still exists")


def _remove(path: str) -> None:
    os.unlink(path)
    try:
        dfd = os.open(os.path.dirname(path), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def _route_md(p: Patch, before: str, after: str) -> str:
    return (
        f"# Route {p.route}\n\n"
        f"## Hypothesis\n{p.hypothesis}\n\n"
        f"## Patch\n```json\n{json.dumps(_patch_dict(p), indent=2, ensure_ascii=False)}\n```\n\n"
        f"## Applied\n- kind: {p.kind}\n- spec_sha_before: {before}\n- spec_sha_after: {after}\n"
    )


def _patch_dict(p: Patch) -> dict:
    return {"route": p.route, "kind": p.kind, "step": p.step, "old": p.old, "new": p.new,
            "rule": p.rule, "hypothesis": p.hypothesis}


def apply(disk: str, p: Patch) -> tuple:
    """Apply p, assert it landed, write routes/<route>.md. Return (sha_before, sha_after).
    Raise PatchError on 0 / >1 matches, missing rule, or edit not landed."""
    _validate(p)
    before = spec_sha(disk) if os.path.isfile(os.path.join(disk, SPEC)) else None
    if before is None:
        raise PatchError(f"no {SPEC} on disk {disk}")
    if p.kind == "rule_off":
        _apply_rule_off(disk, p)
    else:
        _apply_spec(disk, p)
    after = spec_sha(disk)
    if p.kind == "spec_line" and after == before:
        raise PatchError("spec_line did not land: spec sha unchanged")
    if p.kind in ("control", "rule_off") and after != before:
        raise PatchError(f"{p.kind} changed spec.md (sha {before[:12]} -> {after[:12]})")
    routes = os.path.join(disk, ROUTES)
    os.makedirs(routes, exist_ok=True)
    _write_bytes(os.path.join(routes, p.route + ".md"), _route_md(p, before, after).encode("utf-8"))
    return before, after
