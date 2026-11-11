"""git in DISK/workspace with a fixed identity. Owner: C1."""
from __future__ import annotations

import os
import re
import subprocess

from builder import convo
from builder.types import WORKSPACE, ResumeError

_IDENTITY = [
    "-c", "user.name=builder",
    "-c", "user.email=builder@dryrun.local",
    "-c", "commit.gpgsign=false",
    "-c", "tag.gpgsign=false",
    "-c", "init.defaultBranch=main",
    "-c", "core.hooksPath=/dev/null",
]
_TAG_RE = re.compile(r"^step-(\d+)$")


def _ws(disk: str) -> str:
    return os.path.join(disk, WORKSPACE)


def _env() -> dict:
    # Minimal env: the agent can write workspace/.git/config (filter drivers etc.), so anything git runs
    # must not see the harness's secrets (ANTHROPIC_API_KEY, DRYRUN_CHECK_CMD, ...).
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "builder"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "builder@dryrun.local"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(disk: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *_IDENTITY, *args], cwd=_ws(disk), env=_env(),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed ({r.returncode}): {r.stderr.strip()}")
    return r


def init_workspace(disk: str) -> str:
    """If workspace/ has no .git: git init, empty commit, tag step-0. Return HEAD sha. Idempotent."""
    os.makedirs(_ws(disk), exist_ok=True)
    if not os.path.exists(os.path.join(_ws(disk), ".git")):
        _git(disk, "init", "-q")
        _git(disk, "add", "-A")   # c_0 = the workspace as delivered (empty, or P2's starter files)
        _git(disk, "commit", "-q", "--allow-empty", "-m", "step 0")
        _git(disk, "tag", "-f", "step-0")
    elif tag_sha(disk, 0) is None:
        if _git(disk, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode != 0:
            _git(disk, "commit", "-q", "--allow-empty", "-m", "step 0")
        _git(disk, "tag", "-f", "step-0")
    return head(disk)


def commit_step(disk: str, k: int) -> str:
    """git add -A; commit --allow-empty -m 'step k' (identity builder/builder@dryrun.local); tag -f step-k. Return sha.
    Exactly one commit per step: any commits/tags the agent made itself are squashed away, and nested .git
    dirs (an agent `git init` in a subfolder) are removed so their files are committed, not a gitlink."""
    _remove_nested_git(disk)
    if tag_sha(disk, k - 1) is not None:
        _git(disk, "reset", "-q", "--soft", f"refs/tags/step-{k - 1}")
    delete_tags_after(disk, k - 1)
    _git(disk, "add", "-A")
    _git(disk, "commit", "-q", "--allow-empty", "-m", f"step {k}")
    _git(disk, "tag", "-f", f"step-{k}")
    return head(disk)


def _remove_nested_git(disk: str) -> None:
    import shutil
    root = _ws(disk)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath == root:
            dirnames[:] = [d for d in dirnames if d != ".git"]
            continue
        if ".git" in dirnames:
            shutil.rmtree(os.path.join(dirpath, ".git"), ignore_errors=True)
            dirnames.remove(".git")
        if ".git" in filenames:   # a worktree/submodule .git file
            os.remove(os.path.join(dirpath, ".git"))


def head(disk: str) -> str:
    return _git(disk, "rev-parse", "HEAD").stdout.strip()


def tag_sha(disk: str, k: int) -> str | None:
    """sha of tag step-k, or None."""
    r = _git(disk, "rev-parse", "--verify", "-q", f"refs/tags/step-{k}^{{commit}}", check=False)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _step_tags(disk: str) -> list:
    out = []
    for name in _git(disk, "tag", "--list", "step-*").stdout.split():
        m = _TAG_RE.match(name)
        if m:
            out.append((int(m.group(1)), name))
    return sorted(out)


def reset_to(disk: str, k: int) -> None:
    """reset --hard step-k; clean -fdx; delete tags step-j for j > k."""
    if tag_sha(disk, k) is None:
        raise ResumeError(f"tag step-{k} missing in {_ws(disk)}")
    _git(disk, "reset", "-q", "--hard", f"refs/tags/step-{k}")
    _git(disk, "clean", "-q", "-ffdx")
    delete_tags_after(disk, k)


def delete_tags_after(disk: str, k: int) -> list:
    """Delete tags step-j, j > k. Return deleted tag names."""
    stale = [name for j, name in _step_tags(disk) if j > k]
    if stale:
        _git(disk, "tag", "-d", *stale)
    return stale


def _dirty(disk: str) -> bool:
    # Ignored files (build/, .pytest_cache, deps) are not a crash sign; only tracked or untracked changes are.
    return bool(_git(disk, "status", "--porcelain", "--untracked-files=all").stdout.strip())


def repair(disk: str, last_done: int) -> list:
    """Make log, HEAD and tags agree with last_done (truncate log, reset, clean, drop stale tags).
    Return list of human-readable repair actions taken ([] if consistent).
    Raise ResumeError if tag step-<last_done> is missing."""
    if not os.path.exists(os.path.join(_ws(disk), ".git")):
        raise ResumeError(f"no git repo at {_ws(disk)}")
    want = tag_sha(disk, last_done)
    if want is None:
        raise ResumeError(f"tag step-{last_done} missing in {_ws(disk)}")
    actions = []

    dropped = convo.truncate_after(disk, last_done)
    if dropped:
        actions.append(f"truncated conversation log: dropped {dropped} record(s) with step > {last_done}")

    cur = _git(disk, "rev-parse", "--verify", "-q", "HEAD", check=False).stdout.strip()
    moved, dirty = cur != want, _dirty(disk)
    if moved or dirty:
        _git(disk, "reset", "-q", "--hard", f"refs/tags/step-{last_done}")
        _git(disk, "clean", "-q", "-ffdx" if moved else "-ffd")
        if moved:
            actions.append(f"reset --hard HEAD {cur[:12] or '(none)'} -> step-{last_done} {want[:12]}; clean -fdx")
        else:
            actions.append(f"discarded uncommitted workspace changes (reset --hard step-{last_done}; clean -fd)")

    stale = delete_tags_after(disk, last_done)
    if stale:
        actions.append(f"deleted stale tags: {', '.join(stale)}")
    return actions
