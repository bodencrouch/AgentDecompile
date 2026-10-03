"""Persist decompiled-C shape features into a store or part file."""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from contextlib import contextmanager
from itertools import count
from pathlib import Path

from .decompile_shape import features
from .store import DECOMP_TABLE_DDL, DECOMP_INDEX_SQL, connect, decomp_read_state, require_decomp_schema


# This is deliberately a syntax fingerprint, not a claim that a real compiler
# IR or Ghidra P-code was produced.  The prefix keeps that provenance visible
# when the value crosses the store/API boundary.
_AST_FINGERPRINT_VERSION = "ASTv1:"
_C_KEYWORDS = frozenset(
    "auto break case char const continue default do double else enum extern float"
    " for goto if inline int long register restrict return short signed sizeof"
    " static struct switch typedef union unsigned void volatile while _Bool"
    " _Complex _Imaginary class namespace template true false nullptr"
    .split()
)
_C_TOKEN = re.compile(
    r"(?P<space>\s+)|(?P<comment>//[^\n]*|/\*.*?\*/)|"
    r"(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|"
    r"(?P<number>0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|"
    r"(?P<ident>[A-Za-z_]\w*)|"
    r"(?P<op>>>>=|<<=|->\*|\.\.\.|==|!=|<=|>=|&&|\|\||\+\+|--|->|<<|>>|"
    r"\+=|-=|\*=|/=|%=|&=|\|=|\^=|##|::|[{}()\[\];,?:.~!+\-*/%&|^<>=#])",
    re.S,
)


def syntax_fingerprint(code: str) -> str:
    """Hash normalized C token structure for a cheap semantic-ish fallback.

    Identifiers are intentionally anonymized, while keyword/operator and
    delimiter order is retained.  This is not an AST: preprocessing, parser
    recovery, typedef resolution, and compiler IR transformations are outside
    this lightweight boundary.  It is therefore suitable as corroborating
    evidence only, never as a byte or P-code proof.
    """
    tokens: list[str] = []
    for match in _C_TOKEN.finditer(code):
        kind, value = match.lastgroup, match.group()
        if kind in ("space", "comment"):
            continue
        if kind == "ident":
            if value in _C_KEYWORDS:
                token = f"K:{value}"
            else:
                token = "I"
        elif kind == "number":
            token = "N"
        elif kind == "string":
            token = "S"
        else:
            # Operators and delimiters retain expression/control-flow shape
            # without depending on a guessed symbol table.
            token = f"O:{value}"
        tokens.append(token)

    # Include unmatched source as a stable marker rather than silently making
    # malformed/truncated input collide with a valid token stream.
    covered = sum(len(m.group()) for m in _C_TOKEN.finditer(code))
    marker = "|UNSCANNED|" if covered != len(code) else ""
    canonical = " ".join(tokens) + marker
    digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()
    return f"{_AST_FINGERPRINT_VERSION}{digest}"

PART_SCHEMA = """
CREATE TABLE IF NOT EXISTS decomp_part (
    repo_path     TEXT NOT NULL,
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
    PRIMARY KEY (repo_path, addr)
);
"""

# Import compatibility only; corpus operations obtain schema from migration 11.
MAIN_SCHEMA = DECOMP_TABLE_DDL + ";\n" + DECOMP_INDEX_SQL + ";\n"
_SAVEPOINT_IDS = count()


@contextmanager
def _main_write_scope(con: sqlite3.Connection, *, commit_caller: bool = False):
    """Undo only this operation on failure, if SQLite retains its transaction.

    persist_code intentionally commits caller work on success. Keep its private
    savepoint until that commit so pre-durability commit failure can undo just
    the operation. Never reconstruct a lost transaction or hide cleanup errors.
    """
    owns = not con.in_transaction
    savepoint = f"decomp_write_{next(_SAVEPOINT_IDS)}"
    con.execute("BEGIN IMMEDIATE" if owns else f"SAVEPOINT {savepoint}")
    try:
        require_decomp_schema(con)
        if _decomp_domain(con) != "corpus":
            raise ValueError("decomp corpus destination required")
        yield
        if owns or commit_caller:
            con.commit()
        else:
            con.execute(f"RELEASE SAVEPOINT {savepoint}")
    except BaseException as exc:
        if not con.in_transaction:
            raise RuntimeError(
                "decomp transaction ended before failure acknowledgement; "
                "durability/rollback is uncertain and caller work cannot be reconstructed"
            ) from exc
        if owns:
            con.rollback()
        else:
            con.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            con.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise


def _materialize_main(con: sqlite3.Connection) -> None:
    # Admission belongs to the surrounding scope. This helper owns only DML.
    con.execute("UPDATE main.decomp_schema_state SET mode=? WHERE singleton=1", ("ast_fingerprint",))


def _decomp_domain(con: sqlite3.Connection) -> str:
    """Keep independent part installation out of the corpus ownership domain."""
    names = ("binary", "schema_migration", "decomp", "decomp_schema_state", "decomp_part")
    marks = ','.join('?' for _ in names)
    if con.execute(f"SELECT 1 FROM temp.sqlite_schema WHERE name COLLATE NOCASE IN ({marks})", names).fetchone():
        raise ValueError("shadowing decomp temp object")
    rows = list(con.execute(f"SELECT name,type FROM main.sqlite_schema WHERE name COLLATE NOCASE IN ({marks})", names))
    ascii_lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    for name, _ in rows:
        if name.translate(ascii_lower) != name:
            raise ValueError(f"unsupported decomp object spelling {name}")
    present = {row[0] for row in rows}
    corpus = bool(present & set(names[:-1]))
    if corpus and "decomp_part" in present:
        raise ValueError("mixed corpus and decomp_part ownership")
    return "corpus" if corpus else "part" if "decomp_part" in present else "empty"


