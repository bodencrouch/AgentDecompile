"""Durable workspace UI state for React and static dashboard pages."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_SECTIONS = ("drafts", "notes", "meta")
MAX_WORKSPACE_STATE_BYTES = 4 * 1024 * 1024
MAX_KEYS_PER_SECTION = 500
MAX_VALUE_CHARS = 512 * 1024


def store_path() -> Path | None:
    from .common import live_root

    root = live_root()
    return root / "workbench-workspace-state.json" if root else None


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    encoded = json.dumps(data, indent=2)
    if len(encoded.encode("utf-8")) > MAX_WORKSPACE_STATE_BYTES:
        raise ValueError(
            f"workspace state exceeds {MAX_WORKSPACE_STATE_BYTES // (1024 * 1024)} MiB after merge"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def _empty() -> dict[str, Any]:
    return {"revision": 0, "updatedAt": 0.0, "drafts": {}, "notes": {}, "meta": {}}


def _parse_revision(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("revision must be a non-negative integer") from None
    if parsed < 0:
        raise ValueError("revision must be a non-negative integer")
    return parsed


def _validate_section(section: str, incoming: dict[str, Any]) -> None:
    if len(incoming) > MAX_KEYS_PER_SECTION:
        raise ValueError(f"{section} exceeds {MAX_KEYS_PER_SECTION} keys")
    for key, value in incoming.items():
        if value is None:
            continue
        if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
            raise ValueError(f"{section}.{key} exceeds {MAX_VALUE_CHARS} characters")


def _load_json_file(path: Path, empty: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        backup = path.with_suffix(path.suffix + f".corrupt-{int(time.time())}.bak")
        try:
            path.replace(backup)
        except OSError:
            pass
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    return data


def load_state() -> dict[str, Any]:
    path = store_path()
    if path is None:
        return _empty()
    data = _load_json_file(path, _empty())
    for section in _SECTIONS:
        data.setdefault(section, {})
    data.setdefault("revision", 0)
    return data


def patch_state(body: dict[str, Any]) -> dict[str, Any]:
    path = store_path()
    if path is None:
        return {"ok": False, "error": "Choose a server workspace before saving UI state."}
    try:
        client_revision = _parse_revision(body.get("revision"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    for section in _SECTIONS:
        incoming = body.get(section)
        if incoming is None:
            continue
        if not isinstance(incoming, dict):
            return {"ok": False, "error": f"{section} must be an object"}
        try:
            _validate_section(section, incoming)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
    with _LOCK:
        current = load_state()
        stored_revision = int(current.get("revision") or 0)
        if client_revision is not None and client_revision != stored_revision:
            merged = False
            for section in _SECTIONS:
                incoming = body.get(section)
                if not isinstance(incoming, dict):
                    continue
                bucket = current.setdefault(section, {})
                for key, value in incoming.items():
                    if value is None:
                        bucket.pop(key, None)
                    else:
                        bucket[key] = value
                merged = True
            if not merged:
                return {"ok": True, "merged": True, **current}
        else:
            for section in _SECTIONS:
                incoming = body.get(section)
                if not isinstance(incoming, dict):
                    continue
                bucket = current.setdefault(section, {})
                for key, value in incoming.items():
                    if value is None:
                        bucket.pop(key, None)
                    else:
                        bucket[key] = value
        current["revision"] = stored_revision + 1
        current["updatedAt"] = time.time()
        try:
            atomic_write(path, current)
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, **current}
