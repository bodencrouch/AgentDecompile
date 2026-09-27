"""Materialized views: replay the VERIFIED stream of one partition into a SQLite database.

The corpus store is a *view* of the log (design §2.4): nothing that computes ever holds its
write lock.  ``SQLiteViewApplier`` is the one working ``Applier``: one instance per partition,
it reads records in partition order and writes exactly two grid-owned tables --

* ``grid_results(task_id, kind, partition, result_ref, outputs_json, verified_seq, ...)`` --
  one row per verified result, generic for every kind;
* ``grid_view_position(partition, seq, basis_hash, last_digest, state)`` -- where the replay
  stands, updated **in the same transaction** as the rows it covers, so a crash between the
  two can never double-apply (that is what "idempotent" buys here);

plus ``grid_tasks`` (``task_id -> kind``, filled from TASK records so a VERIFIED record never
needs to carry the kind).  Everything kind-specific goes through ``VIEW_HOOKS``: a registered
kind implements ``apply_result(kind, result, objects, con)`` and writes receipt tables only.

**Delta binders (U143/U150).**  Store tables (``identity``, ``logical_function``, ``binary``
columns) change through exactly one path: a VERIFIED record whose result names a delta object
(``deltas.Delta``, output ``delta`` / ``delta.<label>``) is loaded, validated
(``deltas.validate_delta``), and handed to the ``DELTA_BINDERS`` entry the delta names, inside
the applier's transaction, under a ``ConflictPolicy``.  The binder is the only code that writes
the table; it states the columns it may write and refuses the rest.  A RESULT record never
binds (it is a proposal); a VERIFIED record signed by the producer's own key never binds
(``delta-self-verified``); a delta ref already in the receipt table ``grid_applied_deltas`` is a
no-op by content hash; apply order is log order (``seq``), never wall clock.  Neither a hook nor
the applier itself writes an identity table directly.  Working binders: ``identity-delta``,
``logical-delta``, ``image-registered``, ``basis-stamped`` (registered by the lanes); declared
slots: ``placement-delta`` (U144), ``bsim-merge`` (U169).  Working policy: ``RefuseOnConflict``
(a differing existing row is a named conflict in the receipt, never an overwrite); declared
slots ``LastVerifiedWins`` and ``QuorumWins`` (the thesis is trust-the-hash: a verified delta is
right because an independent key recomputed it, so a quorum adds nothing and is not default).

Rules the applier enforces by construction:

* only ``RecordType.VERIFIED`` records produce rows; RESULT/INTENT are proposals and are skipped;
* ``seq <= position`` is skipped (replay is idempotent); ``seq > position + 1`` is a named
  ``ViewGap`` refusal, never a silent skip;
* the first non-empty ``basis_hash`` seen for a partition is pinned in ``grid_view_position``;
  a later record under another basis is a named ``ViewBasisMismatch``;
* a lock held by a foreign writer surfaces as ``ViewStale`` (state ``view-stale``) after
  ``busy_timeout_s``; the applier never blocks a worker and never retries silently (H1);
* a verified record whose result object is absent stops the partition **before** that seq with
  state ``view-stale: missing-object`` -- the position never advances past a hole;
* transactions are bounded (``batch_rows`` / ``batch_seconds``, §2.4: 200 rows or 2 s).

``materialize(root, db_path)`` rebuilds every partition from record 1 (a fresh view, or an
explicit reset of the grid tables); ``resume=True`` continues from the stored position.

Acceptance tests (named here, landed in the verification phase, see U128):

* ``test_view_materialize_twice_identical_dump`` -- two materialisations of one verified set
  give byte-identical ``.dump`` output;
* ``test_view_apply_is_idempotent`` -- re-applying the same records adds no rows and moves no
  position;
* ``test_view_gap_is_named`` -- a record at ``position + 2`` raises ``ViewGap``;
* ``test_view_stale_under_foreign_lock`` -- a foreign writer holding the lock for longer than
  ``busy_timeout_s`` yields ``ViewStale`` and state ``view-stale``, never a hang;
* ``test_view_missing_object_never_advances`` -- position stays before the hole;
* ``test_view_basis_mismatch_named`` -- a record under a second basis is refused by name;
* ``test_view_no_worker_opens_view_for_writing`` -- grep: no worker module imports this one;
* ``test_view_position_commits_with_rows`` -- killing the process mid-batch leaves position and
  rows consistent;
* ``test_identity_delta_applied_only_from_verified_records`` -- a RESULT record binds nothing;
  the VERIFIED record of the same result binds the delta once; a second materialisation (or a
  second sight of the same ref) adds no row and writes no second receipt;
* ``test_backfill_replays_identically_on_both_surfaces`` -- the ``image-registered`` /
  ``basis-stamped`` deltas bound into a fresh store copy give the same ``binary`` columns as the
  verb run in place.
"""
from __future__ import annotations

import importlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from ..core import (
    APPLIERS,
    GridError,
    NotConfigured,
    ObjectRef,
    ObjectStore,
    Record,
    RecordType,
    Refused,
    Registry,
    ResultStatus,
    TaskResult,
    canonical_json,
)
from .deltas import Delta, delta_ref, is_delta_output, load_delta, validate_delta

