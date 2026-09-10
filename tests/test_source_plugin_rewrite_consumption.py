"""Forwarded source reaches the compiler dispatcher and retains the proof gate."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentdecompile_recovery import rewrite_queue, source_parity_synthesize, source_plugins
from agentdecompile_recovery.source_parity_synthesize import GeneratedCandidate

pytestmark = pytest.mark.unit

REWRITE = "int sample(void) { return 7; }\n"


def forwarded_context(tmp_path, *, source=REWRITE, source_suffix=".c"):
    candidate = GeneratedCandidate(
        rule="one-return", variant="original", c_name="sample", symbol="_sample",
        source="int sample(void) { return 1; }\n", callconv="cdecl", return_type="int",
        extra_flags=("trusted-flag",), evidence={"sourceRecoveryScope": "partial-source-slice"},
        source_suffix=source_suffix,
    )
    request_id = rewrite_queue.write_rewrite_request(
        tmp_path, function_name="sample", entry="0x1000", candidate_source=candidate.source,
        mismatch_class="operand", mismatch_histogram={},
    )
    payload = rewrite_queue.find_entry(tmp_path, request_id)
    assert rewrite_queue.import_exchange_result(tmp_path, request_id, payload=payload, source=source, receipt="server-receipt")
    return {
        "sourceParityRow": {"name": "sample", "entry": "0x1000", "bytes": "c3"},
        "selectedSourceCandidate": candidate, "workDir": str(tmp_path), "outDir": str(tmp_path / "out"),
    }, request_id


@pytest.mark.parametrize("compiler", ["msvc", "clang", "clang-cl"])
@pytest.mark.parametrize("shape_search", [False, True])
@pytest.mark.parametrize("differences", [0, 2])
@pytest.mark.parametrize("source_suffix", [".c", ".asm"])
def test_forwarded_rewrite_reaches_each_compiler_and_objdiff_gate(tmp_path, monkeypatch, compiler, shape_search, differences, source_suffix):
    context, request_id = forwarded_context(tmp_path, source_suffix=source_suffix)
    original = context["selectedSourceCandidate"]
    context.update(compiler=compiler, sourceShapeSearch=shape_search)
    seen = []

    def backend(row, candidate, case_dir, source_path, base_record, **kwargs):
        seen.append(candidate)
        assert source_path.read_text() == REWRITE
        assert source_path.suffix == candidate.source_suffix == ".c"
        assert (candidate.symbol, candidate.callconv, candidate.extra_flags) == (original.symbol, original.callconv, original.extra_flags)
        assert candidate.evidence == {**original.evidence, "rewriteRequestId": request_id}
        assert not kwargs.get("source_shape_search")
        assert kwargs.get("pending_rewrite_result") is None
        return [{**base_record, "status": "matched", "differences": differences}]

    backend_name = {
        "msvc": "attempt_candidate_with_msvc_synthetic_slice",
        "clang": "attempt_candidate_with_clang_slice_objdiff",
        "clang-cl": "attempt_candidate_with_clangcl_slice_objdiff",
    }[compiler]
    monkeypatch.setattr(source_parity_synthesize, backend_name, backend)
    result, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert len(seen) == 1
    assert seen[0].source == REWRITE
    assert original.source != REWRITE
    assert result.status == ("success" if differences == 0 else "failure")
    assert len(updated["sourceParityMatchRecords"]) == (1 if differences == 0 else 0)
    assert rewrite_queue.find_entry(tmp_path, request_id) is None


@pytest.mark.parametrize("failure_point", ["compiler", "recording", "dry-run", "no-attempt"])
def test_unattempted_or_interrupted_rewrite_is_retained(tmp_path, monkeypatch, failure_point):
    context, request_id = forwarded_context(tmp_path)
    context["dryRun"] = failure_point == "dry-run"

    def attempt(*args, **kwargs):
        assert args[1].source == REWRITE
        if failure_point == "compiler":
            raise OSError("compiler unavailable")
        if failure_point == "no-attempt":
            return []
        return [{"status": "compile-failed", "differences": -1}]

    def fail_recording(*args, **kwargs):
        raise OSError("attempt recording unavailable")

    if failure_point != "dry-run":
        monkeypatch.setattr(source_plugins, "attempt_candidate", attempt)
    if failure_point == "recording":
        monkeypatch.setattr(source_plugins, "enrich_attempt_records", fail_recording)
    if failure_point in {"compiler", "recording"}:
        with pytest.raises(OSError):
            source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    else:
        result, _ = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
        assert result.status == "failure"
    assert rewrite_queue.find_entry(tmp_path, request_id)["source"] == REWRITE


def test_rejected_content_never_reaches_compiler(tmp_path, monkeypatch):
    context, request_id = forwarded_context(tmp_path, source='#include "/private/data"\n' + REWRITE)
    seen = []

    def attempt(row, candidate, *args, **kwargs):
        seen.append(candidate.source)
        return [{"status": "compile-failed", "differences": -1}]

    monkeypatch.setattr(source_plugins, "attempt_candidate", attempt)
    source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert seen == [context["selectedSourceCandidate"].source]
    assert rewrite_queue.find_entry(tmp_path, request_id) is None


@pytest.mark.parametrize("compiler", ["msvc", "clang", "clang-cl"])
def test_missing_target_slice_retains_forwarded_rewrite(tmp_path, monkeypatch, compiler):
    context, request_id = forwarded_context(tmp_path)
    context["compiler"] = compiler
    context["sourceParityRow"].pop("bytes")

    def missing_inventory_slice(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="target slice unavailable")

    # MSVC without inline bytes invokes inventory_slice; the clang backends
    # reject missing inline bytes directly. All three are pre-compiler failures.
    monkeypatch.setattr(source_parity_synthesize, "run", missing_inventory_slice)
    result, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert result.status == "failure"
    assert [record["status"] for record in updated["sourceParityAttemptRecords"]] == ["slice-failed"]
    assert rewrite_queue.find_entry(tmp_path, request_id)["source"] == REWRITE


@pytest.mark.parametrize("status", ["generated-only", "slice-failed", "error", "unknown", "compile-failed", "mismatched"])
def test_only_candidate_outcomes_consume_forwarded_rewrite(tmp_path, monkeypatch, status):
    context, request_id = forwarded_context(tmp_path)
    monkeypatch.setattr(source_plugins, "attempt_candidate", lambda *args, **kwargs: [{"status": status, "differences": -1}])
    source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert (rewrite_queue.find_entry(tmp_path, request_id) is None) == (status in {"compile-failed", "mismatched"})
