"""Forwarded source reaches the compiler dispatcher and retains the proof gate."""
from __future__ import annotations

import json

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery import package_verify, rewrite_queue, source_parity_synthesize, source_plugins
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
        return [{**base_record, "status": "matched" if differences == 0 else "mismatched", "differences": differences, "candidateCompileInvoked": True, "objdiffExit": 0}]

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


@pytest.mark.parametrize(
    "unsafe_source",
    [
        '#include "/private/data"\n' + REWRITE,
        "%:include <private/data>\n" + REWRITE,
        'int sample(void) { __asm__ volatile("ret"); }\n',
        "__attribute__((naked)) int sample(void) { return 7; }\n",
    ],
)
def test_rejected_content_never_reaches_compiler_or_inherits_semantic_evidence(tmp_path, monkeypatch, unsafe_source):
    context, request_id = forwarded_context(tmp_path, source=unsafe_source)
    seen = []

    def attempt(row, candidate, *args, **kwargs):
        seen.append(candidate)
        return [{"status": "compile-failed", "differences": -1}]

    monkeypatch.setattr(source_plugins, "attempt_candidate", attempt)
    source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert seen == [context["selectedSourceCandidate"]]
    assert "rewriteRequestId" not in seen[0].evidence
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
@pytest.mark.parametrize("invoked", [None, False, True])
def test_only_candidate_outcomes_consume_forwarded_rewrite(tmp_path, monkeypatch, status, invoked):
    context, request_id = forwarded_context(tmp_path)
    monkeypatch.setattr(source_plugins, "attempt_candidate", lambda *args, **kwargs: [{
        "status": status, "differences": -1, "candidateCompileInvoked": invoked,
        "objdiffExit": 0,
    }])
    source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert (rewrite_queue.find_entry(tmp_path, request_id) is None) == (invoked is True and status in {"compile-failed", "mismatched"})


@pytest.mark.parametrize("compiler", ["msvc", "msvc-inventory", "clang", "clang-cl"])
def test_real_missing_candidate_toolchain_retains_forwarded_rewrite(tmp_path, monkeypatch, compiler):
    context, request_id = forwarded_context(tmp_path)
    context.update(
        compiler="msvc" if compiler == "msvc-inventory" else compiler,
        compilerProfiles=[("test", [])],
        clang=str(tmp_path / "missing-clang"), vcRoot=str(tmp_path / "missing-msvc"),
    )
    # Target construction is independent of candidate compilation. Only bypass
    # that setup so each actual candidate helper reaches its missing executable.
    monkeypatch.setattr(source_parity_synthesize, "compile_asm_to_coff", lambda **kwargs: {"status": "ok"})
    if compiler == "msvc-inventory":
        context["sourceParityRow"].pop("bytes")
        monkeypatch.setattr(source_parity_synthesize, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""))
    elif compiler == "clang":
        compile_clang = source_parity_synthesize.compile_with_clang

        def compile_target_or_candidate(**kwargs):
            return {"status": "ok"} if kwargs["source"].suffix == ".S" else compile_clang(**kwargs)

        monkeypatch.setattr(source_parity_synthesize, "compile_with_clang", compile_target_or_candidate)
    if compiler.startswith("msvc"):
        result, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
        assert result.status == "failure"
        record, = updated["sourceParityAttemptRecords"]
        assert record["status"] == "compile-failed"
        assert record["candidateCompileInvoked"] is False
        assert "cl.exe not found" in record["stderr"]
    else:
        with pytest.raises(FileNotFoundError):
            source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert rewrite_queue.find_entry(tmp_path, request_id)["source"] == REWRITE


def test_real_missing_wine_retains_forwarded_rewrite(tmp_path, monkeypatch):
    context, request_id = forwarded_context(tmp_path)
    root = tmp_path / "msvc"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "cl.exe").touch()
    context.update(compiler="msvc", vcRoot=str(root), wine=str(tmp_path / "missing-wine"), compilerProfiles=[("test", [])])
    monkeypatch.setattr(source_parity_synthesize, "compile_asm_to_coff", lambda **kwargs: {"status": "ok"})
    with pytest.raises(FileNotFoundError):
        source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert rewrite_queue.find_entry(tmp_path, request_id)["source"] == REWRITE


