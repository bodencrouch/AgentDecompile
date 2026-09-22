"""Admit a real multi-build store to the content-hash key (register A4).

A store that grew by hand carries three kinds of ``binary`` rows the keyed
verbs cannot serve: analyzed builds whose original image is not on disk
(no ``content_sha256``), placeholder registrations with no analysis at
all, and the same image registered twice. ``corpus admit`` turns that
store into one the key applies to, without a human:

1. classify every row (``AdmissionPolicy``);
2. quarantine placeholders (``PlaceholderHandling``);
3. resolve the raw image of every analyzed build through the resolver
   registry (:mod:`raw_images`) and record its ``content_sha256``;
4. merge duplicate registrations into one keeper plus aliases
   (``DuplicateResolution``), with a ``binary_source_alias`` row;
5. mark every analyzed, hashed, non-duplicate row ``admitted``.

Scope. The content-hash key applies to admitted builds. Placeholders,
duplicates, contested and unresolved rows are outside every key, basis,
manifest and pack by design. :func:`admitted_predicate` is the one place
that predicate lives; ``determinism_basis``, ``logical`` and
``export_hookpack`` call it. Until the first admit run (no row carries an
``admission_status``) the predicate is empty and the legacy unscoped
behaviour holds, so a migrated-but-not-admitted store behaves as before.

Writes. One ``BEGIN IMMEDIATE`` transaction per row, committed before the
row's receipt is written, so a receipt always implies a committed row.
Receipts live at ``<receipts>/admit/<identity>.json`` where identity is
the content hash or ``slug-<sha256(slug)[:12]>``. Nothing in a receipt is
clock-derived and no receipt carries a slug or a path.

Deadlines. Every loop checks the overall deadline between rows; the raw
image walk gets the per-row deadline. Overrunning stops the verb between
rows with status ``deadline`` -- it is reported, never waited on.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from .raw_images import (
    RawImage,
    RawImageError,
    close_resolvers,
    last_misses,
    raw_image_root,
    resolve_raw_image,
    resolver_order,
    row_context,
    sha12,
)

DEADLINE_ENV = "AGENT_DECOMPILE_ADMIT_DEADLINE_S"
DEFAULT_DEADLINE_S = 1800.0
VERB = "admit"


class AdmissionError(ValueError):
    """A refusal: the verb cannot start (bad configuration, missing columns)."""


class AdmissionClass(str, Enum):
    ANALYZED = "analyzed"
    PLACEHOLDER = "placeholder"


class AdmissionStatus(str, Enum):
    ADMITTED = "admitted"
    PLACEHOLDER = "placeholder"
    DUPLICATE = "duplicate"
    CONTESTED = "contested"
    UNRESOLVED = "unresolved"


class PlaceholderHandling(str, Enum):
    """What happens to a row with no analysis.

    ``QUARANTINE`` keeps the row, marks it ``placeholder`` and leaves it out
    of every key, basis, manifest and pack -- the pack does not mention it.
    ``EXCLUDE`` does the same and additionally lists the row under the
    pack's ``excluded_builds``. ``DROP`` deletes the row and its per-binary
    rows through ``store.remove_binary``; it is never the default.
    """

    QUARANTINE = "quarantine"
    EXCLUDE = "exclude"
    DROP = "drop"


@dataclass(frozen=True)
class RowStats:
    func_rows: int
    has_md5: bool
    has_format: bool
    has_analyzer_version: bool

    def as_dict(self) -> dict:
        return {
            "func_rows": int(self.func_rows),
            "has_analyzer_version": bool(self.has_analyzer_version),
            "has_format": bool(self.has_format),
            "has_md5": bool(self.has_md5),
        }


# --- policies -------------------------------------------------------------------


@runtime_checkable
class AdmissionPolicy(Protocol):
    name: str

    def classify(self, row: dict, stats: RowStats) -> AdmissionClass: ...


class DefaultAdmissionPolicy:
    """``ANALYZED`` when the row has ``func`` rows; ``PLACEHOLDER`` otherwise."""

    name = "default"

    def classify(self, row: dict, stats: RowStats) -> AdmissionClass:
        return AdmissionClass.ANALYZED if stats.func_rows > 0 else AdmissionClass.PLACEHOLDER


class ManifestPolicy:
    """Slot: a declared manifest decides.

    Contract: a JSON manifest keyed by hashed slug (``sha256(slug)``) maps
    each row to a class; rows absent from the manifest fall back to
    :class:`DefaultAdmissionPolicy`. The manifest path is the constructor
    argument; its sha256 goes into every receipt's ``input_key``.
    """

    name = "manifest"

    def __init__(self, manifest: Path | None = None) -> None:
        self.manifest = manifest

    def classify(self, row: dict, stats: RowStats) -> AdmissionClass:
        raise NotImplementedError("A4.manifest_policy")


class StrictPolicy:
    """Slot: analysis rows are not enough; the row must also carry analyzer
    identity (``analyzer_version``), a ``format`` and an ``md5``.

    Contract: ``ANALYZED`` only when ``func_rows > 0`` and all three flags
    are set; a row with analysis but no identity is ``PLACEHOLDER`` with
    the receipt naming which flag was missing.
    """

    name = "strict"

    def classify(self, row: dict, stats: RowStats) -> AdmissionClass:
        raise NotImplementedError("A4.strict_policy")


ADMISSION_POLICIES: dict[str, AdmissionPolicy] = {
    p.name: p for p in (DefaultAdmissionPolicy(), ManifestPolicy(), StrictPolicy())
}


# --- duplicates -----------------------------------------------------------------


@runtime_checkable
class DuplicateResolution(Protocol):
    name: str

    def resolve(self, group: list[dict]) -> tuple[dict, list[dict]]: ...


class KeepMostAnalyzed:
    """Keeper = most ``func`` rows, then smallest ``repo_path``, then smallest
    ``slug``. Never a rowid."""

    name = "keep_most_analyzed"

    def resolve(self, group: list[dict]) -> tuple[dict, list[dict]]:
        if not group:
            raise ValueError("duplicate group is empty")
        ordered = sorted(
            group,
            key=lambda r: (-int(r.get("func_rows") or 0), str(r.get("repo_path") or ""), str(r.get("slug") or "")),
        )
        return ordered[0], ordered[1:]


class MergeEvidence:
    """Slot: fold the aliases' ``func`` / ``match`` rows into the keeper.

    Contract: for every alias, ``func`` rows at addresses the keeper lacks
    are re-keyed to the keeper; ``match`` rows are re-pointed; conflicts
    are receipts, not guesses. Then the alias is marked as
    :class:`KeepMostAnalyzed` marks it.
    """

    name = "merge_evidence"

    def resolve(self, group: list[dict]) -> tuple[dict, list[dict]]:
        raise NotImplementedError("U30")


DUPLICATE_RESOLUTIONS: dict[str, DuplicateResolution] = {
    d.name: d for d in (KeepMostAnalyzed(), MergeEvidence())
}


# --- scope helpers ---------------------------------------------------------------


def has_admission_columns(con) -> bool:
    cols = {row[1] for row in con.execute("PRAGMA table_info(binary)")}
    return "admission_status" in cols


def admission_active(con) -> bool:
    """True once any row carries an ``admission_status`` (admit has run)."""
    if not has_admission_columns(con):
        return False
    row = con.execute("SELECT 1 FROM binary WHERE admission_status IS NOT NULL LIMIT 1").fetchone()
    return row is not None


def admission_scope(con) -> str:
    """``"admitted"`` when the keyed verbs must see admitted rows only, else ``"all"``."""
    return "admitted" if admission_active(con) else "all"


def admitted_predicate(con, alias: str = "binary") -> str:
    """SQL fragment (leading ``AND``) restricting *alias* to admitted rows.

    Empty on a pre-migration store and on a migrated store where admit has
    not run yet, so callers can append it to any ``WHERE`` unconditionally.
    Placeholders are outside the key by design (A4).
    """
    if admission_scope(con) != "admitted":
        return ""
    return f" AND {alias}.admission_status = '{AdmissionStatus.ADMITTED.value}'"


def identity_for(row: dict) -> str:
    """The name a row goes by in output: its content hash, else ``slug-<sha12>``.

    A duplicate alias carries the keeper's hash, so it goes by its slug
    form; the hash names the keeper alone.
    """
    digest = str(row.get("content_sha256") or "").strip()
    if digest and row.get("admission_status") != AdmissionStatus.DUPLICATE.value:
        return digest
    return "slug-" + sha12(str(row.get("slug") or ""))


def exclusion_reason(row: dict) -> str:
    """One sentence per non-admitted status, for ``excluded_builds``."""
    status = row.get("admission_status")
    if status is None:
        return "not admitted: the row was added after admission ran; run corpus admit"
    if status == AdmissionStatus.PLACEHOLDER.value:
        return "placeholder: no analysis rows; quarantined outside the key by design"
    if status == AdmissionStatus.DUPLICATE.value:
        return f"duplicate: same image as {row.get('duplicate_of') or 'another build'}"
    if status == AdmissionStatus.CONTESTED.value:
        return "contested: the stored content hash disagrees with the resolved image"
    if status == AdmissionStatus.UNRESOLVED.value:
        return "unresolved: no resolver produced the image"
    return f"{status}: not admitted"


def excluded_builds(con) -> list[dict]:
    """Every non-admitted row the pack should name, sorted by identity.

    Quarantined placeholders are left out (they are outside the pack by
    design); placeholders handled as ``exclude`` and every duplicate,
    contested, unresolved or never-admitted row are listed. Empty when
    admission has not run.
    """
    if not admission_active(con):
        return []
    cur = con.execute(
        "SELECT slug, content_sha256, admission_status, duplicate_of, admission_handling FROM binary"
        " WHERE admission_status IS NULL OR admission_status != ?",
        (AdmissionStatus.ADMITTED.value,),
    )
    names = [d[0] for d in cur.description]
    out = []
    for raw in cur.fetchall():
        row = dict(zip(names, raw))
        if (
            row["admission_status"] == AdmissionStatus.PLACEHOLDER.value
            and (row.get("admission_handling") or PlaceholderHandling.QUARANTINE.value)
            == PlaceholderHandling.QUARANTINE.value
        ):
            continue
        out.append(
            {
                "identity": identity_for(row),
                "reason": exclusion_reason(row),
                "status": row["admission_status"] or "not_admitted",
            }
        )
    return sorted(out, key=lambda e: (e["identity"], e["status"]))


# --- the verb --------------------------------------------------------------------


def _dump(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _rows(con) -> list[dict]:
    cur = con.execute(
        "SELECT * FROM binary ORDER BY COALESCE(NULLIF(TRIM(content_sha256), ''), ''), repo_path, slug"
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def _func_counts(con) -> dict[str, int]:
    """``repo_path`` -> number of ``func`` rows."""
    return {
        str(r[0]): int(r[1])
        for r in con.execute(
            "SELECT b.repo_path, COUNT(f.id) FROM binary b LEFT JOIN func f ON f.binary_id = b.id GROUP BY b.repo_path"
        )
    }


def _stats(row: dict, func_rows: int) -> RowStats:
    return RowStats(
        func_rows=int(func_rows),
        has_md5=bool(str(row.get("md5") or "").strip()),
        has_format=bool(str(row.get("format") or "").strip()),
        has_analyzer_version=bool(str(row.get("analyzer_version") or "").strip()),
    )


def _receipt_dir(receipts_dir: Path) -> Path:
    return Path(receipts_dir) / VERB


def _input_key(row: dict, stats: RowStats, order: tuple[str, ...]) -> dict:
    return {
        "func_rows": int(stats.func_rows),
        "md5": str(row.get("md5") or "").strip().lower() or None,
        "repo_path_sha256": hashlib.sha256(str(row.get("repo_path") or "").encode("utf-8")).hexdigest(),
        "resolver_order": list(order),
    }


def _load_receipt(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _existing_receipt(receipt_dir: Path, row: dict, key: dict) -> tuple[Path, dict] | None:
    """The row's receipt when it exists, carries *key* and the store agrees on its hash."""
    candidates = []
    digest = str(row.get("content_sha256") or "").strip()
    if digest:
        candidates.append(receipt_dir / f"{digest}.json")
    candidates.append(receipt_dir / f"slug-{sha12(str(row.get('slug') or ''))}.json")
    stored = str(row.get("admission_receipt") or "").strip()
    for path in candidates:
        if not path.is_file():
            continue
        body = _load_receipt(path)
        if body is None or body.get("input_key") != key:
            continue
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        if stored and actual != stored:
            continue
        return path, body
    return None


