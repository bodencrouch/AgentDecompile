"""SQLite store for cross-build function identity.

The central idea is `logical_function`: an identity that exists independently of
any binary. Each `identity` row binds one concrete function in one binary to a
logical function, with the evidence and confidence that produced the binding.

There is no default database path. Callers pass the store file they own.
This module owns baseline DDL; ``migrations`` owns versioned initialization.

New manifest roles are ``donor`` and ``member``. Read-side consumers also
recognize the legacy ``anchor`` role. NULL and unknown stored roles retain their
historical meaning; connection admission does not normalize or constrain them.
"""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3

STABS_TYPE_DDL = """
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
)
"""
STABS_INDEX_SQL = {
    "ix_stabs_type_bin": "CREATE INDEX IF NOT EXISTS ix_stabs_type_bin ON stabs_type(binary_id, kind)",
    "ix_stabs_type_src": "CREATE INDEX IF NOT EXISTS ix_stabs_type_src ON stabs_type(binary_id, source_file)",
}
STABS_FUNC_INDEX_SQL = "CREATE INDEX IF NOT EXISTS ix_func_srcfile ON func(binary_id, source_file)"
STABS_FUNC_COLUMNS = (
    ("source_file", "TEXT"), ("object_file", "TEXT"),
    ("stabs_name", "TEXT"), ("stabs_type", "TEXT"),
)

DECOMP_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS decomp (
    binary_id     INTEGER NOT NULL,
    addr          INTEGER NOT NULL,
    ok            INTEGER,
    n_tokens      INTEGER,
    n_lines       INTEGER,
    max_nest      INTEGER,
    n_calls       INTEGER,
    n_locals      INTEGER,
    n_deref       INTEGER,
    n_index       INTEGER,
    n_field       INTEGER,
    ctrl          TEXT,
    ops           TEXT,
    skeleton_hash TEXT,
    ast_fingerprint TEXT,
    PRIMARY KEY (binary_id, addr)
)
"""
DECOMP_INDEX_SQL = "CREATE INDEX IF NOT EXISTS ix_decomp_bin ON decomp(binary_id)"
DECOMP_COMPAT_STATE_DDL = """
CREATE TABLE decomp_schema_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode TEXT NOT NULL CHECK (mode IN ('absent', 'skeleton_hash', 'ast_fingerprint'))
)
"""
# Only declarations actually emitted by historical CREATE / ADD COLUMN paths.
_DECOMP_LEGACY_DDL = DECOMP_TABLE_DDL.replace("    ast_fingerprint TEXT,\n", "")
_DECOMP_ALTER_DDL = _DECOMP_LEGACY_DDL.rstrip().removesuffix(")") + ", ast_fingerprint TEXT)"
_DECOMP_COLUMNS = ("binary_id", "addr", "ok", "n_tokens", "n_lines", "max_nest",
                   "n_calls", "n_locals", "n_deref", "n_index", "n_field",
                   "ctrl", "ops", "skeleton_hash", "ast_fingerprint")

CONVENTION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS func_convention_derived (
    binary_id     INTEGER NOT NULL,
    addr          INTEGER NOT NULL,
    deco_class    TEXT NOT NULL,
    stack_bytes   INTEGER,
    fastcall_n    INTEGER,
    class_source  TEXT NOT NULL,
    n_source      TEXT NOT NULL,
    PRIMARY KEY (binary_id, addr)
);
"""

