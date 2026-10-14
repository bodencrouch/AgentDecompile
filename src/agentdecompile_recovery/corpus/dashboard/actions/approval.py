"""Local, revision-bound approval for the dashboard's K1 byte verifier.

The dashboard binds to loopback and runs as one OS user. Its explicit second
confirmation is recorded under that OS identity, then consumed before the job
is accepted. This is a local-workstation trust boundary, not remote-user auth.
"""
from __future__ import annotations

import getpass
import hashlib
import ipaddress
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

ACTION_ID = "corpus.verify-byteexact"
APPROVAL_TTL_SECONDS = 600


class ApprovalError(ValueError):
    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def local_actor(client_host: str | None, origin: str | None, expected_origin: str) -> str:
    """Identify the local OS account only for a same-origin loopback request."""
    try:
        if not client_host or not ipaddress.ip_address(client_host).is_loopback:
            raise ApprovalError("approval requires a loopback dashboard session", status=403)
    except ValueError as exc:
        raise ApprovalError("approval requires a loopback dashboard session", status=403) from exc
    if not origin or origin.rstrip("/") != expected_origin.rstrip("/"):
        raise ApprovalError("approval requires a same-origin dashboard request", status=403)
    return f"uid:{os.getuid()}:{getpass.getuser()}"


def _directory() -> Path:
    from . import job_history

    root = job_history.directory()
    if root is None:
        raise ApprovalError("dashboard workbench receipt directory is unavailable", status=503)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def _connect() -> sqlite3.Connection:
    path = _directory() / "approvals.sqlite3"
    con = sqlite3.connect(path, timeout=5, isolation_level=None)
    os.chmod(path, 0o600)
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS action_approval (
            id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            params_sha256 TEXT NOT NULL,
            target_revision TEXT NOT NULL,
            operation_key TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('issued','reserved','consumed','expired')),
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            job_id TEXT
        );
        CREATE TABLE IF NOT EXISTS action_approval_audit (
            id TEXT PRIMARY KEY,
            approval_id TEXT NOT NULL,
            event TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            occurred_at REAL NOT NULL,
            detail_json TEXT NOT NULL,
            FOREIGN KEY(approval_id) REFERENCES action_approval(id)
        );
        CREATE INDEX IF NOT EXISTS action_approval_live
            ON action_approval(status, expires_at, action_id);
        """
    )
    for private_path in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            os.chmod(private_path, 0o600)
        except FileNotFoundError:
            pass
    return con


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ApprovalError("action parameters are not canonical JSON") from exc


def _target_revision(params: dict[str, Any]) -> str:
    raw = params.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        database = params.get("db")
        binary_id = params.get("binary-id")
        if not isinstance(database, str) or not database.strip() or binary_id is None:
            raise ApprovalError("byte verification requires either an original image or a bound Ghidra binary")
        try:
            db_path = Path(database).expanduser().resolve(strict=True)
            with sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True) as con:
                row = con.execute(
                    "SELECT content_sha256 FROM binary WHERE id=?",
                    (int(binary_id),),
                ).fetchone()
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise ApprovalError("selected Ghidra binary identity is unavailable") from exc
        revision = str(row[0] or "").strip().lower() if row else ""
        if len(revision) != 64 or any(character not in "0123456789abcdef" for character in revision):
            raise ApprovalError("selected Ghidra binary has no valid registered SHA-256 identity")
        return revision
    try:
        path = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ApprovalError("selected raw image is unavailable") from exc
    if not path.is_file():
        raise ApprovalError("selected raw image is unavailable")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ApprovalError("selected raw image could not be hashed") from exc
    return digest.hexdigest()


def _audit(con: sqlite3.Connection, approval_id: str, event: str, actor: str, detail: dict[str, Any]) -> str:
    event_id = uuid.uuid4().hex
    con.execute(
        "INSERT INTO action_approval_audit(id,approval_id,event,actor_id,occurred_at,detail_json) VALUES(?,?,?,?,?,?)",
        (event_id, approval_id, event, actor, time.time(), json.dumps(detail, sort_keys=True)),
    )
    return event_id


def issue(action_id: str, params: dict[str, Any], operation_key: str, actor: str) -> dict[str, Any]:
    """Record the dashboard's explicit approval of the exact verifier request."""
    if action_id != ACTION_ID:
        raise ApprovalError("this local approval flow only covers byte verification", status=403)
    if not isinstance(params, dict) or not operation_key or len(operation_key) > 128:
        raise ApprovalError("approval request is malformed")
    target = _target_revision(params)
    canonical_params = _canonical(params)
    now = time.time()
    approval_id = uuid.uuid4().hex
    expires = now + APPROVAL_TTL_SECONDS
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            "INSERT INTO action_approval(id,actor_id,action_id,params_sha256,target_revision,operation_key,status,created_at,expires_at) VALUES(?,?,?,?,?,?,'issued',?,?)",
            (approval_id, actor, action_id, hashlib.sha256(canonical_params).hexdigest(), target,
             operation_key, now, expires),
        )
        audit_event_id = _audit(con, approval_id, "issued", actor, {"actionId": action_id, "targetRevision": target})
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "id": approval_id,
        "actorId": actor,
        "auditEventId": audit_event_id,
        "actionId": action_id,
        "params": params,
        "targetRevision": target,
        "expiresAt": expires,
    }


