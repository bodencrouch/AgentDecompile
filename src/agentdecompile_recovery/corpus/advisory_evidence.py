"""Read binary-bound, external reverse-engineering observations.

The shared Ghidra project may receive carefully curated observations from
another operator without turning those observations into Ghidra names, source,
or proof.  The sidecar stays beside the project and every row has to bind to
the exact registered slug *and* executable MD5 before it is returned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

LEDGER = "agentdecompile-advisory-evidence.json"


def ledger_path(locator: str | Path) -> Path | None:
    """Return the project-local evidence ledger for a local project locator."""
    try:
        path = Path(locator).expanduser()
    except (TypeError, ValueError):
        return None
    if path.suffix.lower() == ".gpr":
        path = path.parent
    return path / LEDGER if path.is_dir() else None


def read(locator: str | Path, binary: Mapping[str, Any], address: int | None = None) -> list[dict[str, Any]]:
    """Return only exact-binary advisory observations for ``address``.

    Invalid records and incomplete identity bindings are ignored.  This is
    intentionally read-only: applying an observation to Ghidra is an explicit,
    separate mutation with its own provenance and conflict handling.
    """
    path = ledger_path(locator)
    slug = str(binary.get("slug") or "")
    md5 = str(binary.get("md5") or "").lower()
    if path is None or not slug or not md5:
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(document, dict) or document.get("schema") != "agentdecompile-advisory-evidence-v1":
        return []
    records = document.get("records")
    if not isinstance(records, list):
        return []
    out: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict) or item.get("claim") != "advisory":
            continue
        target = item.get("target")
        if not isinstance(target, dict):
            continue
        if str(target.get("slug") or "") != slug or str(target.get("md5") or "").lower() != md5:
            continue
        recorded = item.get("address")
        if address is not None and recorded not in (address, f"0x{address:08x}"):
            continue
        # The source and claim fields make it impossible for this response to
        # look like an accepted source-recovery or byte-verification receipt.
        out.append({**item, "source": "project-local advisory ledger", "ledger": str(path), "claim": "advisory"})
    return out


__all__ = ["LEDGER", "ledger_path", "read"]