@pytest.mark.parametrize("compiler", ["msvc", "msvc-inventory", "clang", "clang-cl"])
def test_compiler_rejection_records_invocation_and_consumes_rewrite(tmp_path, monkeypatch, compiler):
    context, request_id = forwarded_context(tmp_path)
    root = tmp_path / "msvc"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "cl.exe").touch()
    context.update(compiler="msvc" if compiler == "msvc-inventory" else compiler, vcRoot=str(root), compilerProfiles=[("test", [])])
    calls = []

    def reject_source(command, **kwargs):
        if "agentdecompile_recovery.inventory_slice" in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        calls.append(command)
        diagnostic = {
            "clang": "candidate.c:1:2: error: expected expression",
            "clang-cl": "candidate.c(1,2): error: expected expression",
        }.get(compiler, "in.c(1) : error C2143: syntax error")
        return SimpleNamespace(returncode=1, stdout="", stderr=diagnostic)

    monkeypatch.setattr(package_verify, "run_command", reject_source)
    monkeypatch.setattr(source_parity_synthesize, "run", reject_source)
    monkeypatch.setattr(source_parity_synthesize, "compile_asm_to_coff", lambda **kwargs: {"status": "ok"})
    if compiler == "msvc-inventory":
        context["sourceParityRow"].pop("bytes")
    elif compiler == "clang":
        compile_clang = source_parity_synthesize.compile_with_clang
        monkeypatch.setattr(source_parity_synthesize, "compile_with_clang", lambda **kwargs: (
            {"status": "ok"} if kwargs["source"].suffix == ".S" else compile_clang(**kwargs)
        ))
    result, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert calls
    assert result.status == "failure"
    record, = updated["sourceParityAttemptRecords"]
    assert record["status"] == "compile-failed"
    assert record["candidateCompileInvoked"] is True
    assert rewrite_queue.find_entry(tmp_path, request_id) is None


def test_wine_startup_failure_does_not_count_as_candidate_compilation(tmp_path, monkeypatch):
    context, request_id = forwarded_context(tmp_path)
    root = tmp_path / "msvc"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "cl.exe").touch()
    context.update(compiler="msvc", vcRoot=str(root), compilerProfiles=[("test", [])])
    monkeypatch.setattr(source_parity_synthesize, "compile_asm_to_coff", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(package_verify, "run_command", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout="", stderr="wine: could not load kernel32.dll, status c0000135",
    ))
    _, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    record, = updated["sourceParityAttemptRecords"]
    assert record["status"] == "compile-failed"
    assert record["candidateCompileInvoked"] is False
    assert rewrite_queue.find_entry(tmp_path, request_id)["source"] == REWRITE


@pytest.mark.parametrize("compiler", ["clang", "clang-cl"])
def test_native_loader_failure_does_not_count_as_candidate_compilation(tmp_path, monkeypatch, compiler):
    context, request_id = forwarded_context(tmp_path)
    context.update(compiler=compiler, compilerProfiles=[("test", [])])
    monkeypatch.setattr(source_parity_synthesize, "compile_asm_to_coff", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(source_parity_synthesize, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=127, stdout="", stderr="clang: error while loading shared libraries: libLLVM.so: cannot open shared object file",
    ))
    if compiler == "clang":
        compile_clang = source_parity_synthesize.compile_with_clang
        monkeypatch.setattr(source_parity_synthesize, "compile_with_clang", lambda **kwargs: (
            {"status": "ok"} if kwargs["source"].suffix == ".S" else compile_clang(**kwargs)
        ))
    _, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    record, = updated["sourceParityAttemptRecords"]
    assert record["status"] == "compile-failed"
    assert record["candidateCompileInvoked"] is False
    assert rewrite_queue.find_entry(tmp_path, request_id)["source"] == REWRITE


