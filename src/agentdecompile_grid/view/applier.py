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
kind implements ``apply_result(kind, result, objects, con)`` and is the only code that may touch
pipeline tables, and only through the pipeline's own binders.  The applier itself never writes
``identity``, ``logical_function``, ``match`` or ``func`` -- verified results only, hooks only.

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
  rows consistent.
"""
from __future__ import annotations

import importlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..core import (
    APPLIERS,
    GridError,
    NotConfigured,
    ObjectRef,
    ObjectStore,
    Record,
    RecordType,
    Registry,
    ResultStatus,
    TaskResult,
    canonical_json,
)

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
"""

GRID_TABLES = ("grid_view_position", "grid_tasks", "grid_results", "grid_view_events")


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
    events: list[tuple[int, str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "partition": self.partition, "applied": self.applied, "skipped": self.skipped,
            "verified_rows": self.verified_rows, "task_rows": self.task_rows,
            "hook_rows": self.hook_rows, "events": [list(e) for e in self.events],
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
        """Forget this partition's replay so ``apply`` starts again from record 1."""
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
        return {
            "applier": cls.name,
            "status": "working",
            "writes": list(GRID_TABLES),
            "never_writes": ["identity", "logical_function", "match", "func", "binary"],
            "consumes": [RecordType.TASK.value, RecordType.VERIFIED.value],
            "config_schema": dict(cls.CONFIG_SCHEMA),
            "hooks": VIEW_HOOKS.names(),
            "named_states": ["view-stale: locked", "view-stale: missing-object:<ref>", "view-stale: hook-failed"],
            "errors": {
                "ViewStale": ViewStale.exit_code, "ViewGap": ViewGap.exit_code,
                "ViewBasisMismatch": ViewBasisMismatch.exit_code, "ViewHookFailed": ViewHookFailed.exit_code,
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
    "ApplyStats", "GRID_TABLES", "SCHEMA_SQL", "SQLiteViewApplier", "VIEW_HOOKS", "VIEW_RESETS",
    "VIEW_SCHEMA_VERSION", "ViewBasisMismatch", "ViewGap", "ViewHookFailed", "ViewStale",
    "decode_result", "ensure_tables", "is_lock_error", "materialize", "open_view", "view_hook", "view_reset",
]
