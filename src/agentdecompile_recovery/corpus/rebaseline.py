"""Re-baseline a store after its package basis moved (U25).

The rule: never silently mix bases in one store; a package-constant change
is a supersession, recorded, then re-stamped.

Every ``binary`` row carries the ``basis_hash`` the package computed when
the row was stamped. When a pinned constant moves (``ALGORITHM_VERSION``,
a threshold table, a seed, a ``PENDING_FIELDS`` removal) the hash the
package computes today differs from the stored one and :func:`basis`
refuses with "re-baseline". Backfill fills NULLs only, so nothing else can
re-stamp. This verb is the one path that may: it names the old and the new
basis, writes one ``basis_supersession`` row and re-stamps every stale row
in one transaction, then writes the receipt. A second run finds no drift
and returns ``unchanged``.

What the verb refuses (``BasisError``, exit 2 through the CLI):

* a store with no ``binary`` row;
* a row without ``analyzer_version`` or ``basis_hash`` -- that is
  backfill's job (``corpus backfill --pass analyzer_identity``);
* more than one ``analyzer_version`` across rows;
* more than one *stale* ``basis_hash`` across rows. Two old bases in one
  store cannot be merged into one supersession row without inventing an
  ``old_basis_hash`` for half of them.

Refusal text names builds by ``sha256(slug)[:12]`` and counts only.

Receipts: ``<receipts>/rebaseline/<new_basis_hash[:16]>.json`` holds the
supersession; ``<new_basis_hash[:16]>.diff.json`` holds the site diff
against a prior pack when one is given. Neither file carries a clock
value; ``basis_supersession.recorded_at`` is the only clock-derived value
this verb writes and it lives in the store, never in a receipt. The
receipt's ``sha256`` is stored in the supersession row, and the row commits
before the file is written, so a receipt on disk always implies a
committed supersession.

Extension points, each with one working implementation and named slots:

* :class:`SupersessionPolicy` -- what a supersession does to the rows.
  :class:`RestampOnly` works; :class:`RecomputeDivergence` is the U14 slot.
* :class:`PackDiffer` -- how two packs are compared.
  :class:`JsonSitesDiffer` works; :class:`BinaryPackDiffer` is a slot.
* :class:`OldBasisResolver` -- how the old package basis is reconstructed.
  :class:`LedgerResolver` works; :class:`PackResolver` is a slot.
* :data:`HOOKS` -- a registry of phase hooks (``before_restamp``,
  ``after_restamp``, ``after_export``), each a no-op by default.

Every phase runs under a deadline (``deadline_s``; default from
``AGENT_DECOMPILE_REBASELINE_DEADLINE_S``, then 600). A deadline exceeded
between phases stops the verb with ``status: "deadline"`` (exit 4). The
re-stamp is one transaction, so a deadline can never leave a partial
re-stamp; it can only skip the export and the diff.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .determinism_basis import (
    ALGORITHM_VERSION,
    ALGORITHM_VERSION_HISTORY,
    BasisError,
    basis_hash_of,
    package_basis,
    package_basis_with_algorithm,
    stored_basis_rows,
)
from .migrations import SUPERSESSION_TABLE, ledger_rows

#: Receipt format tag, bumped when the receipt shape changes.
RECEIPT_FORMAT = "agentdecompile.rebaseline-receipt/v1"
#: Diff receipt format tag.
DIFF_FORMAT = "agentdecompile.rebaseline-diff/v1"
#: Subdirectory of the receipts dir that this verb owns.
RECEIPT_DIRNAME = "rebaseline"
#: Environment variable that sets the default deadline (seconds).
DEADLINE_ENV = "AGENT_DECOMPILE_REBASELINE_DEADLINE_S"
#: Deadline when neither the argument nor the environment sets one.
DEFAULT_DEADLINE_S = 600.0
#: Longest key list a diff receipt carries; longer lists are cut and flagged.
DIFF_KEY_CAP = 500
#: Hashed build names a refusal line carries before "+N more".
REFUSAL_NAME_CAP = 16
#: Rows between deadline checks inside the row loops.
LOOP_CHECK_EVERY = 256
#: Phases in order. ``deadline`` results name the phase that did not start.
PHASES = ("read", "resolve", "restamp", "export", "diff")
#: Value written to ``binary.basis_source`` by a supersession, with the new
#: hash prefix appended so a row names the receipt that re-stamped it.
BASIS_SOURCE_PREFIX = "rebaseline:"

_BRACKETED = re.compile(r"\[[^\]]*\]")


def hashed_slug(slug: object) -> str:
    """A build name for a message or receipt: ``sha256(slug)[:12]``, never the slug."""
    return hashlib.sha256(str(slug).encode("utf-8")).hexdigest()[:12]


def _names(slugs: list[str]) -> str:
    shown = [hashed_slug(s) for s in sorted(slugs)[:REFUSAL_NAME_CAP]]
    more = len(slugs) - len(shown)
    return ", ".join(shown) + (f", +{more} more" if more > 0 else "")


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=2) + "\n"


def _compact(obj) -> str:
    """The serialization ``basis_hash_for`` hashes: ``sha256(_compact(pb)) == basis_hash``."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _recorded_at() -> str:
    """ISO-8601 UTC. ``SOURCE_DATE_EPOCH`` wins when set, so attestation runs
    write a reproducible row."""
    raw = str(os.environ.get("SOURCE_DATE_EPOCH", "")).strip()
    stamp = int(raw) if raw.isdigit() else time.time()
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- deadline ---------------------------------------------------------------