@pytest.mark.parametrize("compiler", ["msvc", "msvc-inventory", "clang", "clang-cl"])
@pytest.mark.parametrize("outcome", ["matched", "mismatched", "error", "invalid-output"])
@pytest.mark.parametrize("forwarded", [True, False])
def test_real_dispatch_and_objdiff_receipt_gate(tmp_path, monkeypatch, compiler, outcome, forwarded):
    context, request_id = forwarded_context(tmp_path)
    context.update(compiler="msvc" if compiler == "msvc-inventory" else compiler, compilerProfiles=[("test", [])], sourceShapeSearch=True)
    if not forwarded:
        context.pop("workDir")
    if compiler == "msvc-inventory":
        context["sourceParityRow"].pop("bytes")
    objdiff_calls = []
    compiled_sources = []

    def compile_object(**kwargs):
        if kwargs["source"].suffix == ".c":
            compiled_sources.append(kwargs["source"].read_text())
        kwargs["object_path"].write_bytes(b"controlled object")
        return {"status": "ok", "compilerInvoked": True, "object": str(kwargs["object_path"])}

    def verifier_process(command, **kwargs):
        if "agentdecompile_recovery.inventory_slice" in command:
            case_dir = Path(command[command.index("--out-dir") + 1])
            (case_dir / "target.obj").write_bytes(b"controlled target")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[0] == "objdump":
            return SimpleNamespace(returncode=0, stdout="0000: c3  ret\n", stderr="")
        assert command[:2] == ["objdiff", "diff"]
        objdiff_calls.append(command)
        output = json.dumps({"sections": [{"kind": "SECTION_CODE", "match_percent": 50 if outcome == "mismatched" else 100}]})
        return SimpleNamespace(returncode=1 if outcome == "error" else 0, stdout="not JSON" if outcome == "invalid-output" else output, stderr="")

    for name in ("compile_with_msvc", "compile_with_clang", "compile_with_clangcl", "compile_asm_to_coff"):
        monkeypatch.setattr(source_parity_synthesize, name, compile_object)
    monkeypatch.setattr(source_parity_synthesize, "run", verifier_process)
    monkeypatch.setattr(source_parity_synthesize, "semantic_equivalent_variants", lambda *args, **kwargs: [{"name": "probe", "source": REWRITE}])
    monkeypatch.setattr(source_parity_synthesize, "object_text_bytes", lambda *args, **kwargs: b"\xc3")
    result, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert objdiff_calls
    assert compiled_sources[0] == (REWRITE if forwarded else context["selectedSourceCandidate"].source)
    assert result.status == ("success" if outcome == "matched" else "failure")
    assert bool(updated["sourceParityMatchRecords"]) == (outcome == "matched")
    if outcome in {"error", "invalid-output"}:
        assert all(record["status"] == "error" for record in updated["sourceParityAttemptRecords"])
        assert updated["sourceShapeMatchRecords"] == []
        for record in updated["sourceParityAttemptRecords"]:
            assert record["differences"] == -1
            assert record["diagnosticFallback"]["status"] == "matched"
        assert result.data["matchCount"] == result.data["sourceShapeMatchCount"] == 0
    if forwarded:
        assert (rewrite_queue.find_entry(tmp_path, request_id) is None) == (outcome in {"matched", "mismatched"})


@pytest.mark.parametrize("status", ["matched", "code-slice-matched", "mismatched"])
@pytest.mark.parametrize("receipt", [{}, {"objdiffExit": 1}, {"objdiffExit": 0, "fallback": "objdump"}])
def test_plugin_rejects_incomplete_or_fallback_match_receipt(tmp_path, monkeypatch, status, receipt):
    context, request_id = forwarded_context(tmp_path)
    monkeypatch.setattr(source_plugins, "attempt_candidate", lambda *args, **kwargs: [{
        "status": status, "differences": 0, "candidateCompileInvoked": True, **receipt,
    }])
    result, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert result.status == "failure"
    assert updated["sourceParityMatchRecords"] == []
    assert rewrite_queue.find_entry(tmp_path, request_id)["source"] == REWRITE


