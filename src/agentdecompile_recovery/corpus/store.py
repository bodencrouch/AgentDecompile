"""SQLite store for cross-build function identity.

The central idea is `logical_function`: an identity that exists independently of
any binary. Each `identity` row binds one concrete function in one binary to a
logical function, with the evidence and confidence that produced the binding.

There is no default database path. Callers pass the store file they own.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS binary (
    id            INTEGER PRIMARY KEY,
    repo_path     TEXT UNIQUE NOT NULL,
    slug          TEXT UNIQUE NOT NULL,
    game          TEXT,
    platform      TEXT,
    variant       TEXT,
    language_id   TEXT,
    arch          TEXT,
    bits          INTEGER,
    format        TEXT,
    md5           TEXT,
    image_base    INTEGER,
    func_count    INTEGER,
    named_count   INTEGER,
    role          TEXT,
    recovery_family TEXT
);

CREATE TABLE IF NOT EXISTS func (
    id                INTEGER PRIMARY KEY,
    binary_id         INTEGER NOT NULL REFERENCES binary(id),
    addr              INTEGER NOT NULL,
    name              TEXT,
    namespace         TEXT,
    source            TEXT,
    size              INTEGER,
    ranges            INTEGER,
    is_thunk          INTEGER,
    thunked_to        INTEGER,
    calling_convention TEXT,
    return_type       TEXT,
    param_count       INTEGER,
    param_types       TEXT,
    stack_frame_size  INTEGER,
    stack_param_size  INTEGER,
    stack_local_size  INTEGER,
    plate             TEXT,
    signature         TEXT,
    n_instr           INTEGER,
    n_blocks          INTEGER,
    n_edges           INTEGER,
    back_edges        INTEGER,
    cyclomatic        INTEGER,
    n_callees         INTEGER,
    indirect_calls    INTEGER,
    data_refs         INTEGER,
    mnem              TEXT,
    strings           TEXT,
    consts            TEXT,
    ext_calls         TEXT,
    block_hashes      TEXT,
    canon_class       TEXT,
    canon_method      TEXT,
    canon_key         TEXT,
    canon_arity       INTEGER,
    name_origin       TEXT,
    source_file       TEXT,
    object_file       TEXT,
    UNIQUE(binary_id, addr)
);
CREATE INDEX IF NOT EXISTS ix_func_bin      ON func(binary_id);
CREATE INDEX IF NOT EXISTS ix_func_canon    ON func(canon_key);
CREATE INDEX IF NOT EXISTS ix_func_class    ON func(canon_class);
CREATE INDEX IF NOT EXISTS ix_func_bin_addr ON func(binary_id, addr);
CREATE INDEX IF NOT EXISTS ix_func_priority_cover
    ON func(binary_id, addr, size, n_instr, name);

CREATE TABLE IF NOT EXISTS calledge (
    binary_id   INTEGER NOT NULL,
    caller_addr INTEGER NOT NULL,
    callee_addr INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_edge_caller ON calledge(binary_id, caller_addr);
CREATE INDEX IF NOT EXISTS ix_edge_callee ON calledge(binary_id, callee_addr);

CREATE TABLE IF NOT EXISTS logical_function (
    id           INTEGER PRIMARY KEY,
    canon_key    TEXT,
    canon_class  TEXT,
    canon_method TEXT,
    game         TEXT,
    best_name    TEXT,
    best_signature TEXT,
    source_file  TEXT,
    object_file  TEXT,
    n_members    INTEGER,
    notes        TEXT
);
CREATE INDEX IF NOT EXISTS ix_logical_key ON logical_function(canon_key);

CREATE TABLE IF NOT EXISTS identity (
    logical_id  INTEGER NOT NULL REFERENCES logical_function(id),
    binary_id   INTEGER NOT NULL,
    addr        INTEGER NOT NULL,
    confidence  REAL,
    method      TEXT,
    evidence    TEXT,
    PRIMARY KEY (binary_id, addr)
);
CREATE INDEX IF NOT EXISTS ix_identity_logical ON identity(logical_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_identity_bin_addr ON identity(binary_id, addr);

CREATE TABLE IF NOT EXISTS stabs_type (
    id INTEGER PRIMARY KEY,
    binary_id INTEGER NOT NULL,
    source_file TEXT,
    object_file TEXT,
    name TEXT NOT NULL,
    kind TEXT,
    stab TEXT NOT NULL,
    func_addr INTEGER,
    UNIQUE(binary_id, source_file, name, kind, stab, func_addr)
);
CREATE INDEX IF NOT EXISTS ix_stabs_type_bin ON stabs_type(binary_id, kind);
CREATE INDEX IF NOT EXISTS ix_stabs_type_src ON stabs_type(binary_id, source_file);

CREATE TABLE IF NOT EXISTS match (
    id          INTEGER PRIMARY KEY,
    run         TEXT,
    src_binary  INTEGER, src_addr INTEGER,
    dst_binary  INTEGER, dst_addr INTEGER,
    score       REAL,
    margin      REAL,
    evidence    TEXT,
    status      TEXT,
    relation    TEXT NOT NULL DEFAULT 'one_to_one',
    src_end     INTEGER,
    dst_end     INTEGER
);
CREATE INDEX IF NOT EXISTS ix_match_src ON match(run, src_binary, src_addr);
CREATE INDEX IF NOT EXISTS ix_match_dst ON match(run, dst_binary, dst_addr);
CREATE INDEX IF NOT EXISTS ix_match_status_score ON match(status, score, id);

CREATE TABLE IF NOT EXISTS eval (
    run       TEXT,
    metric    TEXT,
    value     REAL,
    detail    TEXT
);
"""


