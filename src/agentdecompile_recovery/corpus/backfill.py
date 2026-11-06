"""Re-derive per-binary columns from the raw images already on disk.

This is the frame that later re-extraction passes plug into (masked
patterns, decode-based block hashes, per-parameter storage). Each pass is a
pure function of one ``binary`` row and its raw image bytes; the frame owns
iteration order, resumability, and the receipts.

Receipts: one JSON file per (pass, binary) under ``receipts_dir/<pass>/``.
The file name and the ``key`` inside it come from the raw image's own
sha256 when the image exists, and from the slug when it does not. Nothing
in a receipt is clock-derived, so a re-run over unchanged inputs writes
identical bytes -- and with ``resume=True`` does not write at all.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PassFn = Callable[[sqlite3.Connection, dict, "bytes | None"], dict]


@dataclass(frozen=True)
class BackfillPass:
    name: str
    needs_raw_image: bool
    fn: PassFn


def _pass_content_sha256(con: sqlite3.Connection, binary_row: dict, raw: bytes | None) -> dict:
    """Write ``binary.content_sha256`` from the raw image when NULL or stale."""
    assert raw is not None  # needs_raw_image=True; the frame skips otherwise
    digest = hashlib.sha256(raw).hexdigest()
    stored = binary_row.get("content_sha256")
    if stored == digest:
        return {"status": "unchanged", "content_sha256": digest}
    con.execute("UPDATE binary SET content_sha256=? WHERE id=?", (digest, int(binary_row["id"])))
    return {"status": "updated", "content_sha256": digest}


def _pass_analyzer_identity(con: sqlite3.Connection, binary_row: dict, raw: bytes | None) -> dict:
    """Fill NULL ``analyzer_version`` / ``processor_spec_hash`` / ``basis_hash``
    from the *current* install and mark the row ``basis_source='backfill'``.

    Never overwrites a value that is already present, so a row an ingest
    stamped keeps its captured identity. A row whose three columns are all
    present is ``unchanged``. When the install's version cannot be read the
    row is ``skipped`` with reason ``no_install`` rather than stamped
    ``"unknown"``; a row without a language id is ``skipped`` with reason
    ``no_language_id``.
    """
    from .determinism_basis import install_analyzer_version
    from .extract import stamp_analyzer_identity

    bid = int(binary_row["id"])
    present = all(binary_row.get(c) for c in ("analyzer_version", "processor_spec_hash", "basis_hash"))
    if present:
        return {"status": "unchanged", "basis_hash": binary_row["basis_hash"]}
    version = binary_row.get("analyzer_version") or install_analyzer_version()
    if not version:
        return {"status": "skipped", "reason": "no_install"}
    if not binary_row.get("processor_spec_hash") and not str(binary_row.get("language_id") or "").strip():
        return {"status": "skipped", "reason": "no_language_id"}
    result = stamp_analyzer_identity(con, analyzer_version=version, binary_ids=[bid], source="backfill")
    if bid in result["skipped"]:
        return {"status": "skipped", "reason": "basis_incomplete"}
    row = con.execute(
        "SELECT analyzer_version, processor_spec_hash, basis_hash FROM binary WHERE id=?", (bid,)
    ).fetchone()
    return {
        "status": "updated",
        "analyzer_version": row[0],
        "processor_spec_hash": row[1],
        "basis_hash": row[2],
        "basis_source": "backfill",
    }


def _pass_raw_image(con: sqlite3.Connection, binary_row: dict, raw: bytes | None) -> dict:
    """Materialize the raw image and report its hash and size; writes no column.

    The frame resolves the image through the resolver registry before any
    pass runs, so by the time this pass is called the image is on disk at
    ``raw_image_path(repo_path)``. A missing image is ``skipped`` with
    ``no_raw_image`` by the frame, never here.
    """
    assert raw is not None  # needs_raw_image=True; the frame skips otherwise
    return {"status": "present", "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


PASSES: dict[str, BackfillPass] = {
    "raw_image": BackfillPass("raw_image", True, _pass_raw_image),
    "content_sha256": BackfillPass("content_sha256", True, _pass_content_sha256),
    "analyzer_identity": BackfillPass("analyzer_identity", False, _pass_analyzer_identity),
}


_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _receipt_path(receipts_dir: Path, pass_name: str, identity: str) -> Path:
    stem = identity if re.fullmatch(r"[0-9a-f]{64}", identity) else "slug-" + _SAFE.sub("_", identity)
    return receipts_dir / pass_name / f"{stem}.json"


def _raw_image(
    repo_path: str,
    con: sqlite3.Connection | None = None,
    slug: str | None = None,
    *,
    deadline_s: float = 120.0,
) -> tuple[Path, bytes | None]:
    """``(raw_image_path, bytes | None)`` for *repo_path*.

    Resolution goes through the resolver registry (:mod:`raw_images`): the
    raw directory first, then the registered file, an explicit map, the
    content-identity tables and the analysis project's stored file bytes.
    A hit is materialized at ``raw_image_path(repo_path)`` so every later
    verb finds it there. *con* supplies the row context (program bindings,
    identity rows) when given; without it only file-based resolvers apply.
    The return shape is unchanged; a miss is ``(path, None)``.
    """
    from .ghidra_bulk import raw_image_path
    from .raw_images import resolve_raw_image, row_context

    path = raw_image_path(repo_path)
    row: dict = {"repo_path": repo_path, "slug": slug or ""}
    if con is not None:
        try:
            row = row_context(con, row)
        except sqlite3.Error:
            pass
    # A bad resolver configuration (RawImageError, a ValueError) propagates:
    # it is a refusal, not a missing image.
    image = resolve_raw_image(row, deadline_s=deadline_s)
    target = image.path if image is not None and image.path is not None else path
    if not target.is_file():
        return path, None
    try:
        return path, target.read_bytes()
    except OSError:
        return path, None


def _binary_rows(con: sqlite3.Connection) -> list[dict]:
    cur = con.execute("SELECT * FROM binary ORDER BY id")
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _dump(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode("utf-8")


def run(
    con: sqlite3.Connection,
    passes: list[str],
    *,
    receipts_dir: Path,
    resume: bool = True,
) -> dict:
    """Run *passes* over every binary in id order. Returns a summary.

    Per (pass, binary): a receipt keyed by the raw image's sha256 (or the
    slug when there is no image). With ``resume=True`` a pair whose receipt
    already exists with a matching key is counted as ``resumed`` and not
    re-run. A missing raw image is ``skipped`` with reason ``no_raw_image``,
    never an exception. The database write for a pair is committed before
    its receipt is written, so a receipt always implies a committed row.
    """
    unknown = sorted(set(passes) - set(PASSES))
    if unknown:
        raise ValueError(f"unknown backfill pass: {', '.join(unknown)} (known: {', '.join(sorted(PASSES))})")
    wanted = [PASSES[name] for name in sorted(set(passes))]
    receipts_dir = Path(receipts_dir)

    from .raw_images import close_resolvers

    summary: dict = {"passes": {}, "receipts_dir": str(receipts_dir)}
    try:
        for step in wanted:
            _run_pass(con, step, receipts_dir=receipts_dir, resume=resume, summary=summary)
    finally:
        # Resolvers may hold analysis projects open across rows; release them.
        summary["resolvers_closed"] = close_resolvers()
    return summary


def _run_pass(
    con: sqlite3.Connection,
    step: BackfillPass,
    *,
    receipts_dir: Path,
    resume: bool,
    summary: dict,
) -> None:
    """One pass over every binary; fills ``summary["passes"][step.name]``."""
    counts = {"updated": 0, "unchanged": 0, "skipped": 0, "resumed": 0}
    entries: list[dict] = []
    # Re-read per pass: an earlier pass may have written columns this
    # one reads.
    for row in _binary_rows(con):
        binary_id = int(row["id"])
        slug = str(row.get("slug") or binary_id)
        raw_path, raw = _raw_image(str(row.get("repo_path") or ""), con, slug)
        identity = hashlib.sha256(raw).hexdigest() if raw is not None else slug
        key = {"pass": step.name, "identity": identity}
        receipt = _receipt_path(receipts_dir, step.name, identity)

        if resume and receipt.is_file():
            try:
                existing = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = None
            if isinstance(existing, dict) and existing.get("key") == key:
                counts["resumed"] += 1
                entries.append({"id": binary_id, "slug": slug, "status": "resumed"})
                continue

        if raw is None and step.needs_raw_image:
            result = {"status": "skipped", "reason": "no_raw_image"}
        else:
            result = step.fn(con, row, raw)
            con.commit()
        status = str(result.get("status", "unchanged"))

        # The receipt records what was derived, not whether this run had
        # to write it: the same inputs always produce the same bytes.
        body = {
            "key": key,
            "binary": {"id": binary_id, "slug": slug, "repo_path": row.get("repo_path")},
            "raw_image": str(raw_path) if raw is not None else None,
            "result": {k: v for k, v in result.items() if k != "status"},
        }
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(_dump(body))
        counts[status] = counts.get(status, 0) + 1
        entry = {"id": binary_id, "slug": slug, "status": status}
        if "reason" in result:
            entry["reason"] = result["reason"]
        entries.append(entry)
    summary["passes"][step.name] = {"counts": counts, "binaries": entries}
