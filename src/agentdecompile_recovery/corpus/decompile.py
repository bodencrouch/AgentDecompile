"""Persist decompiled-C shape features into a store or part file."""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from pathlib import Path

from .decompile_shape import features
from .store import connect


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

MAIN_SCHEMA = """
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
);
CREATE INDEX IF NOT EXISTS ix_decomp_bin ON decomp(binary_id);
"""


def persist_code(con, binary_id: int, addr: int, code: str | None) -> dict:
    con.executescript(MAIN_SCHEMA)
    ensure_decomp_columns(con)
    if not code:
        con.execute(
            """INSERT OR REPLACE INTO decomp
               (binary_id, addr, ok, n_tokens, n_lines, max_nest, n_calls, n_locals,
                n_deref, n_index, n_field, ctrl, ops, skeleton_hash, ast_fingerprint)
               VALUES (?,?,0,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (binary_id, addr, *[None] * 12),
        )
        con.commit()
        return {"ok": 0, "addr": addr}
    ft = features(code)
    ft["ast_fingerprint"] = syntax_fingerprint(code)
    con.execute(
        """INSERT OR REPLACE INTO decomp
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
    con.commit()
    return {"ok": 1, "addr": addr, **ft}


def persist_part(part_path: Path, repo_path: str, addr: int, code: str | None) -> dict:
    con = sqlite3.connect(part_path)
    con.executescript(PART_SCHEMA)
    ensure_decomp_columns(con)
    if not code:
        con.execute(
            """INSERT OR REPLACE INTO decomp_part
               (repo_path, addr, ok, n_tokens, n_lines, max_nest, n_calls, n_locals,
                n_deref, n_index, n_field, ctrl, ops, skeleton_hash, ast_fingerprint)
               VALUES (?,?,0,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (repo_path, addr, *[None] * 12),
        )
        con.commit()
        con.close()
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
    con.close()
    return {"ok": 1, "addr": addr, **ft}


def attach_store(store_path: Path) -> sqlite3.Connection:
    con = connect(store_path)
    con.executescript(MAIN_SCHEMA)
    ensure_decomp_columns(con)
    return con


def ensure_decomp_columns(con: sqlite3.Connection) -> None:
    for table in ("decomp", "decomp_part"):
        try:
            cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        if cols and "ast_fingerprint" not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN ast_fingerprint TEXT")
