"""One bounded setup path for an isolated Wine prefix (U9 FP-04).

Every consumer of a prefix (compiler wrapper, recorder, live driver) calls ``ensure_prefix``.
An initialized prefix is reused without running anything. A fresh prefix is set up once, under
an exclusive lock, by a single ``wineboot --init`` with a deadline. A failed or timed-out setup
is recorded and not retried automatically; ``reset_failure`` is the explicit way back. The
user's default ``~/.wine`` is refused.
"""
from __future__ import annotations

import fcntl
import json
import os
import pwd
import subprocess
import time
from pathlib import Path

MARKER = ".agentdecompile-prefix.json"
SCHEMA = "agentdecompile.wine-prefix/v1"


def _default_prefix() -> str:
    return os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".wine"))


def _marker(prefix: Path) -> dict | None:
    try:
        return json.loads((prefix / MARKER).read_text())
    except (OSError, ValueError):
        return None


def _write_marker(prefix: Path, row: dict) -> None:
    tmp = prefix / (MARKER + ".tmp")
    tmp.write_text(json.dumps({"schema": SCHEMA, **row}, sort_keys=True))
    os.replace(tmp, prefix / MARKER)


def state(prefix: Path | str) -> str:
    prefix = Path(prefix)
    row = _marker(prefix)
    if row and row.get("state") == "ready" and (prefix / "system.reg").is_file():
        return "ready"
    if row and row.get("state") == "setup_failed":
        return "setup_failed"
    return "uninitialized"


def ensure_prefix(prefix: Path | str, wine: str, *, timeout: float = 300.0, env: dict | None = None) -> dict:
    """Return ``{"state": "reused"|"initialized"|"setup_failed"|"refused", ...}``."""
    prefix = Path(prefix)
    if os.path.realpath(prefix) == _default_prefix():
        return {"state": "refused", "reason": "the default ~/.wine prefix is never used"}
    if state(prefix) == "ready":
        return {"state": "reused", "prefix": str(prefix)}
    prefix.parent.mkdir(parents=True, exist_ok=True)
    lock_path = prefix.parent / f".{prefix.name}.setup.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = state(prefix)  # another consumer may have finished while we waited
        if current == "ready":
            return {"state": "reused", "prefix": str(prefix)}
        if current == "setup_failed":
            return {"state": "setup_failed", "prefix": str(prefix), "failure": _marker(prefix),
                    "nextAction": "inspect_prefix_then_reset_failure"}
        prefix.mkdir(parents=True, exist_ok=True)
        started = time.time()
        run_env = {**(env if env is not None else os.environ), "WINEPREFIX": str(prefix),
                   "WINEDEBUG": "-all", "WINEDLLOVERRIDES": "mscoree,mshtml="}
        try:
            proc = subprocess.run([wine, "wineboot", "--init"], env=run_env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout)
            ok, detail = proc.returncode == 0 and (prefix / "system.reg").is_file(), (proc.stderr or "")[-800:]
            returncode = proc.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            ok, detail, returncode = False, type(exc).__name__ + ": " + str(exc)[-400:], None
        row = {"state": "ready" if ok else "setup_failed", "wine": wine, "returncode": returncode,
               "seconds": round(time.time() - started, 3), "detail": detail}
        _write_marker(prefix, row)
        return {**row, "state": "initialized" if ok else "setup_failed", "prefix": str(prefix)}


def reset_failure(prefix: Path | str) -> None:
    """Explicitly allow one more setup attempt after an operator has looked at the failure."""
    prefix = Path(prefix)
    if state(prefix) == "setup_failed":
        (prefix / MARKER).unlink()