# --------------------------------------------------------------------------- registries
#: kind -> ``apply_result(kind, result, objects, con) -> int``; registered by the kind's lane module.
#: A hook runs inside the applier's transaction: ``con.execute`` only (``ensure_tables`` for DDL),
#: never ``executescript`` / ``commit`` / ``rollback``.
VIEW_HOOKS = Registry("view hook")
#: kind -> ``reset(kind, con, partition) -> None``; optional, run by ``materialize`` on a rebuild.
VIEW_RESETS = Registry("view reset hook")

ViewHook = Callable[[str, TaskResult, ObjectStore, sqlite3.Connection], int]


def view_hook(kind: str, *, replace: bool = False) -> Callable[[ViewHook], ViewHook]:
    """Decorator: register ``fn(kind, result, objects, con) -> rows`` for *kind*."""

    def register(fn: ViewHook) -> ViewHook:
        VIEW_HOOKS.register(kind, fn, replace=replace)
        return fn

    return register


def view_reset(kind: str, *, replace: bool = False):
    def register(fn):
        VIEW_RESETS.register(kind, fn, replace=replace)
        return fn

    return register


# --------------------------------------------------------------------------- delta binders
class BinderRefused(Refused):
    """A binder refused the whole delta by name (a column it may not write, a missing table).

    Raised *before* the binder writes anything; the applier records it as a ``delta-refused``
    event, binds nothing for that delta and advances the position (the record is consumed, the
    refusal is surfaced in the materialize report -- never a silent skip, never a stalled view).
    """

    exit_code = 9


@dataclass
class BindReceipt:
    """What a binder did with one delta: counts plus the named conflicts (rows it did not write)."""

    binder: str
    target_table: str
    applied: int = 0            # rows written (insert or update)
    skipped: int = 0            # rows already equal in the store (idempotent no-op)
    conflicts: list[dict[str, Any]] = field(default_factory=list)   # {key, reason, ...} per refused row
    policy: str = ""
    columns_written: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "binder": self.binder, "target_table": self.target_table, "applied": self.applied,
            "skipped": self.skipped, "conflicts": [dict(c) for c in self.conflicts], "policy": self.policy,
            "columns_written": list(self.columns_written),
        }


@runtime_checkable
class ConflictPolicy(Protocol):
    """What a binder does when the store already holds a *different* row for a delta key.

    ``resolve`` returns ``"apply"`` (write the incoming row), ``"skip"`` (keep the stored row, no
    conflict) or ``"conflict"`` (keep the stored row, record it in the receipt).  A binder with
    an irreversibility rule of its own (``image-registered`` never overwrites a stored hash) may
    refuse regardless of the policy; the receipt says which rule fired.
    """

    name: ClassVar[str]

    def resolve(self, existing: Mapping[str, Any], incoming: Mapping[str, Any], key: tuple[Any, ...]) -> str: ...


class RefuseOnConflict:
    """Working default: a differing stored row is a named conflict; nothing is overwritten.

    Trust-the-hash (design §2.4): a verified delta is right because an independent key
    recomputed it from the same basis, so a *different* stored row means two verified facts
    disagree -- that is a defect to surface, never a vote to take.
    """

    name: ClassVar[str] = "refuse-on-conflict"

    def resolve(self, existing: Mapping[str, Any], incoming: Mapping[str, Any], key: tuple[Any, ...]) -> str:
        return "conflict"

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"policy": cls.name, "status": "working", "on_difference": "conflict (recorded, never overwritten)"}


class LastVerifiedWins:
    """Slot: the later VERIFIED record (higher ``seq``) overwrites.  Declared so the choice is
    named; refuses until a lane needs it, because it turns a disagreement into a silent
    overwrite ordered by log position."""

    name: ClassVar[str] = "last-verified-wins"

    def resolve(self, existing: Mapping[str, Any], incoming: Mapping[str, Any], key: tuple[Any, ...]) -> str:
        raise NotConfigured("conflict policy last-verified-wins is declared, not wired: a differing row is a defect, not a race")

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"policy": cls.name, "status": "declared", "on_difference": "later seq overwrites (not default: hides disagreement)"}


class QuorumWins:
    """Slot: the row most verified keys agree on wins.  Named to document why it is **not** the
    default: the grid trusts the hash, not a count -- one independent recompute under the same
    basis is the whole proof (a VERIFIED record needs a second key), and N keys running the same
    code on the same basis add correlated votes, not evidence.  Refuses until a lane can show a
    disagreement that a count, rather than a basis, would settle."""

    name: ClassVar[str] = "quorum-wins"

    def resolve(self, existing: Mapping[str, Any], incoming: Mapping[str, Any], key: tuple[Any, ...]) -> str:
        raise NotConfigured("conflict policy quorum-wins is declared, not wired: trust-the-hash, no quorum")

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"policy": cls.name, "status": "declared", "on_difference": "majority of verified keys (not default: trust-the-hash, no quorum)"}


