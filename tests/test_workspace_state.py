from __future__ import annotations

from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.dashboard import workspace_state

pytestmark = pytest.mark.unit


@pytest.fixture
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_WORK_DIR", str(work))
    return work


def test_load_state_empty_when_missing(workspace_root: Path) -> None:
    assert workspace_state.load_state() == {
        "revision": 0,
        "updatedAt": 0.0,
        "drafts": {},
        "notes": {},
        "meta": {},
    }


def test_patch_state_writes_and_increments_revision(
    workspace_root: Path,
) -> None:
    first = workspace_state.patch_state(
        {"revision": 0, "meta": {"activity": [{"id": "a1"}]}}
    )
    assert first["ok"] is True
    assert first["revision"] == 1
    assert first["meta"]["activity"] == [{"id": "a1"}]

    second = workspace_state.patch_state(
        {"revision": 1, "notes": {"ctx:1": "remember this"}}
    )
    assert second["revision"] == 2
    assert second["notes"]["ctx:1"] == "remember this"
    assert second["meta"]["activity"] == [{"id": "a1"}]


def test_patch_state_merges_on_revision_conflict(workspace_root: Path) -> None:
    workspace_state.patch_state({"revision": 0, "drafts": {"k1": {"text": "a"}}})
    merged = workspace_state.patch_state(
        {
            "revision": 0,
            "drafts": {"k2": {"text": "b"}},
            "meta": {"layout": {"explorer": 360}},
        }
    )
    assert merged["ok"] is True
    assert merged["drafts"]["k1"]["text"] == "a"
    assert merged["drafts"]["k2"]["text"] == "b"
    assert merged["meta"]["layout"]["explorer"] == 360


def test_patch_state_deletes_with_null(workspace_root: Path) -> None:
    workspace_state.patch_state({"revision": 0, "notes": {"gone": "x", "stay": "y"}})
    updated = workspace_state.patch_state({"revision": 1, "notes": {"gone": None}})
    assert "gone" not in updated["notes"]
    assert updated["notes"]["stay"] == "y"


def test_patch_state_rejects_invalid_revision(workspace_root: Path) -> None:
    result = workspace_state.patch_state({"revision": "bad", "meta": {"x": 1}})
    assert result["ok"] is False
    assert "revision" in str(result.get("error", "")).lower()


def test_patch_state_rejects_oversized_section(workspace_root: Path) -> None:
    huge = {"k": "x" * (workspace_state.MAX_VALUE_CHARS + 1)}
    result = workspace_state.patch_state({"revision": 0, "notes": huge})
    assert result["ok"] is False


def test_write_sessions_empty_payload_does_not_wipe(
    workspace_root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentdecompile_recovery.corpus.dashboard import workbench
    from agentdecompile_recovery.corpus.ghidra_project import save_sessions

    save_sessions(
        workspace_root,
        {
            "active": "s1",
            "sessions": [
                {
                    "id": "s1",
                    "title": "Saved",
                    "locator": "/tmp/project.gpr",
                    "imports": [],
                }
            ],
        },
    )
    result = workbench.write_sessions({"active": "", "sessions": []})
    assert result.get("ignored") is True
    assert result["sessions"][0]["title"] == "Saved"


def test_workspace_state_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agentdecompile_recovery.corpus.dashboard.router import create_dashboard_router
    from agentdecompile_recovery.corpus.store import connect

    db = tmp_path / "corpus.sqlite"
    connect(db).close()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_DB", str(db))
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_WORK_DIR", str(work))

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app)

    empty = client.get("/dashboard/api/workbench/workspace-state")
    assert empty.status_code == 200
    assert empty.json()["revision"] == 0

    patched = client.patch(
        "/dashboard/api/workbench/workspace-state",
        json={"revision": 0, "meta": {"theme": "dark"}},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["ok"] is True
    assert body["revision"] == 1
    assert body["meta"]["theme"] == "dark"