class _Deadline:
    def __init__(self, seconds: float) -> None:
        self.seconds = float(seconds)
        self.start = time.monotonic()
        self.hit = False

    def remaining(self) -> float:
        return self.seconds - (time.monotonic() - self.start)

    def check(self) -> bool:
        """True when time is up (and remembers it)."""
        if self.remaining() <= 0:
            self.hit = True
        return self.hit


def _write_row(con, *, dry_run: bool, statements: list[tuple[str, tuple]]) -> None:
    """Run *statements* in one ``BEGIN IMMEDIATE`` transaction; nothing on a dry run."""
    if dry_run or not statements:
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        for sql, params in statements:
            con.execute(sql, params)
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def _commit_receipt(con, *, dry_run: bool, receipt_dir: Path, row: dict, body: dict, status: str,
                    duplicate_of: str | None, handling: str | None,
                    extra: list[tuple[str, tuple]] | None = None,
                    db_state: tuple | None = None) -> str:
    """Stamp the row with its final status and receipt hash, commit, then write the receipt.

    *extra* statements (the alias row) join the same transaction. When
    *db_state* (the row's stored status, duplicate_of, receipt hash and
    handling) already equals what would be written and there is nothing
    extra, no transaction is opened: a re-run over unchanged inputs writes
    nothing.
    """
    row["admission_status"] = status
    identity = identity_for(row)
    body = dict(body)
    body["identity"] = identity
    body["status"] = status
    data = _dump(body)
    receipt_sha = hashlib.sha256(data).hexdigest()
    new_state = (status, duplicate_of, receipt_sha, handling)
    statements = list(extra or [])
    if db_state != new_state or statements:
        statements.append(
            (
                "UPDATE binary SET admission_status=?, duplicate_of=?, admission_receipt=?, admission_handling=?"
                " WHERE repo_path=?",
                (status, duplicate_of, receipt_sha, handling, str(row.get("repo_path") or "")),
            )
        )
        _write_row(con, dry_run=dry_run, statements=statements)
    if not dry_run:
        path = receipt_dir / f"{identity}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not (path.is_file() and path.read_bytes() == data):
            path.write_bytes(data)
    return receipt_sha


