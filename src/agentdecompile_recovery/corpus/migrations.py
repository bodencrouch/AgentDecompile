"""Forward-only schema migrations for the corpus identity store.

Two records describe a store's schema state:

* ``PRAGMA user_version`` -- the fast check. Every ``connect()`` reads it and
  returns immediately when it already equals ``SCHEMA_VERSION``. That path
  performs no write and never asks for the write lock, so any number of
  read-only watchers can open the store at once.
* ``schema_migration`` -- the ledger. One row per applied migration with the
  version, the name, when it was applied, and a hash of the determinism
  basis at that moment. ``applied_at`` and ``basis_supersession.recorded_at``
  are recovery metadata; match-review UUIDs and audit times are separate
  control-plane metadata excluded from deterministic recovery content.
  ``basis_hash`` is NULL when the basis cannot be computed; a
  re-baseline (``corpus rebaseline``) records its supersession in
  ``basis_supersession`` rather than rewriting this ledger.

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


SUPERSESSION_TABLE = "basis_supersession"
#: One row per re-baseline: the old and new package basis (hash, algorithm
#: version and object), what drove it, how many rows it re-stamped and the
#: sha256 of the receipt file. ``old_package_basis_json`` is NULL when the
#: old object could not be reconstructed. ``UNIQUE(old, new)`` makes a
#: replayed supersession a constraint error, never a second row.
SUPERSESSION_SQL = f"""CREATE TABLE IF NOT EXISTS {SUPERSESSION_TABLE} (
    id                     INTEGER PRIMARY KEY,
    old_basis_hash         TEXT NOT NULL,
    new_basis_hash         TEXT NOT NULL,
    old_algorithm_version  TEXT NOT NULL,
    new_algorithm_version  TEXT NOT NULL,
    old_package_basis_json TEXT,
    new_package_basis_json TEXT NOT NULL,
    analyzer_version       TEXT NOT NULL,
    reason                 TEXT,
    binaries_restamped     INTEGER NOT NULL,
    receipt_sha256         TEXT NOT NULL,
    recorded_at            TEXT NOT NULL,
    UNIQUE(old_basis_hash, new_basis_hash)
)"""
SUPERSESSION_INDEX_SQL = (
    f"CREATE INDEX IF NOT EXISTS ix_{SUPERSESSION_TABLE}_new ON {SUPERSESSION_TABLE}(new_basis_hash)"
)


def _basis_supersession(con: sqlite3.Connection) -> None:
    """Version 3: the ``basis_supersession`` ledger for ``corpus rebaseline``.

    A package-constant change moves every stamped row's ``basis_hash`` and
    makes the basis refuse. The re-baseline verb records the old and the new
    basis here and re-stamps the rows in the same transaction, so a store
    never silently mixes bases. ``recorded_at`` is ISO-8601 UTC, taken from
    ``SOURCE_DATE_EPOCH`` when set. The index on ``new_basis_hash`` serves
    the lookup a later supersession makes to name its old basis. Creates
    nothing else and touches no row.
    """
    con.execute(SUPERSESSION_SQL)
    con.execute(SUPERSESSION_INDEX_SQL)

#: Columns migration 4 adds to ``binary`` (register A4, ``corpus admit``).
#: ``admission_status`` is NULL until the admit verb has seen the row; its
#: values are ``admitted``, ``placeholder``, ``duplicate``, ``contested`` and
#: ``unresolved``. ``duplicate_of`` names the keeper (its content hash, or
#: ``slug:<sha256(slug)[:12]>`` when it has none). ``admission_receipt`` is
#: the sha256 of the row's receipt file. ``admission_handling`` records how
#: a placeholder was treated (``quarantine`` or ``exclude``): the hook pack
#: lists excluded placeholders under ``excluded_builds`` and stays silent
#: about quarantined ones, and the store is the only channel that reaches
#: the exporter.
ADMISSION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("admission_status", "TEXT"),
    ("duplicate_of", "TEXT"),
    ("admission_receipt", "TEXT"),
    ("admission_handling", "TEXT"),
)

#: The admitted-rows view. Placeholders, duplicates, contested and
#: unresolved rows are outside every key, basis, manifest and pack by design
#: (A4); readers that must survive later column adds filter ``binary``
#: directly with the same predicate.
ADMITTED_VIEW = "admitted_binary"


def _admission(con: sqlite3.Connection) -> None:
    """Version 14: admission columns on ``binary`` and the ``admitted_binary`` view.

    Additive only; every existing row keeps ``admission_status`` NULL, which
    every scoped reader treats as "admission has not run" and falls back to
    the unscoped legacy behaviour until the first ``corpus admit``. NVMe's
    earlier standalone lineage recorded these same columns as migration 4;
    that lineage is recognized without rewriting its ledger, and its missing
    match-review migration is repaired before later schema steps run.
    """
    if not con.in_transaction:
        raise ValueError("admission migration requires an owned transaction")
    require_ledger(con, version=13)
    cols = {row[1] for row in con.execute("PRAGMA table_info(binary)")}
    for col, decl in ADMISSION_COLUMNS:
        if col not in cols:
            con.execute(f"ALTER TABLE binary ADD COLUMN {col} {decl}")
    con.execute(
        f"CREATE VIEW IF NOT EXISTS {ADMITTED_VIEW} AS "
        "SELECT * FROM binary WHERE admission_status = 'admitted'"
    )


def _has_legacy_admission_lineage(con: sqlite3.Connection) -> bool:
    """Whether this store came from the standalone NVMe schema-v4 branch."""
    row = con.execute(
        "SELECT name FROM main.schema_migration WHERE version=4"
    ).fetchone()
    return row is not None and row[0] == "admission"


def _require_admission_shape(con: sqlite3.Connection) -> None:
    columns = {row[1]: row[2].upper() for row in con.execute("PRAGMA main.table_info(binary)")}
    if any(columns.get(name) != "TEXT" for name, _ in ADMISSION_COLUMNS):
        raise ValueError("admission_schema_corrupt")
    view = con.execute(
        "SELECT type,sql FROM main.sqlite_schema WHERE name=?", (ADMITTED_VIEW,)
    ).fetchone()
    if view is None or view[0] != "view" or not view[1]:
        raise ValueError("admission_schema_corrupt")


def _match_review(con: sqlite3.Connection) -> None:
    """Version 4: durable per-entity review freshness and atomic decision audit."""
    from .match_review_schema import install

    install(con)


def _function_storage(con: sqlite3.Connection) -> None:
    """Version 5: lossless observed ABI storage; existing rows remain unknown."""
    columns = {row[1] for row in con.execute("PRAGMA table_info(func)")}
    for name in ("return_storage", "function_properties"):
        if name not in columns:
            con.execute(f"ALTER TABLE func ADD COLUMN {name} TEXT")
    con.execute("""CREATE TABLE IF NOT EXISTS func_param (
        binary_id INTEGER NOT NULL,
        addr INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        name TEXT,
        type TEXT,
        pieces_json TEXT,
        PRIMARY KEY(binary_id, addr, ordinal),
        FOREIGN KEY(binary_id, addr) REFERENCES func(binary_id, addr) ON DELETE CASCADE
    )""")


def _typed_fields(con: sqlite3.Connection) -> None:
    """Version 6: typed layout witnesses alongside byte-accurate headers."""
    con.execute("""CREATE TABLE IF NOT EXISTS ghidra_field (
        binary_id INTEGER NOT NULL REFERENCES binary(id),
        type_name TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        offset INTEGER NOT NULL,
        size INTEGER NOT NULL,
        name TEXT NOT NULL,
        dt_kind TEXT NOT NULL,
        pointee_type TEXT,
        composite_type TEXT,
        element_type TEXT,
        array_count INTEGER,
        type_json TEXT NOT NULL,
        PRIMARY KEY(binary_id, type_name, ordinal)
    )""")


def _matching_evidence(con: sqlite3.Connection) -> None:
    """Version 7: optional BSim evidence with explicit query provenance."""
    con.execute("""CREATE TABLE IF NOT EXISTS bsim_query (
        src_binary INTEGER NOT NULL REFERENCES binary(id),
        dst_binary INTEGER NOT NULL REFERENCES binary(id),
        database_id TEXT NOT NULL, src_digest TEXT NOT NULL, dst_digest TEXT NOT NULL,
        state TEXT NOT NULL, reason TEXT NOT NULL,
        PRIMARY KEY(src_binary, dst_binary)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS bsim_hit (
        src_binary INTEGER NOT NULL REFERENCES binary(id), src_addr INTEGER NOT NULL,
        dst_binary INTEGER NOT NULL REFERENCES binary(id), dst_addr INTEGER NOT NULL,
        database_id TEXT NOT NULL, similarity REAL NOT NULL,
        significance REAL NOT NULL, self_significance REAL,
        PRIMARY KEY(src_binary, src_addr, dst_binary, dst_addr)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_bsim_pair ON bsim_hit(src_binary,dst_binary)")


def _pcode_channel(con: sqlite3.Connection) -> None:
    """Version 8: correct the algorithm label, retaining historical decisions."""
    import json
    for row in con.execute("SELECT id,evidence FROM match ORDER BY id").fetchall():
        try:
            evidence = json.loads(row[1] or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(evidence, dict) or evidence.get("stage") != "pcode_il_ast" or evidence.get("primary_channel") != "M":
            continue
        evidence["primary_channel"] = "K"
        evidence["channels"] = sorted({"K" if c == "M" else c for c in evidence.get("channels", ["M"])})
        # Historical confidence and operator decisions are immutable evidence.
        # Explicitly require review rather than silently promoting on +4 base.
        evidence["algorithm_relabel"] = {"from": "M", "to": "K", "base_delta": 4,
                                        "confidence_review_required": True}
        con.execute("UPDATE match SET evidence=? WHERE id=?", (json.dumps(evidence, sort_keys=True), row[0]))


def _match_metadata(con: sqlite3.Connection) -> None:
    """Version 9: queryable projection of recorded evidence, no rescoring."""
    import json
    _store.ensure_match_columns(con)
    for row in con.execute("SELECT id,evidence FROM match ORDER BY id").fetchall():
        try:
            evidence = json.loads(row[1] or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(evidence, dict):
            continue
        confidence = evidence.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            confidence = None
        con.execute("UPDATE match SET kind=?,confidence=?,algorithm=? WHERE id=?",
                    (evidence.get("kind"), confidence,
                     evidence.get("primary_channel") or evidence.get("channel"), row[0]))
    con.execute("CREATE INDEX IF NOT EXISTS ix_match_algorithm_confidence ON match(algorithm,confidence)")


def _stabs_schema_ownership(con: sqlite3.Connection) -> None:
    """Version 10: adopt existing STABS attribution without inventing values."""
    if not con.in_transaction:
        raise ValueError("STABS migration requires an owned transaction")
    version = user_version(con)
    if version == 10:
        require_ledger(con, version=10)
        _store._require_stabs_shape(con, complete=True)
        return
    require_ledger(con, version=9)
    _store._require_stabs_shape(con, complete=False)
    columns = {row[1] for row in con.execute("PRAGMA main.table_xinfo(func)")}
    for name in ("stabs_name", "stabs_type"):
        if name not in columns:
            con.execute(f"ALTER TABLE main.func ADD COLUMN {name} TEXT")
    for sql in (*_store.STABS_INDEX_SQL.values(), _store.STABS_FUNC_INDEX_SQL):
        con.execute(sql)
    _store._require_stabs_shape(con, complete=True)

def _decomp_schema_ownership(con: sqlite3.Connection) -> None:
    """Version 11: preserve preexisting global witness/selector semantics."""
    if not con.in_transaction:
        raise ValueError("decomp migration requires an owned transaction")
    _store._decomp_objects(con)
    if user_version(con) == 11:
        require_ledger(con, version=11)
        _store._require_stabs_shape(con, complete=True)
        _store._require_decomp_shape(con, complete=True)
        return
    require_ledger(con, version=10)
    _store._require_stabs_shape(con, complete=True)
    mode = _store._require_decomp_shape(con, complete=False)
    if mode is None:
        con.execute(_store.DECOMP_TABLE_DDL)
    elif mode == "skeleton_hash":
        con.execute("ALTER TABLE main.decomp ADD COLUMN ast_fingerprint TEXT")
    if "ix_decomp_bin" not in _store._decomp_objects(con):
        con.execute(_store.DECOMP_INDEX_SQL)
    con.execute(_store.DECOMP_COMPAT_STATE_DDL)
    con.execute("INSERT INTO main.decomp_schema_state(singleton,mode) VALUES (1,?)",
                (mode or "absent",))
    _store._require_decomp_shape(con, complete=True)


def _convention_schema_ownership(con: sqlite3.Connection) -> None:
    """Version 12: own derived storage without changing rows or donor meaning."""
    if not con.in_transaction:
        raise ValueError("convention migration requires an owned transaction")
    version = user_version(con)
    _store._require_convention_shape(con, complete=version == 12)
    if version == 12:
        require_ledger(con, version=12)
        _store._require_stabs_shape(con, complete=True)
        _store._require_decomp_shape(con, complete=True)
        return
    require_ledger(con, version=11)
    _store._require_stabs_shape(con, complete=True)
    _store._require_decomp_shape(con, complete=True)
    if con.execute(
        "SELECT 1 FROM main.sqlite_schema WHERE name='func_convention_derived'"
    ).fetchone() is None:
        con.execute(_store.CONVENTION_TABLE_DDL)
    _store._require_convention_shape(con, complete=True)


def _type_schema_ownership(con: sqlite3.Connection) -> None:
    """Version 13: own type storage, retaining original inventory availability."""
    if not con.in_transaction:
        raise ValueError("type migration requires an owned transaction")
    version = user_version(con)
    if version == 13:
        require_ledger(con, version=13)
        _store._require_stabs_shape(con, complete=True)
        _store._require_decomp_shape(con, complete=True)
        _store._require_convention_shape(con, complete=True)
        _store._require_type_shape(con, complete=True)
        return
    require_ledger(con, version=12)
    _store._require_stabs_shape(con, complete=True)
    _store._require_decomp_shape(con, complete=True)
    _store._require_convention_shape(con, complete=True)
    mode = _store._require_type_shape(con, complete=False)
    if mode == "absent":
        con.execute(_store.TYPE_TABLE_DDL)
    elif not any(row[1] == "origin" for row in con.execute("PRAGMA main.table_xinfo(ghidra_type)")):
        con.execute("ALTER TABLE main.ghidra_type ADD COLUMN origin TEXT")
    con.execute(_store.TYPE_ORIGIN_DDL)
    con.execute(_store.TYPE_INDEX_SQL)
    con.execute(_store.TYPE_INVENTORY_STATE_DDL)
    con.execute("INSERT INTO main.type_inventory_state(singleton,mode) VALUES (1,?)", (mode,))
    _store._require_type_shape(con, complete=True)


def _project_workspace_schema(con: sqlite3.Connection) -> None:
    """Own project identities additively; preserve legacy bindings verbatim."""
    if not con.in_transaction:
        raise ValueError("project workspace migration requires an owned transaction")
    require_ledger(con, version=14)
    for ddl in _store.PROJECT_TABLES.values():
        con.execute(ddl)
    legacy = con.execute("SELECT 1 FROM main.sqlite_schema WHERE type='table' AND name='program_binding'").fetchone()
    if legacy:
        for source_path, locator, program in con.execute("SELECT source_path,locator,program FROM program_binding").fetchall():
            if not locator or not program:
                # Keep incomplete historical bindings intact for targeted validation.
                continue
            provider = "project-api" if str(locator).startswith(("http://", "https://")) else "legacy-project"
            workspace_id = _store.resolve_workspace(con, str(locator), provider)
            _store.bind_analysis_instance(con, workspace_id, str(locator), str(program),
                                          {"status": "historical-unvalidated"}, source_path=str(source_path))


MIGRATIONS: list[Migration] = [
    Migration(1, "baseline", _baseline),
    Migration(2, "analyzer_identity", _analyzer_identity),
    Migration(3, "basis_supersession", _basis_supersession),
    Migration(4, "match_review", _match_review),
    Migration(5, "function_storage", _function_storage),
    Migration(6, "typed_fields", _typed_fields),
    Migration(7, "matching_evidence", _matching_evidence),
    Migration(8, "pcode_channel", _pcode_channel),
    Migration(9, "match_metadata", _match_metadata),
    Migration(10, "stabs_schema_ownership", _stabs_schema_ownership),
    Migration(11, "decomp_schema_ownership", _decomp_schema_ownership),
    Migration(12, "convention_schema_ownership", _convention_schema_ownership),
    Migration(13, "type_schema_ownership", _type_schema_ownership),
    Migration(14, "admission", _admission),
    Migration(15, "project_workspaces", _project_workspace_schema),
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


def require_ledger(con: sqlite3.Connection, *, version: int) -> None:
    """Inspect an exact supported ledger prefix, including its column shape.

    NULL historic basis hashes remain valid. SQL/I/O errors propagate unchanged.
    This helper never initializes schema or takes transaction ownership.
    """
    if version not in {step.version for step in MIGRATIONS} or user_version(con) != version:
        raise ValueError(f"incompatible schema version; expected {version}")
    if con.execute("SELECT 1 FROM temp.sqlite_schema WHERE name COLLATE NOCASE = ?", (LEDGER_TABLE,)).fetchone():
        raise ValueError("shadowing migration ledger")
    obj = con.execute(
        "SELECT type,sql FROM main.sqlite_schema WHERE name=?", (LEDGER_TABLE,)
    ).fetchone()
    expected_columns = [
        (0, "version", "INTEGER", 0, None, 1, 0),
        (1, "name", "TEXT", 1, None, 0, 0),
        (2, "applied_at", "TEXT", 1, None, 0, 0),
        (3, "basis_hash", "TEXT", 0, None, 0, 0),
    ]
    if obj is None or obj[0] != "table" or [tuple(row) for row in con.execute(
        "PRAGMA main.table_xinfo(schema_migration)"
    )] != expected_columns:
        raise ValueError("missing or malformed migration ledger")
    rows = con.execute("SELECT version, name FROM main.schema_migration ORDER BY version").fetchall()
    expected = [(step.version, step.name) for step in MIGRATIONS if step.version <= version]
    legacy_admission = any(v == 4 and name == "admission" for v, name in rows)
    if legacy_admission and version >= 4:
        # The standalone NVMe branch used schema version 4 for admission,
        # while integration used it for match review. Preserve its immutable
        # ledger entry and recognize only that exact known alternate lineage.
        expected = [(v, "admission" if v == 4 else name) for v, name in expected]
        _require_admission_shape(con)
        if version >= 5:
            from .match_review_schema import _require_objects

            _require_objects(con)
    if [tuple(row) for row in rows] != expected:
        raise ValueError("inconsistent migration ledger")


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
    if registry is MIGRATIONS and current == 4 and goal >= 5 and _has_legacy_admission_lineage(con):
        # The standalone NVMe lineage spent version 4 on admission. Install
        # integration's missing v4 match-review schema as an idempotent,
        # owned transaction before applying versions 5..13. Its original
        # version-4 ledger row remains untouched and is checked as a known
        # alternate lineage by require_ledger().
        try:
            con.execute("BEGIN IMMEDIATE")
            now = user_version(con)
            if now == 4 and _has_legacy_admission_lineage(con):
                _require_admission_shape(con)
                _match_review(con)
            if user_version(con) == now:
                con.execute("COMMIT")
            else:
                _rollback(con)
            current = user_version(con)
        except sqlite3.OperationalError as exc:
            _rollback(con)
            if current >= LEDGER_VERSION and _store._is_lock_or_readonly(exc):
                return applied
            raise
        except BaseException:
            _rollback(con)
            raise
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
