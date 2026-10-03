"""Dashboard-facing wiring for the explicit publish-approval step (R50/U29).

Resolves the live corpus selection to a sqlite connection and an approval
receipt path, then delegates the actual gate check and approval bookkeeping
to `..publish_gate`. Never performs an outbound network call.
"""

from __future__ import annotations

import sqlite3

from ..publish_gate import approve_publish as _approve_publish
from ..publish_gate import default_approval_path, publish_status as _publish_status
from .common import corpus_file_identity, live_db


def _ro_connection(database):
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=10)
    connection.execute("PRAGMA query_only = ON")
    return connection


def publish_status() -> dict:
    """Read-only: current gate state plus any recorded approval. Never sends anything."""
    database = live_db()
    corpus = corpus_file_identity(database)
    if not corpus["identity"]:
        return {"ok": False, "error": "Selected corpus database is unavailable"}
    connection = _ro_connection(database)
    try:
        payload = _publish_status(connection, default_approval_path(database))
    finally:
        connection.close()
    payload["corpusIdentity"] = corpus["identity"]
    return payload


def approve_publish(*, confirm: bool) -> dict:
    """Record an explicit operator approval once the gate passes."""
    database = live_db()
    corpus = corpus_file_identity(database)
    if not corpus["identity"]:
        return {"ok": False, "error": "Selected corpus database is unavailable"}
    connection = _ro_connection(database)
    try:
        payload = _approve_publish(
            connection, default_approval_path(database),
            confirm=confirm, corpus_identity=corpus["identity"],
        )
    finally:
        connection.close()
    return payload
