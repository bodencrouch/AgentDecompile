"""U30 tests for U25's local, revocable spectator access (R46/AE16).

Converted from the U25 inline verification sequence: is_write_blocked's
truthiness contract, the router's hard rejection of any write request
carrying the spectator header (except its own touch heartbeat), and that
tokens are persisted hashed, never in plaintext.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdecompile_recovery.corpus.dashboard import spectator
from agentdecompile_recovery.corpus.dashboard.router import create_dashboard_router

pytestmark = pytest.mark.unit


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_dashboard_router())
    return TestClient(app)


@pytest.fixture(autouse=True)
def _spectator_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTDECOMPILE_WORKSPACE", str(tmp_path))
    yield tmp_path


def test_is_write_blocked_none_and_empty_are_false() -> None:
    assert spectator.is_write_blocked(None) is False
    assert spectator.is_write_blocked("") is False


def test_is_write_blocked_nonempty_is_true() -> None:
    assert spectator.is_write_blocked("anything") is True
    assert spectator.is_write_blocked("a-stale-or-forged-token") is True


def test_router_rejects_post_carrying_spectator_header() -> None:
    client = _client()
    response = client.post(
        "/dashboard/api/workbench/spectator/enable",
        json={"enabled": True},
        headers={spectator.HEADER: "some-token"},
    )
    assert response.status_code == 403


def test_router_allows_post_without_spectator_header() -> None:
    client = _client()
    response = client.post(
        "/dashboard/api/workbench/spectator/enable",
        json={"enabled": True},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_spectator_touch_endpoint_allowed_even_with_header() -> None:
    client = _client()
    # Enable spectating and mint a token first (no header on these calls).
    client.post("/dashboard/api/workbench/spectator/enable", json={"enabled": True})
    token = client.post("/dashboard/api/workbench/spectator/token").json()["token"]

    response = client.post(
        "/dashboard/api/workbench/spectator/touch",
        headers={spectator.HEADER: token},
    )

    # The touch route is exempted from the write-rejection dependency; it
    # answers from its own handler (200 for a live token) rather than 403.
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_tokens_are_stored_hashed_not_plaintext(tmp_path) -> None:
    spectator.enable(True)
    created = spectator.create_token()
    assert created["ok"] is True
    plaintext_token = created["token"]

    state_file = tmp_path / ".agentdecompile" / "spectator.json"
    raw = state_file.read_text(encoding="utf-8")
    on_disk = json.loads(raw)

    assert plaintext_token not in raw
    stored_keys = list(on_disk["tokens"].keys())
    assert len(stored_keys) == 1
    assert stored_keys[0] == spectator._hash(plaintext_token)
