"""Immutable original-byte targets for independent recovery verification.

A Ghidra analysis image may be unpacked, normalized, or otherwise derived.  It
is useful for analysis but can never be the authority for a byte receipt.  This
module snapshots only the original executable path recorded by Ghidra and
keeps a small, hash-bound provenance receipt beside the recovery work.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from agentdecompile_recovery.targets import sha256_file


def _same_path(left: str | Path | None, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(left).expanduser().resolve() == right.resolve()
    except OSError:
        return False


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def materialize_original_target(
    source_path: str | Path,
    output_root: str | Path,
    *,
    program: str,
    program_fingerprint: str = "",
    expected_sha256: str = "",
    protection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy and hash the original executable for later byte comparisons.

    ``source_path`` must be the Ghidra-recorded original executable.  The
    optional protection record is used solely to reject its analysis image; it
    is never transformed back into an authority target.
    """
    source = Path(source_path).expanduser()
    if not source.is_file():
        return {
            "ok": False,
            "state": "original-unavailable",
            "reason": "The original executable path is unavailable; no byte-comparison target was created.",
            "sourcePath": str(source),
            "authority": "none",
        }
    source = source.resolve()
    protection = protection if isinstance(protection, dict) else {}
    analysis_path = protection.get("analysisPath")
    derived_hash = str(protection.get("derivedSha256") or "").lower()
    source_hash = sha256_file(source)
    if analysis_path and _same_path(analysis_path, source) and derived_hash and source_hash == derived_hash:
        return {
            "ok": False,
            "state": "derived-image-rejected",
            "reason": "The selected path is a derived analysis image and cannot be used as the byte authority.",
            "sourcePath": str(source),
            "sourceSha256": source_hash,
            "authority": "none",
        }
    expected = expected_sha256.lower().strip()
    if expected and source_hash != expected:
        return {
            "ok": False,
            "state": "source-hash-mismatch",
            "reason": "The original executable bytes no longer match the registered binary hash.",
            "sourcePath": str(source),
            "sourceSha256": source_hash,
            "expectedSha256": expected,
            "authority": "none",
        }

    root = Path(output_root).expanduser().resolve() / "target-images" / source_hash
    root.mkdir(parents=True, exist_ok=True)
    target = root / source.name
    receipt = root / "target-image.json"
    prior: dict[str, Any] = {}
    try:
        prior = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not target.is_file() or sha256_file(target) != source_hash:
        temporary = target.with_suffix(".partial")
        temporary.unlink(missing_ok=True)
        shutil.copyfile(source, temporary)
        if sha256_file(temporary) != source_hash:
            temporary.unlink(missing_ok=True)
            return {
                "ok": False,
                "state": "copy-hash-mismatch",
                "reason": "The original executable changed while its verification target was being copied.",
                "sourcePath": str(source),
                "sourceSha256": source_hash,
                "authority": "none",
            }
        temporary.replace(target)
    # Re-read the origin after the copy.  A mutable source must never create a
    # receipt that silently points at a different target than the copied bytes.
    if sha256_file(source) != source_hash:
        return {
            "ok": False,
            "state": "source-changed",
            "reason": "The original executable changed while its verification target was being materialized.",
            "sourcePath": str(source),
            "sourceSha256": source_hash,
            "authority": "none",
        }
    data = {
        "schema": "agentdecompile.original-target.v1",
        "state": "ready",
        "authority": "original-imported-executable",
        "program": program,
        "programFingerprint": program_fingerprint,
        "sourcePath": str(source),
        "sourceSha256": source_hash,
        "expectedSha256": expected or None,
        "targetPath": str(target),
        "targetSha256": sha256_file(target),
        "analysisImagePath": analysis_path or None,
        "analysisImageIsAuthority": False,
        "createdAt": prior.get("createdAt") or time.time(),
        "verifiedAt": time.time(),
    }
    _atomic_json(receipt, data)
    return {"ok": True, **data, "receiptPath": str(receipt)}