CONFLICT_POLICIES = Registry("conflict policy")
for _policy in (RefuseOnConflict, LastVerifiedWins, QuorumWins):
    CONFLICT_POLICIES.register(_policy.name, _policy)
DEFAULT_CONFLICT_POLICY = RefuseOnConflict.name


@runtime_checkable
class DeltaBinder(Protocol):
    """Binds one validated delta into its store table inside the applier's transaction.

    ``bind`` uses ``con.execute`` only (never ``commit`` / ``rollback`` / ``executescript``),
    writes ``writes`` columns of ``target_table`` and nothing else, resolves hashes to store
    rowids itself, and returns a ``BindReceipt``.  It raises ``BinderRefused`` before any write
    for a delta it cannot take as a whole (a foreign column, a missing table); per-row
    disagreements go into ``conflicts`` under the policy.  Binding the same delta twice yields
    ``applied == 0`` the second time (every row ``skipped``): idempotent by content.
    """

    name: ClassVar[str]
    target_table: ClassVar[str]
    writes: ClassVar[tuple[str, ...]]

    def bind(self, con: sqlite3.Connection, delta: Delta, *, policy: ConflictPolicy) -> BindReceipt: ...


class DeclaredBinder:
    """A named slot in ``DELTA_BINDERS``: the delta shape is reserved; binding refuses by name."""

    name: ClassVar[str] = ""
    target_table: ClassVar[str] = ""
    writes: ClassVar[tuple[str, ...]] = ()
    unit: ClassVar[str] = ""

    def bind(self, con: sqlite3.Connection, delta: Delta, *, policy: ConflictPolicy) -> BindReceipt:
        raise NotConfigured(f"delta binder {self.name} is declared, not wired ({self.unit})")

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"binder": cls.name, "status": "declared", "target_table": cls.target_table, "writes": list(cls.writes), "unit": cls.unit}


class PlacementDeltaBinder(DeclaredBinder):
    """U144: placement objects ``[{dst_addr, body_hash, provenance}]`` -> the placed-body rows;
    the cross-place ``should_write`` decision moves here so placement objects stay pure."""

    name = "placement-delta"
    target_table = "placement"
    unit = "U144 cross-place as placement objects"


class BsimMergeBinder(DeclaredBinder):
    """U169: merged-signature objects -> the similarity index through its commit verb (the
    ``similarity`` applier's path); keyed ``(merged_xml_sha256, cluster_url)``."""

    name = "bsim-merge"
    target_table = "similarity-index"
    unit = "U169 similarity index as a view"


DELTA_BINDERS = Registry("delta binder")
for _slot in (PlacementDeltaBinder, BsimMergeBinder):
    DELTA_BINDERS.register(_slot.name, _slot())


def delta_binder(cls: type) -> type:
    """Class decorator: register an instance of a ``DeltaBinder`` under ``cls.name`` (replacing a slot)."""
    DELTA_BINDERS.register(cls.name, cls(), replace=True)
    return cls


def describe_binders() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, binder in DELTA_BINDERS.items():
        describe = getattr(binder, "describe", None)
        out[name] = describe() if callable(describe) else {
            "binder": name, "status": "working", "target_table": getattr(binder, "target_table", ""),
            "writes": list(getattr(binder, "writes", ())),
        }
    return out


# --------------------------------------------------------------------------- named states
class ViewStale(GridError):
    """The view could not advance: a foreign writer holds the lock or an object is missing."""

    exit_code = 5

    def __init__(self, reason: str, partition: str = "", seq: int = 0) -> None:
        super().__init__(f"view-stale: {reason} (partition {partition!r} at seq {seq})")
        self.reason = reason
        self.partition = partition
        self.seq = seq


class ViewGap(GridError):
    """A record arrived beyond ``position + 1``; the log between is not here yet."""

    exit_code = 6


class ViewBasisMismatch(GridError):
    """A record under a second ``basis_hash`` reached a partition pinned to another."""

    exit_code = 7


class ViewHookFailed(GridError):
    """A kind's hook raised; the batch was rolled back.  Names the kind and task, never text."""

    exit_code = 8


_LOCK_MARKERS = ("locked", "busy", "readonly", "read-only", "unable to open")


def is_lock_error(exc: BaseException) -> bool:
    """A lock/busy/read-only ``OperationalError`` (our own check; the recovery one is off limits)."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _LOCK_MARKERS)


# --------------------------------------------------------------------------- schema
VIEW_SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS grid_view_position (
    partition   TEXT PRIMARY KEY,
    seq         INTEGER NOT NULL DEFAULT 0,
    basis_hash  TEXT NOT NULL DEFAULT '',
    last_digest TEXT NOT NULL DEFAULT '',
    state       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS grid_tasks (
    task_id       TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    kind_version  INTEGER NOT NULL DEFAULT 1,
    partition     TEXT NOT NULL,
    basis_hash    TEXT NOT NULL DEFAULT '',
    spec_json     TEXT NOT NULL,
    published_seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS grid_results (
    task_id      TEXT NOT NULL,
    kind         TEXT NOT NULL,
    partition    TEXT NOT NULL,
    result_ref   TEXT NOT NULL,
    outputs_json TEXT NOT NULL,
    verified_seq INTEGER NOT NULL,
    verifier_key TEXT NOT NULL DEFAULT '',
    method       TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'ok',
    PRIMARY KEY (task_id, result_ref)
);
CREATE INDEX IF NOT EXISTS ix_grid_results_kind ON grid_results(kind);
CREATE INDEX IF NOT EXISTS ix_grid_results_partition ON grid_results(partition, verified_seq);
CREATE TABLE IF NOT EXISTS grid_view_events (
    partition TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    event     TEXT NOT NULL,
    detail    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (partition, seq, event)
);
CREATE TABLE IF NOT EXISTS grid_applied_deltas (
    delta_ref      TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL,
    binder         TEXT NOT NULL,
    partition      TEXT NOT NULL,
    applied_at_seq INTEGER NOT NULL,
    receipt_json   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_grid_applied_deltas_partition ON grid_applied_deltas(partition, applied_at_seq);
"""

