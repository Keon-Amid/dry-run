"""The swap point from CONTRACT.md: save(step) -> checkpoint_id and resume(checkpoint_id) -> worker.

ArchilStore: one Archil disk per run. The build sandbox mounts the disk; save() makes a disk checkpoint from inside
it; resume() branches the disk at a checkpoint and mounts the branch in a fresh sandbox.
LocalStore: same calls on plain folders (save = copytree), for tests and the no-Archil flip test.

A worker exposes: mnt (the agent's disk), tools (a folder outside the disk for builder/check code),
exec(cmd) -> (code, stdout, stderr), put(path, text), put_tree(local_dir, remote_dir), delete(),
and timings_ms {branch, sandbox, mount}.
Disk tokens live only in memory; nothing here writes one to a file.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path

MNT, TOOLS = "/mnt/agent", "/opt/dryrun"
IMAGE = dict(base_image="python:3.13", vcpu_count=1, mem_size_mib=1024)


def safe_name(name: str) -> str:
    """Archil sandbox/branch name: <= 63 lowercase letters, digits, hyphens; a random suffix keeps it unique
    (branches can't be deleted, so a rerun on the same disk must not reuse a name)."""
    base = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", name.lower())).strip("-")[:55].strip("-") or "x"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


# ---------------------------------------------------------------- Archil

class ArchilWorker:
    def __init__(self, sandbox, mnt: str, branch: str | None, timings_ms: dict):
        self.sandbox, self.mnt, self.tools, self.branch, self.timings_ms = sandbox, mnt, TOOLS, branch, timings_ms

    def exec(self, cmd: str, env: dict | None = None, timeout: int = 900):
        r = self.sandbox.exec(cmd, env=env, timeout_seconds=timeout)
        return r.exit_code, (r.stdout or "").strip(), (r.stderr or "").strip()

    def must(self, cmd: str, env: dict | None = None, timeout: int = 900) -> str:
        code, out, err = self.exec(cmd, env, timeout)
        if code != 0:
            raise RuntimeError(f"{self.sandbox.name}: `{cmd[:80]}` exit {code}: {(err or out)[-500:]}")
        return out

    def put(self, path: str, text: str) -> None:
        b64 = base64.b64encode(text.encode()).decode()
        self.must(f"mkdir -p {os.path.dirname(path)} && echo {b64} | base64 -d > {path}")

    def put_tree(self, local_dir: Path, remote_dir: str) -> None:
        """Copy a local folder (e.g. a Python package) into the sandbox: tar.gz, upload, extract."""
        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
            with tarfile.open(tmp.name, "w:gz") as tar:
                tar.add(local_dir, arcname=Path(local_dir).name,
                        filter=lambda ti: None if "__pycache__" in ti.name else ti)
            remote_tar = f"/tmp/{uuid.uuid4().hex}.tar.gz"
            self.sandbox.files.upload_file(tmp.name, remote_tar)
        self.must(f"mkdir -p {remote_dir} && tar xzf {remote_tar} -C {remote_dir} && rm -f {remote_tar}")

    def get_tree(self, remote_dir: str, local_dir: Path) -> None:
        """Copy a folder out of the sandbox (minus .git and __pycache__): tar.gz over base64."""
        out = self.must(f"cd {remote_dir} && tar czf - --exclude=.git --exclude=__pycache__ . | base64 -w0")
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
            tmp.write(base64.b64decode(out))
            tmp.flush()
            with tarfile.open(tmp.name) as tar:
                tar.extractall(local_dir, filter="data")

    def delete(self) -> None:
        for step in ("stop", "delete"):
            try:
                getattr(self.sandbox, step)()
            except Exception as e:  # keep going: an undeleted sandbox counts against the cap
                print(f"  {self.sandbox.name}: {step} failed: {type(e).__name__}: {e}", flush=True)


class ArchilStore:
    kind = "archil"

    def __init__(self, client, region: str, disk, token: str):
        self.client, self.region, self.disk, self._token = client, region, disk, token
        self.build: ArchilWorker | None = None

    @classmethod
    def new(cls, client, region: str, name: str) -> "ArchilStore":
        created = client.disks.create(name=name)
        if not created.token:
            raise RuntimeError("disk create returned no mount token")
        return cls(client, region, created.disk, created.token)

    @classmethod
    def attach(cls, client, region: str, disk_id: str) -> "ArchilStore":
        """Reopen a run's disk from another process: mint a fresh mount token (the old one was never saved)."""
        disk = client.disks.get(disk_id)
        return cls(client, region, disk, disk.create_token(f"dryrun-{uuid.uuid4().hex[:6]}").token)

    @property
    def disk_id(self) -> str:
        return self.disk.id

    def start_build(self, name: str) -> ArchilWorker:
        from archil._models import SandboxMountSpec
        t0 = time.perf_counter()
        sb = self.client.sandboxes.create(name=safe_name(name), idle_ttl_seconds=900, **IMAGE,
                                          mounts=[SandboxMountSpec(disk=self.disk, path=MNT)])
        self.build = ArchilWorker(sb, MNT, None, {"sandbox": _ms(t0)})
        return self.build

    def save(self, step: int) -> str:
        """Checkpoint the disk from inside the build sandbox, between agent turns."""
        self.build.must(f"sync && archil checkpoints create {MNT} c{step}")
        return f"{self.disk.id}/c{step}"

    def resume(self, checkpoint_id: str, name: str) -> ArchilWorker:
        """A fresh sandbox with a new branch of the disk at checkpoint_id mounted at MNT."""
        disk_id, ckpt = checkpoint_id.split("/", 1)
        assert disk_id == self.disk.id, f"checkpoint {checkpoint_id} is not on disk {self.disk.id}"
        branch = safe_name(name)
        t0 = time.perf_counter()
        self.disk.create_branch(branch, ckpt)
        timings = {"branch": _ms(t0)}
        t0 = time.perf_counter()
        sb = self.client.sandboxes.create(name=branch, idle_ttl_seconds=900, **IMAGE)
        timings["sandbox"] = _ms(t0)
        w = ArchilWorker(sb, MNT, branch, timings)
        try:
            t0 = time.perf_counter()
            w.must(f"mkdir -p {MNT} && archil mount {self.disk.id} {MNT} --region {self.region} --branch {branch}"
                   f" && test -f {MNT}/state.json", env={"ARCHIL_MOUNT_TOKEN": self._token})
            timings["mount"] = _ms(t0)
        except Exception:
            w.delete()
            raise
        return w


# ---------------------------------------------------------------- local folders

class LocalWorker:
    def __init__(self, mnt: Path, tools: Path, branch: str | None, timings_ms: dict):
        self.mnt, self.tools, self.branch, self.timings_ms = str(mnt), str(tools), branch, timings_ms

    def exec(self, cmd: str, env: dict | None = None, timeout: int = 900):
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **(env or {})})
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    def must(self, cmd: str, env: dict | None = None, timeout: int = 900) -> str:
        code, out, err = self.exec(cmd, env, timeout)
        if code != 0:
            raise RuntimeError(f"`{cmd[:80]}` exit {code}: {(err or out)[-500:]}")
        return out

    def put(self, path: str, text: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)

    def put_tree(self, local_dir: Path, remote_dir: str) -> None:
        shutil.copytree(local_dir, Path(remote_dir) / Path(local_dir).name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))

    def get_tree(self, remote_dir: str, local_dir: Path) -> None:
        shutil.copytree(remote_dir, local_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))

    def delete(self) -> None:
        pass  # branches stay on disk for inspection, like Archil branches


class LocalStore:
    kind = "local"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.disk_id = f"local:{self.root}"
        self.build: LocalWorker | None = None

    def start_build(self, name: str) -> LocalWorker:
        (self.root / "disk").mkdir(parents=True, exist_ok=True)
        self.build = LocalWorker(self.root / "disk", self.root / "tools" / name, None, {"sandbox": 0.0})
        return self.build

    def save(self, step: int) -> str:
        shutil.copytree(self.root / "disk", self.root / "checkpoints" / f"c{step}")
        return f"{self.disk_id}/c{step}"

    def resume(self, checkpoint_id: str, name: str) -> LocalWorker:
        ckpt = checkpoint_id.rsplit("/", 1)[1]
        branch = safe_name(name)  # same names as Archil, so local runs catch bad names too
        t0 = time.perf_counter()
        shutil.copytree(self.root / "checkpoints" / ckpt, self.root / "branches" / branch)
        return LocalWorker(self.root / "branches" / branch, self.root / "tools" / branch, branch,
                           {"branch": _ms(t0), "sandbox": 0.0, "mount": 0.0})
