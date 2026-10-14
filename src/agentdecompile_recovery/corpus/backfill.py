"""Re-derive per-binary columns from the raw images already on disk.

This is the frame that later re-extraction passes plug into (masked
patterns, decode-based block hashes, per-parameter storage). Each pass is a
pure function of one ``binary`` row and its raw image bytes; the frame owns
iteration order, resumability, and the receipts.

Receipts: one JSON file per (pass, binary) under ``receipts_dir/<pass>/``.
The file name and the ``key`` inside it come from the raw image's own
sha256 when the image exists (the stored ``content_sha256`` for a pass that
does not read the image), and from ``slug-<sha256(slug)[:12]>`` when there is
no hash. Nothing in a receipt is clock-derived, so a re-run over unchanged
inputs writes identical bytes -- and with ``resume=True`` does not write at
all.

No slug reaches a receipt after this commit. ``body["binary"]`` carries the
row's ``identity`` (the same value as the key), ``repo_path_sha12`` and the
non-name columns (``format``, ``arch``, ``bits``, ``md5``,
``analyzer_version``, ``basis_hash``); never ``slug``, ``repo_path``, ``game``
or the row id. The raw image's path (which spells the repo path) is reduced
to ``raw_image_present``.

Legacy receipts are resumed once and rewritten: a hashless row's old file
(``slug-<sanitized slug>.json`` keyed by the raw slug, found through
``_legacy_receipt_path``) is rewritten at the new stem and the old file is
removed; a hashed row's old-shape body at the unchanged stem is rewritten in
place. Either way the ``result`` is carried over verbatim and only the fields
around it are renamed. One-way; nothing reads the old shape after that.
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
#: ``satisfied(row, receipt_result)``: does the stored row still hold what the
#: receipt says the pass derived? Gates resume.
SatisfiedFn = Callable[[dict, dict], bool]

#: Receipt statuses that resume may trust (subject to ``satisfied``).
RESUMABLE_STATUSES = frozenset({"updated", "unchanged"})


def _never_satisfied(row: dict, result: dict) -> bool:
    """Default for a pass that names no check: resume always re-runs it."""
    return False


@dataclass(frozen=True)
class BackfillPass:
    name: str
    needs_raw_image: bool
    fn: PassFn
    satisfied: SatisfiedFn = _never_satisfied


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


def _content_sha256_satisfied(row: dict, result: dict) -> bool:
    digest = result.get("content_sha256")
    return bool(digest) and row.get("content_sha256") == digest


def _analyzer_identity_satisfied(row: dict, result: dict) -> bool:
    return all(row.get(c) and row.get(c) == result.get(c) for c in ("analyzer_version", "processor_spec_hash", "basis_hash"))


def _raw_image_satisfied(row: dict, result: dict) -> bool:
    """Resume only while a stored content hash still identifies this image."""
    return bool(row.get("content_sha256")) and row.get("content_sha256") == result.get("sha256")


def _pass_raw_image(con: sqlite3.Connection, binary_row: dict, raw: bytes | None) -> dict:
    """Materialize the raw image and report its hash and size; writes no column."""
    assert raw is not None  # needs_raw_image=True; the frame skips otherwise
    return {"status": "unchanged", "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


PASSES: dict[str, BackfillPass] = {
    "raw_image": BackfillPass("raw_image", True, _pass_raw_image, _raw_image_satisfied),
    "content_sha256": BackfillPass("content_sha256", True, _pass_content_sha256, _content_sha256_satisfied),
    "analyzer_identity": BackfillPass(
        "analyzer_identity", False, _pass_analyzer_identity, _analyzer_identity_satisfied
    ),
}


_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_RECEIPT_COLUMNS = ("format", "arch", "bits", "md5", "analyzer_version", "basis_hash")


def _sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _receipt_identity(identity: str, slug: str) -> str:
    """The name a binary goes by in a receipt, its file name and the summary:
    the content sha256 when that is the identity, else ``slug-<sha256(slug)[:12]>``.
    The summary goes to a verb's stdout, so it never carries a slug or a row id."""
    if _HEX64.fullmatch(identity):
        return identity
    return "slug-" + _sha12(slug)


_entry_identity = _receipt_identity


def _receipt_path(receipts_dir: Path, pass_name: str, receipt_identity: str) -> Path:
    """``<receipts_dir>/<pass>/<receipt identity>.json``; the stem is a hash either way."""
    return receipts_dir / pass_name / f"{receipt_identity}.json"


def _legacy_receipt_path(receipts_dir: Path, pass_name: str, slug: str) -> Path:
    """Where a hashless row's receipt lived before the stem was hashed (``slug-<sanitized slug>``).
    Read for resume only; nothing writes here."""
    return receipts_dir / pass_name / f"slug-{_SAFE.sub('_', slug)}.json"


