from __future__ import annotations

import hashlib
import json
import threading
import time

from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.dashboard.actions import catalog, jobs, matching
from agentdecompile_recovery.gnu_c_compiler import CompileResult

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _preset_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "presets"
    root.mkdir()
    monkeypatch.setenv("AGENT_DECOMPILE_MATCHING_PRESET_ROOT", str(root))


def _params(tmp_path: Path) -> dict[str, str]:
    target = tmp_path / "target.o"
    target.write_bytes(b"target")
    preset = tmp_path / "presets" / "fixture-gcc.json"
    preset.write_text(json.dumps({
        "id": "fixture-gcc",
        "artifactHash": "a" * 64,
        "compilerScript": "cc -c {{cFilePath}} -o {{objFilePath}}",
        "projectRoot": str(tmp_path),
        "targets": {"candidate_fn": {
            "path": "target.o",
            "sha256": hashlib.sha256(b"target").hexdigest(),
            "symbol": "candidate_fn",
        }},
    }))
    return {
        "artifactHash": "a" * 64,
        "targetRevision": hashlib.sha256(b"target").hexdigest(),
        "function": "candidate_fn",
        "candidateSource": "int candidate_fn(void) { return 1; }",
        "compilerPreset": "fixture-gcc",
    }


def _compiled(tmp_path: Path) -> CompileResult:
    out = tmp_path / "compile" / "candidate_fn.o"
    out.parent.mkdir()
    out.write_bytes(b"candidate")
    return CompileResult(success=True, obj_path=out)


def test_catalog_exposes_atomic_matching_action() -> None:
    action = catalog.action_by_id("workbench.match-candidate")
    assert action is not None
    assert action.backend == "matching"
    assert action.danger is True
    assert {field.name for field in action.fields} == {
        "artifactHash", "targetRevision", "function", "candidateSource", "compilerPreset"
    }


def test_compile_success_with_objdiff_mismatch_is_unverified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matching.GnuCCompiler, "compile", lambda *_: _compiled(tmp_path))
    monkeypatch.setattr(matching, "build_decomp_match_payload", lambda **_: {
        "scan": {"available": True, "exitCode": 0, "stdout": json.dumps({
            "left": {"symbols": [{"kind": "SYMBOL_FUNCTION", "match_percent": 75,
                                    "instructions": [{"diff_kind": "DIFF_REPLACE", "instruction": {"formatted": "ret"}}]}]},
            "right": {"symbols": [{"kind": "SYMBOL_FUNCTION", "match_percent": 75,
                                     "instructions": [{"diff_kind": "DIFF_REPLACE", "instruction": {"formatted": "nop"}}]}]},
        })}
    })

    code, raw = matching.execute(_params(tmp_path), threading.Event())
    payload = json.loads(raw)

    assert code == 0
    assert payload["phase"] == "mismatch"
    assert payload["verified"] is False
    assert payload["receipt"]["differences"] == 1
    assert payload["receipt"]["targetRevision"] != payload["receipt"]["compiledRevision"]


def test_only_objdiff_zero_creates_verified_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matching.GnuCCompiler, "compile", lambda *_: _compiled(tmp_path))
    monkeypatch.setattr(matching, "build_decomp_match_payload", lambda **_: {
        "scan": {"available": True, "exitCode": 0, "stdout": json.dumps({
            "left": {"symbols": [{"name": "candidate_fn", "kind": "SYMBOL_FUNCTION", "match_percent": 100,
                                     "instructions": [{"diff_kind": "DIFF_NONE", "instruction": {"formatted": "ret"}}]}]},
            "right": {"symbols": [{"name": "candidate_fn", "kind": "SYMBOL_FUNCTION", "match_percent": 100,
                                      "instructions": [{"diff_kind": "DIFF_NONE", "instruction": {"formatted": "ret"}}]}]},
        })}
    })

    code, raw = matching.execute(_params(tmp_path), threading.Event())
    payload = json.loads(raw)

    assert code == 0
    assert payload["phase"] == "objdiff-verified"
    assert payload["verified"] is True
    assert payload["receipt"]["differences"] == 0
    assert payload["receipt"]["candidateRevision"] == payload["candidateRevision"]


def test_matching_json_with_failed_objdiff_exit_never_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matching.GnuCCompiler, "compile", lambda *_: _compiled(tmp_path))
    monkeypatch.setattr(matching, "build_decomp_match_payload", lambda **_: {
        "scan": {"available": True, "exitCode": 1, "stdout": json.dumps({
            "left": {"symbols": [{"kind": "SYMBOL_FUNCTION", "match_percent": 100}]},
            "right": {"symbols": [{"kind": "SYMBOL_FUNCTION", "match_percent": 100}]},
        })}
    })

    code, raw = matching.execute(_params(tmp_path), threading.Event())
    payload = json.loads(raw)

    assert code == 1
    assert payload["phase"] == "failed"
    assert payload["verified"] is False
    assert payload["receipt"]["objdiffExit"] == 1


def test_one_sided_objdiff_json_never_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matching.GnuCCompiler, "compile", lambda *_: _compiled(tmp_path))
    monkeypatch.setattr(matching, "build_decomp_match_payload", lambda **_: {
        "scan": {"available": True, "exitCode": 0, "stdout": json.dumps({
            "left": {"symbols": [{"name": "candidate_fn", "kind": "SYMBOL_FUNCTION", "match_percent": 100,
                                     "instructions": [{"diff_kind": "DIFF_NONE", "instruction": {"formatted": "ret"}}]}]},
        })}
    })

    code, raw = matching.execute(_params(tmp_path), threading.Event())
    payload = json.loads(raw)

    assert code == 1
    assert payload["phase"] == "failed"
    assert payload["verified"] is False


