"""Local, opt-in, revocable spectator access (R46 / AE16).

Spectating lets a second local viewer follow the operator's current
preparation state read-only. It starts disabled. The operator enables it
and creates a token that is shown exactly once; after first use the token
travels in a request header, never in the URL. The backend rejects any
write request carrying that header outright — a legitimate operator
session never sends it — independent of whether the token itself is still
valid, so a stale or forged header still fails closed.

State is a small local JSON file next to the workspace, not a database
table, because this plan sets up no remote exposure and no durable
multi-host story: it is a single local on/off switch plus a revocable
token set.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

HEADER = "X-Spectator-Token"
_LOCK = threading.Lock()
_VIEWER_WINDOW_SECONDS = 120


def _state_path() -> Path:
    root = Path(os.environ.get("AGENTDECOMPILE_WORKSPACE") or Path.cwd())
    return root / ".agentdecompile" / "spectator.json"


def _load() -> dict:
    path = _state_path()
    if not path.exists():
        return {"enabled": False, "tokens": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"enabled": False, "tokens": {}}
    if not isinstance(data, dict) or not isinstance(data.get("tokens"), dict):
        return {"enabled": False, "tokens": {}}
    data.setdefault("enabled", False)
    return data


def _save(data) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(json.dumps(data), encoding="utf-8")
    temp.replace(path)


def _hash(token) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def status() -> dict:
    with _LOCK:
        data = _load()
    now = time.time()
    viewers = sum(1 for entry in data["tokens"].values() if now - float(entry.get("lastSeen") or 0) < _VIEWER_WINDOW_SECONDS)
    return {"ok": True, "enabled": bool(data["enabled"]), "tokenCount": len(data["tokens"]), "activeViewers": viewers}


def enable(value) -> dict:
    with _LOCK:
        data = _load()
        data["enabled"] = bool(value)
        if not data["enabled"]:
            # Disabling spectating revokes every outstanding token; there is
            # no "disabled but still-valid token" state to reason about.
            data["tokens"] = {}
        _save(data)
    return status()


def create_token() -> dict:
    with _LOCK:
        data = _load()
        if not data["enabled"]:
            return {"ok": False, "error": "Spectating is disabled. Enable it before creating a token."}
        token = secrets.token_urlsafe(32)
        data["tokens"][_hash(token)] = {"createdAt": time.time(), "lastSeen": 0}
        _save(data)
    # The plaintext token is returned exactly once here and never stored;
    # only its hash is retained, so this response is the one chance to see it.
    return {"ok": True, "token": token}


def revoke_all() -> dict:
    with _LOCK:
        data = _load()
        data["tokens"] = {}
        _save(data)
    return status()


def touch(token) -> bool:
    """Record a spectator heartbeat; return whether the token is live."""
    digest = _hash(token)
    with _LOCK:
        data = _load()
        if not data["enabled"] or digest not in data["tokens"]:
            return False
        data["tokens"][digest]["lastSeen"] = time.time()
        _save(data)
    return True


def is_write_blocked(header_value) -> bool:
    """Any write request carrying this header is rejected, regardless of the
    token's validity: an operator's own browser never sends this header."""
    return bool(header_value)