def admit(
    con: sqlite3.Connection,
    *,
    receipts_dir: Path,
    work_dir: Path | None = None,
    resolver_order: tuple[str, ...] | None = None,
    policy: AdmissionPolicy | None = None,
    duplicates: DuplicateResolution | None = None,
    placeholders: PlaceholderHandling = PlaceholderHandling.QUARANTINE,
    dry_run: bool = False,
    resume: bool = True,
    row_deadline_s: float = 120.0,
    deadline_s: float | None = None,
) -> dict:
    """Run admission over *con*. Returns the summary (also printed by the CLI).

    ``exit_code`` in the summary is 0 when every analyzed row ended
    ``admitted`` or ``duplicate``, 3 when any stays ``unresolved`` or
    ``contested``, 4 when the overall deadline stopped the run. A dry run
    computes the same summary without writing the store, the receipts or
    the raw image directory, so its exit code predicts the real run's.
    """
    from . import raw_images as _ri

    if not has_admission_columns(con):
        raise AdmissionError("binary has no admission columns; the store must be migrated to v3 first")
    order = _ri.resolver_order(resolver_order)
    policy = policy or ADMISSION_POLICIES["default"]
    duplicates = duplicates or DUPLICATE_RESOLUTIONS["keep_most_analyzed"]
    placeholders = PlaceholderHandling(placeholders)
    if deadline_s is None:
        env = os.environ.get(DEADLINE_ENV, "").strip()
        deadline_s = float(env) if env else DEFAULT_DEADLINE_S
    overall = _Deadline(deadline_s)
    receipt_dir = _receipt_dir(Path(receipts_dir))
    root = raw_image_root(work_dir)

    elapsed: dict[str, float] = {}
    counts_class: dict[str, int] = {c.value: 0 for c in AdmissionClass}
    counts_status: dict[str, int] = {s.value: 0 for s in AdmissionStatus}
    counts_status["dropped"] = 0
    resolvers: dict[str, dict] = {n: {"hits": 0, "misses": {}} for n in order}
    unresolved: list[dict] = []
    contested: list[dict] = []
    groups_out: list[dict] = []
    resumed = 0
    rows_seen = 0
    stopped_at: str | None = None

    def phase_done(name: str, started: float) -> None:
        elapsed[name] = round(time.monotonic() - started, 3)

    # 1. classify --------------------------------------------------------------
    t0 = time.monotonic()
    func_counts = _func_counts(con)
    rows = _rows(con)
    work: list[dict] = []
    for row in rows:
        stats = _stats(row, func_counts.get(str(row.get("repo_path") or ""), 0))
        cls = policy.classify(row, stats)
        counts_class[cls.value] += 1
        work.append(
            {
                "row": row,
                "stats": stats,
                "class": cls,
                "key": _input_key(row, stats, order),
                "db_state": (
                    row.get("admission_status"),
                    row.get("duplicate_of"),
                    row.get("admission_receipt"),
                    row.get("admission_handling"),
                ),
            }
        )
    phase_done("classify", t0)

    # 2. placeholders ---------------------------------------------------------
    t0 = time.monotonic()
    for item in work:
        if item["class"] is not AdmissionClass.PLACEHOLDER:
            continue
        if overall.check():
            stopped_at = stopped_at or "placeholders"
            break
        rows_seen += 1
        row, stats = item["row"], item["stats"]
        body = {
            "class": AdmissionClass.PLACEHOLDER.value,
            "handling": placeholders.value,
            "input_key": item["key"],
            "policy": policy.name,
            "stats": stats.as_dict(),
            "stored_content_sha256": str(row.get("content_sha256") or "").strip() or None,
            "verb": VERB,
        }
        if placeholders is PlaceholderHandling.DROP:
            if not dry_run:
                from .store import remove_binary

                remove_binary(con, slug=str(row["slug"]))
                path = receipt_dir / f"{identity_for(row)}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                body["identity"] = identity_for(row)
                body["status"] = "dropped"
                path.write_bytes(_dump(body))
            counts_status["dropped"] += 1
            item["status"] = "dropped"
            continue
        existing = _existing_receipt(receipt_dir, row, item["key"]) if resume else None
        if existing is not None and existing[1].get("handling") == placeholders.value:
            resumed += 1
        _commit_receipt(
            con,
            dry_run=dry_run,
            receipt_dir=receipt_dir,
            row=row,
            body=body,
            status=AdmissionStatus.PLACEHOLDER.value,
            duplicate_of=None,
            handling=placeholders.value,
            db_state=item["db_state"],
        )
        counts_status[AdmissionStatus.PLACEHOLDER.value] += 1
        item["status"] = AdmissionStatus.PLACEHOLDER.value
    phase_done("placeholders", t0)

    # 3. raw images + hash -----------------------------------------------------
    t0 = time.monotonic()
    analyzed = [item for item in work if item["class"] is AdmissionClass.ANALYZED]
    try:
        for item in analyzed:
            if stopped_at or overall.check():
                stopped_at = stopped_at or "resolve"
                break
            rows_seen += 1
            row = item["row"]
            stored = str(row.get("content_sha256") or "").strip().lower() or None
            existing = _existing_receipt(receipt_dir, row, item["key"]) if resume else None
            if existing is not None and existing[1].get("status") == AdmissionStatus.UNRESOLVED.value:
                # A recorded miss is not done work: try again.
                existing = None
            if existing is not None:
                resumed += 1
                item["resolution"] = existing[1].get("resolution")
                item["resumed"] = True
                if existing[1].get("contested"):
                    item["contested"] = existing[1]["contested"]
                continue
            ctx = row_context(con, row)
            budget = min(float(row_deadline_s), max(0.0, overall.remaining()))
            image: RawImage | None = resolve_raw_image(
                ctx,
                order=order,
                work_dir=work_dir,
                deadline_s=budget,
                materialize=not dry_run,
                expected_sha256=stored,
            )
            if image is None:
                misses = last_misses()
                for name, reason in misses.items():
                    bucket = resolvers.setdefault(name, {"hits": 0, "misses": {}})["misses"]
                    bucket[reason] = bucket.get(reason, 0) + 1
                reasons = {k: misses[k] for k in sorted(misses)}
                if budget <= 0 or all(v == "deadline" for v in misses.values()):
                    reasons = {"deadline": "unresolved:deadline", **reasons}
                item["resolution"] = {"hit": None, "misses": reasons}
                continue
            resolvers.setdefault(image.resolver, {"hits": 0, "misses": {}})["hits"] += 1
            for name, reason in image.provenance.get("misses", {}).items():
                bucket = resolvers.setdefault(name, {"hits": 0, "misses": {}})["misses"]
                bucket[reason] = bucket.get(reason, 0) + 1
            item["resolution"] = {"hit": image.as_record(), "misses": dict(image.provenance.get("misses", {}))}
            if stored is None:
                _write_row(
                    con,
                    dry_run=dry_run,
                    statements=[
                        (
                            "UPDATE binary SET content_sha256=? WHERE repo_path=?"
                            " AND (content_sha256 IS NULL OR TRIM(content_sha256) = '')",
                            (image.sha256, str(row.get("repo_path") or "")),
                        )
                    ],
                )
                row["content_sha256"] = image.sha256
            elif stored != image.sha256:
                # R3: a stored hash is never overwritten; the disagreement is the record.
                item["contested"] = {"resolved": image.sha256, "stored": stored}
            else:
                item["resolution"]["verified"] = True
    finally:
        closed = close_resolvers()
    phase_done("resolve", t0)

    # 4. duplicates ------------------------------------------------------------
    t0 = time.monotonic()
    by_hash: dict[str, list[dict]] = {}
    by_md5: dict[str, list[dict]] = {}
    for item in analyzed:
        if stopped_at and "resolution" not in item:
            continue
        if item.get("contested"):
            continue
        row = item["row"]
        digest = str(row.get("content_sha256") or "").strip().lower()
        md5 = str(row.get("md5") or "").strip().lower()
        if digest:
            by_hash.setdefault(digest, []).append(item)
        elif md5:
            by_md5.setdefault(md5, []).append(item)
    for key_kind, groups in (("content_sha256", by_hash), ("md5", by_md5)):
        for key, members in sorted(groups.items()):
            if len(members) < 2:
                continue
            group = [
                {
                    "func_rows": m["stats"].func_rows,
                    "repo_path": m["row"]["repo_path"],
                    "slug": m["row"]["slug"],
                    "_item": m,
                }
                for m in members
            ]
            keeper, aliases = duplicates.resolve(group)
            keeper_item = keeper["_item"]
            keeper_row = keeper_item["row"]
            keeper_row["admission_status"] = None  # finalized in the admit phase
            keeper_digest = str(keeper_row.get("content_sha256") or "").strip().lower()
            duplicate_of = keeper_digest or ("slug:" + sha12(str(keeper_row.get("slug") or "")))
            alias_ids = []
            for alias in aliases:
                alias_item = alias["_item"]
                alias_item["row"]["admission_status"] = AdmissionStatus.DUPLICATE.value
                alias_item["_keeper_slug"] = str(keeper_row.get("slug") or "")
                alias_item["duplicate"] = {
                    "alias_row_written": bool(keeper_digest),
                    "key": key_kind,
                    "of": duplicate_of,
                    "reason": None if keeper_digest else "no_content_sha256",
                    "resolution": duplicates.name,
                }
                alias_ids.append(identity_for(alias_item["row"]))
            keeper_item["duplicates"] = {
                "aliases": sorted(alias_ids),
                "key": key_kind,
                "resolution": duplicates.name,
            }
            groups_out.append(
                {"aliases": sorted(alias_ids), "keeper": identity_for(keeper_row), "key": key_kind}
            )
    phase_done("duplicates", t0)

    # 5. admit ---------------------------------------------------------------
    t0 = time.monotonic()
    for item in analyzed:
        if stopped_at and "resolution" not in item:
            continue
        # Stamping a resolved row costs milliseconds; this phase finishes
        # for every row the resolve phase reached, deadline or not.
        row, stats = item["row"], item["stats"]
        digest = str(row.get("content_sha256") or "").strip().lower() or None
        body = {
            "class": AdmissionClass.ANALYZED.value,
            "input_key": item["key"],
            "policy": policy.name,
            "resolution": item.get("resolution"),
            "stats": stats.as_dict(),
            "stored_content_sha256": digest,
            "verb": VERB,
        }
        duplicate_of: str | None = None
        extra: list[tuple[str, tuple]] = []
        if item.get("contested"):
            status = AdmissionStatus.CONTESTED.value
            body["contested"] = item["contested"]
        elif item.get("duplicate"):
            status = AdmissionStatus.DUPLICATE.value
            body["duplicate"] = item["duplicate"]
            duplicate_of = item["duplicate"]["of"]
            if item["duplicate"]["alias_row_written"] and digest:
                extra = [
                    (
                        "CREATE TABLE IF NOT EXISTS binary_source_alias"
                        " (source_path TEXT PRIMARY KEY, binary_slug TEXT NOT NULL, sha256 TEXT NOT NULL)",
                        (),
                    ),
                    (
                        "INSERT INTO binary_source_alias(source_path, binary_slug, sha256) VALUES(?, ?, ?)"
                        " ON CONFLICT(source_path) DO UPDATE SET binary_slug=excluded.binary_slug,"
                        " sha256=excluded.sha256",
                        (str(row["repo_path"]), item["_keeper_slug"], digest),
                    ),
                ]
        elif digest:
            status = AdmissionStatus.ADMITTED.value
            if item.get("duplicates"):
                body["duplicates"] = item["duplicates"]
        else:
            status = AdmissionStatus.UNRESOLVED.value
            reasons = (item.get("resolution") or {}).get("misses") or {"none": "no_resolver_ran"}
            body["unresolved_reasons"] = reasons
        row["admission_status"] = status
        if status == AdmissionStatus.CONTESTED.value:
            contested.append({"identity": identity_for(row), **item["contested"]})
        elif status == AdmissionStatus.UNRESOLVED.value:
            unresolved.append({"identity": identity_for(row), "reasons": body["unresolved_reasons"]})
        _commit_receipt(
            con,
            dry_run=dry_run,
            receipt_dir=receipt_dir,
            row=row,
            body=body,
            status=status,
            duplicate_of=duplicate_of,
            handling=None,
            extra=extra,
            db_state=item["db_state"],
        )
        counts_status[status] += 1
        item["status"] = status
    phase_done("admit", t0)
    elapsed["total"] = round(time.monotonic() - overall.start, 3)

    incomplete = counts_status[AdmissionStatus.UNRESOLVED.value] + counts_status[AdmissionStatus.CONTESTED.value]
    if stopped_at:
        status_word, exit_code = "deadline", 4
    elif incomplete:
        status_word, exit_code = "incomplete", 3
    else:
        status_word, exit_code = "ok", 0
    summary = {
        "classes": counts_class,
        "contested": sorted(contested, key=lambda e: e["identity"]),
        "deadline": {
            "overall_s": float(deadline_s),
            "row_s": float(row_deadline_s),
            "hit": bool(stopped_at),
            "stopped_in_phase": stopped_at,
        },
        "dry_run": bool(dry_run),
        "duplicate_groups": sorted(groups_out, key=lambda g: g["keeper"]),
        "duplicates": duplicates.name,
        "elapsed_s": elapsed,
        "exit_code": exit_code,
        "placeholders": placeholders.value,
        "policy": policy.name,
        "projects_closed": closed,
        "raw_image_root": str(root),
        "raw_image_root_exists": root.is_dir(),
        "receipts_dir": str(receipt_dir),
        "resolver_order": list(order),
        "resolvers": {
            n: {"hits": v["hits"], "misses": {k: v["misses"][k] for k in sorted(v["misses"])}}
            for n, v in sorted(resolvers.items())
        },
        "resumed": resumed,
        "rows": len(rows),
        "rows_seen": rows_seen,
        "status": status_word,
        "statuses": counts_status,
        "unresolved": sorted(unresolved, key=lambda e: e["identity"]),
        "verb": VERB,
        "work_dir": str(work_dir) if work_dir is not None else None,
    }
    return summary


__all__ = [
    "ADMISSION_POLICIES",
    "AdmissionClass",
    "AdmissionError",
    "AdmissionPolicy",
    "AdmissionStatus",
    "DUPLICATE_RESOLUTIONS",
    "DefaultAdmissionPolicy",
    "DuplicateResolution",
    "KeepMostAnalyzed",
    "ManifestPolicy",
    "MergeEvidence",
    "PlaceholderHandling",
    "RawImageError",
    "RowStats",
    "StrictPolicy",
    "admit",
    "admission_active",
    "admission_scope",
    "admitted_predicate",
    "excluded_builds",
    "exclusion_reason",
    "has_admission_columns",
    "identity_for",
]