def submit(
    action_id: str,
    params: dict[str, Any],
    *,
    context: dict[str, Any] | None,
    confirm: bool,
    dry_run: bool,
    approval_id: str | None,
    operation_key: str | None,
    actor: str,
) -> tuple[dict[str, Any], int]:
    """Enforce verifier approval on every HTTP entry point before dispatch."""
    from .jobs import get_job, start_job

    if action_id != ACTION_ID or dry_run:
        return start_job(action_id, params, context=context, confirm=confirm, dry_run=dry_run)
    if not confirm or not approval_id or not operation_key:
        raise ApprovalError("explicit review, approval record, and operation key are required", status=403)
    reservation = reserve(approval_id, action_id, params, operation_key, actor)
    if reservation["replay"]:
        job = get_job(str(reservation["jobId"]))
        if job is None:
            raise ApprovalError("approval was consumed but its job receipt is unavailable; inspect job history", status=409)
        return {"ok": True, "deduplicated": True, "job": job.to_dict()}, 202

    payload, status = start_job(action_id, params, context=context, confirm=True, dry_run=False)
    job = payload.get("job")
    job_id = job.get("id") if isinstance(job, dict) else None
    if status >= 400 or not payload.get("ok") or not job_id:
        # start_job returned a definitive no-dispatch refusal. A reserved
        # approval is never released after a possibly accepted dispatch.
        release(approval_id, operation_key, actor, str(payload.get("error") or "request was not dispatched"))
        return payload, status
    complete(approval_id, operation_key, str(job_id), actor)
    return payload, status


def reserve(approval_id: str, action_id: str, params: dict[str, Any], operation_key: str, actor: str) -> dict[str, Any]:
    """Atomically reserve a valid approval; same-key retries never redispatch."""
    if action_id != ACTION_ID:
        raise ApprovalError("approval action does not match", status=403)
    target = _target_revision(params)
    params_hash = hashlib.sha256(_canonical(params)).hexdigest()
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT actor_id,action_id,params_sha256,target_revision,operation_key,status,expires_at,job_id FROM action_approval WHERE id=?",
            (approval_id,),
        ).fetchone()
        if row is None:
            raise ApprovalError("approval record not found", status=403)
        row_actor, row_action, row_params, row_target, row_key, status, expires, job_id = row
        if row_actor != actor or row_action != action_id or row_params != params_hash or row_target != target:
            raise ApprovalError("approval does not cover this actor, request, or target revision", status=403)
        if row_key != operation_key:
            raise ApprovalError("approval is bound to another operation key", status=409)
        if status == "issued" and expires <= time.time():
            con.execute("UPDATE action_approval SET status='expired' WHERE id=?", (approval_id,))
            _audit(con, approval_id, "expired", actor, {})
            con.commit()
            raise ApprovalError("approval expired; review and confirm the request again", status=409)
        if status == "consumed" and job_id:
            con.commit()
            return {"replay": True, "jobId": job_id}
        if status == "issued":
            con.execute("UPDATE action_approval SET status='reserved' WHERE id=? AND status='issued'", (approval_id,))
            _audit(con, approval_id, "reserved", actor, {"operationKey": operation_key})
            con.commit()
            return {"replay": False, "jobId": None}
        raise ApprovalError("approval is already reserved or consumed; inspect Jobs before retrying", status=409)
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()


def complete(approval_id: str, operation_key: str, job_id: str, actor: str) -> None:
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        changed = con.execute(
            "UPDATE action_approval SET status='consumed',job_id=? WHERE id=? AND actor_id=? AND operation_key=? AND status='reserved'",
            (job_id, approval_id, actor, operation_key),
        ).rowcount
        if changed != 1:
            raise ApprovalError("approval reservation changed before job receipt was recorded", status=409)
        _audit(con, approval_id, "consumed", actor, {"jobId": job_id})
        con.commit()
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()


def release(approval_id: str, operation_key: str, actor: str, reason: str) -> None:
    """Release only a confirmed no-dispatch refusal; uncertain outcomes stay reserved."""
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        changed = con.execute(
            "UPDATE action_approval SET status='issued' WHERE id=? AND actor_id=? AND operation_key=? AND status='reserved' AND job_id IS NULL",
            (approval_id, actor, operation_key),
        ).rowcount
        if changed:
            _audit(con, approval_id, "released-no-dispatch", actor, {"reason": reason[:500]})
        con.commit()
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()
