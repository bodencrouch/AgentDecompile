from __future__ import annotations

import json

import pytest

from agentdecompile_recovery.corpus.dashboard import workspace_state

pytestmark = pytest.mark.unit


def test_patch_state_persists_atomically(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_WORK_DIR", str(tmp_path))
    first = workspace_state.patch_state(
        {"drafts": {"editor:a": {"text": "int main(){}"}}, "notes": {"context": "note"}}
    )
    assert first["ok"] is True
    assert first["revision"] == 1
    second = workspace_state.patch_state(
        {
            "revision": first["revision"],
            "drafts": {"editor:b": {"text": "void foo(){}"}},
        }
    )
    assert second["ok"] is True
    assert second["revision"] == 2
    assert second["drafts"]["editor:a"]["text"] == "int main(){}"
    stored = json.loads((tmp_path / "workbench-workspace-state.json").read_text())
    assert stored["notes"]["context"] == "note"
