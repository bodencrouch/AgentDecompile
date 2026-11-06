"""Immutable original-byte targets for independent recovery verification.

A Ghidra analysis image may be unpacked, normalized, or otherwise derived.  It
is useful for analysis but can never be the authority for a byte receipt.  This
module snapshots only the original executable path recorded by Ghidra and
keeps a small, hash-bound provenance receipt beside the recovery work.
"""
from __future__ import annotations

import hashlib
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


def _md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog_target_authority(registry_path: str | Path, repo_path: str) -> dict[str, Any] | None:
    """Return a catalog-original candidate only when its registered MD5 agrees.

    Shared Ghidra projects can retain an executable location from the computer
    where a program was first imported.  The catalog is a separate authority:
    it names an immutable raw image and the historical binary identity that
    image must satisfy.  Merely finding a similarly named file is never enough.
    """
    try:
        payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("repo_path") != repo_path:
            continue
        source = str(entry.get("sourcePath") or "")
        expected_md5 = str(entry.get("catalogMd5") or entry.get("md5") or "").lower()
        if not source or len(expected_md5) != 32 or not entry.get("catalogMd5Matches"):
            return None
        return {
            "sourcePath": source,
            "expectedMd5": expected_md5,
            "catalogDatabase": entry.get("catalogDatabase"),
            "catalogRepoPath": repo_path,
            "sourceKind": entry.get("sourceKind") or "catalog-raw-image",
            "claimBoundary": entry.get("claimBoundary"),
        }
    return None


def materialize_original_target(
    source_path: str | Path,
    output_root: str | Path,
    *,
    program: str,
    program_fingerprint: str = "",
    expected_sha256: str = "",
    expected_md5: str = "",
    protection: dict[str, Any] | None = None,
    source_provenance: dict[str, Any] | None = None,
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
    expected_md5 = expected_md5.lower().strip()
    if expected_md5:
        source_md5 = _md5_file(source)
        if source_md5 != expected_md5:
            return {
                "ok": False,
                "state": "source-md5-mismatch",
                "reason": "The catalog original does not match the registered binary MD5.",
                "sourcePath": str(source),
                "sourceMd5": source_md5,
                "expectedMd5": expected_md5,
                "authority": "none",
            }
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
        "expectedMd5": expected_md5 or None,
        "targetPath": str(target),
        "targetSha256": sha256_file(target),
        "analysisImagePath": analysis_path or None,
        "analysisImageIsAuthority": False,
        "sourceProvenance": source_provenance if isinstance(source_provenance, dict) else None,
        "createdAt": prior.get("createdAt") or time.time(),
        "verifiedAt": time.time(),
    }
    _atomic_json(receipt, data)
    return {"ok": True, **data, "receiptPath": str(receipt)}
