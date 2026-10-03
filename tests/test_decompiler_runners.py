"""U30 test for U20's licensed-local-only decompiler runner config (R41).

Converted from the U20 inline verification sequence: a configured runner
entry whose endpoint host is not loopback must be dropped rather than
honored, so a misconfiguration can never become an outbound call to a
public service.
"""

from __future__ import annotations

import json

import pytest

from agentdecompile_recovery.corpus.dashboard import decompiler_runners

pytestmark = pytest.mark.unit


def test_non_loopback_runner_entries_are_dropped(monkeypatch) -> None:
    config = [
        {"id": "local-one", "label": "Local Decompiler", "endpoint": "http://127.0.0.1:9001/decompile"},
        {"id": "local-two", "label": "Local via hostname", "endpoint": "http://localhost:9002/decompile"},
        {"id": "public-evil", "label": "Public service", "endpoint": "https://dogbolt.example.com/decompile"},
        {"id": "no-scheme", "label": "No scheme", "endpoint": "127.0.0.1:9003/decompile"},
    ]
    monkeypatch.setenv("AGENTDECOMPILE_DECOMPILER_RUNNERS", json.dumps(config))
    monkeypatch.delenv("AGENTDECOMPILE_DECOMPILER_RUNNERS_FILE", raising=False)

    result = decompiler_runners.list_runners()

    assert result["ok"] is True
    ids = {runner["id"] for runner in result["runners"]}
    assert ids == {"local-one", "local-two"}
    assert "public-evil" not in ids
    assert "no-scheme" not in ids
    assert result["configured"] is True


def test_empty_config_yields_no_runners(monkeypatch) -> None:
    monkeypatch.delenv("AGENTDECOMPILE_DECOMPILER_RUNNERS", raising=False)
    monkeypatch.delenv("AGENTDECOMPILE_DECOMPILER_RUNNERS_FILE", raising=False)

    result = decompiler_runners.list_runners()

    assert result == {"ok": True, "runners": [], "configured": False}


def test_fetch_output_for_dropped_nonloopback_id_reports_not_configured(monkeypatch) -> None:
    config = [{"id": "public-evil", "label": "Public", "endpoint": "https://dogbolt.example.com/decompile"}]
    monkeypatch.setenv("AGENTDECOMPILE_DECOMPILER_RUNNERS", json.dumps(config))
    monkeypatch.delenv("AGENTDECOMPILE_DECOMPILER_RUNNERS_FILE", raising=False)

    result = decompiler_runners.fetch_output("public-evil", "loc", "prog", "0x1000")

    assert result["ok"] is False
    assert "No configured local runner" in result["error"]