TYPE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ghidra_type (
    binary_id   INTEGER NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    size        INTEGER,
    definition  TEXT NOT NULL,
    n_fields    INTEGER,
    origin      TEXT,
    PRIMARY KEY (binary_id, name, kind)
)
"""
TYPE_INDEX_SQL = "CREATE INDEX IF NOT EXISTS ix_ghidra_type_bin ON ghidra_type(binary_id)"
TYPE_ORIGIN_DDL = """
CREATE TABLE IF NOT EXISTS ghidra_type_origin (
    binary_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    donor_slug TEXT NOT NULL,
    donor_game TEXT,
    size INTEGER,
    PRIMARY KEY (binary_id, name)
)
"""
TYPE_INVENTORY_STATE_DDL = """
CREATE TABLE type_inventory_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode TEXT NOT NULL CHECK (mode IN ('absent', 'installed'))
)
"""
_TYPE_LEGACY_DDL = TYPE_TABLE_DDL.replace("    origin      TEXT,\n", "")
_TYPE_ALTER_DDL = _TYPE_LEGACY_DDL.rstrip().removesuffix(")") + ", origin TEXT)"
# Migration 6 remains the installer. This declaration is inspection data only.
TYPE_FIELD_DDL = """CREATE TABLE IF NOT EXISTS ghidra_field (
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
    )"""
_TYPE_COLUMN_SHAPES = {
    "ghidra_type": [(i, name, "INTEGER" if i in {0, 3, 5} else "TEXT",
                     int(i in {0, 1, 2, 4}), None, i + 1 if i < 3 else 0, 0)
                    for i, name in enumerate(("binary_id", "name", "kind", "size", "definition", "n_fields", "origin"))],
    "ghidra_type_origin": [(i, name, "INTEGER" if i in {0, 4} else "TEXT",
                            int(i < 3), None, i + 1 if i < 2 else 0, 0)
                           for i, name in enumerate(("binary_id", "name", "donor_slug", "donor_game", "size"))],
    "ghidra_field": [(i, name, "INTEGER" if i in {0, 2, 3, 4, 10} else "TEXT",
                      int(i < 7 or i == 11), None, i + 1 if i < 3 else 0, 0)
                     for i, name in enumerate(("binary_id", "type_name", "ordinal", "offset", "size", "name",
                                               "dt_kind", "pointee_type", "composite_type", "element_type",
                                               "array_count", "type_json"))],
    "type_inventory_state": [(0, "singleton", "INTEGER", 0, None, 1, 0),
                             (1, "mode", "TEXT", 1, None, 0, 0)],
}

SCHEMA = f"""
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

{STABS_TYPE_DDL.strip()};
{STABS_INDEX_SQL["ix_stabs_type_bin"]};
{STABS_INDEX_SQL["ix_stabs_type_src"]};

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


class SchemaCompatibilityError(ValueError):
    """The selected store cannot be admitted with this schema contract."""

    def __init__(self, path: pathlib.Path, observed: int, supported: int, reason: str) -> None:
        super().__init__(
            f"Corpus store {path.resolve()}: observed schema version {observed}, "
            f"supported version {supported}: {reason}. Use the existing 8080 "
            "workbench action catalog for migration under its ownership/admission "
            "checks; no migration is performed by read-only admission."
        )


