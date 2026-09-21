"""Declare the basis a hook pack is deterministic against, and check it.

"Same inputs, same bytes" is only meaningful relative to a declared basis:
which decoder produced the analysis, which algorithm and masking rules ran,
which thresholds applied, and which corpus images were declared. Every pack
carries this object at its root so a re-run can be compared under an
identical basis.

`decoder` is a versioned placeholder until a raw-image decoder is chosen.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

ALGORITHM_VERSION = "phase0.1"
MASKING_RULE_VERSION = "none"
THRESHOLD_PARAMS: dict = {}


def _ghidra_version() -> str:
    install = os.environ.get("GHIDRA_INSTALL_DIR", "").strip()
    if not install:
        return "unknown"
    props = Path(install) / "Ghidra" / "application.properties"
    try:
        for line in props.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("application.version="):
                return line.split("=", 1)[1].strip() or "unknown"
    except OSError:
        pass
    return "unknown"


def _processor_spec_hash(con) -> str:
    """Hash of the sorted language ids the store declares.

    A stand-in for a hash over the processor specification files themselves;
    it still pins which language definitions the analysis was run under.
    """
    ids = sorted(
        str(r[0]) for r in con.execute("SELECT DISTINCT language_id FROM binary WHERE language_id IS NOT NULL")
    )
    if not ids:
        return "unknown"
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:16]


def corpus_manifest_hash(con) -> str:
    """sha256 over the sorted per-image identities, one per line.

    content_sha256 is the identity; md5 stands in when it is missing; the slug
    is the last resort so an image with no recorded hash still counts.
    Blank strings are treated as missing.
    """
    rows = con.execute(
        "SELECT COALESCE(NULLIF(TRIM(content_sha256), ''), NULLIF(TRIM(md5), ''), slug) FROM binary"
    ).fetchall()
    manifest = sorted(str(r[0]) for r in rows)
    return hashlib.sha256("\n".join(manifest).encode("utf-8")).hexdigest()


def basis(con) -> dict:
    return {
        "decoder": f"ghidra-analysis/{_ghidra_version()}+{_processor_spec_hash(con)}",
        "algorithm_version": ALGORITHM_VERSION,
        "masking_rule_version": MASKING_RULE_VERSION,
        "threshold_params": dict(THRESHOLD_PARAMS),
        "corpus_manifest_hash": corpus_manifest_hash(con),
    }


def _copy_store(src: Path, dst: Path) -> None:
    # Backup API, not a file copy: the store runs in WAL mode, so a plain copy
    # of the main file can miss committed rows. Read-only URI never touches src.
    a = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def first_diff_path(a, b, path: str = "$") -> str:
    """Path of the first differing JSON node, walking keys in sorted order."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}"
            sub = first_diff_path(a[k], b[k], f"{path}.{k}")
            if sub:
                return sub
        return ""
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            sub = first_diff_path(x, y, f"{path}[{i}]")
            if sub:
                return sub
        return f"{path}[{min(len(a), len(b))}]" if len(a) != len(b) else ""
    return "" if a == b else path


def verify_export(db: Path, export) -> dict:
    """Run *export(con, out)* against two temp copies of *db* and byte-diff.

    Returns {"identical": bool, "diff": <first differing key path or "">}.
    """
    from .store import connect

    with tempfile.TemporaryDirectory() as tmp:
        outs = []
        for tag in ("a", "b"):
            copy = Path(tmp) / f"{tag}.sqlite"
            _copy_store(Path(db), copy)
            out = Path(tmp) / f"{tag}.json"
            export(connect(copy), out)
            outs.append(out.read_bytes())
    if outs[0] == outs[1]:
        return {"identical": True, "diff": ""}
    path = first_diff_path(json.loads(outs[0]), json.loads(outs[1]))
    return {"identical": False, "diff": path or "$ (serialization only)"}
