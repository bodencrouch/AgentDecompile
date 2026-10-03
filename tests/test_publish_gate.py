"""U30 tests for U29's explicit publish-approval step (R50).

Converted from the U29 inline verification sequence: a blocked gate refuses
approval and writes no receipt; confirm=False always refuses; an open gate
plus confirm=True records an "approved_unsent" receipt labeled as not yet
sent. Also covers the publish-status/publish-approve CLI exit codes.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

from agentdecompile_recovery.corpus import cli
from agentdecompile_recovery.corpus.publish_gate import (
    APPROVED_UNSENT_LABEL,
    approve_publish,
    default_approval_path,
    publish_status,
)

pytestmark = pytest.mark.unit


def _empty_connection(path) -> sqlite3.Connection:
    """No `binary` table at all: run_gate_for_all_binaries short-circuits to {}."""
    con = sqlite3.connect(path)
    return con


def test_blocked_gate_refuses_approval_and_writes_no_file(tmp_path) -> None:
    con = _empty_connection(tmp_path / "corpus.sqlite")
    approval_file = tmp_path / "publish-approval.json"
    blocked_reconciliation = {
        1: {"status": "failed", "errors": [{"code": "unreconciled_inventory", "members": [1], "count": 1}]},
    }

    with patch(
        "agentdecompile_recovery.corpus.publish_gate.run_gate_for_all_binaries",
        return_value=blocked_reconciliation,
    ):
        result = approve_publish(con, approval_file, confirm=True)

    assert result["ok"] is False
    assert "blocked" in result["error"]
    assert not approval_file.exists()


def test_confirm_false_refuses_regardless_of_gate(tmp_path) -> None:
    con = _empty_connection(tmp_path / "corpus.sqlite")
    approval_file = tmp_path / "publish-approval.json"

    result = approve_publish(con, approval_file, confirm=False)

    assert result["ok"] is False
    assert "confirm" in result["error"]
    assert not approval_file.exists()


def test_open_gate_confirmed_records_approved_unsent(tmp_path) -> None:
    con = _empty_connection(tmp_path / "corpus.sqlite")
    approval_file = tmp_path / "publish-approval.json"

    result = approve_publish(con, approval_file, confirm=True, corpus_identity="abc123")

    assert result["ok"] is True
    assert result["status"] == "approved_unsent"
    assert result["label"] == APPROVED_UNSENT_LABEL
    assert approval_file.is_file()

    status_after = publish_status(con, approval_file)
    assert status_after["status"] == "approved_unsent"
    assert status_after["label"] == APPROVED_UNSENT_LABEL
    assert status_after["approval"]["corpusIdentity"] == "abc123"


def test_default_approval_path_sits_next_to_db(tmp_path) -> None:
    db_path = tmp_path / "nested" / "corpus.sqlite"
    assert default_approval_path(db_path) == db_path.parent / "publish-approval.json"


def test_cli_publish_approve_exit_1_on_refusal(tmp_path) -> None:
    db_path = tmp_path / "corpus.sqlite"
    from agentdecompile_recovery.corpus.store import connect

    connect(db_path).close()

    rc = cli.main(["publish-approve", "--db", str(db_path)])  # no --confirm

    assert rc == 1
    assert not (tmp_path / "publish-approval.json").exists()


def test_cli_publish_approve_exit_0_on_success(tmp_path) -> None:
    db_path = tmp_path / "corpus.sqlite"
    from agentdecompile_recovery.corpus.store import connect

    connect(db_path).close()

    rc = cli.main(["publish-approve", "--db", str(db_path), "--confirm"])

    assert rc == 0
    approval_file = tmp_path / "publish-approval.json"
    assert approval_file.is_file()
    assert json.loads(approval_file.read_text())["status"] == "approved_unsent"


def test_cli_publish_status_never_errors_on_open_gate(tmp_path, capsys) -> None:
    db_path = tmp_path / "corpus.sqlite"
    from agentdecompile_recovery.corpus.store import connect

    connect(db_path).close()

    rc = cli.main(["publish-status", "--db", str(db_path)])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