class DeadlineExceeded(Exception):
    """Raised between phases when the budget is spent. Carries the phase that did not start."""

    def __init__(self, phase: str):
        super().__init__(f"rebaseline: deadline exceeded before phase {phase}")
        self.phase = phase


@dataclass(frozen=True)
class Deadline:
    budget_s: float
    started: float

    @classmethod
    def start(cls, seconds: float | None) -> "Deadline":
        if seconds is None:
            raw = str(os.environ.get(DEADLINE_ENV, "")).strip()
            try:
                seconds = float(raw) if raw else DEFAULT_DEADLINE_S
            except ValueError:
                seconds = DEFAULT_DEADLINE_S
        if seconds <= 0:
            raise ValueError(f"deadline_s must be > 0, got {seconds!r}")
        return cls(budget_s=float(seconds), started=time.monotonic())

    def exceeded(self) -> bool:
        return time.monotonic() - self.started > self.budget_s

    def check(self, phase: str) -> None:
        """Raise :class:`DeadlineExceeded` naming *phase* when the budget is spent."""
        if self.exceeded():
            raise DeadlineExceeded(phase)


# --- extension points -------------------------------------------------------


class SupersessionPolicy(Protocol):
    """What a supersession does to the store's rows, inside the verb's transaction.

    ``on_supersede`` runs after ``BEGIN IMMEDIATE`` and before the
    ``basis_supersession`` row is inserted. It returns a JSON-ready dict that
    the verb records under ``receipt["policy"]``; the result must be a pure
    function of the store's rows and *receipt*, never of a clock. Raising
    rolls the transaction back and nothing is written.
    """

    name: str

    def on_supersede(self, con: sqlite3.Connection, receipt: dict) -> dict: ...


class RestampOnly:
    """Working policy: set every stale row's ``basis_hash`` to the new hash.

    ``basis_source`` becomes ``rebaseline:<new_basis_hash[:16]>`` so the row
    names the receipt that re-stamped it. Rows already carrying the new hash
    are left alone; the returned ``restamped`` count is the UPDATE's rowcount
    and must equal ``receipt["restamped"]`` or the verb rolls back.
    """

    name = "restamp_only"

    def on_supersede(self, con: sqlite3.Connection, receipt: dict) -> dict:
        cur = con.execute(
            "UPDATE binary SET basis_hash = ?, basis_source = ? WHERE basis_hash = ?",
            (receipt["new_basis_hash"], receipt["basis_source"], receipt["old_basis_hash"]),
        )
        return {"restamped": int(cur.rowcount)}


