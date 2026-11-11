"""Local Exec: tools confined to DISK/workspace. Owner: C2."""
from __future__ import annotations

MAX_OUT = 4000

TOOL_SCHEMAS: list = []   # Anthropic tool defs: read_file{path}, write_file{path,content}, list_files{path?}, bash{command}


class LocalExec:
    def __init__(self, workspace: str):
        raise NotImplementedError

    def read_file(self, p: str) -> str:
        raise NotImplementedError

    def write_file(self, p: str, s: str) -> str:
        raise NotImplementedError

    def list_files(self, p: str = ".") -> str:
        raise NotImplementedError

    def bash(self, cmd: str, timeout: int = 30) -> str:
        raise NotImplementedError


def dispatch(ex, name: str, args: dict) -> str:
    """Call the named tool on ex. Raise on unknown tool / bad args (caller turns it into is_error)."""
    raise NotImplementedError
