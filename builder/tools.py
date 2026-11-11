"""Local Exec: tools confined to DISK/workspace. Owner: C2.

Known limit: bash can still `cd /` and read any file on the box. Path checks only cover the
file tools. Real isolation is the sandbox; locally, keep checks outside the disk folder.
"""
from __future__ import annotations

import os
import signal
import subprocess

MAX_OUT = 4000
KEEP_ENV = ("PATH", "HOME", "LANG", "TMPDIR")

TOOL_SCHEMAS: list = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file in the workspace. Path is relative to the workspace root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path relative to the workspace."}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file in the workspace with the given content. Parent directories are created.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the workspace."},
                "content": {"type": "string", "description": "Full file content."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "Recursively list files under a workspace directory (default: the workspace root). Skips .git.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory relative to the workspace.", "default": "."}},
            "required": [],
        },
    },
    {
        "name": "bash",
        "description": "Run a shell command with cwd = workspace root. 30 s timeout. Returns combined stdout+stderr and the exit code.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The shell command to run."}},
            "required": ["command"],
        },
    },
]


class PathEscape(ValueError):
    """A tool path resolved outside the workspace."""


def truncate(s: str, limit: int = MAX_OUT) -> str:
    """Cap s at `limit` chars total, ending with a marker that says how much was cut."""
    if len(s) <= limit:
        return s
    marker = "\n[... truncated: {} chars omitted ...]"
    # Marker length depends on the omitted count; size it with the worst case.
    keep = limit - len(marker.format(len(s)))
    return s[:keep] + marker.format(len(s) - keep)


def clean_env() -> dict:
    return {k: os.environ[k] for k in KEEP_ENV if k in os.environ}


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class LocalExec:
    def __init__(self, workspace: str):
        os.makedirs(workspace, exist_ok=True)
        self.workspace = os.path.realpath(workspace)

    def _resolve(self, p: str) -> str:
        if not isinstance(p, str) or p == "":
            raise PathEscape(f"bad path: {p!r}")
        cand = p if os.path.isabs(p) else os.path.join(self.workspace, p)
        real = os.path.realpath(cand)   # follows symlinks, so a link pointing out resolves out
        if os.path.commonpath([real, self.workspace]) != self.workspace:
            raise PathEscape(f"path escapes workspace: {p}")
        return real

    def read_file(self, p: str) -> str:
        real = self._resolve(p)
        with open(real, "r", encoding="utf-8", errors="replace") as f:
            return truncate(f.read())

    def write_file(self, p: str, s: str) -> str:
        real = self._resolve(p)
        if real == self.workspace:
            raise PathEscape(f"cannot write to the workspace root: {p}")
        os.makedirs(os.path.dirname(real), exist_ok=True)
        with open(real, "w", encoding="utf-8") as f:
            f.write(s)
        return f"wrote {len(s.encode('utf-8'))} bytes to {os.path.relpath(real, self.workspace)}"

    def list_files(self, p: str = ".") -> str:
        root = self._resolve(p)
        if not os.path.isdir(root):
            raise NotADirectoryError(f"not a directory: {p}")
        out = []
        for d, dirs, files in os.walk(root):          # followlinks=False: never walks out via a link
            dirs[:] = sorted(x for x in dirs if x != ".git")
            for name in sorted(files):
                out.append(os.path.relpath(os.path.join(d, name), self.workspace))
        return truncate("\n".join(out) if out else "(no files)")

    def bash(self, cmd: str, timeout: int = 30) -> str:
        proc = subprocess.Popen(
            ["/bin/bash", "-c", cmd],
            cwd=self.workspace,
            env=clean_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc.pid)
            out, _ = proc.communicate()
            text = out.decode("utf-8", errors="replace")
            tail = f"\n[timeout after {timeout}s: process group killed]"
            return truncate(text, MAX_OUT - len(tail)) + tail
        finally:
            _kill_group(proc.pid)   # reap any background children left behind
        text = out.decode("utf-8", errors="replace")
        tail = f"\n[exit code {proc.returncode}]"
        return truncate(text, MAX_OUT - len(tail)) + tail


def dispatch(ex, name: str, args: dict) -> str:
    """Call the named tool on ex. Raise on unknown tool / bad args (caller turns it into is_error)."""
    if not isinstance(args, dict):
        raise ValueError(f"tool args must be an object, got {type(args).__name__}")

    def need(key: str) -> str:
        if key not in args:
            raise ValueError(f"{name}: missing required argument '{key}'")
        v = args[key]
        if not isinstance(v, str):
            raise ValueError(f"{name}: argument '{key}' must be a string")
        return v

    if name == "read_file":
        return ex.read_file(need("path"))
    if name == "write_file":
        return ex.write_file(need("path"), need("content"))
    if name == "list_files":
        return ex.list_files(need("path") if "path" in args else ".")
    if name == "bash":
        return ex.bash(need("command"))
    raise ValueError(f"unknown tool: {name}")