def _require_stabs_shape(con: sqlite3.Connection, *, complete: bool) -> None:
    """Inspect main's declared STABS objects; never repair an observed shape.

    The migration may admit missing additive fields/indexes. Writers require
    the complete postcondition. Unrelated func extensions are left untouched.
    """
    from .match_review_schema import _normalized

    if con.execute(
        "SELECT 1 FROM temp.sqlite_schema WHERE name COLLATE NOCASE IN ('func','stabs_type')"
    ).fetchone():
        raise ValueError("shadowing STABS temp object")
    rows = [tuple(row) for row in con.execute(
        "SELECT type,name,tbl_name,sql FROM main.sqlite_schema"
    )]
    objects = {row[1]: row for row in rows}
    # Triggers have a separate name namespace. A dict alone could hide a
    # trigger sharing a declared index/table name, depending on schema order.
    declared = {"func", "stabs_type", "ix_func_srcfile", *STABS_INDEX_SQL}
    ascii_lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    for _, name, _, _ in rows:
        if name.translate(ascii_lower) in declared and name not in declared:
            raise ValueError(f"unsupported STABS object spelling {name}")
    for name in declared:
        if sum(row[1] == name for row in rows) > 1:
            raise ValueError(f"occupied STABS object name {name}")
    for name in ("func", "stabs_type"):
        obj = objects.get(name)
        if obj is None or obj[0] != "table" or not obj[3] or not obj[3].startswith("CREATE TABLE"):
            raise ValueError(f"missing or unsupported STABS table {name}")
    if _normalized(objects["stabs_type"][3]) != _normalized(STABS_TYPE_DDL):
        raise ValueError("unsupported STABS table stabs_type")
    columns = {row[1]: tuple(row)[2:] for row in con.execute("PRAGMA main.table_xinfo(func)")}
    # type, notnull, default, primary-key ordinal, hidden/generated flag
    expected = {"binary_id": ("INTEGER", 1, None, 0, 0)}
    expected.update({name: (typ, 0, None, 0, 0) for name, typ in STABS_FUNC_COLUMNS})
    for name in columns:
        if name.translate(ascii_lower) in expected and name not in expected:
            raise ValueError(f"unsupported STABS column spelling func.{name}")
    for name, shape in expected.items():
        if name not in columns and not complete and name in {"stabs_name", "stabs_type"}:
            continue
        if columns.get(name) != shape:
            raise ValueError(f"missing or unsupported STABS column func.{name}")
    indexes = {**STABS_INDEX_SQL, "ix_func_srcfile": STABS_FUNC_INDEX_SQL}
    for name, sql in indexes.items():
        obj = objects.get(name)
        if obj is None and not complete:
            continue
        owner = "func" if name == "ix_func_srcfile" else "stabs_type"
        if obj is None or obj[0] != "index" or obj[2] != owner or not obj[3] or _normalized(obj[3]) != _normalized(sql):
            raise ValueError(f"missing or unsupported STABS index {name}")
    for kind, name, owner, sql in rows:
        if owner != "stabs_type" or kind == "table" or name in STABS_INDEX_SQL:
            continue
        if kind == "index" and sql is None and name.startswith("sqlite_autoindex_stabs_type_"):
            continue  # The exact table declaration above owns this UNIQUE key.
        raise ValueError(f"undeclared STABS object {name}")


def require_stabs_schema(con: sqlite3.Connection) -> None:
    """Require current ledger and STABS postconditions without changing *con*."""
    from . import migrations

    version = migrations.user_version(con)
    try:
        migrations.require_ledger(con, version=migrations.SCHEMA_VERSION)
        _require_stabs_shape(con, complete=True)
    except ValueError as exc:
        raise ValueError(
            f"STABS schema required: observed version {version}, "
            f"supported version {migrations.SCHEMA_VERSION}: {exc}"
        ) from exc


def _decomp_sql(sql: str) -> str:
    """Known declarations only: tolerate SQLite ADD COLUMN punctuation spacing."""
    from .match_review_schema import _normalized

    return re.sub(r"\s*([(),])\s*", r"\1", _normalized(sql))


def _decomp_objects(con: sqlite3.Connection) -> dict:
    """Inspect reserved main names before any potentially shadowed access."""
    reserved = {"decomp", "decomp_schema_state", "schema_migration", "ix_decomp_bin"}
    if con.execute(
        "SELECT 1 FROM temp.sqlite_schema WHERE name COLLATE NOCASE IN "
        "('decomp','decomp_schema_state','schema_migration','ix_decomp_bin')"
    ).fetchone():
        raise ValueError("shadowing decomp temp object")
    rows = [tuple(row) for row in con.execute(
        "SELECT type,name,tbl_name,sql FROM main.sqlite_schema"
    )]
    ascii_lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    for _, name, _, _ in rows:
        if name.translate(ascii_lower) in reserved and name not in reserved:
            raise ValueError(f"unsupported decomp object spelling {name}")
    for name in reserved:
        if sum(row[1] == name for row in rows) > 1:
            raise ValueError(f"occupied decomp object name {name}")
    for kind, name, owner, sql in rows:
        if owner not in {"decomp", "decomp_schema_state"} or kind == "table":
            continue
        if kind == "index" and owner == "decomp" and (
            name == "ix_decomp_bin" or (sql is None and name == "sqlite_autoindex_decomp_1")
        ):
            continue
        raise ValueError(f"undeclared decomp object {name}")
    return {row[1]: row for row in rows}


