"""Forward-only schema migrations for the corpus identity store.

Two records describe a store's schema state:

* ``PRAGMA user_version`` -- the fast check. Every ``connect()`` reads it and
  returns immediately when it already equals ``SCHEMA_VERSION``. That path
  performs no write and never asks for the write lock, so any number of
  read-only watchers can open the store at once.
* ``schema_migration`` -- the ledger. One row per applied migration with the
  version, the name, when it was applied, and a hash of the determinism
  basis at that moment. ``applied_at`` is the only clock-derived value in the
  store; nothing else may derive from it. ``basis_hash`` is a hook for a
  later re-baseline step and is NULL when the basis cannot be computed.

Rules every migration follows:

* Safe to run twice. Use ``IF NOT EXISTS`` or ``PRAGMA table_info`` checks.
* Never ``DROP`` and never rewrite existing rows.
* One transaction per migration. The ledger row and the ``user_version``
  bump commit together with the migration body, or not at all.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from . import store as _store


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    fn: Callable[[sqlite3.Connection], None]


LEDGER_TABLE = "schema_migration"
LEDGER_SQL = f"""CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    basis_hash TEXT
)"""

# The first version whose migration creates the ledger. Below this a store
# has no ledger at all, so a connection that cannot write has nothing to
# fall back on and the failure is real.
LEDGER_VERSION = 1


def _statements(script: str) -> list[str]:
    """Split a DDL script into single statements, dropping PRAGMAs.

    ``executescript`` cannot be used inside the migration transaction (it
    commits first), and ``PRAGMA journal_mode`` cannot run inside one either.
    ``sqlite3.complete_statement`` respects semicolons inside string literals.
    """
    out: list[str] = []
    buf: list[str] = []

    def flush(chunk: str) -> None:
        lines = [ln for ln in chunk.strip().splitlines() if not ln.strip().startswith("--")]
        text = "\n".join(lines).strip().rstrip(";").strip()
        if text and not text.upper().startswith("PRAGMA"):
            out.append(text)

    for line in script.splitlines():
        buf.append(line)
        chunk = "\n".join(buf)
        if sqlite3.complete_statement(chunk):
            flush(chunk)
            buf = []
    flush("\n".join(buf))
    return out


def _baseline(con: sqlite3.Connection) -> None:
    """Version 1: the schema as it stood before the ledger existed.

    Creates every table and index from ``store.SCHEMA`` and then applies the
    additive column adds that ``connect()`` used to run on every open. On a
    store that predates the ledger every statement is a no-op; on an empty
    file it builds the whole schema.
    """
    for stmt in _statements(_store.SCHEMA):
        con.execute(stmt)
    _store.ensure_func_columns(con)
    _store.ensure_match_columns(con)
    _store.ensure_priority_index(con)


#: Columns migration 2 adds to ``binary``. Added by ALTER TABLE on both the
#: fresh and the legacy path (never put into ``store.SCHEMA``) so the two
#: paths yield identical ``PRAGMA table_info`` shapes.
ANALYZER_IDENTITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("basis_hash", "TEXT"),
    ("decoder_revision", "TEXT"),
    ("analyzer_version", "TEXT"),
    ("processor_spec_hash", "TEXT"),
    ("basis_source", "TEXT"),
)


def _analyzer_identity(con: sqlite3.Connection) -> None:
    """Version 2: per-binary analyzer identity and basis hash.

    ``analyzer_version`` and ``processor_spec_hash`` are captured at ingest,
    ``basis_hash`` is the package basis under that analyzer, ``basis_source``
    says which path wrote them (``ingest`` or ``backfill``) and
    ``decoder_revision`` waits for the unit that picks the decoder. Existing
    rows stay NULL here; ``corpus.backfill --pass analyzer_identity`` fills
    them from the current install. A NULL row makes the basis refuse.
    """
    cols = {row[1] for row in con.execute("PRAGMA table_info(binary)")}
    for col, decl in ANALYZER_IDENTITY_COLUMNS:
        if col not in cols:
            con.execute(f"ALTER TABLE binary ADD COLUMN {col} {decl}")


MIGRATIONS: list[Migration] = [
    Migration(1, "baseline", _baseline),
    Migration(2, "analyzer_identity", _analyzer_identity),
]

SCHEMA_VERSION = MIGRATIONS[-1].version


def _check_registry(migrations: list[Migration]) -> None:
    versions = [m.version for m in migrations]
    assert versions == sorted(versions) and len(set(versions)) == len(versions), (
        f"migration versions must be strictly increasing: {versions}"
    )
    assert versions[0] >= 1, "migration versions start at 1"
    names = [m.name for m in migrations]
    assert len(set(names)) == len(names), f"migration names must be unique: {names}"


_check_registry(MIGRATIONS)


def user_version(con: sqlite3.Connection) -> int:
    return int(con.execute("PRAGMA user_version").fetchone()[0])


def ledger_rows(con: sqlite3.Connection) -> list[dict]:
    """Applied migrations in version order. Empty when the ledger is absent."""
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (LEDGER_TABLE,)
    ).fetchone()
    if not exists:
        return []
    cur = con.execute(
        f"SELECT version, name, applied_at, basis_hash FROM {LEDGER_TABLE} ORDER BY version"
    )
    return [
        {"version": int(r[0]), "name": str(r[1]), "applied_at": str(r[2]), "basis_hash": r[3]}
        for r in cur.fetchall()
    ]


def _basis_hash(con: sqlite3.Connection) -> str | None:
    """Stable hash of the determinism basis, or None when it cannot be built."""
    from .determinism_basis import BasisError, basis_hash

    try:
        return basis_hash(con)
    except (sqlite3.Error, BasisError):
        # The ledger is a hook, never a gate: a store whose tables cannot be
        # read yet (baseline runs before the identity columns exist) or whose
        # rows carry no analyzer identity records NULL; a later re-baseline
        # fills it in.
        return None


def _rollback(con: sqlite3.Connection) -> None:
    if con.in_transaction:
        con.execute("ROLLBACK")


def apply_pending(
    con: sqlite3.Connection,
    *,
    migrations: list[Migration] | None = None,
    target: int | None = None,
) -> list[Migration]:
    """Bring *con* up to ``SCHEMA_VERSION``. Returns the migrations applied.

    Hot path: when ``user_version`` already equals the target nothing is
    written and the write lock is never requested.

    Otherwise each pending migration runs in its own ``BEGIN IMMEDIATE``
    transaction. The version is re-read under that lock so two processes
    migrating the same file at once cannot apply a step twice: the second
    one sees the first one's commit and skips.

    A connection that cannot write (read-only handle, or a writer holding the
    lock past ``busy_timeout``) is tolerated only when the store already has a
    ledger -- some other writer will bring it forward. A store with no ledger
    yet on such a connection raises: there is nothing to fall back on.
    """
    registry = MIGRATIONS if migrations is None else migrations
    goal = registry[-1].version if target is None else target
    current = user_version(con)
    if current >= goal:
        return []
    applied: list[Migration] = []
    for step in registry:
        if step.version <= current or step.version > goal:
            continue
        try:
            con.execute("BEGIN IMMEDIATE")
            now = user_version(con)
            if now >= step.version:
                # Another writer got here first; its commit is visible under
                # the lock we now hold.
                _rollback(con)
                current = now
                continue
            step.fn(con)
            con.execute(LEDGER_SQL)
            con.execute(
                f"INSERT OR IGNORE INTO {LEDGER_TABLE}(version, name, applied_at, basis_hash) "
                "VALUES (?, ?, ?, ?)",
                (
                    step.version,
                    step.name,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    _basis_hash(con),
                ),
            )
            con.execute(f"PRAGMA user_version = {int(step.version)}")
            con.execute("COMMIT")
        except sqlite3.OperationalError as exc:
            _rollback(con)
            if current >= LEDGER_VERSION and _store._is_lock_or_readonly(exc):
                return applied
            raise
        except BaseException:
            _rollback(con)
            raise
        current = step.version
        applied.append(step)
    return applied
