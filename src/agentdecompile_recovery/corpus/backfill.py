"""Re-derive per-binary columns from the raw images already on disk.

This is the frame that later re-extraction passes plug into (masked
patterns, decode-based block hashes, per-parameter storage). Each pass is a
pure function of one ``binary`` row and its raw image bytes; the frame owns
iteration order, resumability, and the receipts.

Receipts: one JSON file per (pass, binary) under ``receipts_dir/<pass>/``.
The file name and the ``key`` inside it come from the raw image's own
sha256 when the image exists, and from the slug when it does not. Nothing
in a receipt is clock-derived. With ``resume=True`` a valid completed
receipt is not rewritten; an explicit fresh run may change its status from
``updated`` to ``unchanged``.

A receipt records the pair's ``status``. Resume trusts a receipt only when
that status is ``updated`` or ``unchanged`` *and* the row still satisfies
the pass (:attr:`BackfillPass.satisfied`). A ``skipped`` receipt, a receipt
without a status, or a row that lost its value since is re-run, so a pair
skipped for a missing input is retried once the input appears.
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


def _pass_reloc_table(con: sqlite3.Connection, binary_row: dict, raw: bytes | None) -> dict:
    """Record ``binary.reloc_table_present`` (1, 0 or NULL for unknown) from the image (U52)."""
    from .reloc_presence import relocation_table
    assert raw is not None  # needs_raw_image=True; the frame skips otherwise
    columns = {r[1] for r in con.execute("PRAGMA table_info(binary)")}
    for column, kind in (("reloc_table_present", "INTEGER"), ("reloc_table_reason", "TEXT")):
        if column not in columns:
            con.execute(f"ALTER TABLE binary ADD COLUMN {column} {kind}")
    found = relocation_table(raw)
    value = None if found["present"] is None else int(found["present"])
    current = con.execute("SELECT reloc_table_present, reloc_table_reason FROM binary WHERE id=?",
                          (int(binary_row["id"]),)).fetchone()
    result = {"reloc_table_present": value, "reloc_table_reason": found["reason"], "format": found["format"]}
    if current is not None and tuple(current) == (value, found["reason"]):
        return {"status": "unchanged", **result}
    con.execute("UPDATE binary SET reloc_table_present=?, reloc_table_reason=? WHERE id=?",
                (value, found["reason"], int(binary_row["id"])))
    return {"status": "updated", **result}


def _reloc_table_satisfied(row: dict, result: dict) -> bool:
    return row.get("reloc_table_reason") == result.get("reloc_table_reason")


def _content_sha256_satisfied(row: dict, result: dict) -> bool:
    digest = result.get("content_sha256")
    return bool(digest) and row.get("content_sha256") == digest


def _analyzer_identity_satisfied(row: dict, result: dict) -> bool:
    return all(row.get(c) for c in ("analyzer_version", "processor_spec_hash", "basis_hash"))


PASSES: dict[str, BackfillPass] = {
    "content_sha256": BackfillPass("content_sha256", True, _pass_content_sha256, _content_sha256_satisfied),
    "analyzer_identity": BackfillPass(
        "analyzer_identity", False, _pass_analyzer_identity, _analyzer_identity_satisfied
    ),
    "reloc_table": BackfillPass("reloc_table", True, _pass_reloc_table, _reloc_table_satisfied),
}


_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _receipt_path(receipts_dir: Path, pass_name: str, identity: str) -> Path:
    stem = identity if re.fullmatch(r"[0-9a-f]{64}", identity) else "slug-" + _SAFE.sub("_", identity)
    return receipts_dir / pass_name / f"{stem}.json"


def _raw_image(repo_path: str) -> tuple[Path, bytes | None]:
    from .ghidra_bulk import raw_image_path

    path = raw_image_path(repo_path)
    if not path.is_file():
        return path, None
    try:
        return path, path.read_bytes()
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
    slug when there is no image). With ``resume=True`` a pair is counted as
    ``resumed`` and not re-run only when its receipt has a matching key, a
    status of ``updated`` or ``unchanged``, and the row still satisfies the
    pass; any other receipt (``skipped``, no status, a row that changed
    since) is re-run and rewritten. A missing raw image is ``skipped`` with
    reason ``no_raw_image``, never an exception. The database write for a
    pair is committed before its receipt is written, so a receipt always
    implies a committed row.
    """
    unknown = sorted(set(passes) - set(PASSES))
    if unknown:
        raise ValueError(f"unknown backfill pass: {', '.join(unknown)} (known: {', '.join(sorted(PASSES))})")
    wanted = [PASSES[name] for name in sorted(set(passes))]
    receipts_dir = Path(receipts_dir)

    summary: dict = {"passes": {}, "receipts_dir": str(receipts_dir)}
    for step in wanted:
        counts = {"updated": 0, "unchanged": 0, "skipped": 0, "resumed": 0}
        entries: list[dict] = []
        # Re-read per pass: an earlier pass may have written columns this
        # one reads.
        for row in _binary_rows(con):
            binary_id = int(row["id"])
            slug = str(row.get("slug") or binary_id)
            raw_path, raw = _raw_image(str(row.get("repo_path") or ""))
            identity = hashlib.sha256(raw).hexdigest() if raw is not None else slug
            key = {"pass": step.name, "identity": identity}
            receipt = _receipt_path(receipts_dir, step.name, identity)

            if resume and receipt.is_file():
                try:
                    existing = json.loads(receipt.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    existing = None
                if (
                    isinstance(existing, dict)
                    and existing.get("key") == key
                    and existing.get("status") in RESUMABLE_STATUSES
                    and isinstance(existing.get("result"), dict)
                    and step.satisfied(row, existing["result"])
                ):
                    counts["resumed"] += 1
                    entries.append({"id": binary_id, "slug": slug, "status": "resumed"})
                    continue

            if raw is None and step.needs_raw_image:
                result = {"status": "skipped", "reason": "no_raw_image"}
            else:
                result = step.fn(con, row, raw)
                con.commit()
            status = str(result.get("status", "unchanged"))

            # The receipt records both what was derived and this run's status;
            # resume needs the latter to distinguish completed work from a
            # skipped attempt whose missing input may now be available.
            body = {
                "key": key,
                "binary": {"id": binary_id, "slug": slug, "repo_path": row.get("repo_path")},
                "raw_image": str(raw_path) if raw is not None else None,
                "result": {k: v for k, v in result.items() if k != "status"},
                "status": status,
            }
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_bytes(_dump(body))
            counts[status] = counts.get(status, 0) + 1
            entry = {"id": binary_id, "slug": slug, "status": status}
            if "reason" in result:
                entry["reason"] = result["reason"]
            entries.append(entry)
        summary["passes"][step.name] = {"counts": counts, "binaries": entries}
    return summary