def _require_decomp_shape(con: sqlite3.Connection, *, complete: bool) -> str | None:
    """Bounded physical admission; incomplete means the pre-v11 shapes only."""
    objects = _decomp_objects(con)
    state = objects.get("decomp_schema_state")
    if not complete and state is not None:
        raise ValueError("unexpected pre-v11 decomp_schema_state")
    obj = objects.get("decomp")
    if obj is None:
        if complete or objects.get("ix_decomp_bin") is not None:
            raise ValueError("missing decomp table")
        return None
    allowed = {_decomp_sql(DECOMP_TABLE_DDL), _decomp_sql(_DECOMP_ALTER_DDL)}
    if not complete:
        allowed.add(_decomp_sql(_DECOMP_LEGACY_DDL))
    if obj[0] != "table" or not obj[3] or _decomp_sql(obj[3]) not in allowed:
        raise ValueError("unsupported decomp table shape (including P-code extensions)")
    cols = [tuple(row) for row in con.execute("PRAGMA main.table_xinfo(decomp)")]
    expected = [
        (i, name, "INTEGER" if i < 11 else "TEXT", int(i < 2), None,
         i + 1 if i < 2 else 0, 0)
        for i, name in enumerate(_DECOMP_COLUMNS)
    ]
    if cols != expected and (complete or cols != expected[:-1]):
        raise ValueError("unsupported decomp column shape")
    index = objects.get("ix_decomp_bin")
    if index is None:
        if complete:
            raise ValueError("missing decomp index ix_decomp_bin")
    elif (index[0] != "index" or index[2] != "decomp" or not index[3]
          or _decomp_sql(index[3]) != _decomp_sql(DECOMP_INDEX_SQL)):
        raise ValueError("unsupported decomp index ix_decomp_bin")
    if not complete:
        return "ast_fingerprint" if len(cols) == 15 else "skeleton_hash"
    if (state is None or state[0] != "table" or not state[3]
            or _decomp_sql(state[3]) != _decomp_sql(DECOMP_COMPAT_STATE_DDL)):
        raise ValueError("missing or unsupported decomp_schema_state")
    if [tuple(row) for row in con.execute("PRAGMA main.table_xinfo(decomp_schema_state)")] != [
        (0, "singleton", "INTEGER", 0, None, 1, 0), (1, "mode", "TEXT", 1, None, 0, 0)
    ]:
        raise ValueError("unsupported decomp_schema_state columns")
    rows = [tuple(row) for row in con.execute("SELECT singleton,mode FROM main.decomp_schema_state")]
    if len(rows) != 1 or rows[0][0] != 1 or rows[0][1] not in {"absent", "skeleton_hash", "ast_fingerprint"}:
        raise ValueError("decomp_schema_state requires exactly one valid singleton")
    mode = rows[0][1]
    if mode == "absent" and con.execute("SELECT 1 FROM main.decomp LIMIT 1").fetchone():
        raise ValueError("decomp absent state contains rows")
    # Integrity cost: proving all ASTs NULL may scan the table in skeleton mode.
    if mode == "skeleton_hash" and con.execute(
        "SELECT 1 FROM main.decomp WHERE ast_fingerprint IS NOT NULL LIMIT 1"
    ).fetchone():
        raise ValueError("decomp skeleton state contains non-NULL AST values")
    return None if mode == "absent" else mode


