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


PASSES: dict[str, BackfillPass] = {
    "content_sha256": BackfillPass("content_sha256", True, _pass_content_sha256),
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
    return summary
