"""Durable, conservative supervision primitives; no recovery acceptance authority.

The output-root lock coordinates this orchestrator only. It does not establish
ownership of external Ghidra, compiler, Wine, or corpus writers.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class SupervisionError(RuntimeError):
    pass


RESERVED = {"launch_intent", "running", "needs_reconciliation"}
STATES = RESERVED | {"ready", "failed_exit", "pass_done"}


def execution_basis(argv: list[str], provider_revision: str, input_basis: str) -> str:
    """Only explicit inputs/code/arguments; never mutable output or DB metadata."""
    return hashlib.sha256(json.dumps([argv, provider_revision, input_basis],
                                    separators=(",", ":")).encode()).hexdigest()


def provider_revision(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "dashboard" in path.relative_to(root).parts:
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def decide(record: dict, basis: str, now: float, max_failed_exits: int) -> str:
    """Pure admission decision; unknown children retain their reservation."""
    if record.get("state") in RESERVED:
        return "needs_reconciliation"
    if record.get("basis") != basis:
        return "launch"
    if record.get("failed_exits", 0) >= max_failed_exits:
        return "budget_exhausted"
    if now < record.get("next_eligible_at", 0):
        return "cooldown"
    return "launch"


def load_state(path: Path, scope: dict) -> dict:
    if not path.exists():
        return {"version": 1, "scope": scope, "stages": {}}
    try:
        state = json.loads(path.read_text())
        if state["version"] != 1 or state["scope"] != scope or not isinstance(state["stages"], dict):
            raise ValueError("schema or scope mismatch")
        for name, record in state["stages"].items():
            if not isinstance(name, str) or not isinstance(record, dict):
                raise ValueError("invalid stage")
            if record["state"] not in STATES or not isinstance(record["basis"], str):
                raise ValueError("invalid stage state/basis")
            count = record["failed_exits"]
            if type(count) is not int or count < 0:
                raise ValueError("invalid failure count")
            deadline = record["next_eligible_at"]
            if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline < 0:
                raise ValueError("invalid cooldown")
        return state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SupervisionError(f"supervision state unreadable/invalid; refusing admission: {exc}") from exc


def save_state(path: Path, state: dict) -> None:
    """Replace plus fsync file and directory before any dispatch is permitted."""
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def owner_lock(directory: Path):
    try:
        import fcntl
    except ImportError as exc:
        raise SupervisionError("dispatch requires POSIX flock support; use --status for read-only inspection on this host") from exc
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "owner.lock").open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SupervisionError("another orchestrator owns this output root") from exc
        yield


def process_identity(pid: int) -> dict:
    """Diagnostic identity only, never permission to kill or adopt a process."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": stat[19],
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    except (OSError, IndexError):
        return {"pid": pid, "identity_unavailable": True}


def session_clearance(identity: dict, proc_root: Path = Path("/proc")) -> str:
    """Check the admitted Linux session after its leader was reaped.

    Signal-free observation never kills/adopts a PID. Unreadable membership or
    missing original identity is unknown. This covers session descendants, not
    external writers or children deliberately escaping into a new session.
    """
    if identity.get("identity_unavailable") or not identity.get("start_ticks"):
        return "unknown"
    try:
        if (proc_root / "sys/kernel/random/boot_id").read_text().strip() != identity.get("boot_id"):
            return "unknown"
        entries = list(proc_root.iterdir())
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                # pgrp and session are fields 5 and 6 (state is index zero).
                if int(fields[2]) == identity["pid"] or int(fields[3]) == identity["pid"]:
                    return "occupied"
            except FileNotFoundError:
                continue  # unrelated processes may exit during enumeration
        return "clear"
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return "unknown"