class RecomputeDivergence:
    """Slot (U14): re-stamp, then re-evaluate divergence classifications.

    Contract: run :class:`RestampOnly`, then re-evaluate every divergence
    classification against ``receipt["new_package_basis"]["threshold_params"]
    ["divergence"]`` and return ``{"restamped": n, "divergence_delta":
    {"reclassified": n, "by_transition": {"<old>-><new>": n}}}``. The delta
    is reported, never written over the stored classifications. Lands when
    U14 removes ``threshold_params.divergence`` from ``PENDING_FIELDS``.
    """

    name = "recompute_divergence"

    def on_supersede(self, con: sqlite3.Connection, receipt: dict) -> dict:
        raise NotImplementedError("U14: RecomputeDivergence.on_supersede")


#: Registered policies by name. Slots raise ``NotImplementedError``.
POLICIES: dict[str, type] = {
    RestampOnly.name: RestampOnly,
    RecomputeDivergence.name: RecomputeDivergence,
}


class PackDiffer(Protocol):
    """Compare a prior pack with the pack exported under the new basis.

    ``diff`` returns a JSON-ready dict with ``counts`` (``added``,
    ``removed``, ``changed``, ``unchanged``), the sorted key lists capped at
    :data:`DIFF_KEY_CAP`, and ``truncated``. It reads both files and writes
    nothing: the prior pack stays loadable.
    """

    name: str

    def diff(self, prior: Path, new: Path) -> dict: ...


class JsonSitesDiffer:
    """Working differ: compare the two packs' ``sites`` maps by site key.

    Site keys are the pack's stable keys (name or canon key, suffixed only
    on collision). The ``basis`` block is not compared: the two packs differ
    there by construction. A site is ``changed`` when its object differs
    anywhere; ``added`` and ``removed`` are keys present on one side only.
    """

    name = "json_sites"

    @staticmethod
    def _sites(path: Path) -> dict:
        pack = json.loads(Path(path).read_text(encoding="utf-8"))
        sites = pack.get("sites") if isinstance(pack, dict) else None
        if not isinstance(sites, dict):
            raise ValueError(f"pack has no sites map: {path}")
        return sites

    def diff(self, prior: Path, new: Path) -> dict:
        before = self._sites(prior)
        after = self._sites(new)
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        common = sorted(set(before) & set(after))
        changed = [k for k in common if _compact(before[k]) != _compact(after[k])]
        out = {
            "format": DIFF_FORMAT,
            "differ": self.name,
            "counts": {
                "added": len(added),
                "removed": len(removed),
                "changed": len(changed),
                "unchanged": len(common) - len(changed),
            },
            "truncated": False,
        }
        for key, keys in (("added_keys", added), ("removed_keys", removed), ("changed_keys", changed)):
            out[key] = keys[:DIFF_KEY_CAP]
            if len(keys) > DIFF_KEY_CAP:
                out["truncated"] = True
        return out


class BinaryPackDiffer:
    """Slot: diff two packs in a non-JSON container.

    Contract: decode both containers to their site maps, then return the
    same shape :class:`JsonSitesDiffer` returns. Lands with the first
    non-JSON pack format (U23 ``--format v2``).
    """

    name = "binary"

    def diff(self, prior: Path, new: Path) -> dict:
        raise NotImplementedError("U23: BinaryPackDiffer.diff")


#: Registered differs by name. Slots raise ``NotImplementedError``.
DIFFERS: dict[str, type] = {
    JsonSitesDiffer.name: JsonSitesDiffer,
    BinaryPackDiffer.name: BinaryPackDiffer,
}


@dataclass(frozen=True)
class ResolvedBasis:
    """The old basis as far as it could be reconstructed.

    ``algorithm_version`` is ``"unknown"`` and ``package_basis`` is None when
    the old hash matches nothing the package can rebuild. ``source`` names
    what produced the answer: ``supersession_ledger``, ``history``,
    ``migration_ledger`` (hash confirmed, object not recoverable) or ``none``.
    """

    algorithm_version: str
    package_basis: dict | None
    source: str


