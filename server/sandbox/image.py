"""Builds the Vercel Sandbox snapshots the worker runs from (see PLAN.md Contracts, slice 1.1).

  python server/sandbox/image.py base              universal image + libreoffice/poppler-utils/fontconfig +
                                                     the repo at /vercel/sandbox/app + server/.venv +
                                                     skill/.venv (skill/scripts/setup.sh) -> snapshot id
  python server/sandbox/image.py code --base <id>   current server/ and skill/ code on top of <id> -> snapshot id

Both commands print progress to stderr and the resulting snapshot id, alone, as the last stdout line.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from vercel.sandbox import SnapshotSource
from vercel.sandbox import sync as sandbox

ROOT = Path(__file__).resolve().parents[2]
REPO_REMOTE = "/vercel/sandbox/app"   # must match config.SANDBOX_REPO
EXCLUDE_PARTS = {".venv", "__pycache__", "data"}
APT_PACKAGES = ["libreoffice", "poppler-utils", "fontconfig"]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _tracked_files(*subpaths: str) -> list[str]:
    """Git-tracked plus untracked-but-not-ignored paths (so local edits and new files travel too), under
    `subpaths` or the whole repo, minus .venv/__pycache__/data even if gitignore ever missed them."""
    args = ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    if subpaths:
        args += ["--", *subpaths]
    out = subprocess.run(args, capture_output=True, check=True).stdout
    paths = (raw.decode() for raw in out.split(b"\0") if raw)
    return sorted({p for p in paths if not EXCLUDE_PARTS & set(Path(p).parts)})


def _upload(box, paths: list[str], remote_root: str) -> None:
    """Uploads local repo-relative `paths` into `remote_root` on the sandbox (directories first)."""
    dirs = sorted({str(Path(remote_root, p).parent) for p in paths})
    box.run_command("mkdir", ["-p", remote_root, *dirs], check=True)
    t0 = time.time()
    sent = 0
    with box.fs.batch() as batch:
        for p in paths:
            try:
                data = (ROOT / p).read_bytes()
            except OSError:
                # another agent's checkout edit raced us (e.g. a file deleted but not yet un-tracked); skip it
                _log(f"skip (unreadable): {p}")
                continue
            batch.write_bytes(f"{remote_root}/{p}", data)
            sent += 1
    _log(f"uploaded {sent} file(s) to {remote_root} in {time.time() - t0:.1f}s")


def _run(box, cmd: str, args: list[str], **kw):
    t0 = time.time()
    r = box.run_command(cmd, args, capture_output=True, **kw)
    _log(f"$ {cmd} {' '.join(args)}  [{time.time() - t0:.1f}s, rc={r.returncode}]")
    if r.returncode != 0:
        _log((r.stdout or "")[-2000:])
        _log((r.stderr or "")[-2000:])
        r.check_returncode()
    return r


def build_base() -> str:
    t_create = time.time()
    box = sandbox.create_sandbox(name=f"deck-image-base-{int(t_create)}", execution_time_limit=1800)
    _log(f"sandbox created, status={box.status}")
    _run(box, "sudo", ["apt-get", "update"])
    _log(f"create -> first command: {time.time() - t_create:.1f}s")
    try:
        _run(box, "sudo", ["apt-get", "install", "-y", *APT_PACKAGES], kill_after=900)
        _upload(box, _tracked_files("server", "skill"), REPO_REMOTE)
        _run(box, "python3", ["-m", "venv", f"{REPO_REMOTE}/server/.venv"])
        _run(box, f"{REPO_REMOTE}/server/.venv/bin/python",
             ["-m", "pip", "install", "-q", "-r", f"{REPO_REMOTE}/server/requirements.txt"], kill_after=600)
        _run(box, "bash", [f"{REPO_REMOTE}/skill/scripts/setup.sh"], kill_after=600)
        snap = box.snapshot()
        _log(f"base snapshot: {snap.id}")
        return snap.id
    finally:
        box.destroy()


def build_code(base_snapshot: str) -> str:
    box = sandbox.create_sandbox(name=f"deck-image-code-{int(time.time())}",
                                  source=SnapshotSource(snapshot_id=base_snapshot), execution_time_limit=900)
    try:
        _upload(box, _tracked_files("server", "skill"), REPO_REMOTE)
        snap = box.snapshot()
        _log(f"code snapshot: {snap.id}")
        return snap.id
    finally:
        box.destroy()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("base")
    code_p = sub.add_parser("code")
    code_p.add_argument("--base", required=True)
    args = ap.parse_args()
    print(build_base() if args.cmd == "base" else build_code(args.base))


if __name__ == "__main__":
    main()
