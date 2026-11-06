"""Describe a writable shared Ghidra repository and its local peer.

This is deliberately a state projection, not a file copier.  Ghidra's own
shared-project actions perform pull, reconciliation, checkout/check-in, and
verification so concurrent annotations retain their native conflict handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ghidra_project import inspect_locator


def _origin(info: dict[str, Any]) -> dict[str, Any]:
    rep = info.get("rep")
    if not rep:
        return {}
    path = Path(str(rep)) / "user" / "origin.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def describe(shared_locator: str, local_locator: str) -> dict[str, Any]:
    """Return one pair and the catalog operations that preserve both sides.

    A local project is a peer with its own curated state.  It is never labelled
    a snapshot and this routine intentionally does not select a winner by
    timestamp.  ``sync-project`` owns three-way reconciliation and Ghidra owns
    any per-program conflict resolution.
    """
    shared = inspect_locator(shared_locator)
    local = inspect_locator(local_locator)
    if not shared.get("ok") or not local.get("ok"):
        return {
            "ok": False,
            "shared": shared,
            "local": local,
            "reason": "Both the writable shared repository and local Ghidra project must resolve before reconciliation.",
        }
    origin = _origin(local)
    shared_key = str(shared.get("canonical") or shared.get("locator") or "")
    origin_key = str(origin.get("source_canonical") or origin.get("source_locator") or "")
    linked = bool(shared_key and origin_key and Path(shared_key).expanduser().resolve() == Path(origin_key).expanduser().resolve())
    return {
        "ok": True,
        "kind": "shared-local-pair",
        "shared": {"locator": shared_key, "programs": shared.get("programs") or [], "writable": True},
        "local": {"locator": str(local.get("canonical") or local.get("locator") or ""), "programs": local.get("programs") or [], "origin": origin},
        "linked": linked,
        "claimBoundary": "Pair membership and reconciliation status are project-state facts. They do not establish source recovery or byte verification.",
        "operations": [
            {"id": "mcp.sync-project", "label": "Pull shared changes", "params": {"mode": "pull", "sharedLocator": shared_key, "localLocator": local.get("locator")}},
            {"id": "mcp.sync-project", "label": "Reconcile both project histories", "params": {"mode": "bidirectional", "sharedLocator": shared_key, "localLocator": local.get("locator")}},
            {"id": "mcp.checkout-status", "label": "Inspect program checkout state", "params": {"locator": shared_key}},
            {"id": "mcp.checkin-program", "label": "Check in curated program changes", "params": {"locator": shared_key}},
            {"id": "mcp.inspect-source", "label": "Verify shared/local program inventory", "params": {"locator": shared_key, "localLocator": local.get("locator")}},
        ],
    }


__all__ = ["describe"]