def decomp_read_state(con: sqlite3.Connection) -> str | None:
    """Pure bounded v9/v10/v11/v12/v13 selector; NULL/empty ASTs never fall back."""
    from . import migrations

    version = migrations.user_version(con)
    try:
        _decomp_objects(con)
        if version not in {9, 10, 11, 12, 13}:
            raise ValueError("unsupported reader version")
        migrations.require_ledger(con, version=version)
        return _require_decomp_shape(con, complete=version in {11, 12, 13})
    except ValueError as exc:
        raise ValueError(f"decomp schema required: observed version {version}, supported versions 9/10/11/12/13: {exc}") from exc


def require_decomp_schema(con: sqlite3.Connection) -> None:
    """Pure current writer admission; never migrate or commit caller work."""
    from . import migrations

    version = migrations.user_version(con)
    try:
        _decomp_objects(con)
        migrations.require_ledger(con, version=migrations.SCHEMA_VERSION)
        _require_stabs_shape(con, complete=True)
        _require_decomp_shape(con, complete=True)
    except ValueError as exc:
        raise ValueError(
            f"decomp schema required: observed version {version}, "
            f"supported version {migrations.SCHEMA_VERSION}: {exc}"
        ) from exc


def _require_convention_shape(con: sqlite3.Connection, *, complete: bool) -> None:
    """Inspect the historical declaration and its unqualified derivation inputs.

    Missing storage is admissible only before migration 12. No stored value is
    interpreted as ABI evidence, and unrelated table extensions remain untouched.
    """
    reserved = {"binary", "func", "identity", "schema_migration", "func_convention_derived"}
    marks = ",".join("?" for _ in reserved)
    if con.execute(
        f"SELECT 1 FROM temp.sqlite_schema WHERE name COLLATE NOCASE IN ({marks})"
        " OR tbl_name COLLATE NOCASE = 'func_convention_derived'",
        tuple(reserved),
    ).fetchone():
        raise ValueError("shadowing convention temp object")
    rows = [tuple(row) for row in con.execute(
        "SELECT type,name,tbl_name,sql FROM main.sqlite_schema"
    )]
    ascii_lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    for _, name, _, _ in rows:
        if name.translate(ascii_lower) in reserved and name not in reserved:
            raise ValueError(f"unsupported convention object spelling {name}")
    for name in reserved:
        if sum(row[1] == name for row in rows) > 1:
            raise ValueError(f"occupied convention object name {name}")
    objects = {row[1]: row for row in rows}
    for name in reserved - {"func_convention_derived"}:
        obj = objects.get(name)
        if (obj is None or obj[0] != "table" or not obj[3]
                or not obj[3].upper().startswith("CREATE TABLE")):
            raise ValueError(f"missing or unsupported convention input table {name}")
    obj = objects.get("func_convention_derived")
    if obj is None:
        if complete:
            raise ValueError("missing convention table func_convention_derived")
        return
    if (obj[0] != "table" or not obj[3]
            or _decomp_sql(obj[3]) != _decomp_sql(CONVENTION_TABLE_DDL)):
        raise ValueError("unsupported convention table func_convention_derived")
    columns = ("binary_id", "addr", "deco_class", "stack_bytes", "fastcall_n", "class_source", "n_source")
    expected = [(i, name, "TEXT" if i in {2, 5, 6} else "INTEGER",
                 int(i not in {3, 4}), None, i + 1 if i < 2 else 0, 0)
                for i, name in enumerate(columns)]
    if [tuple(row) for row in con.execute("PRAGMA main.table_xinfo(func_convention_derived)")] != expected:
        raise ValueError("unsupported convention column shape")
    for kind, name, owner, sql in rows:
        if owner != "func_convention_derived" or kind == "table":
            continue
        if kind == "index" and name == "sqlite_autoindex_func_convention_derived_1" and sql is None:
            continue
        raise ValueError(f"undeclared convention object {name}")


def require_convention_schema(con: sqlite3.Connection) -> None:
    """Pure v13 applying admission; never migrate or commit caller work."""
    from . import migrations

    version = migrations.user_version(con)
    try:
        _require_convention_shape(con, complete=True)
        migrations.require_ledger(con, version=13)
        _require_stabs_shape(con, complete=True)
        _require_decomp_shape(con, complete=True)
    except ValueError as exc:
        raise ValueError(
            f"convention schema required: observed version {version}, supported version 13: {exc}"
        ) from exc