def test_incomplete_instruction_rows_never_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matching.GnuCCompiler, "compile", lambda *_: _compiled(tmp_path))
    monkeypatch.setattr(matching, "build_decomp_match_payload", lambda **_: {
        "scan": {"available": True, "exitCode": 0, "stdout": json.dumps({
            "left": {"symbols": [{"name": "candidate_fn", "kind": "SYMBOL_FUNCTION", "match_percent": 100,
                                     "instructions": [{}]}]},
            "right": {"symbols": [{"name": "candidate_fn", "kind": "SYMBOL_FUNCTION", "match_percent": 100,
                                      "instructions": [{}]}]},
        })}
    })

    code, raw = matching.execute(_params(tmp_path), threading.Event())

    assert code == 1
    assert json.loads(raw)["phase"] == "failed"
    assert json.loads(raw)["receipt"]["status"] == "incomplete"


def test_compile_failure_never_runs_objdiff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matching.GnuCCompiler, "compile", lambda *_: CompileResult(
        success=False, error_message="compiler rejected candidate"
    ))
    objdiff_called = False

    def should_not_diff(**_kwargs):
        nonlocal objdiff_called
        objdiff_called = True
        return {}

    monkeypatch.setattr(matching, "build_decomp_match_payload", should_not_diff)
    code, raw = matching.execute(_params(tmp_path), threading.Event())
    payload = json.loads(raw)

    assert code == 1
    assert payload["phase"] == "compile-failed"
    assert payload["verified"] is False
    assert objdiff_called is False


def test_invalid_preset_fails_without_losing_candidate_revision(tmp_path: Path) -> None:
    params = _params(tmp_path)
    (tmp_path / "presets" / "fixture-gcc.json").write_text("{}")

    code, raw = matching.execute(params, threading.Event())
    payload = json.loads(raw)

    assert code == 1
    assert payload["phase"] == "failed"
    assert payload["candidateRevision"]
    assert "artifactHash" in payload["error"]
    assert payload["verified"] is False


def test_stale_target_revision_fails_before_compile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    params = _params(tmp_path)
    params["targetRevision"] = "0" * 64
    compiled = False

    def should_not_compile(*_args):
        nonlocal compiled
        compiled = True
        return _compiled(tmp_path)

    monkeypatch.setattr(matching.GnuCCompiler, "compile", should_not_compile)
    code, raw = matching.execute(params, threading.Event())

    assert code == 1
    assert json.loads(raw)["phase"] == "failed"
    assert "targetRevision" in json.loads(raw)["error"]
    assert compiled is False


def test_preset_must_bind_selected_artifact(tmp_path: Path) -> None:
    params = _params(tmp_path)
    params["artifactHash"] = "b" * 64

    code, raw = matching.execute(params, threading.Event())

    assert code == 1
    assert "not bound" in json.loads(raw)["error"]


def test_attempt_identity_includes_approved_preset_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = _params(tmp_path)
    original = json.loads((tmp_path / "presets" / "fixture-gcc.json").read_text())
    second_preset = {**original, "id": "fixture-gcc-debug", "compilerScript": original["compilerScript"] + " -g"}
    (tmp_path / "presets" / "fixture-gcc-debug.json").write_text(json.dumps(second_preset))
    second = {**first, "compilerPreset": "fixture-gcc-debug"}
    monkeypatch.setattr(matching.GnuCCompiler, "compile", lambda *_: CompileResult(
        success=False, error_message="stop after identity"
    ))

    _, first_raw = matching.execute(first, threading.Event())
    _, second_raw = matching.execute(second, threading.Event())
    first_result, second_result = json.loads(first_raw), json.loads(second_raw)

    assert first_result["attemptId"] != second_result["attemptId"]
    assert first_result["compilerPresetFingerprint"] != second_result["compilerPresetFingerprint"]


def test_objdiff_reads_immutable_target_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    params = _params(tmp_path)

    def compile_and_mutate(*_args):
        (tmp_path / "target.o").write_bytes(b"changed-after-snapshot")
        return _compiled(tmp_path)

    def diff_snapshot(**kwargs):
        assert Path(kwargs["target_object_path"]).read_bytes() == b"target"
        return {"scan": {"available": True, "exitCode": 0, "stdout": json.dumps({
            "left": {"symbols": [{"name": "candidate_fn", "kind": "SYMBOL_FUNCTION",
                                     "match_percent": 75, "instructions": [{"diff_kind": "DIFF_REPLACE"}]}]},
            "right": {"symbols": [{"name": "candidate_fn", "kind": "SYMBOL_FUNCTION",
                                      "match_percent": 75, "instructions": [{"diff_kind": "DIFF_REPLACE"}]}]},
        })}}

    monkeypatch.setattr(matching.GnuCCompiler, "compile", compile_and_mutate)
    monkeypatch.setattr(matching, "build_decomp_match_payload", diff_snapshot)
    code, raw = matching.execute(params, threading.Event())

    assert code == 0
    assert json.loads(raw)["phase"] == "mismatch"


def test_job_store_runs_matching_action_and_redacts_draft_from_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"schema": matching.SCHEMA, "phase": "mismatch", "verified": False}
    monkeypatch.setattr(matching, "execute", lambda _params, _cancel: (0, json.dumps(expected)))

    started, status = jobs.start_job("workbench.match-candidate", _params(tmp_path), confirm=True)
    assert status == 202
    job_id = started["job"]["id"]
    deadline = time.monotonic() + 3
    current = jobs.get_job(job_id)
    while current is not None and current.status in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = jobs.get_job(job_id)

    assert current is not None
    assert current.status == "ok"
    assert json.loads(current.log)["phase"] == "mismatch"
    listed = current.to_dict(include_log=False, include_details=False)
    assert "candidateSource" not in listed["params"]