GRID_TABLES = ("grid_view_position", "grid_tasks", "grid_results", "grid_view_events", "grid_applied_deltas")


def ensure_tables(con: sqlite3.Connection, sql: str) -> None:
    """Run the ``CREATE ... IF NOT EXISTS`` statements of *sql* one ``execute`` at a time.

    Hooks must use this, never ``executescript``: ``executescript`` issues an implicit COMMIT
    first, which would split the applier's transaction and detach the position row from the
    rows it covers (the double-apply-on-crash defect idempotency exists to prevent).
    """
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            con.execute(statement)


def open_view(db_path: str | Path, *, busy_timeout_s: float = 5.0) -> sqlite3.Connection:
    """Open (or create) a view database and ensure the grid tables exist.

    The view may be a fresh file or the corpus store itself; only ``grid_*`` tables are created.
    ``busy_timeout_s`` is short on purpose: a held lock must become a named state, not a wait.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=busy_timeout_s, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute(f"PRAGMA busy_timeout={int(busy_timeout_s * 1000)}")
    try:
        ensure_tables(con, SCHEMA_SQL)
    except sqlite3.OperationalError as exc:
        con.close()
        if is_lock_error(exc):
            raise ViewStale("locked") from exc
        raise
    return con


# --------------------------------------------------------------------------- result decoding
def decode_result(data: bytes) -> TaskResult:
    """A ``TaskResult`` from the canonical JSON stored at ``result_ref`` (``TaskResult.to_record``)."""
    rec = json.loads(data.decode("utf-8"))
    return TaskResult(
        task_id=str(rec["task_id"]),
        status=ResultStatus(rec.get("status", ResultStatus.OK.value)),
        outputs={k: ObjectRef(v) for k, v in dict(rec.get("outputs", {})).items()},
        producer_key=str(rec.get("producer_key", "")),
        basis_hash=str(rec.get("basis_hash", "")),
        elapsed_s=float(rec.get("elapsed_s", 0.0)),
        reason=str(rec.get("reason", "")),
        candidates=tuple(rec.get("candidates", ())),
        metrics=dict(rec.get("metrics", {})),
    )


def _verified_body(body: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """``(task_id, result_ref, verifier_key, method)`` from a VERIFIED record body.

    The body is assumed to carry the ``Verification`` dataclass fields by name
    (``task_id``, ``result_ref``, ``verifier_key``, ``method``); a nested ``verification``
    object is accepted too.  The log slice fixes the final shape.
    """
    src: Mapping[str, Any] = body
    nested = body.get("verification")
    if isinstance(nested, Mapping):
        src = {**nested, **{k: v for k, v in body.items() if k != "verification"}}
    task_id = str(src.get("task_id", ""))
    result_ref = str(src.get("result_ref") or src.get("result") or "")
    return task_id, result_ref, str(src.get("verifier_key", "")), str(src.get("method", ""))


# --------------------------------------------------------------------------- the applier
@dataclass
class ApplyStats:
    partition: str
    applied: int = 0            # records that moved the position
    skipped: int = 0            # seq <= position
    verified_rows: int = 0
    task_rows: int = 0
    hook_rows: int = 0
    deltas_bound: int = 0       # delta objects bound (a receipt row written)
    deltas_skipped: int = 0     # delta refs already in grid_applied_deltas (no-op by content hash)
    delta_rows: int = 0         # store rows the binders wrote
    delta_conflicts: int = 0    # rows the binders refused under the policy
    events: list[tuple[int, str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "partition": self.partition, "applied": self.applied, "skipped": self.skipped,
            "verified_rows": self.verified_rows, "task_rows": self.task_rows,
            "hook_rows": self.hook_rows, "deltas_bound": self.deltas_bound, "deltas_skipped": self.deltas_skipped,
            "delta_rows": self.delta_rows, "delta_conflicts": self.delta_conflicts,
            "events": [list(e) for e in self.events],
        }


class SQLiteViewApplier:
    """Replays one partition's verified stream into a SQLite view.  One instance per partition."""

    name = "sqlite"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "db_path": "path of the view database (fresh file or the corpus store)",
        "partition": "the one partition this applier replays",
        "batch_rows": "int, max records per transaction (default 200, §2.4)",
        "batch_seconds": "float, max seconds per transaction (default 2.0, §2.4)",
        "busy_timeout_s": "float, lock wait before the named view-stale state (default 5.0)",
        "hooks": "Registry of kind -> apply_result(kind, result, objects, con)",
        "binders": "Registry of delta binder name -> DeltaBinder (default DELTA_BINDERS)",
        "policy": "ConflictPolicy name (default refuse-on-conflict)",
    }

    def __init__(
        self,
        db_path: str | Path,
        partition: str,
        *,
        batch_rows: int = 200,
        batch_seconds: float = 2.0,
        busy_timeout_s: float = 5.0,
        hooks: Registry | None = None,
        binders: Registry | None = None,
        policy: ConflictPolicy | str | None = None,
        con: sqlite3.Connection | None = None,
    ) -> None:
        if not partition:
            raise GridError("SQLiteViewApplier needs a partition: one applier per partition")
        self.db_path = Path(db_path)
        self.partition = partition
        self.batch_rows = max(1, int(batch_rows))
        self.batch_seconds = max(0.01, float(batch_seconds))
        self.busy_timeout_s = float(busy_timeout_s)
        self.hooks = hooks if hooks is not None else VIEW_HOOKS
        self.binders = binders if binders is not None else DELTA_BINDERS
        if policy is None or isinstance(policy, str):
            self.policy: ConflictPolicy = CONFLICT_POLICIES.get(policy or DEFAULT_CONFLICT_POLICY)()
        else:
            self.policy = policy
        self._con = con
        self._state = ""
        self.stats = ApplyStats(partition)

    # ----------------------------------------------------------------- connection / position
    @property
    def con(self) -> sqlite3.Connection:
        if self._con is None:
            self._con = open_view(self.db_path, busy_timeout_s=self.busy_timeout_s)
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def _position_row(self) -> tuple[int, str, str]:
        row = self.con.execute(
            "SELECT seq, basis_hash, last_digest FROM grid_view_position WHERE partition=?",
            (self.partition,),
        ).fetchone()
        if row is None:
            return 0, "", ""
        return int(row["seq"]), str(row["basis_hash"]), str(row["last_digest"])

    def position(self) -> Mapping[str, int]:
        try:
            seq, _, _ = self._position_row()
        except sqlite3.OperationalError as exc:
            if is_lock_error(exc):
                raise ViewStale("locked", self.partition) from exc
            raise
        return {self.partition: seq}

    def state(self) -> Mapping[str, Any]:
        """Named state of this partition's view: ``''`` (current) or ``view-stale: <reason>``."""
        seq, basis, digest = self._position_row()
        return {
            "partition": self.partition, "seq": seq, "basis_hash": basis,
            "last_digest": digest, "state": self._state,
        }

    def _set_state(self, state: str) -> None:
        self._state = state
        try:
            self.con.execute(
                "INSERT INTO grid_view_position(partition, seq, state) VALUES (?, 0, ?) "
                "ON CONFLICT(partition) DO UPDATE SET state=excluded.state",
                (self.partition, state),
            )
        except sqlite3.OperationalError:
            pass  # recording the state must never itself block or raise past the named error

    # ----------------------------------------------------------------- apply
    def apply(self, records: Iterable[Record], objects: ObjectStore) -> int:
        """Apply *records* (partition order) and return how many advanced the position.

        Bounded transactions; the position row is written inside each one.  Raises the named
        ``ViewGap`` / ``ViewBasisMismatch`` / ``ViewStale`` / ``ViewHookFailed`` after committing
        every complete batch before the offending record.
        """
        con = self.con
        pos, pinned_basis, last_digest = self._position_row()
        batch_count = 0
        batch_started = time.monotonic()
        in_tx = False
        applied = 0

        def begin() -> None:
            nonlocal in_tx, batch_count, batch_started
            if not in_tx:
                con.execute("BEGIN IMMEDIATE")
                in_tx = True
                batch_count = 0
                batch_started = time.monotonic()

        def commit() -> None:
            nonlocal in_tx
            if in_tx:
                con.execute(
                    "INSERT INTO grid_view_position(partition, seq, basis_hash, last_digest, state) "
                    "VALUES (?, ?, ?, ?, '') ON CONFLICT(partition) DO UPDATE SET "
                    "seq=excluded.seq, basis_hash=excluded.basis_hash, last_digest=excluded.last_digest, state=''",
                    (self.partition, pos, pinned_basis, last_digest),
                )
                con.execute("COMMIT")
                in_tx = False

        def rollback() -> None:
            nonlocal in_tx, applied
            if in_tx:
                try:
                    if con.in_transaction:
                        con.execute("ROLLBACK")
                finally:
                    in_tx = False
                    # the uncommitted batch never landed: neither did its count
                    applied -= batch_count
                    self.stats.applied -= batch_count

        try:
            for rec in records:
                if rec.partition != self.partition:
                    raise GridError(
                        f"applier for partition {self.partition!r} was handed a record of {rec.partition!r}"
                    )
                if rec.seq <= pos:
                    self.stats.skipped += 1
                    continue
                if rec.seq != pos + 1:
                    commit()
                    raise ViewGap(
                        f"view-gap: partition {self.partition!r} is at seq {pos}, record seq {rec.seq} arrived"
                    )
                if rec.basis_hash:
                    if pinned_basis and rec.basis_hash != pinned_basis:
                        commit()
                        raise ViewBasisMismatch(
                            f"basis-mismatch: partition {self.partition!r} pinned to {pinned_basis[:12]}, "
                            f"record seq {rec.seq} carries {rec.basis_hash[:12]}"
                        )
                    pinned_basis = pinned_basis or rec.basis_hash

                begin()
                try:
                    self._apply_one(rec, objects)
                except ViewStale as exc:
                    # ``_apply_one`` raises this before writing anything for *rec*, so the open
                    # transaction holds only complete earlier records: commit them, then name
                    # the hole.  The position stays at ``pos`` -- before the missing object.
                    commit()
                    self._set_state(f"view-stale: {exc.reason}")
                    raise
                except GridError:
                    rollback()
                    raise
                except Exception as exc:  # a hook raised: never a traceback into the view
                    rollback()
                    self._set_state("view-stale: hook-failed")
                    raise ViewHookFailed(
                        f"hook-failed: {type(exc).__name__} in partition {self.partition!r} at seq {rec.seq}"
                    ) from exc

                pos = rec.seq
                last_digest = rec.digest()
                applied += 1
                batch_count += 1
                self.stats.applied += 1
                if batch_count >= self.batch_rows or (time.monotonic() - batch_started) >= self.batch_seconds:
                    commit()
            commit()
        except sqlite3.OperationalError as exc:
            rollback()
            if is_lock_error(exc):
                self._set_state("view-stale: locked")
                raise ViewStale("locked", self.partition, pos + 1) from exc
            raise
        return applied

    def _apply_one(self, rec: Record, objects: ObjectStore) -> None:
        con = self.con
        if rec.type == RecordType.TASK:
            body = rec.body
            task_id = str(body.get("task_id", ""))
            if task_id:
                con.execute(
                    "INSERT OR IGNORE INTO grid_tasks(task_id, kind, kind_version, partition, basis_hash, "
                    "spec_json, published_seq) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        task_id, str(body.get("kind", "")), int(body.get("kind_version", 1)),
                        self.partition, str(body.get("basis_hash", rec.basis_hash)),
                        canonical_json(dict(body)).decode("utf-8"), rec.seq,
                    ),
                )
                self.stats.task_rows += 1
            return
        if rec.type != RecordType.VERIFIED:
            return  # proposals, intents, notes, checkpoints: position only

        task_id, result_ref, verifier_key, method = _verified_body(rec.body)
        if not task_id or not result_ref:
            self._event(rec.seq, "malformed-verified", "")
            return
        ref = ObjectRef(result_ref)
        if not objects.exists(ref):
            raise ViewStale(f"missing-object:{ref.hex[:12]}", self.partition, rec.seq)
        result = decode_result(objects.get(ref))
        if result.task_id != task_id:
            self._event(rec.seq, "result-task-mismatch", ref.hex[:12])
            return
        # A delta object this record would bind must be here before anything is written for
        # the record: a hole in the object store stops the partition *before* this seq.
        delta_refs = [(name, ObjectRef(str(r))) for name, r in sorted(result.outputs.items()) if is_delta_output(name)]
        for _name, dref in delta_refs:
            if not objects.exists(dref):
                raise ViewStale(f"missing-object:{dref.hex[:12]}", self.partition, rec.seq)
        kind = self._kind_of(task_id, rec.body)
        con.execute(
            "INSERT OR IGNORE INTO grid_results(task_id, kind, partition, result_ref, outputs_json, "
            "verified_seq, verifier_key, method, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id, kind, self.partition, str(ref),
                canonical_json({k: str(v) for k, v in sorted(result.outputs.items())}).decode("utf-8"),
                rec.seq, verifier_key, method, result.status.value,
            ),
        )
        self.stats.verified_rows += 1
        if kind and kind in self.hooks:
            rows = self.hooks.get(kind)(kind, result, objects, con)
            self.stats.hook_rows += int(rows or 0)
        elif not kind:
            self._event(rec.seq, "kind-unknown", task_id[:12])
        if delta_refs and result.status == ResultStatus.OK:
            for _name, dref in delta_refs:
                self._bind_delta(rec, dref, result, objects, verifier_key=verifier_key)

    # ----------------------------------------------------------------- delta binding
    def _bind_delta(self, rec: Record, dref: ObjectRef, result: TaskResult, objects: ObjectStore, *, verifier_key: str) -> None:
        """Bind one verified delta through its registered binder; the only path into a store table.

        Order of checks, each a named event (position advances, nothing bound) rather than a
        stall: already bound (receipt by content hash -> no-op); not a delta / fails
        ``validate_delta``; verifier key equals the producer key (not an independent
        verification); binder declared but not wired; binder refuses the whole delta.  A binder
        that raises anything else is ``ViewHookFailed`` (the batch rolls back).
        """
        con = self.con
        if con.execute("SELECT 1 FROM grid_applied_deltas WHERE delta_ref=?", (str(dref),)).fetchone() is not None:
            self.stats.deltas_skipped += 1
            return
        try:
            delta = load_delta(objects, dref)
        except ValueError as exc:
            self._event(rec.seq, "delta-refused", str(exc)[:80])
            return
        refusals = validate_delta(delta, binders=self.binders.names())
        if delta.task_id != result.task_id:
            refusals.append(f"delta-task-mismatch:{delta.task_id[:12]}")
        if refusals:
            self._event(rec.seq, "delta-refused", ";".join(refusals)[:200])
            return
        if not result.producer_key or not verifier_key or verifier_key == result.producer_key:
            self._event(rec.seq, "delta-self-verified", f"{result.producer_key[:24]}=={verifier_key[:24]}")
            return
        binder = self.binders.get(delta.binder)
        try:
            receipt = binder.bind(con, delta, policy=self.policy)
        except NotConfigured as exc:
            self._event(rec.seq, "delta-binder-not-configured", f"{delta.binder}:{str(exc)[:80]}")
            return
        except BinderRefused as exc:
            self._event(rec.seq, "delta-refused", f"{delta.binder}:{exc.reason[:120]}")
            return
        if str(delta_ref(delta)) != str(dref):
            # the stored bytes were not canonical: the receipt keys on the ref the log names
            self._event(rec.seq, "delta-ref-noncanonical", dref.hex[:12])
        con.execute(
            "INSERT INTO grid_applied_deltas(delta_ref, task_id, binder, partition, applied_at_seq, receipt_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(dref), result.task_id, delta.binder, self.partition, rec.seq, canonical_json(receipt.as_dict()).decode("utf-8")),
        )
        self.stats.deltas_bound += 1
        self.stats.delta_rows += int(receipt.applied)
        self.stats.delta_conflicts += len(receipt.conflicts)
        if receipt.conflicts:
            self._event(rec.seq, "delta-conflicts", f"{delta.binder}:{len(receipt.conflicts)}")

    def _kind_of(self, task_id: str, body: Mapping[str, Any]) -> str:
        row = self.con.execute("SELECT kind FROM grid_tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is not None:
            return str(row["kind"])
        return str(body.get("kind", ""))

    def _event(self, seq: int, event: str, detail: str) -> None:
        self.con.execute(
            "INSERT OR IGNORE INTO grid_view_events(partition, seq, event, detail) VALUES (?, ?, ?, ?)",
            (self.partition, seq, event, detail),
        )
        self.stats.events.append((seq, event, detail))

    # ----------------------------------------------------------------- rebuild
    def reset(self) -> None:
        """Forget this partition's replay so ``apply`` starts again from record 1.

        The delta receipts of the partition go too (``grid_applied_deltas`` is scoped by
        ``partition``), so the replay binds every verified delta again; the binders are
        idempotent by content (a row already equal is ``skipped``), so a rebuild over an
        unchanged store writes nothing and a rebuild into a fresh store copy writes everything.
        Rows a binder wrote are *not* deleted here: the store is a view of the log, and the
        replay is what makes it current.
        """
        con = self.con
        try:
            con.execute("BEGIN IMMEDIATE")
            try:
                kinds = [str(r["kind"]) for r in con.execute(
                    "SELECT DISTINCT kind FROM grid_results WHERE partition=?", (self.partition,)
                )]
                for kind in kinds:
                    if kind in VIEW_RESETS:
                        VIEW_RESETS.get(kind)(kind, con, self.partition)
                con.execute("DELETE FROM grid_applied_deltas WHERE partition=?", (self.partition,))
                con.execute("DELETE FROM grid_results WHERE partition=?", (self.partition,))
                con.execute("DELETE FROM grid_tasks WHERE partition=?", (self.partition,))
                con.execute("DELETE FROM grid_view_events WHERE partition=?", (self.partition,))
                con.execute("DELETE FROM grid_view_position WHERE partition=?", (self.partition,))
                con.execute("COMMIT")
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        except sqlite3.OperationalError as exc:
            if is_lock_error(exc):
                self._state = "view-stale: locked"
                raise ViewStale("locked", self.partition) from exc
            raise
        self._state = ""

    @classmethod
    def describe(cls) -> dict[str, Any]:
        from .deltas import describe_schema

        return {
            "applier": cls.name,
            "status": "working",
            "writes": list(GRID_TABLES),
            "writes_through_binders": {name: getattr(b, "target_table", "") for name, b in DELTA_BINDERS.items()},
            "never_writes_directly": ["identity", "logical_function", "match", "func", "binary"],
            "binds_from": [RecordType.VERIFIED.value],
            "never_binds_from": [RecordType.RESULT.value, RecordType.INTENT.value, "a VERIFIED record signed by the producer key"],
            "consumes": [RecordType.TASK.value, RecordType.VERIFIED.value],
            "config_schema": dict(cls.CONFIG_SCHEMA),
            "hooks": VIEW_HOOKS.names(),
            "binders": describe_binders(),
            "conflict_policies": {name: p.describe() for name, p in CONFLICT_POLICIES.items()},
            "default_policy": DEFAULT_CONFLICT_POLICY,
            "delta_schema": describe_schema(),
            "receipt_table": "grid_applied_deltas(delta_ref PK, task_id, binder, partition, applied_at_seq, receipt_json)",
            "named_states": ["view-stale: locked", "view-stale: missing-object:<ref>", "view-stale: hook-failed"],
            "named_events": [
                "delta-refused:<reasons>", "delta-self-verified", "delta-binder-not-configured:<binder>",
                "delta-conflicts:<binder>:<n>", "delta-ref-noncanonical",
            ],
            "errors": {
                "ViewStale": ViewStale.exit_code, "ViewGap": ViewGap.exit_code,
                "ViewBasisMismatch": ViewBasisMismatch.exit_code, "ViewHookFailed": ViewHookFailed.exit_code,
                "BinderRefused": BinderRefused.exit_code,
            },
        }


APPLIERS.register(SQLiteViewApplier.name, SQLiteViewApplier)


# --------------------------------------------------------------------------- materialize
def _local_objects(root: str | Path) -> ObjectStore:
    """The local object store of a grid root, in the ``config.PathsConfig`` layout (``<root>/objects``)."""
    from ..config import PathsConfig

    try:
        mod = importlib.import_module("agentdecompile_grid.objects.local")
    except ImportError as exc:
        raise NotConfigured("agentdecompile_grid.objects.local not present in this checkout yet") from exc
    return mod.LocalDirStore(PathsConfig(root=str(root)).resolved().objects)


def _local_log(root: str | Path):
    """The local log of a grid root (partitions under ``<root>/log``)."""
    from ..config import PathsConfig

    try:
        mod = importlib.import_module("agentdecompile_grid.log.local")
    except ImportError as exc:
        raise NotConfigured("agentdecompile_grid.log.local not present in this checkout yet") from exc
    paths = PathsConfig(root=str(root)).resolved()
    return mod.LocalFileLog(paths.root, log_dir=paths.log)


def materialize(
    root: str | Path,
    db_path: str | Path,
    *,
    partitions: Sequence[str] | None = None,
    resume: bool = False,
    objects: ObjectStore | None = None,
    log: Any = None,
    applier_factory: Callable[..., SQLiteViewApplier] = SQLiteViewApplier,
    batch_rows: int = 200,
    batch_seconds: float = 2.0,
    busy_timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Rebuild the view at *db_path* from record 1 of every partition under *root*.

    Default is a full rebuild: each partition's grid rows are reset, then replayed from seq 1.
    ``resume=True`` continues from the stored position instead.  Named states are collected per
    partition rather than aborting the whole run, so one stale partition never hides the rest;
    ``report["events"]`` lists every record the applier had to skip by name.
    """
    objects = objects if objects is not None else _local_objects(root)
    log = log if log is not None else _local_log(root)
    names = list(partitions) if partitions else sorted(log.partitions())
    report: dict[str, Any] = {"db": str(db_path), "root": str(root), "partitions": {}, "stale": [], "events": {}}
    for partition in names:
        applier = applier_factory(
            db_path, partition, batch_rows=batch_rows, batch_seconds=batch_seconds,
            busy_timeout_s=busy_timeout_s,
        )
        try:
            try:
                if not resume:
                    applier.reset()
                since = applier.position()[partition]
                applied = applier.apply(log.read(partition, since_seq=since), objects)
                entry = {"applied": applied, **applier.stats.as_dict(), "state": applier.state()["state"]}
            except (ViewStale, ViewGap, ViewBasisMismatch, ViewHookFailed) as exc:
                entry = {
                    "applied": applier.stats.applied, **applier.stats.as_dict(),
                    "state": f"{type(exc).__name__}: {exc}",
                }
                report["stale"].append(partition)
            report["partitions"][partition] = entry
            if applier.stats.events:
                # a VERIFIED record the applier could not use (malformed body, unknown kind,
                # result/task mismatch) is a contract mismatch with the log slice: surfaced,
                # never silently absorbed into an empty view
                report["events"][partition] = [list(e) for e in applier.stats.events]
        finally:
            applier.close()
    return report


__all__ = [
    "ApplyStats", "BindReceipt", "BinderRefused", "BsimMergeBinder", "CONFLICT_POLICIES", "ConflictPolicy",
    "DEFAULT_CONFLICT_POLICY", "DELTA_BINDERS", "DeclaredBinder", "DeltaBinder", "GRID_TABLES", "LastVerifiedWins",
    "PlacementDeltaBinder", "QuorumWins", "RefuseOnConflict", "SCHEMA_SQL", "SQLiteViewApplier", "VIEW_HOOKS",
    "VIEW_RESETS", "VIEW_SCHEMA_VERSION", "ViewBasisMismatch", "ViewGap", "ViewHookFailed", "ViewStale",
    "decode_result", "delta_binder", "describe_binders", "ensure_tables", "is_lock_error", "materialize", "open_view",
    "view_hook", "view_reset",
]