@pytest.mark.parametrize("compiler", ["msvc", "clang-cl"])
@pytest.mark.parametrize("objdiff_exit", [0, 1])
def test_source_shape_promotion_requires_its_own_objdiff_receipt(tmp_path, monkeypatch, compiler, objdiff_exit):
    context, _ = forwarded_context(tmp_path)
    target = tmp_path / "target.obj"
    target.write_bytes(b"controlled target")

    def compile_object(**kwargs):
        kwargs["object_path"].write_bytes(b"controlled candidate")
        return {"status": "ok", "object": str(kwargs["object_path"])}

    def verifier_process(command, **kwargs):
        if command[0] == "objdump":
            return SimpleNamespace(returncode=0, stdout="0000: c3  ret\n", stderr="")
        assert command[:2] == ["objdiff", "diff"]
        assert command[3] == str(target)
        return SimpleNamespace(returncode=objdiff_exit, stdout=json.dumps({"sections": [{"kind": "SECTION_CODE", "match_percent": 100}]}), stderr="")

    monkeypatch.setattr(source_parity_synthesize, "semantic_equivalent_variants", lambda *args, **kwargs: [{"name": "probe", "source": REWRITE}])
    monkeypatch.setattr(source_parity_synthesize, "compile_with_msvc", compile_object)
    monkeypatch.setattr(source_parity_synthesize, "compile_with_clangcl", compile_object)
    monkeypatch.setattr(source_parity_synthesize, "object_text_bytes", lambda *args, **kwargs: b"\xc3")
    monkeypatch.setattr(source_parity_synthesize, "run", verifier_process)
    kwargs = {"data": b"\xc3", "target_obj": target, "timeout": 1}
    if compiler == "msvc":
        search = source_parity_synthesize.run_msvc_source_shape_search(
            context["sourceParityRow"], context["selectedSourceCandidate"], tmp_path,
            **kwargs, compiler_profiles=[("test", [])], vc_root=None, wine="wine", wineprefix=None,
        )
    else:
        search = source_parity_synthesize.run_source_shape_search(
            context["sourceParityRow"], context["selectedSourceCandidate"], tmp_path, **kwargs, clang_cl="clang-cl",
        )
    assert search["summary"]["status"] == ("matched" if objdiff_exit == 0 else "no-match")
    promoted = source_parity_synthesize.matched_source_shape_record({"name": "sample"}, search["path"])
    assert (promoted is not None) == (objdiff_exit == 0)
    if promoted is not None:
        assert promoted["objdiffExit"] == promoted["differences"] == 0


@pytest.mark.parametrize(("outcomes", "consumed"), [
    (("compile-failed", "error"), False),
    (("mismatched", "error"), False),
    (("compile-failed", "mismatched"), True),
    (("error", "matched"), True),
    (("slice-failed", "mismatched"), False),
    (("compiler-unavailable", "mismatched"), False),
])
def test_multi_profile_rewrite_requires_complete_rejection_or_a_match(tmp_path, monkeypatch, outcomes, consumed):
    context, request_id = forwarded_context(tmp_path)
    context.update(compiler="clang", compilerProfiles=[("a", ["-O0"]), ("b", ["-O1"])])
    compiled_sources = []

    def profile_outcome(path):
        return outcomes[0 if path.parent.name.startswith("profile_00") else 1]

    def compile_object(**kwargs):
        outcome = profile_outcome(kwargs["object_path"])
        if kwargs["source"].suffix == ".c":
            compiled_sources.append(kwargs["source"].read_text())
            if outcome in {"compile-failed", "compiler-unavailable"}:
                return {"status": "failed", "compilerInvoked": outcome == "compile-failed"}
        elif outcome == "slice-failed":
            return {"status": "failed"}
        kwargs["object_path"].write_bytes(b"controlled object")
        return {"status": "ok", "compilerInvoked": True}

    def verifier_process(command, **kwargs):
        if command[0] == "objdump":
            return SimpleNamespace(returncode=1, stdout="", stderr="diagnostic unavailable")
        assert command[:2] == ["objdiff", "diff"]
        outcome = profile_outcome(Path(command[5]))
        output = json.dumps({"sections": [{"kind": "SECTION_CODE", "match_percent": 100 if outcome == "matched" else 50}]})
        return SimpleNamespace(returncode=1 if outcome == "error" else 0, stdout=output, stderr="")

    monkeypatch.setattr(source_parity_synthesize, "compile_with_clang", compile_object)
    monkeypatch.setattr(source_parity_synthesize, "run", verifier_process)
    result, updated = source_plugins.SourceCandidateObjdiffPlugin().execute(context)
    assert compiled_sources == [REWRITE, REWRITE]
    expected = ["code-slice-matched" if outcome == "matched" else "compile-failed" if outcome == "compiler-unavailable" else outcome for outcome in outcomes]
    assert [record["status"] for record in updated["sourceParityAttemptRecords"]] == expected
    assert result.status == ("success" if "matched" in outcomes else "failure")
    assert (rewrite_queue.find_entry(tmp_path, request_id) is None) == consumed