def _binary_block(row: dict, receipt_identity: str) -> dict:
    """``body["binary"]``: identity, hashed repo path and the non-name columns. No slug, repo path, game or id."""
    repo_path = str(row.get("repo_path") or "")
    block = {"identity": receipt_identity, "repo_path_sha12": _sha12(repo_path) if repo_path else None}
    for column in _RECEIPT_COLUMNS:
        block[column] = row.get(column)
    return block


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


def _load_receipt(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _body(key: dict, row: dict, receipt_identity: str, *, raw_present: bool, result: dict, status: str) -> dict:
    """One receipt's content. Every field is a hash, a column value or the derived result."""
    return {
        "key": key,
        "binary": _binary_block(row, receipt_identity),
        "raw_image_present": bool(raw_present),
        "result": dict(result),
        "status": status,
    }


def _current_shape(existing: dict) -> bool:
    """Whether a receipt on disk already has this commit's body (no slug, no repo path, no raw image path)."""
    binary = existing.get("binary")
    return (
        isinstance(binary, dict) and "identity" in binary and "slug" not in binary and "repo_path" not in binary
        and "raw_image" not in existing
    )


def _migrated(existing: dict, key: dict, row: dict, receipt_identity: str) -> dict:
    """An old-shape receipt rewritten under this commit's shape: same ``result``, renamed fields.
    Old bodies carried the raw image's path (or ``None``); only its presence survives."""
    if "raw_image_present" in existing:
        raw_present = bool(existing["raw_image_present"])
    else:
        raw_present = existing.get("raw_image") is not None
    return _body(key, row, receipt_identity, raw_present=raw_present,
                 result=existing.get("result") or {}, status=str(existing.get("status") or "legacy"))


def run(
    con: sqlite3.Connection,
    passes: list[str],
    *,
    receipts_dir: Path,
    resume: bool = True,
) -> dict:
    """Run *passes* over every binary in id order. Returns a summary.

    Per (pass, binary): a receipt keyed by the raw image's sha256 (or
    ``slug-<sha12>`` when there is no image). With ``resume=True`` a pair whose
    receipt has a matching key, a status of ``updated`` or ``unchanged``, and
    the row still satisfies the pass; any other receipt (including ``skipped``)
    is re-run. Legacy receipts are rewritten without their raw slug/path fields.
    A missing raw image is ``skipped`` with reason ``no_raw_image``, never an
    exception. The database write for a pair is committed before its receipt is
    written, so a receipt always implies a committed row.
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
        if step.needs_raw_image:
            _, raw = _raw_image(str(row.get("repo_path") or ""), con, slug)
            identity = hashlib.sha256(raw).hexdigest() if raw is not None else slug
        else:
            # A pass that does not read the image must not pay for resolving
            # it (a resolver may boot the analyzer): its receipt is keyed by
            # the stored content hash, else the slug (3b report; H14).
            raw = None
            stored = str(row.get("content_sha256") or "").strip()
            identity = stored if stored else slug
        receipt_identity = _receipt_identity(identity, slug)
        key = {"pass": step.name, "identity": receipt_identity}
        receipt = _receipt_path(receipts_dir, step.name, receipt_identity)

        if resume:
            existing = _load_receipt(receipt)
            if isinstance(existing, dict) and existing.get("key") == key:
                if not _current_shape(existing):
                    # Same stem, old body (a hashed row receipted before this commit):
                    # rewrite in place so the slug leaves the file.
                    existing = _migrated(existing, key, row, receipt_identity)
                    receipt.write_bytes(_dump(existing))
                if (
                    existing.get("status") in RESUMABLE_STATUSES
                    and isinstance(existing.get("result"), dict)
                    and step.satisfied(row, existing["result"])
                ):
                    counts["resumed"] += 1
                    entries.append({"identity": receipt_identity, "status": "resumed"})
                    continue
            if receipt_identity != identity:
                legacy = _legacy_receipt_path(receipts_dir, step.name, slug)
                existing = _load_receipt(legacy) if legacy != receipt else None
                if isinstance(existing, dict) and existing.get("key") == {"pass": step.name, "identity": identity}:
                    # One-way migration: same result, renamed fields, hashed stem; the old file goes.
                    receipt.parent.mkdir(parents=True, exist_ok=True)
                    receipt.write_bytes(_dump(_migrated(existing, key, row, receipt_identity)))
                    legacy.unlink()

        if raw is None and step.needs_raw_image:
            result = {"status": "skipped", "reason": "no_raw_image"}
        else:
            result = step.fn(con, row, raw)
            con.commit()
        status = str(result.get("status", "unchanged"))

        body = _body(key, row, receipt_identity, raw_present=raw is not None,
                     result={k: v for k, v in result.items() if k != "status"}, status=status)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(_dump(body))
        counts[status] = counts.get(status, 0) + 1
        entry = {"identity": receipt_identity, "status": status}
        if "reason" in result:
            entry["reason"] = result["reason"]
        entries.append(entry)
    summary["passes"][step.name] = {"counts": counts, "binaries": entries}