def _require_type_shape(con: sqlite3.Connection, *, complete: bool) -> str:
    """Inspect only owned type objects and declared inputs; never install them."""
    owned = {"ghidra_type", "ghidra_type_origin", "ghidra_field", "type_inventory_state"}
    reserved = owned | {"binary", "schema_migration", "ix_ghidra_type_bin"}
    marks = ",".join("?" for _ in reserved)
    owners = ",".join("?" for _ in owned)
    if con.execute(
        f"SELECT 1 FROM temp.sqlite_schema WHERE name COLLATE NOCASE IN ({marks})"
        f" OR tbl_name COLLATE NOCASE IN ({owners})", (*reserved, *owned),
    ).fetchone():
        raise ValueError("shadowing type temp object")
    rows = [tuple(row) for row in con.execute("SELECT type,name,tbl_name,sql FROM main.sqlite_schema")]
    ascii_lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    for _, name, _, _ in rows:
        if name.translate(ascii_lower) in reserved and name not in reserved:
            raise ValueError(f"unsupported type object spelling {name}")
    for name in reserved:
        if sum(row[1] == name for row in rows) > 1:
            raise ValueError(f"occupied type object name {name}")
    objects = {row[1]: row for row in rows}
    for name in ("binary", "schema_migration"):
        obj = objects.get(name)
        if obj is None or obj[0] != "table" or not obj[3] or not obj[3].startswith("CREATE TABLE"):
            raise ValueError(f"missing or unsupported type input table {name}")
    if not complete and "type_inventory_state" in objects:
        raise ValueError("unexpected pre-v13 type_inventory_state")
    if "ghidra_type_origin" in objects and "ghidra_type" not in objects:
        raise ValueError("type origin without parent ghidra_type")
    declarations = {"ghidra_type": TYPE_TABLE_DDL, "ghidra_type_origin": TYPE_ORIGIN_DDL,
                    "ghidra_field": TYPE_FIELD_DDL, "type_inventory_state": TYPE_INVENTORY_STATE_DDL}
    for name, ddl in declarations.items():
        obj = objects.get(name)
        if obj is None and not complete and name != "ghidra_field":
            continue
        allowed = {_decomp_sql(ddl)}
        if name == "ghidra_type":
            allowed.add(_decomp_sql(_TYPE_ALTER_DDL))
            if not complete:
                allowed.add(_decomp_sql(_TYPE_LEGACY_DDL))
        if obj is None or obj[0] != "table" or not obj[3] or _decomp_sql(obj[3]) not in allowed:
            raise ValueError(f"missing or unsupported type table {name}")
        columns = [tuple(row) for row in con.execute(f"PRAGMA main.table_xinfo({name})")]
        expected = _TYPE_COLUMN_SHAPES[name]
        if columns != expected and not (not complete and name == "ghidra_type" and columns == expected[:-1]):
            raise ValueError(f"unsupported type columns {name}")
    index = objects.get("ix_ghidra_type_bin")
    if index is None:
        if complete:
            raise ValueError("missing type index ix_ghidra_type_bin")
    elif ("ghidra_type" not in objects or index[0] != "index" or index[2] != "ghidra_type"
          or not index[3] or _decomp_sql(index[3]) != _decomp_sql(TYPE_INDEX_SQL)):
        raise ValueError("unsupported type index ix_ghidra_type_bin")
    for kind, name, owner, sql in rows:
        if owner not in owned or kind == "table":
            continue
        if kind == "index" and owner == "ghidra_type" and name == "ix_ghidra_type_bin":
            continue
        if (kind == "index" and owner != "type_inventory_state"
                and name == f"sqlite_autoindex_{owner}_1" and sql is None):
            continue
        raise ValueError(f"undeclared type object {name}")
    if not complete:
        return "installed" if "ghidra_type" in objects else "absent"
    state = [tuple(row) for row in con.execute("SELECT singleton,mode FROM main.type_inventory_state")]
    if len(state) != 1 or state[0][0] != 1 or state[0][1] not in {"absent", "installed"}:
        raise ValueError("type_inventory_state requires exactly one valid singleton")
    if state[0][1] == "absent":
        for name in ("ghidra_type", "ghidra_type_origin"):
            if con.execute(f"SELECT 1 FROM main.{name} LIMIT 1").fetchone():
                raise ValueError(f"type absent state contains rows in {name}")
    return state[0][1]