def connect(path: pathlib.Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    """Open (or create) a corpus identity store at *path*. Path is required.

    Schema lives in ``migrations``: the first connection to a new or legacy
    file brings it to ``migrations.SCHEMA_VERSION``; every later connection
    only reads ``PRAGMA user_version`` and touches nothing. The one data step
    that stays per-connect is the ``recovery_family`` backfill, which is
    read-checked, writes only when a row needs it, and commits that write
    itself: the connection returned here holds no transaction.

    ``read_only=True`` opens a ``mode=ro`` handle. It never migrates; on a
    store that has not been migrated yet it raises.
    """
    from . import migrations

    dest = pathlib.Path(path)
    if read_only:
        con = sqlite3.connect(dest.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(dest, timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.row_factory = sqlite3.Row
        if not read_only:
            # Cannot run inside a transaction, so it stays out of the migration.
            con.execute("PRAGMA journal_mode=WAL")
        migrations.apply_pending(con)
        backfill_recovery_family(con)
    except BaseException:
        # This function owns the newly opened handle until it returns.  Failed
        # initialization must not leak it through a retained traceback, even
        # for interruption-like exceptions or when rollback itself fails.
        try:
            if con.in_transaction:
                con.rollback()
        finally:
            con.close()
        raise
    return con


def remove_binary(
    con: sqlite3.Connection,
    *,
    repo_path: str | None = None,
    slug: str | None = None,
) -> dict:
    """Delete one binary and its per-binary rows. Does not drop logical_function."""
    if repo_path:
        row = con.execute("SELECT id, slug, repo_path FROM binary WHERE repo_path=?", (repo_path,)).fetchone()
    elif slug:
        row = con.execute("SELECT id, slug, repo_path FROM binary WHERE slug=?", (slug,)).fetchone()
    else:
        raise ValueError("repo_path or slug is required")
    if row is None:
        raise SystemExit(f"no binary matching {repo_path or slug!r}")
    bid = int(row["id"])
    deleted: dict[str, int] = {}
    for table in ("calledge", "identity", "func_param", "ghidra_field", "func", "stabs_type"):
        cur = con.execute(f"DELETE FROM {table} WHERE binary_id=?", (bid,))
        deleted[table] = cur.rowcount
    deleted["match"] = con.execute(
        "DELETE FROM match WHERE src_binary=? OR dst_binary=?", (bid, bid)
    ).rowcount
    deleted["binary"] = con.execute("DELETE FROM binary WHERE id=?", (bid,)).rowcount
    con.commit()
    return {
        "id": bid,
        "slug": row["slug"],
        "repo_path": row["repo_path"],
        "deleted": deleted,
    }


def ensure_func_columns(con: sqlite3.Connection) -> None:
    cols = {row[1] for row in con.execute("PRAGMA table_info(func)")}
    for col, decl in (
        ("block_hashes", "TEXT"),
        # Canonical basic-block topology.  IDs are local ordinals, never
        # addresses, so this survives rebasing and cross-build layout changes.
        ("cfg_nodes", "TEXT"),
        ("cfg_edges", "TEXT"),
        ("hash_reloc", "TEXT"),
        ("hash_instr", "TEXT"),
        ("hash_mnemonic", "TEXT"),
        ("hash_raw", "TEXT"),
        ("symbol_provenance", "TEXT"),
    ):
        if col not in cols:
            con.execute(f"ALTER TABLE func ADD COLUMN {col} {decl}")
    ensure_binary_columns(con)


def ensure_match_columns(con: sqlite3.Connection) -> None:
    """Keep Correspondence shape additive for existing corpus databases."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(match)")}
    for col, decl in (
        ("relation", "TEXT NOT NULL DEFAULT 'one_to_one'"),
        ("src_end", "INTEGER"),
        ("dst_end", "INTEGER"),
    ):
        if col not in cols:
            con.execute(f"ALTER TABLE match ADD COLUMN {col} {decl}")


# Primary SQLite result codes meaning "the write cannot run right now". Use
# numeric fallbacks because sqlite3 did not expose the named constants on every
# supported Python 3.10 build.
_BACKFILL_SKIP_CODES = frozenset(
    {
        getattr(sqlite3, "SQLITE_BUSY", 5),
        getattr(sqlite3, "SQLITE_LOCKED", 6),
        getattr(sqlite3, "SQLITE_READONLY", 8),
    }
)


def ensure_binary_columns(con: sqlite3.Connection) -> None:
    """Additive binary columns, then the recovery_family data backfill.

    Idempotent: column adds are guarded by ``PRAGMA table_info`` and the
    backfill is read-checked. Callers that hold a connection not opened via
    ``connect()`` may call this directly.
    """
    cols = {row[1] for row in con.execute("PRAGMA table_info(binary)")}
    if "content_sha256" not in cols:
        con.execute("ALTER TABLE binary ADD COLUMN content_sha256 TEXT")
    if "recovery_family" not in cols:
        con.execute("ALTER TABLE binary ADD COLUMN recovery_family TEXT")
    backfill_recovery_family(con)


def backfill_recovery_family(con: sqlite3.Connection) -> int:
    """Give every unclassified binary an isolating family. Data, not schema.

    The family is ``'unclassified:' || substr(content_sha256, 1, 16)``: a
    function of the image bytes, so it is identical however the build rows
    were ingested. Rows still carrying the older rowid form
    (``'unclassified:' || id``) are rewritten; that value moved with build
    order and was never a classification. A row with no ``content_sha256``
    cannot be classified: it is left as it is and counted.

    Returns the number of rows that could not be classified.

    The write owns its transaction. Inside a caller's transaction (migration
    1 runs this under ``BEGIN IMMEDIATE``) it participates and the caller
    commits; otherwise it runs ``BEGIN IMMEDIATE`` / ``UPDATE`` / ``COMMIT``
    itself, so a ``connect()`` never returns holding the write lock and the
    rewrite is durable before the verb starts. Python's implicit transaction
    used to hold that lock for the verb's whole run and roll the rewrite
    back on close (attestation A2).
    """
    # Existing inventories predate explicit recovery-family catalog entries.
    # Keep each such build isolated until an operator supplies a catalog map;
    # format, architecture, and game names are intentionally not classifiers.
    # Read-check first: this runs on every connect(), and an unconditional
    # write here made every concurrent connection contend for the write lock
    # (orchestrator: 5 processes connecting at once -> "database is locked").
    stale = (
        "(recovery_family IS NULL OR trim(recovery_family)='' "
        "OR recovery_family = 'unclassified:' || id)"
    )
    has_hash = "(content_sha256 IS NOT NULL AND trim(content_sha256)<>'')"
    unclassifiable = con.execute(
        f"SELECT COUNT(*) FROM binary WHERE {stale} AND NOT {has_hash}"
    ).fetchone()
    needs = con.execute(
        f"SELECT 1 FROM binary WHERE {stale} AND {has_hash} LIMIT 1"
    ).fetchone()
    if needs:
        # Best-effort backfill. This is data, not schema -- reads work without
        # it -- so a read-only consumer that cannot get the write lock (many
        # concurrent orchestrator watchers hold WAL read locks) must proceed
        # rather than crash. Whichever connection wins the lock backfills it;
        # the value is a function of each row's own content hash, so the
        # winner and the visit order cannot change what gets written. Only
        # the lock/read-only cases are tolerated; any other failure surfaces.
        owns = not con.in_transaction
        try:
            if owns:
                con.execute("BEGIN IMMEDIATE")
            con.execute(
                "UPDATE binary SET recovery_family='unclassified:' || substr(trim(content_sha256), 1, 16) "
                f"WHERE {stale} AND {has_hash}"
            )
            if owns:
                con.execute("COMMIT")
        except sqlite3.OperationalError as exc:
            if owns and con.in_transaction:
                con.execute("ROLLBACK")
            if not _is_lock_or_readonly(exc):
                raise
        except BaseException:
            if owns and con.in_transaction:
                con.execute("ROLLBACK")
            raise
    return int(unclassifiable[0]) if unclassifiable else 0


def _is_lock_or_readonly(exc: sqlite3.OperationalError) -> bool:
    code = getattr(exc, "sqlite_errorcode", None)
    if code is not None:
        # Extended result codes retain their primary class in the low byte.
        return (int(code) & 0xFF) in _BACKFILL_SKIP_CODES

    # Python 3.10 did not attach sqlite_errorcode. Match only SQLite's complete
    # canonical messages; arbitrary identifiers containing "busy" or "locked"
    # are schema errors and must propagate.
    text = str(exc).lower()
    if text in {
        "database is locked",
        "database table is locked",
        "database schema is locked",
        "database is busy",
        "attempt to write a readonly database",
        "attempt to write a read-only database",
        "readonly database",
        "read-only database",
    }:
        return True
    return text.startswith(("database table is locked: ", "database schema is locked: "))


def ensure_priority_index(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE INDEX IF NOT EXISTS ix_func_priority_cover
               ON func(binary_id, addr, size, n_instr, name)"""
    )


def j(x) -> str | None:
    return None if x is None else json.dumps(x, separators=(",", ":"))
