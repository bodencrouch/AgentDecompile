"""Register a reviewed group of binary builds with one deterministic receipt."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .registry import BinaryEntry, CorpusManifest, load_corpus, new_corpus

_ENTRY_FIELDS = frozenset(BinaryEntry.__dataclass_fields__)


def register_group(
    manifest_path: Path,
    corpus_path: Path,
    *,
    corpus_id: str | None = None,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Validate and hash every source before atomically adding any entry.

    The manifest is JSON with a ``binaries`` array using ``BinaryEntry`` fields.
    Paths are relative to that manifest when not absolute. Repeating the same
    manifest is idempotent; changing bytes/metadata for an existing id needs an
    explicit ``replace_existing``.
    """
    manifest_path = manifest_path.expanduser().resolve(strict=True)
    raw_bytes = manifest_path.read_bytes()
    raw = json.loads(raw_bytes)
    if not isinstance(raw, dict) or not isinstance(raw.get("binaries"), list) or not raw["binaries"]:
        raise ValueError("manifest must be an object containing a non-empty binaries array")

    sources: list[tuple[BinaryEntry, Path]] = []
    seen_ids: set[str] = set()
    seen_paths: set[Path] = set()
    donors = 0
    for index, item in enumerate(raw["binaries"]):
        if not isinstance(item, dict):
            raise ValueError(f"binaries[{index}] must be an object")
        extra = set(item) - _ENTRY_FIELDS
        if extra:
            raise ValueError(f"binaries[{index}] has unknown field(s): {', '.join(sorted(extra))}")
        entry = BinaryEntry(**item)
        if entry.id in seen_ids:
            raise ValueError(f"duplicate binary id: {entry.id}")
        seen_ids.add(entry.id)
        if entry.role == "donor" or entry.debug in ("stabs", "dwarf"):
            donors += 1
        source = Path(entry.path).expanduser()
        if not source.is_absolute():
            source = manifest_path.parent / source
        source = source.resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"binary source is not a regular file: {source}")
        if source in seen_paths:
            raise ValueError(f"same source file is listed more than once: {source}")
        seen_paths.add(source)
        entry.path = str(source)
        sources.append((entry, source))
    if donors > 1:
        raise ValueError("a binary group may designate at most one donor")

    validated: list[tuple[BinaryEntry, Path, int, str]] = []
    for entry, source in sources:
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(block)
                digest.update(block)
        validated.append((entry, source, size, digest.hexdigest()))

    corpus_path = corpus_path.expanduser().resolve()
    corpus = load_corpus(corpus_path) if corpus_path.is_file() else new_corpus(corpus_id or corpus_path.stem)
    existing = {entry.id: entry for entry in corpus.binaries}
    existing_donor = corpus.donor_id or next(
        (entry.id for entry in corpus.binaries if entry.role == "donor" or entry.debug in ("stabs", "dwarf")),
        None,
    )
    incoming_donors = [
        entry.id for entry, *_ in validated
        if entry.role == "donor" or entry.debug in ("stabs", "dwarf")
    ]
    if incoming_donors and existing_donor and incoming_donors[0] != existing_donor:
        raise ValueError(f"corpus already has donor {existing_donor}; refusing an implicit donor change")

    registered: list[str] = []
    skipped: list[str] = []
    rows = []
    for entry, source, size, digest in validated:
        old = existing.get(entry.id)
        if old is not None:
            same = old.path == entry.path and asdict(old) == asdict(entry)
            if same:
                skipped.append(entry.id)
            elif not replace_existing:
                raise ValueError(f"binary id {entry.id!r} already exists with different path or metadata; pass --replace")
            else:
                corpus.binaries = [row for row in corpus.binaries if row.id != entry.id]
                corpus.binaries.append(entry)
                registered.append(entry.id)
        else:
            corpus.binaries.append(entry)
            registered.append(entry.id)
        if entry.id in incoming_donors:
            corpus.donor_id = entry.id
        rows.append({"id": entry.id, "path": str(source), "sizeBytes": size, "sha256": digest})

    _atomic_json(corpus_path, corpus.to_json())
    return {
        "schema": "agentdecompile.binary-group-registration/v1",
        "corpus": str(corpus_path),
        "corpusId": corpus.id,
        "manifest": str(manifest_path),
        "manifestSha256": hashlib.sha256(raw_bytes).hexdigest(),
        "registered": registered,
        "alreadyPresent": skipped,
        "binaries": rows,
        "claimBoundary": "Registration records build inputs and hashes; it does not analyze, cross-match, recover source, or qualify C/WASM exports.",
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temp_name = stream.name
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