def require_type_schema(con: sqlite3.Connection) -> None:
    """Pure current13 admission, including prior owners and type dependencies."""
    from . import migrations

    version = migrations.user_version(con)
    try:
        _require_type_shape(con, complete=True)
        migrations.require_ledger(con, version=13)
        _require_stabs_shape(con, complete=True)
        _require_decomp_shape(con, complete=True)
        _require_convention_shape(con, complete=True)
    except ValueError as exc:
        raise ValueError(f"type schema required: observed version {version}, supported version 13: {exc}") from exc


def type_inventory_state(con: sqlite3.Connection) -> str:
    """Return the admitted global installation state; this is not capture proof."""
    require_type_schema(con)
    return con.execute("SELECT mode FROM main.type_inventory_state WHERE singleton=1").fetchone()[0]


def type_inventory_available(con: sqlite3.Connection) -> bool:
    """Gate current/future readers; preserve physical presence on raw history."""
    from . import migrations

    if migrations.user_version(con) >= 13:
        return type_inventory_state(con) == "installed"
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ghidra_type'").fetchone() is not None


def connect(
    path: pathlib.Path | str, *, read_only: bool = False, create: bool = True
) -> sqlite3.Connection:
    """Open the selected corpus store. Path is required; no fallback is chosen.

    Writable opens use canonical migrations and the per-connect recovery-family
    backfill, retaining their transaction and lock-contention semantics. Set
    ``create=False`` to require an existing file atomically at SQLite open.

    ``read_only=True`` always uses ``mode=ro``, never creates, and admits only
    the current version with the complete matching migration ledger. It never
    calls migrations or data backfills. Future versions refuse in both modes
    before journal changes or migration/backfill writes.
    """
    from . import migrations

    dest = pathlib.Path(path)
    if read_only or not create:
        mode = "ro" if read_only else "rw"
        con = sqlite3.connect(dest.resolve().as_uri() + f"?mode={mode}", uri=True, timeout=30)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(dest, timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.row_factory = sqlite3.Row
        version = migrations.user_version(con)
        supported = migrations.SCHEMA_VERSION
        if version > supported or (read_only and version != supported):
            raise SchemaCompatibilityError(dest, version, supported, "incompatible schema version")
        if read_only:
            try:
                require_stabs_schema(con)
                require_decomp_schema(con)
                require_convention_schema(con)
                require_type_schema(con)
            except ValueError as exc:
                raise SchemaCompatibilityError(dest, version, supported, str(exc)) from exc
        else:
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


class SchemaTooNewError(RuntimeError):
    """A writer older than the store's schema refused to open it for writing."""


def remove_binary(
    con: sqlite3.Connection,
    *,
    repo_path: str | None = None,
    slug: str | None = None,
) -> dict:
    """Remove one binary using the bounded v9/v10/v11/v12/v13 registry; preserve logical rows.

    With a caller-owned transaction, the returned receipt is provisional until
    the caller commits. This operation releases only its own savepoint.
    """
    from .delete_registry import remove_binary as remove_registered_rows

    return remove_registered_rows(con, repo_path=repo_path, slug=slug)


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
        ("kind", "TEXT"),
        ("confidence", "REAL"),
        ("algorithm", "TEXT"),
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
