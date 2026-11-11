"""0:30 gate spike: does the agent's disk survive checkpoint -> branch -> mount in a second sandbox?

Usage (from the repo root):
    .venv/bin/python spikes/disk_spike.py               # every part
    .venv/bin/python spikes/disk_spike.py --isolation   # only some parts: --main --fallback --baseline --isolation --cap
                                                        # (a partial run keeps the other parts' results in the JSON)

Main path (v8):
  1. create an Archil disk; create sandbox A with the disk mounted at /mnt/agent
  2. in A, write workspace/hello.txt and conversation.jsonl onto the disk
  3. in A, make a disk checkpoint with the `archil` CLI
  4. branch the disk from that checkpoint; in sandbox B, mount the branch and compare both files
  6. check that a sandbox can reach api.anthropic.com
Fallback (v7): write the same files on a plain sandbox's root disk, pause it, fork it, compare in the fork.

Every timing and step outcome goes to spikes/disk_spike.json. Every sandbox is deleted in `finally`.
The disk itself is kept (its checkpoint and branch can't be deleted anyway); its id is in the JSON.
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

import archil
from archil._models import SandboxMountSpec

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).with_suffix(".json")
MNT_A, MNT_B = "/mnt/agent", "/mnt/branch"
CKPT, BRANCH = "c1", "b1"
FILES = ["workspace/hello.txt", "conversation.jsonl"]


def load_env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
REGION = os.environ.get("ARCHIL_REGION", "aws-us-east-1")
client = archil.Archil(api_key=os.environ["ARCHIL_API_KEY"], region=REGION)
stamp = time.strftime("%Y%m%d-%H%M%S")
report = {"region": REGION, "sdk": archil.__version__ if hasattr(archil, "__version__") else None,
          "started": stamp, "timings_s": {}, "steps": {}}
sandboxes = []  # creation order; deleted in reverse (forks before parents)


def save():
    OUT.write_text(json.dumps(report, indent=2) + "\n")


def timed(section, label, fn, *a, **kw):
    t = time.perf_counter()
    out = fn(*a, **kw)
    section["timings_s"][label] = round(time.perf_counter() - t, 3)
    print(f"{label:<34} {section['timings_s'][label]:7.3f}s", flush=True)
    save()
    return out


def sh(sb, cmd, env=None, timeout=120):
    r = sb.exec(cmd, env=env, timeout_seconds=timeout)
    return r.exit_code, (r.stdout or "").strip(), (r.stderr or "").strip()


def must(sb, cmd, step, env=None, timeout=120):
    code, out, err = sh(sb, cmd, env=env, timeout=timeout)
    if code != 0:
        raise RuntimeError(f"step {step}: `{cmd.split(' &&')[0][:80]}` exit {code}: {(err or out)[-600:]}")
    return out


def ok(section, step, **info):
    section["steps"][step] = {"ok": True, **info}
    save()


WRITE = (
    "set -e; cd {m}; mkdir -p workspace; echo 'hello from sandbox A' > workspace/hello.txt; "
    "printf '%s\\n' '{{\"role\":\"user\",\"content\":\"build step 1\"}}' "
    "'{{\"role\":\"assistant\",\"content\":\"done: wrote hello.txt\"}}' > conversation.jsonl; sync; "
    "sha256sum workspace/hello.txt conversation.jsonl"
)
HASH = "cd {m} && sha256sum workspace/hello.txt conversation.jsonl"
INSTALL_CLI = "command -v archil >/dev/null || (curl -fsSL https://archil.com/install | sh) >/tmp/archil-install.log 2>&1; archil --version"


def main_path():
    r = report
    # 1. disk + sandbox A with it mounted
    created = timed(r, "disk_create", client.disks.create, name=f"dryrun-spike-{stamp}")
    disk, token = created.disk, created.token
    r["disk_id"] = disk.id
    if not token:
        raise RuntimeError("step 1: disk create returned no mount token")
    a = timed(r, "sandbox_a_create_with_mount", client.sandboxes.create, name=f"spike-a-{stamp}",
              base_image="python:3.13", vcpu_count=1, mem_size_mib=1024, idle_ttl_seconds=600,
              mounts=[SandboxMountSpec(disk=disk, path=MNT_A)])
    sandboxes.append(a)
    mount_line = timed(r, "sandbox_a_first_exec_mount_check", must, a, f"mount | grep {MNT_A}", "1")
    ok(r, "1_disk_and_mount", mount=mount_line[:200])

    # 2. write the agent's files onto the disk
    hashes_a = timed(r, "write_files", must, a, WRITE.format(m=MNT_A), "2")
    ok(r, "2_write_files", sha256=hashes_a.splitlines())

    # 3. checkpoint from inside A
    cli = timed(r, "archil_cli_install_a", must, a, INSTALL_CLI, "3", timeout=300)
    timed(r, "checkpoint_create", must, a, f"archil checkpoints create {MNT_A} {CKPT}", "3")
    ok(r, "3_checkpoint", cli_version=cli.splitlines()[-1] if cli else None, name=CKPT)

    # 4. branch from the checkpoint, mount it in sandbox B, compare
    branch = timed(r, "branch_create", disk.create_branch, BRANCH, CKPT)
    b = timed(r, "sandbox_b_create", client.sandboxes.create, name=f"spike-b-{stamp}",
              base_image="python:3.13", vcpu_count=1, mem_size_mib=1024, idle_ttl_seconds=600)
    sandboxes.append(b)
    timed(r, "archil_cli_install_b", must, b, INSTALL_CLI, "4", timeout=300)
    timed(r, "branch_mount_b", must, b,
          f"mkdir -p {MNT_B} && archil mount {disk.id} {MNT_B} --region {REGION} --branch {BRANCH} && sleep 1 && mount | grep {MNT_B}",
          "4", env={"ARCHIL_MOUNT_TOKEN": token})
    hashes_b = timed(r, "read_files_b", must, b, HASH.format(m=MNT_B), "4")
    same = hashes_a.splitlines() == hashes_b.splitlines()
    ok(r, "4_branch_mount_identical", branch=branch.branch_name, from_checkpoint=branch.from_checkpoint_name,
       sha256_b=hashes_b.splitlines(), identical=same)
    if not same:
        r["steps"]["4_branch_mount_identical"]["ok"] = False
        raise RuntimeError(f"step 4: files differ on the branch: A={hashes_a!r} B={hashes_b!r}")

    # 6. egress to the model API (from B)
    code = must(b, "curl -s -o /dev/null -m 15 -w '%{http_code}' https://api.anthropic.com/v1/messages || true", "6")
    report["steps"]["6_anthropic_egress"] = {"ok": code not in ("", "000"), "http_code": code}
    save()


def fallback_path():
    f = report["fallback"]
    p = timed(f, "sandbox_create", client.sandboxes.create, name=f"spike-fb-{stamp}",
              base_image="python:3.13", vcpu_count=1, mem_size_mib=1024, idle_ttl_seconds=600)
    sandboxes.append(p)
    hashes_p = timed(f, "write_files", must, p, WRITE.format(m="/root/agent").replace("cd /root/agent", "mkdir -p /root/agent && cd /root/agent"), "fb")
    timed(f, "pause", p.pause)
    child = timed(f, "fork_of_paused", p.fork, name=f"spike-fb-child-{stamp}")
    sandboxes.append(child)
    hashes_c = timed(f, "first_exec_in_fork", must, child, HASH.format(m="/root/agent"), "fb")
    same = hashes_p.splitlines() == hashes_c.splitlines()
    f["steps"]["fork_pause_identical"] = {"ok": same, "sha256_parent": hashes_p.splitlines(), "sha256_fork": hashes_c.splitlines()}
    save()


REPO_URL = "https://github.com/Keon-Amid/dry-run.git"  # our public repo stands in for the agent's workspace
# Shortlink's stack isn't chosen yet; a small Python API stack stands in. HARDCODED; swap for the real requirements.
BASELINE_DEPS = "fastapi uvicorn httpx pytest"


def baseline_path():
    """No-Archil restore, timed once: fresh sandbox, git clone the workspace, install its dependencies."""
    bl = report["baseline"]
    s = timed(bl, "sandbox_create", client.sandboxes.create, name=f"spike-bl-{stamp}",
              base_image="python:3.13", vcpu_count=1, mem_size_mib=1024, idle_ttl_seconds=600)
    sandboxes.append(s)
    timed(bl, "git_clone", must, s, f"git clone -q --depth 1 {REPO_URL} /root/ws", "baseline", timeout=300)
    timed(bl, "dependency_install", must, s,
          f"cd /root/ws && python -m venv .venv && .venv/bin/pip install -q --disable-pip-version-check {BASELINE_DEPS}",
          "baseline", timeout=600)
    bl["timings_s"]["total"] = round(bl["timings_s"]["git_clone"] + bl["timings_s"]["dependency_install"], 3)
    bl["steps"]["restore"] = {"ok": True, "repo": REPO_URL, "deps": BASELINE_DEPS,
                              "note": "restores code and dependencies only, not the conversation"}
    save()


def isolation_path():
    """Own disk: A writes after the checkpoint (must not reach the branch); B writes on the branch (must not reach A)."""
    iso = report["isolation"]
    created = timed(iso, "disk_create", client.disks.create, name=f"dryrun-iso-{stamp}")
    disk, token = created.disk, created.token
    iso["disk_id"] = disk.id
    a = timed(iso, "sandbox_a_create_with_mount", client.sandboxes.create, name=f"iso-a-{stamp}",
              base_image="python:3.13", vcpu_count=1, mem_size_mib=1024, idle_ttl_seconds=600,
              mounts=[SandboxMountSpec(disk=disk, path=MNT_A)])
    sandboxes.append(a)
    hashes_a = must(a, WRITE.format(m=MNT_A), "iso")
    timed(iso, "checkpoint_create", must, a, f"archil checkpoints create {MNT_A} {CKPT}", "iso")
    must(a, f"echo written-after-checkpoint > {MNT_A}/a_after.txt && echo changed >> {MNT_A}/workspace/hello.txt && sync", "iso")
    timed(iso, "branch_create", disk.create_branch, BRANCH, CKPT)
    b = timed(iso, "sandbox_b_create", client.sandboxes.create, name=f"iso-b-{stamp}",
              base_image="python:3.13", vcpu_count=1, mem_size_mib=1024, idle_ttl_seconds=600)
    sandboxes.append(b)
    timed(iso, "branch_mount_b", must, b,
          f"mkdir -p {MNT_B} && archil mount {disk.id} {MNT_B} --region {REGION} --branch {BRANCH} && mount | grep {MNT_B}",
          "iso", env={"ARCHIL_MOUNT_TOKEN": token})
    hashes_b = must(b, HASH.format(m=MNT_B), "iso")
    b_sees_a_after = sh(b, f"test -e {MNT_B}/a_after.txt")[0] == 0
    must(b, f"echo written-in-b > {MNT_B}/b_only.txt && echo b-edit >> {MNT_B}/conversation.jsonl && sync", "iso")
    time.sleep(2)  # give any (unexpected) propagation a moment before checking A
    a_sees_b = sh(a, f"test -e {MNT_A}/b_only.txt")[0] == 0
    a_conv_has_b_edit = sh(a, f"grep -q b-edit {MNT_A}/conversation.jsonl")[0] == 0
    a_sees_own_after = sh(a, f"test -e {MNT_A}/a_after.txt")[0] == 0  # positive control
    checks = {
        "branch_matches_checkpoint": hashes_a.splitlines() == hashes_b.splitlines(),
        "a_after_checkpoint_hidden_from_b": not b_sees_a_after,
        "b_new_file_hidden_from_a": not a_sees_b,
        "b_edit_hidden_from_a": not a_conv_has_b_edit,
        "control_a_sees_own_write": a_sees_own_after,
    }
    iso["steps"]["isolation"] = {"ok": all(checks.values()), **checks}
    save()


N_CAP = 6  # Free plan caps at 5 concurrent sandboxes, Developer at 20: a 6th running one says we're past Free


def cap_path():
    """Start N_CAP sandboxes at once, then exec in each while all are running."""
    from concurrent.futures import ThreadPoolExecutor
    cap = report["cap"]

    def create(i):
        try:
            sb = client.sandboxes.create(name=f"cap-{i}-{stamp}", base_image="python:3.13", vcpu_count=1,
                                         mem_size_mib=1024, idle_ttl_seconds=300)
            sandboxes.append(sb)
            return sb, None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    t = time.perf_counter()
    with ThreadPoolExecutor(N_CAP) as ex:
        results = list(ex.map(create, range(1, N_CAP + 1)))
    cap["timings_s"]["create_all_parallel_wall"] = round(time.perf_counter() - t, 3)
    up = [sb for sb, _ in results if sb]
    alive = sum(1 for sb in up if sh(sb, "echo up")[1] == "up")
    cap["steps"]["concurrent"] = {"ok": alive == N_CAP, "requested": N_CAP, "created": len(up),
                                  "running_at_once": alive, "errors": [e for _, e in results if e]}
    print(f"cap: {alive}/{N_CAP} running at once", flush=True)
    save()


def run(section, fn):
    try:
        fn()
    except Exception as e:
        section["error"] = f"{type(e).__name__}: {e}"
        section["traceback_tail"] = traceback.format_exc().splitlines()[-4:]
        print("FAILED:", section["error"], flush=True)
        save()


PARTS = {  # flag -> (JSON key, label, function); no flag runs every part
    "--main": (None, "main path: disk checkpoint + branch", main_path),
    "--fallback": ("fallback", "fallback: sandbox pause + fork", fallback_path),
    "--baseline": ("baseline", "no-Archil baseline: git clone + dependency install", baseline_path),
    "--isolation": ("isolation", "isolation: writes after the checkpoint / on the branch", isolation_path),
    "--cap": ("cap", f"cap: {N_CAP} sandboxes running at once", cap_path),
}
chosen = [f for f in PARTS if f in sys.argv] or list(PARTS)
if "--main" not in chosen and OUT.exists():  # a partial rerun keeps the earlier results and replaces only its parts
    report = json.loads(OUT.read_text())
for f in chosen:
    key = PARTS[f][0]
    if key:
        report[key] = {"timings_s": {}, "steps": {}, "measured": time.strftime("%Y%m%d-%H%M%S")}

try:
    for f in chosen:
        key, label, fn = PARTS[f]
        print(f"== {label} ==")
        run(report[key] if key else report, fn)
finally:
    report.setdefault("cleanup", {})
    for sb in reversed(sandboxes):  # forks first, then parents
        msgs = []
        for step in ("stop", "delete"):
            try:
                getattr(sb, step)()
                msgs.append(f"{step} ok")
            except Exception as e:
                msgs.append(f"{step} failed: {type(e).__name__}: {e}")
        report["cleanup"][sb.name] = msgs
        print(f"cleanup {sb.name}: {', '.join(msgs)}")
    save()
    client.close()