class OldBasisResolver(Protocol):
    """Reconstruct the package basis behind a stored (now stale) hash."""

    name: str

    def resolve(self, con: sqlite3.Connection, old_hash: str, analyzer_version: str) -> ResolvedBasis: ...


class LedgerResolver:
    """Working resolver: the store's ledgers first, then the version history.

    1. A ``basis_supersession`` row whose ``new_basis_hash`` is *old_hash*
       recorded the object verbatim when it became current.
    2. Otherwise rebuild the package basis with each prior value of
       :data:`ALGORITHM_VERSION_HISTORY` substituted (newest first) and take
       the first whose hash equals *old_hash*. A hit names the old
       algorithm version and yields its object; a miss means some other
       constant moved too.
    3. Otherwise ``schema_migration.basis_hash`` may still confirm the hash
       was the basis at a migration, but that ledger stores no object.
    """

    name = "ledger"

    def resolve(self, con: sqlite3.Connection, old_hash: str, analyzer_version: str) -> ResolvedBasis:
        row = _supersession_by_new_hash(con, old_hash)
        if row is not None:
            return ResolvedBasis(
                algorithm_version=str(row["new_algorithm_version"]),
                package_basis=json.loads(row["new_package_basis_json"]),
                source="supersession_ledger",
            )
        for version in reversed(ALGORITHM_VERSION_HISTORY):
            try:
                candidate = package_basis_with_algorithm(analyzer_version, version)
            except BasisError:
                continue
            if basis_hash_of(candidate) == old_hash:
                return ResolvedBasis(algorithm_version=version, package_basis=candidate, source="history")
        if any(r.get("basis_hash") == old_hash for r in ledger_rows(con)):
            return ResolvedBasis(algorithm_version="unknown", package_basis=None, source="migration_ledger")
        return ResolvedBasis(algorithm_version="unknown", package_basis=None, source="none")


class PackResolver:
    """Slot: read the old basis from a prior pack's ``basis`` block.

    Contract: load the pack, drop ``BASIS_HASH_EXCLUDED`` from its ``basis``
    block, hash the rest with :func:`basis_hash_of`; when it equals
    *old_hash* return that object and its ``algorithm_version`` with source
    ``prior_pack``, else ``unknown``/None/``none``. Takes the pack path at
    construction.
    """

    name = "pack"

    def __init__(self, pack: Path | None = None):
        self.pack = pack

    def resolve(self, con: sqlite3.Connection, old_hash: str, analyzer_version: str) -> ResolvedBasis:
        raise NotImplementedError("PackResolver.resolve")


#: Registered resolvers by name. Slots raise ``NotImplementedError``.
RESOLVERS: dict[str, type] = {
    LedgerResolver.name: LedgerResolver,
    PackResolver.name: PackResolver,
}

#: A phase hook: observes the connection and a copy of the receipt. The
#: return value is ignored; mutating the copy changes nothing.
RebaselineHook = Callable[[sqlite3.Connection, dict], None]


def _noop_hook(con: sqlite3.Connection, receipt: dict) -> None:
    return None


#: Hook phases in the order they fire. ``before_restamp`` fires inside the
#: transaction after ``BEGIN IMMEDIATE``; ``after_restamp`` after the commit
#: and the receipt write; ``after_export`` after the pack and diff files.
HOOK_PHASES = ("before_restamp", "after_restamp", "after_export")

#: Registry of phase hooks. Replace a value to observe that phase.
HOOKS: dict[str, RebaselineHook] = {phase: _noop_hook for phase in HOOK_PHASES}


def _fire(phase: str, con: sqlite3.Connection, receipt: dict) -> None:
    HOOKS.get(phase, _noop_hook)(con, json.loads(_dumps(receipt)))


# --- store reads ------------------------------------------------------------