def _ensure_part_columns(con: sqlite3.Connection) -> None:
    cols = {row[1] for row in con.execute("PRAGMA main.table_info(decomp_part)")}
    if cols and "ast_fingerprint" not in cols:
        con.execute("ALTER TABLE main.decomp_part ADD COLUMN ast_fingerprint TEXT")


def persist_code(con, binary_id: int, addr: int, code: str | None) -> dict:
    """Replace one row atomically; success commits caller pending work too."""
    require_decomp_schema(con)
    if _decomp_domain(con) != "corpus":
        raise ValueError("decomp corpus destination required")
    ft = features(code) if code else None
    if ft is not None:
        ft["ast_fingerprint"] = syntax_fingerprint(code)
    with _main_write_scope(con, commit_caller=True):
        _materialize_main(con)
        if not code:
            con.execute(
                """INSERT OR REPLACE INTO main.decomp
                   (binary_id, addr, ok, n_tokens, n_lines, max_nest, n_calls, n_locals,
                    n_deref, n_index, n_field, ctrl, ops, skeleton_hash, ast_fingerprint)
                   VALUES (?,?,0,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (binary_id, addr, *[None] * 12),
            )
            return {"ok": 0, "addr": addr}
        con.execute(
            """INSERT OR REPLACE INTO main.decomp
               (binary_id, addr, ok, n_tokens, n_lines, max_nest, n_calls, n_locals,
                n_deref, n_index, n_field, ctrl, ops, skeleton_hash, ast_fingerprint)
               VALUES (?,?,1,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                binary_id,
                addr,
                ft["n_tokens"],
                ft["n_lines"],
                ft["max_nest"],
                ft["n_calls"],
                ft["n_locals"],
                ft["n_deref"],
                ft["n_index"],
                ft["n_field"],
                json.dumps(ft["ctrl"]),
                json.dumps(ft["ops"]),
                ft["skeleton_hash"],
                ft["ast_fingerprint"],
            ),
        )
        return {"ok": 1, "addr": addr, **ft}


def persist_part(part_path: Path, repo_path: str, addr: int, code: str | None) -> dict:
    con = sqlite3.connect(part_path)
    try:
        if _decomp_domain(con) == "corpus":
            raise ValueError("independent decomp_part destination required")
        con.executescript(PART_SCHEMA)
        _ensure_part_columns(con)
        if not code:
            con.execute(
                """INSERT OR REPLACE INTO decomp_part
                   (repo_path, addr, ok, n_tokens, n_lines, max_nest, n_calls, n_locals,
                    n_deref, n_index, n_field, ctrl, ops, skeleton_hash, ast_fingerprint)
                   VALUES (?,?,0,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (repo_path, addr, *[None] * 12),
            )
            con.commit()
            return {"ok": 0, "addr": addr}
        ft = features(code)
        ft["ast_fingerprint"] = syntax_fingerprint(code)
        con.execute(
            """INSERT OR REPLACE INTO decomp_part
               (repo_path, addr, ok, n_tokens, n_lines, max_nest, n_calls, n_locals,
                n_deref, n_index, n_field, ctrl, ops, skeleton_hash, ast_fingerprint)
               VALUES (?,?,1,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                repo_path,
                addr,
                ft["n_tokens"],
                ft["n_lines"],
                ft["max_nest"],
                ft["n_calls"],
                ft["n_locals"],
                ft["n_deref"],
                ft["n_index"],
                ft["n_field"],
                json.dumps(ft["ctrl"]),
                json.dumps(ft["ops"]),
                ft["skeleton_hash"],
                ft["ast_fingerprint"],
            ),
        )
        con.commit()
        return {"ok": 1, "addr": addr, **ft}

    finally:
        con.close()


def attach_store(store_path: Path) -> sqlite3.Connection:
    """Open a canonical store and explicitly materialize logical decomp state."""
    con = connect(store_path)
    try:
        require_decomp_schema(con)
        if _decomp_domain(con) != "corpus":
            raise ValueError("decomp corpus destination required")
        with _main_write_scope(con):
            _materialize_main(con)
        return con
    except BaseException:
        try:
            if con.in_transaction:
                con.rollback()
        finally:
            con.close()
        raise


def ensure_decomp_columns(con: sqlite3.Connection) -> None:
    """Compatibility mutator: explicit skeleton→AST transition, never backfill.

    Corpus schema must already be current. Absent remains logically absent.
    Standalone transitions are durable; caller transactions are never committed.
    Independent part handles retain their own nullable column installer.
    """
    domain = _decomp_domain(con)
    if domain == "empty":
        return
    if domain == "part":
        _ensure_part_columns(con)
        return
    require_decomp_schema(con)
    if decomp_read_state(con) != "skeleton_hash":
        return
    with _main_write_scope(con):
        if decomp_read_state(con) == "skeleton_hash":
            _materialize_main(con)
