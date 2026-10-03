"""Deprecated compatibility API for the canonical corpus :mod:`store`.

The historical module-relative path is retained only for existing callers.
Omitted paths warn and refuse creation; explicit paths use canonical migrations.
"""

from __future__ import annotations

import pathlib
import sqlite3
import warnings

from . import store

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "db" / "kotorxid.sqlite"

# Baseline SQL is not a replacement for versioned initialization via connect.
SCHEMA = store.SCHEMA
ensure_priority_index = store.ensure_priority_index
j = store.j


def connect(
    path: pathlib.Path | str | None = None, *, read_only: bool = False
) -> sqlite3.Connection:
    """Delegate to the canonical store, preserving explicit path precedence.

    An omitted path opens only an existing historical file. Writable opens now
    use canonical migrations, including for existing legacy stores.
    """
    if path is not None:
        return store.connect(path, read_only=read_only)
    warnings.warn(
        f"corpus.db.connect() without a path is deprecated; using historical "
        f"store {DB_PATH.resolve()}. Missing files are no longer created. "
        "Pass an explicit path to corpus.store.connect; writable opens use "
        "canonical migrations.",
        FutureWarning,
        stacklevel=2,
    )
    return store.connect(DB_PATH, read_only=read_only, create=False)