def _supersession_by_new_hash(con: sqlite3.Connection, new_hash: str) -> dict | None:
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (SUPERSESSION_TABLE,)
    ).fetchone()
    if not exists:
        return None
    # Every row with one new hash carries the same object (the hash covers
    # it), so the tie-break only has to be stable: old hash, never rowid.
    cur = con.execute(
        f"SELECT new_algorithm_version, new_package_basis_json FROM {SUPERSESSION_TABLE}"
        " WHERE new_basis_hash = ? ORDER BY old_basis_hash LIMIT 1",
        (new_hash,),
    )
    names = [d[0] for d in cur.description]
    row = cur.fetchone()
    return None if row is None else dict(zip(names, row))


def _identity(row: dict) -> str:
    digest = str(row.get("content_sha256") or "").strip()
    return digest if digest else "slug:" + hashed_slug(row.get("slug"))


def _read_rows(con: sqlite3.Connection, deadline: Deadline) -> list[dict]:
    rows = stored_basis_rows(con)
    if not rows:
        raise BasisError("rebaseline: store has no binary rows")
    absent = [r["slug"] for r in rows if not r.get("analyzer_version") or not r.get("basis_hash")]
    if absent:
        raise BasisError(
            f"rebaseline: analyzer identity is absent for {len(absent)} build(s) [{_names(absent)}]; "
            "run `corpus backfill --pass analyzer_identity` on the store first"
        )
    versions: dict[str, int] = {}
    for i, r in enumerate(rows):
        if i % LOOP_CHECK_EVERY == 0:
            deadline.check("read")
        versions[str(r["analyzer_version"])] = versions.get(str(r["analyzer_version"]), 0) + 1
    if len(versions) > 1:
        groups = "; ".join(f"{v}: {n} row(s)" for v, n in sorted(versions.items()))
        raise BasisError(
            f"rebaseline: mixed analyzer.version across binary rows ({len(versions)} versions: {groups}); "
            "one store carries one analyzer version"
        )
    return rows


def _hash_groups(rows: list[dict]) -> dict[str, int]:
    groups: dict[str, int] = {}
    for r in rows:
        groups[str(r["basis_hash"])] = groups.get(str(r["basis_hash"]), 0) + 1
    return groups


def _existing_receipt_conflict(path: Path, old: str, new: str) -> None:
    """Refuse to write over a receipt for a different supersession.

    The file name is the new hash prefix, so two stores sharing one receipts
    dir could collide. A file for the same (old, new) pair is the same
    supersession replayed (a store restored from a copy) and is rewritten
    with identical bytes.
    """
    if not path.is_file():
        return
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = None
    if not isinstance(existing, dict):
        raise BasisError(f"rebaseline: receipt exists and is not readable: {path}")
    if (existing.get("old_basis_hash"), existing.get("new_basis_hash")) != (old, new):
        raise BasisError(
            f"rebaseline: receipt exists for a different supersession at {path}; "
            "use one receipts dir per store"
        )


# --- the verb ---------------------------------------------------------------


def _export_refusal(exc: BaseException) -> dict:
    """A JSON-ready description of an export refusal; names builds by hash only."""
    from .logical import BACKFILL_HINT, ContentHashError

    if isinstance(exc, ContentHashError):
        return {
            "status": "refused",
            "error": "ContentHashError",
            "kind": exc.kind,
            "count": len(exc.slugs),
            "builds": [hashed_slug(s) for s in sorted(exc.slugs)][:REFUSAL_NAME_CAP],
            "hint": BACKFILL_HINT,
        }
    return {
        "status": "refused",
        "error": type(exc).__name__,
        # Bracketed lists in basis messages name builds; drop them.
        "detail": _BRACKETED.sub("[...]", str(exc)),
    }


