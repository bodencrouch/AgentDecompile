"""P1 regression sources, UNRUN under the source-only recovery mission.

Controlled capture/regular-file fixtures verify the binding boundary, not objdiff
qualification. Explicitly enabled real-checker cases require separately authorized
native/Node binaries and authentic target/candidate object inputs.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from pathlib import Path

import pytest

from agentdecompile_grid.core import (
    BudgetClass, ObjectRef, Refused, ResultStatus, TaskSpec, VerificationOutcome, canonical_json, digest,
)
from agentdecompile_grid.objects.local import LocalDirStore
from agentdecompile_recovery.grid_lanes import parity
from agentdecompile_recovery.grid_lanes._common import RunOutcome
from agentdecompile_recovery.objdiff_verification import parse_objdiff_report

pytestmark = [pytest.mark.unit, pytest.mark.skipif(os.name != "posix", reason="P1 needs POSIX descriptor/process ownership")]
MATCH = '{"sections":[{"kind":"SECTION_CODE","match_percent":100}]}'
MISMATCH = '{"sections":[{"kind":"SECTION_CODE","match_percent":70}]}'


@pytest.fixture
def lane(tmp_path, monkeypatch):
    objects = LocalDirStore(tmp_path / "cas", touch_on_read=True, quarantine_corrupt=True)
    binary = tmp_path / "declared-native"
    binary.write_bytes(b"controlled native artifact, never executed by this fixture")
    checker = parity.register_native(binary)
    spec = TaskSpec("parity-check", 1, {"target": objects.put(b"target"), "candidate": objects.put(b"candidate")},
                    {"verifier_id": checker.verifier_id, "symbol": "example"}, "historical-basis")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(parity, "_capture", lambda *args: RunOutcome((), 0, MATCH, "", 0.01, False))
    return parity.ParityCheck(), spec, objects, scratch, checker


def _run(lane):
    kind, spec, objects, scratch, _ = lane
    return kind.run(spec, objects, str(scratch))


def _verify(lane, result, spec=None):
    kind, selected, objects, scratch, _ = lane
    return kind.verify(spec or selected, result, objects, str(scratch))


def _receipt(lane, result):
    return json.loads(Path(lane[2].path_for(result.outputs["receipt"])).read_bytes())


def _replace_receipt(lane, result, **changes):
    receipt = _receipt(lane, result)
    receipt.update(changes)
    return dataclasses.replace(result, outputs={**result.outputs, "receipt": lane[2].put(canonical_json(receipt))})


@pytest.mark.parametrize("raw,code,grade", [(MATCH, 0, "matched"), (MISMATCH, 0, "mismatched"), ("", 2, "error")])
def test_authenticated_observation_classes(lane, monkeypatch, raw, code, grade):
    monkeypatch.setattr(parity, "_capture", lambda *args: RunOutcome((), code, raw, "diagnostic", .01, False))
    result = _run(lane)
    checked = _verify(lane, result)
    assert checked.outcome == VerificationOutcome.VERIFIED
    assert checked.method == "parity-binding-v1"
    assert checked.evidence["reason"] == "receipt_equal"
    assert checked.evidence["grade"] == grade
    assert checked.evidence["comparison_scope"] == "native-reported-code"
    assert checked.evidence["predicate"] == "authenticated-checker-observation-v1"
    assert checked.evidence["checker_identity_scope"] == "registered-artifacts-v1"
    assert checked.evidence["target_region_complete"] is False
    assert checked.evidence["runtime_admission"] == "not_evaluated"
    assert checked.evidence["proposal_outputs"] == result.outputs


def test_valid_historical_observation_and_partial_100_percent(lane):
    kind, spec, objects, scratch, checker = lane
    result = _run(lane)
    historical = {key: value for key, value in parse_objdiff_report(0, MATCH).items() if key != "output"}
    historical.update(kind="parity-check", kind_version=1, verifier_id=checker.verifier_id, verifier="native",
                      sides={key: ref.hex for key, ref in spec.inputs.items()}, symbol="example", grade="matched",
                      basis_hash=spec.basis_hash)
    assert result.outputs["receipt"] == ObjectRef.of_bytes(canonical_json(historical))
    assert spec.task_id == digest(canonical_json({"kind": spec.kind, "kind_version": 1,
        "inputs": dict(spec.inputs), "params": dict(spec.params), "basis_hash": spec.basis_hash}))
    assert _verify(lane, result).evidence["target_region_complete"] is False
    assert "target_region_complete" not in historical
    columns = parity.PARITY_RECEIPT_SQL.split("(", 1)[1].split(");", 1)[0].strip().splitlines()
    assert len(columns) == 8


@pytest.mark.parametrize("change", [
    {"task_id": "f" * 64}, {"basis_hash": "foreign"}, {"status": ResultStatus.ERROR}, {"reason": "unexpected"},
])
def test_foreign_proposal(lane, change):
    checked = _verify(lane, dataclasses.replace(_run(lane), **change))
    assert (checked.outcome, checked.evidence["reason"]) == (VerificationOutcome.REFUTED, "proposal_binding_invalid")


@pytest.mark.parametrize("changes", [
    {"grade": "error"}, {"objdiffExit": True}, {"objdiffExit": 1}, {"differences": False},
    {"kind_version": True}, {"basis_hash": "foreign"}, {"symbol": "foreign"}, {"verifier": "node"},
    {"sides": {"target": "a" * 64, "candidate": "b" * 64}},
])
def test_receipt_binding_and_wrong_grade_exit(lane, changes):
    checked = _verify(lane, _replace_receipt(lane, _run(lane), **changes))
    assert checked.outcome == VerificationOutcome.REFUTED
    assert checked.evidence["reason"] == "proposal_binding_invalid"


def test_swapped_sides(lane):
    result = _run(lane)
    spec = dataclasses.replace(lane[1], inputs={"target": lane[1].inputs["candidate"], "candidate": lane[1].inputs["target"]})
    # Even a restamped task id cannot repair the receipt's named side binding.
    result = dataclasses.replace(result, task_id=spec.task_id)
    assert _verify(lane, result, spec).outcome == VerificationOutcome.REFUTED


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":2}', b'{"x":NaN}', b'{"x":Infinity}', b' {"x":1}'])
def test_duplicate_nonfinite_noncanonical_receipt(lane, raw):
    result = _run(lane)
    result = dataclasses.replace(result, outputs={**result.outputs, "receipt": lane[2].put(raw)})
    assert _verify(lane, result).outcome == VerificationOutcome.REFUTED


def test_raw_unrelated_to_receipt(lane):
    result = _run(lane)
    result = dataclasses.replace(result, outputs={**result.outputs, "raw": lane[2].put(MISMATCH.encode())})
    assert _verify(lane, result).evidence == {"reason": "proposal_binding_invalid", "role": "raw"}


@pytest.mark.parametrize("mode", ["missing_key", "missing_object", "bad_ref", "extra_output", "forged_hash"])
def test_proposal_output_refusals(lane, mode):
    result = _run(lane)
    outputs = dict(result.outputs)
    if mode == "missing_key":
        del outputs["raw"]
    elif mode == "missing_object":
        outputs["raw"] = ObjectRef.of_bytes(b"not stored")
    elif mode == "bad_ref":
        outputs["raw"] = "not-a-ref"
    elif mode == "extra_output":
        outputs["unexpected"] = outputs["raw"]
    else:
        Path(lane[2].path_for(outputs["receipt"])).write_bytes(b"corrupt")
    checked = _verify(lane, dataclasses.replace(result, outputs=outputs))
    expected = VerificationOutcome.UNVERIFIABLE if mode == "missing_object" else VerificationOutcome.REFUTED
    assert checked.outcome == expected
    assert checked.evidence["reason"] == ("proposal_unavailable" if mode == "missing_object" else "proposal_binding_invalid")


@pytest.mark.parametrize("timeout", [True, "1", float("nan"), float("inf"), [], {}])
def test_timeout_shape_refuses_before_io(lane, timeout, monkeypatch):
    kind, spec, objects, scratch, _ = lane
    monkeypatch.setattr(objects, "size", lambda *_: pytest.fail("evidence read before validation"))
    with pytest.raises(Refused, match="^parity_invalid_spec$"):
        kind.run(dataclasses.replace(spec, params={**spec.params, "timeout_s": timeout}), objects, str(scratch))


@pytest.mark.parametrize("changes", [{"kind_version": True}, {"kind": "other"}, {"budget": BudgetClass.MEDIUM},
                                       {"basis_hash": ""}, {"inputs": {}}])
def test_selected_task_shape(lane, changes):
    with pytest.raises(Refused, match="^parity_invalid_spec$"):
        lane[0].run(dataclasses.replace(lane[1], **changes), lane[2], str(lane[3]))


@pytest.mark.parametrize("symbol,reason", [(False, "invalid_spec"), (3, "invalid_spec"), ("a\0b", "invalid_spec"),
                                            ("é" * 2049, "limit_exceeded")])
def test_symbol_bounds(lane, symbol, reason):
    spec = dataclasses.replace(lane[1], params={**lane[1].params, "symbol": symbol})
    with pytest.raises(Refused, match="^parity_" + reason + "$"):
        lane[0].run(spec, lane[2], str(lane[3]))


@pytest.mark.parametrize("timeout,expected", [(None, 60), (-1, 60), (0, 60), (100, 60), (.25, .25)])
def test_timeout_default_cap(lane, timeout, expected):
    spec = dataclasses.replace(lane[1], params={**lane[1].params, "timeout_s": timeout})
    result = lane[0].run(spec, lane[2], str(lane[3]))
    assert result.metrics["deadline_s"] == expected


def test_remote_store_and_gc_configuration_refused(lane):
    class Remote:
        def get(self, *_):
            pytest.fail("unbounded get")
        def get_path(self, *_):
            pytest.fail("unbounded get_path")
    with pytest.raises(Refused, match="parity_transport_unsupported"):
        lane[0].run(lane[1], Remote(), str(lane[3]))
    lane[2].size_cap_bytes = 1000
    with pytest.raises(Refused, match="parity_transport_unsupported"):
        _run(lane)


@pytest.mark.parametrize("mode", ["corrupt", "missing", "symlink", "oversize"])
def test_input_integrity_and_support_bounds(lane, mode, monkeypatch):
    path = Path(lane[2].path_for(lane[1].inputs["target"]))
    if mode == "corrupt":
        path.write_bytes(b"wrong!")
    elif mode == "missing":
        path.unlink()
    elif mode == "symlink":
        saved = path.with_name("external")
        path.rename(saved)
        path.symlink_to(saved)
    else:
        monkeypatch.setattr(parity, "INPUT_LIMIT", 2)
    reason = {"corrupt": "input_integrity_failed", "oversize": "limit_exceeded"}.get(mode, "input_unavailable")
    with pytest.raises(Refused, match="^parity_" + reason + "$"):
        _run(lane)
    if mode == "corrupt":
        assert path.read_bytes() == b"wrong!", "read must not quarantine or replace evidence"


def test_store_inode_isolation(lane, monkeypatch):
    original = Path(lane[2].path_for(lane[1].inputs["target"]))
    def mutate(checker, target, candidate, symbol, deadline):
        assert target.stat().st_ino != original.stat().st_ino
        target.write_bytes(b"modified")
        return RunOutcome((), 0, MATCH, "", .01, False)
    monkeypatch.setattr(parity, "_capture", mutate)
    with pytest.raises(Refused, match="^parity_execution_changed$"):
        _run(lane)
    assert original.read_bytes() == b"target"


def test_corrupt_existing_put(lane):
    first = _run(lane)
    Path(lane[2].path_for(first.outputs["receipt"])).write_bytes(b"corrupt")
    with pytest.raises(Refused, match="^parity_recomputed_binding_invalid$"):
        _run(lane)


def test_cached_native_changed(lane):
    lane[4].path.write_bytes(b"different declared binary")
    with pytest.raises(Refused, match="^parity_checker_identity_mismatch$"):
        _run(lane)


def test_checker_changed_during_run(lane, monkeypatch):
    def mutate(*args):
        lane[4].path.write_bytes(b"changed during execution")
        return RunOutcome((), 0, MATCH, "", .01, False)
    monkeypatch.setattr(parity, "_capture", mutate)
    with pytest.raises(Refused, match="^parity_execution_changed$"):
        _run(lane)


def test_authenticated_receipt_differs(lane, monkeypatch):
    result = _run(lane)
    monkeypatch.setattr(parity, "_capture", lambda *args: RunOutcome((), 0, MISMATCH, "", .01, False))
    checked = _verify(lane, result)
    assert checked.outcome == VerificationOutcome.REFUTED
    assert checked.evidence["reason"] == "receipt_differs"


def test_one_deadline_includes_proposal_read(lane, monkeypatch):
    result = _run(lane)
    clock = [100.0]
    monkeypatch.setattr(parity.time, "monotonic", lambda: clock[0])
    read = parity._local_read
    def slow_read(*args, **kwargs):
        value = read(*args, **kwargs)
        clock[0] += 31
        return value
    monkeypatch.setattr(parity, "_local_read", slow_read)
    monkeypatch.setattr(parity, "_capture", lambda *_: pytest.fail("expired operation executed checker"))
    assert _verify(lane, result).evidence["reason"] == "deadline_exceeded"


def _node_lane(lane, tmp_path):
    script = tmp_path / "checker.mjs"
    script.write_bytes(b"declared script")
    dist = tmp_path / "bundle" / "node_modules" / "objdiff-wasm" / "dist"
    dist.mkdir(parents=True)
    (dist / "objdiff.js").write_bytes(b"declared js")
    (dist / "objdiff.core.wasm").write_bytes(b"declared wasm")
    checker = parity.register_node(script, tmp_path / "bundle", node=sys.executable)
    spec = dataclasses.replace(lane[1], params={"verifier_id": checker.verifier_id, "symbol": ""})
    return (lane[0], spec, lane[2], lane[3], checker), dist


@pytest.mark.parametrize("file", ["objdiff.js", "objdiff.core.wasm"])
def test_cached_wasm_artifact_changed(lane, tmp_path, file):
    lane, dist = _node_lane(lane, tmp_path)
    (dist / file).write_bytes(b"changed")
    with pytest.raises(Refused, match="^parity_checker_identity_mismatch$"):
        _run(lane)


def test_scratch_path_noise_and_node_incomplete_rows(lane, tmp_path, monkeypatch):
    lane, _ = _node_lane(lane, tmp_path)
    def noisy(checker, target, candidate, symbol, deadline):
        return RunOutcome((), 0, f"base: {candidate}\nrows identical: 0, differing: 0\nRESULT: MATCH 100%\n", "", .01, False)
    monkeypatch.setattr(parity, "_capture", noisy)
    first, second = _run(lane), _run(lane)
    assert first.outputs["raw"] != second.outputs["raw"]
    assert first.outputs["receipt"] == second.outputs["receipt"]
    checked = _verify(lane, first)
    assert checked.outcome == VerificationOutcome.VERIFIED
    assert checked.evidence["comparison_scope"] == "node-reported-symbol-rows"
    assert checked.evidence["target_region_complete"] is False
    assert checked.evidence["runtime_admission"] == "not_evaluated"


@pytest.mark.parametrize("mode,reason", [("stdout", "output_limit_exceeded"), ("stderr", "output_limit_exceeded"),
                                         ("hang", "deadline_exceeded"), ("ok", None)])
def test_owned_process_capture(tmp_path, monkeypatch, mode, reason):
    """An actual controlled child tests capture mechanics, never native checker qualification."""
    executable = tmp_path / "controlled-child"
    body = {"stdout": "os.write(1, b'x'*8192)", "stderr": "os.write(2, b'x'*8192)",
            "hang": "time.sleep(10)", "ok": "print('done')"}[mode]
    executable.write_text(f"#!{sys.executable}\nimport os,time\n{body}\n")
    executable.chmod(0o700)
    checker = parity.register_native(executable)
    monkeypatch.setattr(parity, "RAW_LIMIT", 1024)
    monkeypatch.setattr(parity, "STDERR_LIMIT", 1024)
    deadline = time.monotonic() + 2
    if reason:
        with pytest.raises(parity._BindingFailure) as caught:
            parity._capture(checker, tmp_path / "target", tmp_path / "candidate", "", deadline)
        assert caught.value.reason == reason
    else:
        assert parity._capture(checker, tmp_path / "target", tmp_path / "candidate", "", deadline).stdout == "done\n"
    assert time.monotonic() < deadline


@pytest.mark.parametrize("flavour", ["native", "node"])
def test_explicit_real_checker_acceptance(tmp_path, flavour):
    """Separately authorized native/Node acceptance; no fixture qualifies these receipts."""
    if os.environ.get("AGENT_DECOMPILE_P1_REAL_ACCEPTANCE") != "1":
        pytest.skip("requires explicit real-checker acceptance authorization and inputs")
    if flavour == "native":
        checker = parity.register_native(os.environ["AGENT_DECOMPILE_P1_NATIVE"])
    else:
        checker = parity.register_node(os.environ["AGENT_DECOMPILE_P1_SCRIPT"],
                                       os.environ["AGENT_DECOMPILE_P1_WASM_ROOT"], node=os.environ["AGENT_DECOMPILE_P1_NODE"])
    objects = LocalDirStore(tmp_path / "cas")
    spec = TaskSpec("parity-check", 1,
        {role: objects.put(Path(os.environ[f"AGENT_DECOMPILE_P1_{role.upper()}"]).read_bytes()) for role in ("target", "candidate")},
        {"verifier_id": checker.verifier_id, "symbol": os.environ.get("AGENT_DECOMPILE_P1_SYMBOL", "")}, "explicit-acceptance")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    result = parity.ParityCheck().run(spec, objects, str(scratch))
    checked = parity.ParityCheck().verify(spec, result, objects, str(scratch))
    assert checked.outcome == VerificationOutcome.VERIFIED
    assert checked.evidence["grade"] == os.environ["AGENT_DECOMPILE_P1_EXPECTED_GRADE"]
    assert checked.evidence["target_region_complete"] is False


def test_declared_size_contradiction(lane, monkeypatch):
    size = lane[2].size
    monkeypatch.setattr(lane[2], "size", lambda ref: size(ref) + 1)
    with pytest.raises(Refused, match="^parity_input_integrity_failed$"):
        _run(lane)


def test_oversize_proposal_is_unverifiable(lane, monkeypatch):
    result = _run(lane)
    monkeypatch.setattr(parity, "RAW_LIMIT", 1)
    checked = _verify(lane, result)
    assert checked.outcome == VerificationOutcome.UNVERIFIABLE
    assert checked.evidence == {"reason": "limit_exceeded", "role": "raw"}


def test_checker_artifact_support_bound(lane, monkeypatch):
    monkeypatch.setattr(parity, "ARTIFACT_LIMIT", 1)
    with pytest.raises(Refused, match="^parity_limit_exceeded$"):
        _run(lane)


def test_oversize_growing_stream_reads_only_limit_plus_one(tmp_path):
    path = tmp_path / "growing"
    path.write_bytes(b"abc")
    with path.open("rb", buffering=0) as source:
        class Growing:
            consumed = 0
            def fileno(self):
                return source.fileno()
            def read(self, requested):
                if self.consumed == 0:
                    with path.open("ab") as writer:
                        writer.write(b"0123456789")
                chunk = source.read(requested)
                self.consumed += len(chunk)
                return chunk
        growing = Growing()
        with pytest.raises(parity._BindingFailure, match="limit_exceeded"):
            parity._stream(growing, 5, time.monotonic() + 5)
        assert growing.consumed == 6


def test_cache_miss_uses_bounded_resolution(lane, monkeypatch):
    monkeypatch.delitem(parity.PARITY_CHECKERS._items, lane[4].verifier_id)
    monkeypatch.setenv("AGENT_DECOMPILE_OBJDIFF", str(lane[4].path))
    monkeypatch.setattr(parity, "register_native", lambda *_: pytest.fail("unbounded registration on strong route"))
    assert _run(lane).status == ResultStatus.OK


def test_missing_checker_is_unavailable(lane):
    lane[4].path.unlink()
    with pytest.raises(Refused, match="^parity_checker_unavailable$"):
        _run(lane)


def test_put_must_return_supplied_content_address(lane, monkeypatch):
    monkeypatch.setattr(lane[2], "put", lambda _: ObjectRef.of_bytes(b"wrong address"))
    with pytest.raises(Refused, match="^parity_recomputed_binding_invalid$"):
        _run(lane)


def test_parser_failure_is_unavailable_not_proposal_refutation(lane, monkeypatch):
    result = _run(lane)
    def failed_parser(*args):
        raise TypeError("unexpected local parser failure")
    monkeypatch.setattr(parity, "_normalize", failed_parser)
    checked = _verify(lane, result)
    assert checked.outcome == VerificationOutcome.UNVERIFIABLE
    assert checked.evidence["reason"] == "execution_unavailable"


def test_node_executable_and_environment_remain_outside_legacy_id(lane, tmp_path, monkeypatch):
    lane, _ = _node_lane(lane, tmp_path)
    monkeypatch.setattr(parity, "_capture", lambda *args: RunOutcome((), 0,
        "rows identical: 1, differing: 0\nRESULT: MATCH 100%", "", .01, False))
    result = _run(lane)
    alternate = tmp_path / "alternate-runtime"
    alternate.write_bytes(b"different runtime; capture fixture only")
    alternate.chmod(0o700)
    monkeypatch.setitem(parity.PARITY_CHECKERS._items, lane[4].verifier_id,
                        dataclasses.replace(lane[4], node=alternate))
    monkeypatch.setenv("P1_UNQUALIFIED_ENVIRONMENT", "changed")
    checked = _verify(lane, result)
    assert checked.outcome == VerificationOutcome.VERIFIED
    assert checked.evidence["checker_identity_scope"] == "registered-artifacts-v1"
    assert checked.evidence["runtime_admission"] == "not_evaluated"


def test_group_cleanup_never_signals_after_reaping(tmp_path, monkeypatch):
    """Controlled process seam proves ownership ordering without relying on PID timing."""
    import io
    events = []
    class Process:
        pid = 12345
        stdout = io.BytesIO()
        stderr = io.BytesIO()
        returncode = None
        def wait(self, timeout):
            events.append("reap")
            self.returncode = 0
            return 0
    class Selector:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def register(self, *args):
            pass
        def get_map(self):
            return {}
    # File descriptors need not be real: this is an explicit process/capture seam.
    class Pipe(io.BytesIO):
        def fileno(self):
            return 10
    process = Process()
    process.stdout, process.stderr = Pipe(), Pipe()
    monkeypatch.setattr(parity.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(parity.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(parity.os, "set_blocking", lambda *args: None)
    def observe(*args):
        assert "reap" not in events
        events.append("owned-child")
        return object()
    def kill(group, sig):
        assert group == process.pid
        if sig == 0:
            assert "reap" in events
            events.append("non-signalling-existence-probe")
            raise ProcessLookupError
        assert "reap" not in events
        events.append("signal-owned-group")
    monkeypatch.setattr(parity.os, "waitid", observe)
    monkeypatch.setattr(parity.os, "killpg", kill)
    checker = parity.ParityChecker("parity:" + "a" * 64, "native", tmp_path / "checker")
    parity._capture(checker, tmp_path / "target", tmp_path / "candidate", "", time.monotonic() + 5)
    assert events == ["owned-child", "signal-owned-group", "reap", "non-signalling-existence-probe"]


def test_invalid_selected_spec_without_computable_identity_is_unverifiable(lane):
    result = _run(lane)
    malformed = dataclasses.replace(lane[1], inputs=[])
    checked = _verify(lane, result, malformed)
    assert checked.outcome == VerificationOutcome.UNVERIFIABLE
    assert checked.evidence == {"reason": "invalid_spec"}
    assert checked.task_id == result.task_id


def test_surviving_or_reused_group_never_authorizes_termination(monkeypatch):
    clock = [0.0]
    signals = []
    monkeypatch.setattr(parity.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(parity.time, "sleep", lambda duration: clock.__setitem__(0, clock[0] + duration))
    monkeypatch.setattr(parity.os, "killpg", lambda group, sig: signals.append(sig))
    with pytest.raises(parity._BindingFailure, match="execution_unavailable"):
        parity._await_group_exit(12345, .03)
    assert signals and set(signals) == {0}
