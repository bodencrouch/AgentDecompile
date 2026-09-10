#!/usr/bin/env python3
"""Reload the local recovery server only between durable preparation waves.

Usage:
  scripts/watch-recovery-server.py --work-dir /path/to/corpus-work -- \\
    .venv/bin/agentdecompile-server -t streamable-http --host 127.0.0.1 --port 8080

The watcher owns only the child process group it starts.  It writes a small
runtime state file which `/health` exposes when AGENT_DECOMPILE_RUNTIME_STATE_FILE
is present in the child environment.  A source edit is recorded immediately;
the running server is replaced only after no live preparation receipt is owned
by this host.  Durable receipts and child job records are never deleted.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WATCH = (ROOT / "src", ROOT / "scripts")


def _process_start(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _owner_alive(row: dict[str, Any]) -> bool:
    host = str(row.get("ownerHost") or "")
    if host and host != socket.gethostname():
        return True
    pid = row.get("ownerPid")
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    recorded, current = row.get("ownerStart"), _process_start(pid)
    return not (recorded and current and recorded != current)


def active_preparations(work_dir: Path) -> list[str]:
    """Return live durable runs.  An unreadable receipt is conservatively live."""
    active: list[str] = []
    for path in (work_dir / "preparations").glob("*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError, TypeError):
            active.append(path.stem)
            continue
        if row.get("status") in {"queued", "running", "paused"} and _owner_alive(row):
            active.append(str(row.get("id") or path.stem))
    return active


def snapshot(paths: tuple[Path, ...]) -> tuple[str, list[str]]:
    entries: list[tuple[str, int]] = []
    for root in paths:
        root = root.resolve()
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            try:
                entries.append((str(path.relative_to(ROOT)), path.stat().st_mtime_ns))
            except OSError:
                pass
    entries.sort()
    revision = hashlib.sha256(repr(entries).encode()).hexdigest()[:16]
    return revision, [name for name, _ in entries]


def write_state(path: Path, **state: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def start(command: list[str], state_file: Path, revision: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENT_DECOMPILE_RUNTIME_STATE_FILE"] = str(state_file)
    env["AGENT_DECOMPILE_RUNTIME_REVISION"] = revision
    return subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True,
                            stdin=subprocess.DEVNULL, text=True)


def stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="Corpus work directory containing preparations/")
    parser.add_argument("--state-file", type=Path,
                        default=Path("/tmp/agentdecompile-recovery-runtime.json"))
    parser.add_argument("--poll", type=float, default=0.5)
    parser.add_argument("--watch", type=Path, action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("supply the server command after --")
    watch = tuple(args.watch or DEFAULT_WATCH)
    lock_path = args.state_file.with_suffix(args.state_file.suffix + ".lock")
    lock = lock_path.open("w")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    revision, _ = snapshot(watch)
    proc = start(command, args.state_file, revision)
    started_at = time.time()
    pending: str | None = None
    try:
        while True:
            time.sleep(max(0.1, args.poll))
            current, _ = snapshot(watch)
            if current != revision:
                pending = current
            live = active_preparations(args.work_dir)
            state = {
                "pid": proc.pid,
                "startedAt": started_at if proc.poll() is None else None,
                "revision": revision,
                "reload": {"status": "pending" if pending else "current",
                           "requestedRevision": pending,
                           "livePreparations": live},
            }
            write_state(args.state_file, **state)
            if proc.poll() is not None:
                # A normal server exit is restarted using the same durable state.
                revision = pending or current
                pending = None
                proc = start(command, args.state_file, revision)
                started_at = time.time()
                continue
            if pending and not live:
                stop(proc)
                revision, pending = pending, None
                proc = start(command, args.state_file, revision)
                started_at = time.time()
    except KeyboardInterrupt:
        return 0
    finally:
        stop(proc)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