def _rows_with_hash(con: sqlite3.Connection, basis_hash_value: str) -> list[dict]:
    """Every ``binary`` row carrying *basis_hash_value*, in canonical row order.

    Unscoped on purpose (see the caller): the UPDATE the policy issues is
    unscoped too, and the receipt must list exactly the rows it touches.
    """
    cur = con.execute(
        "SELECT slug, content_sha256, analyzer_version, basis_hash, basis_source FROM binary"
        " WHERE basis_hash = ? ORDER BY content_sha256, repo_path, slug",
        (basis_hash_value,),
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def rebaseline(
    con: sqlite3.Connection,
    *,
    receipts_dir: Path,
    reason: str | None = None,
    export_out: Path | None = None,
    prior_pack: Path | None = None,
    dry_run: bool = False,
    policy: SupersessionPolicy | None = None,
    differ: PackDiffer | None = None,
    resolver: OldBasisResolver | None = None,
    deadline_s: float | None = None,
) -> dict:
    """Record the package-basis change as a supersession and re-stamp the rows.

    Returns the receipt plus ``status``: ``superseded``, ``unchanged``,
    ``dry_run`` or ``deadline``. Run-only facts (receipt path and hash,
    ``recorded_at``, export and diff results) sit under ``run``; they are not
    part of the receipt file. Refusals raise :class:`BasisError`.
    """
    deadline = Deadline.start(deadline_s)
    policy = RestampOnly() if policy is None else policy
    differ = JsonSitesDiffer() if differ is None else differ
    resolver = LedgerResolver() if resolver is None else resolver
    receipts_dir = Path(receipts_dir)
    run: dict = {"deadline_s": deadline.budget_s, "policy": policy.name, "resolver": resolver.name}

    # Phase: read. Never basis(con): it refuses on exactly the drift this
    # verb repairs. Rows are read raw and grouped by stored hash.
    try:
        deadline.check("read")
        rows = _read_rows(con, deadline)
    except DeadlineExceeded as exc:
        return {"status": "deadline", "phase": exc.phase, "run": run}
    analyzer_version = str(rows[0]["analyzer_version"])
    new_package_basis = package_basis(analyzer_version)
    current = basis_hash_of(new_package_basis)
    groups = _hash_groups(rows)
    stale = sorted(h for h in groups if h != current)
    if not stale:
        return {
            "status": "unchanged",
            "basis_hash": current,
            "algorithm_version": ALGORITHM_VERSION,
            "analyzer_version": analyzer_version,
            "rows": len(rows),
            "run": run,
        }
    if len(stale) > 1:
        counts = ", ".join(f"{groups[h]} row(s) under {h[:16]}" for h in stale)
        raise BasisError(
            f"rebaseline: mixed basis_hash across binary rows: {len(stale)} stale groups ({counts}); "
            "mixed bases are never silently merged"
        )
    (old,) = stale
    # Drift is judged on the rows the basis covers (A4 admission scope); the
    # re-stamp reaches every row of the store that carries the old hash,
    # admitted or not, so an unadmitted analyzed row never keeps a stale
    # basis that would refuse the moment it is admitted.
    stale_rows = _rows_with_hash(con, old)

    # Phase: resolve the old basis and build the receipt (no clock in it).
    try:
        deadline.check("resolve")
    except DeadlineExceeded as exc:
        return {"status": "deadline", "phase": exc.phase, "run": run}
    resolved = resolver.resolve(con, old, analyzer_version)
    binaries = sorted(
        ({"identity": _identity(r), "old_basis_hash": old, "new_basis_hash": current} for r in stale_rows),
        key=lambda b: b["identity"],
    )
    receipt: dict = {
        "format": RECEIPT_FORMAT,
        "analyzer_version": analyzer_version,
        "old_basis_hash": old,
        "new_basis_hash": current,
        "old_algorithm_version": resolved.algorithm_version,
        "new_algorithm_version": ALGORITHM_VERSION,
        "old_package_basis": resolved.package_basis,
        "old_basis_resolution": resolved.source,
        "new_package_basis": new_package_basis,
        "reason": reason,
        "restamped": len(stale_rows),
        "already_current": len(rows) - len(stale_rows),
        "basis_source": BASIS_SOURCE_PREFIX + current[:16],
        "binaries": binaries,
        "policy": {"name": policy.name},
    }
    receipt_path = receipts_dir / RECEIPT_DIRNAME / f"{current[:16]}.json"
    run["receipt_path"] = str(receipt_path)
    if dry_run:
        return {"status": "dry_run", **receipt, "run": run}
    _existing_receipt_conflict(receipt_path, old, current)

    # Phase: restamp. One BEGIN IMMEDIATE transaction: the policy's writes,
    # the supersession row, then COMMIT; the receipt file comes after.
    try:
        deadline.check("restamp")
    except DeadlineExceeded as exc:
        return {"status": "deadline", "phase": exc.phase, **receipt, "run": run}
    recorded_at = _recorded_at()
    con.execute("BEGIN IMMEDIATE")
    try:
        # The lock is held now; the rows must still be what the read phase saw.
        if _hash_groups(stored_basis_rows(con)) != groups:
            raise BasisError("rebaseline: binary rows changed under the verb; run it again")
        _fire("before_restamp", con, receipt)
        result = policy.on_supersede(con, receipt)
        if int(result.get("restamped", -1)) != len(stale_rows):
            raise BasisError(
                f"rebaseline: policy {policy.name} re-stamped {result.get('restamped')} row(s), "
                f"expected {len(stale_rows)}"
            )
        receipt["policy"] = {"name": policy.name, **result}
        receipt_bytes = _dumps(receipt).encode("utf-8")
        receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        try:
            con.execute(
                f"INSERT INTO {SUPERSESSION_TABLE}(old_basis_hash, new_basis_hash, old_algorithm_version,"
                " new_algorithm_version, old_package_basis_json, new_package_basis_json, analyzer_version,"
                " reason, binaries_restamped, receipt_sha256, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    old,
                    current,
                    resolved.algorithm_version,
                    ALGORITHM_VERSION,
                    None if resolved.package_basis is None else _compact(resolved.package_basis),
                    _compact(new_package_basis),
                    analyzer_version,
                    reason,
                    len(stale_rows),
                    receipt_sha256,
                    recorded_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            # UNIQUE(old, new): this supersession is already on the ledger,
            # yet rows still carry the old hash. Something re-stamped them
            # backwards outside this verb; that is not silently repeated.
            raise BasisError(
                f"rebaseline: supersession {old[:16]} -> {current[:16]} is already recorded "
                f"but {len(stale_rows)} row(s) still carry the old hash"
            ) from exc
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(receipt_bytes)
    run["restamp"] = "committed"
    run["receipt_sha256"] = receipt_sha256
    run["recorded_at"] = recorded_at
    _fire("after_restamp", con, receipt)
    out = {"status": "superseded", **receipt, "run": run}

    # Phase: export the pack under the new basis, then diff it.
    if export_out is None:
        return out
    try:
        deadline.check("export")
    except DeadlineExceeded as exc:
        out["status"], out["phase"] = "deadline", exc.phase
        return out
    from .export_hookpack import export_hookpack
    from .logical import ContentHashError

    pack_path = Path(export_out) / f"pack.{current[:16]}.json"
    try:
        summary = export_hookpack(con, pack_path)
    except (BasisError, ContentHashError) as exc:
        run["export"] = _export_refusal(exc)
        return out
    run["export"] = {
        "status": "wrote",
        "path": str(pack_path),
        "sites": summary.get("sites"),
        "binaries": summary.get("binaries"),
    }
    if prior_pack is not None:
        try:
            deadline.check("diff")
        except DeadlineExceeded as exc:
            out["status"], out["phase"] = "deadline", exc.phase
            return out
        diff_path = receipts_dir / RECEIPT_DIRNAME / f"{current[:16]}.diff.json"
        diff = differ.diff(Path(prior_pack), pack_path)
        diff["prior_pack"] = str(prior_pack)
        diff["new_pack"] = str(pack_path)
        diff["old_basis_hash"] = old
        diff["new_basis_hash"] = current
        diff_path.write_text(_dumps(diff), encoding="utf-8")
        run["diff"] = {"path": str(diff_path), "counts": diff["counts"], "truncated": diff["truncated"]}
    _fire("after_export", con, receipt)
    return out
