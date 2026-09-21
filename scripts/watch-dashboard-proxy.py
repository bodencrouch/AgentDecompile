#!/usr/bin/env python3
"""Keep the dashboard proxy hot-reloadable without touching the MCP server."""
from __future__ import annotations

import os
import fcntl
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCH_ROOT = ROOT / "src" / "agentdecompile_recovery" / "corpus" / "dashboard"
PROXY_HOST = os.environ.get("AGENT_DECOMPILE_PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.environ.get("AGENT_DECOMPILE_PROXY_PORT", "8767"))
COMMAND = [
    str(ROOT / ".venv" / "bin" / "agentdecompile-proxy"), "-t", "streamable-http",
    "--backend-url", os.environ.get("AGENT_DECOMPILE_BACKEND_URL", "http://127.0.0.1:8080/mcp"),
    "-o", PROXY_HOST,
    "-p", str(PROXY_PORT),
]
LOCK_PATH = Path("/tmp/agentdecompile-dashboard-proxy.lock")


def wait_for_port() -> None:
    """Match the proxy's bind preflight so it never falls back after reload."""
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((PROXY_HOST, PROXY_PORT))
            return
        except OSError:
            time.sleep(0.1)


def start() -> subprocess.Popen[str]:
    wait_for_port()
    return subprocess.Popen(
        COMMAND, cwd=ROOT, start_new_session=True,
        stdin=subprocess.DEVNULL, text=True,
    )


def stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=1.0)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=2.0)


def snapshot() -> dict[str, int]:
    """Return a cheap mtime snapshot without requiring third-party watchers."""
    result: dict[str, int] = {}
    for path in WATCH_ROOT.rglob("*.py"):
        try:
            result[str(path)] = path.stat().st_mtime_ns
        except OSError:
            continue
    return result


def main() -> int:
    lock_handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    proc = start()
    previous = snapshot()
    try:
        while True:
            time.sleep(0.4)
            current = snapshot()
            if current != previous:
                previous = current
                stop(proc)
                proc = start()
    except KeyboardInterrupt:
        return 0
    finally:
        stop(proc)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
