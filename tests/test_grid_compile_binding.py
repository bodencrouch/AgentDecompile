"""Compile kind binding regressions; authored but unrun under the recovery mission.

All outputs are synthetic COFF fixtures. The producer is deterministic and does
not call a compiler; even a passing future run would not prove real-toolchain
acceptance, target-image binding, or source recovery.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import struct

import pytest

from agentdecompile_grid.core import (
    ObjectRef, Refused, ResultStatus, TaskResult, TaskSpec, VerificationOutcome,
    canonical_json, digest,
)
from agentdecompile_grid.objects.base import IntegrityError, ObjectMissing
from agentdecompile_grid.worker import sandbox
from agentdecompile_recovery.grid_lanes import compile as lane
from agentdecompile_recovery.grid_lanes._common import Infra

pytestmark = pytest.mark.unit


class MemoryCAS:
    """A get/put CAS with explicit unavailable/corrupt read controls, no filesystem."""

    def __init__(self):
        self.data = {}
        self.errors = {}
        self.reads = []

    def put(self, data):
        ref = ObjectRef.of_bytes(data)
        self.data[ref] = data
        return ref

    def get(self, ref):
        self.reads.append(ref)
        if ref in self.errors:
            raise self.errors[ref]
        if ref not in self.data:
            raise ObjectMissing("synthetic missing object")
        # Intentionally no integrity check: the lane must authenticate actual bytes.
        return self.data[ref]

    def exists(self, ref):
        return ref in self.data


def _coff(timestamp=1, payload=b"\x90\x90\xc3"):
    header = struct.pack("<HHIIIHH", 0x14C, 1, timestamp, 0, 0, 0, 0)
    section = struct.pack("<8sIIIIIIHHI", b".text\0\0\0", 0, 0, len(payload), 60, 0, 0, 0, 0, 0x60000020)
    return header + section + payload


def _spec(objects, **params):
    return TaskSpec(
        lane.CompileAttempt.name, lane.CompileAttempt.version,
        {"tu": objects.put(b"int answer(void) { return 42; }\n")},
        {"toolchain_identity_hash": "a" * 64, **params}, "b" * 64,
    )


def _receipt(spec):
    return {
        "schema": lane.RECEIPT_SCHEMA, "kind": lane.CompileAttempt.name,
        "kind_version": lane.CompileAttempt.version,
        "tu_sha256": spec.inputs["tu"].hex,
        "toolchain_identity_hash": str(spec.params["toolchain_identity_hash"]),
        "profile": str(spec.params.get("profile") or "default"),
        "opt": str(spec.params.get("opt") or lane.DEFAULT_OPT),
        "flags": [str(flag) for flag in (spec.params.get("flags") or ())],
        "basis_hash": spec.basis_hash,
    }


def _result(spec, outputs):
    return TaskResult(spec.task_id, ResultStatus.OK, outputs, "synthetic-producer", spec.basis_hash, 0.0)


def _object_result(spec, objects, data=None):
    data = _coff() if data is None else data
    obj_ref = objects.put(data)
    receipt = _receipt(spec)
    receipt.update({
        "outcome": "obj", "obj_sha256": digest(data), "obj_bytes": len(data),
        # Direct derivation lets malformed COFF fixtures reach the lane's guard.
        "masked_coff_sha256": hashlib.sha256(data[:4] + b"\0" * 4 + data[8:]).hexdigest(),
    })
    return _result(spec, {"obj": obj_ref, "receipt": objects.put(canonical_json(receipt))})


def _diagnostic_result(spec, objects, codes):
    diagnostic_ref = objects.put(b"synthetic compiler diagnostics")
    receipt = _receipt(spec)
    receipt.update({"outcome": "diag", "diagnostic_codes": codes, "diagnostics_sha256": diagnostic_ref.hex})
    return _result(spec, {"diagnostics": diagnostic_ref, "receipt": objects.put(canonical_json(receipt))})


def _edit_receipt(objects, result, **fields):
    receipt = json.loads(objects.get(result.outputs["receipt"]))
    receipt.update(fields)
    return dataclasses.replace(result, outputs={**result.outputs, "receipt": objects.put(canonical_json(receipt))})


def _controlled_producer(monkeypatch, recomputed):
    calls = []

    def run(self, spec, objects, scratch):
        calls.append(spec.task_id)
        return recomputed

    monkeypatch.setattr(lane.CompileAttempt, "run", run)
    return calls


def _refusal(monkeypatch, spec, result, objects, reason, *, outcome=VerificationOutcome.REFUTED, recomputed=None):
    calls = _controlled_producer(monkeypatch, result if recomputed is None else recomputed)
    verdict = lane.CompileAttempt().verify(spec, result, objects, "unused-scratch")
    assert verdict.outcome == outcome
    assert verdict.evidence["reason"] == reason
    assert calls == [], "invalid proposal must not invoke the producer or substitute its bytes"
    return verdict


def test_identical_actual_objects_verify(monkeypatch):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects)
    calls = _controlled_producer(monkeypatch, proposal)
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused-scratch")
    assert verdict.outcome == VerificationOutcome.VERIFIED
    assert verdict.evidence["why"] == "masked-coff-equal"
    assert verdict.evidence["obj_sha256_equal"] is True
    assert calls == [spec.task_id]
    assert objects.reads.count(proposal.outputs["obj"]) == 2


@pytest.mark.parametrize("params", [
    {}, {"profile": None, "opt": "", "flags": None},
    {"profile": "vc6", "opt": "/O1", "flags": ["/DVALUE=42", 7]},
])
def test_receipt_binds_exact_existing_default_semantics(monkeypatch, params):
    objects = MemoryCAS()
    spec = _spec(objects, **params)
    proposal = _object_result(spec, objects)
    _controlled_producer(monkeypatch, proposal)
    assert lane.CompileAttempt().verify(spec, proposal, objects, "unused").outcome == VerificationOutcome.VERIFIED


def test_timestamp_only_difference_verifies_with_authenticated_raw_hashes(monkeypatch):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects, _coff(timestamp=1))
    recomputed = _object_result(spec, objects, _coff(timestamp=999))
    assert proposal.outputs["obj"] != recomputed.outputs["obj"]
    _controlled_producer(monkeypatch, recomputed)
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused")
    assert verdict.outcome == VerificationOutcome.VERIFIED
    assert verdict.evidence["obj_sha256_equal"] is False
    masked = verdict.evidence["masked_coff_sha256"]
    assert masked["proposal"] == masked["recomputed"]


@pytest.mark.parametrize("truthful_raw_hash", [False, True])
def test_substituted_correctly_addressed_object_cannot_use_honest_masked_claim(monkeypatch, truthful_raw_hash):
    objects = MemoryCAS()
    spec = _spec(objects)
    honest = _object_result(spec, objects)
    substituted_bytes = _coff(payload=b"\x91\x90\xc3")
    substituted_ref = objects.put(substituted_bytes)
    poisoned = dataclasses.replace(honest, outputs={**honest.outputs, "obj": substituted_ref})
    if truthful_raw_hash:
        poisoned = _edit_receipt(objects, poisoned, obj_sha256=digest(substituted_bytes))
    assert objects.exists(substituted_ref)
    assert ObjectRef.of_bytes(objects.get(substituted_ref)) == substituted_ref
    reason = "obj-masked-coff-mismatch" if truthful_raw_hash else "obj-sha256-mismatch"
    _refusal(monkeypatch, spec, poisoned, objects, reason, recomputed=honest)


@pytest.mark.parametrize("field,value,reason", [
    ("schema", "unknown", "receipt-schema-mismatch"),
    ("kind", "other-kind", "receipt-kind-mismatch"),
    ("kind_version", 2, "receipt-kind-version-mismatch"),
    ("kind_version", True, "receipt-kind-version-mismatch"),
    ("tu_sha256", "c" * 64, "receipt-tu_sha256-mismatch"),
    ("toolchain_identity_hash", "c" * 64, "receipt-toolchain_identity_hash-mismatch"),
    ("profile", "other", "receipt-profile-mismatch"),
    ("opt", "/O1", "receipt-opt-mismatch"),
    ("flags", ["/DOTHER"], "receipt-flags-mismatch"),
    ("basis_hash", "c" * 64, "receipt-basis_hash-mismatch"),
    ("obj_sha256", "c" * 64, "obj-sha256-mismatch"),
    ("obj_bytes", -1, "obj-bytes-mismatch"),
    ("obj_bytes", 64, "obj-bytes-mismatch"),
    ("obj_bytes", True, "obj-bytes-mismatch"),
    ("obj_bytes", 63.0, "obj-bytes-mismatch"),
    ("obj_bytes", "63", "obj-bytes-mismatch"),
    ("masked_coff_sha256", "c" * 64, "obj-masked-coff-mismatch"),
    ("outcome", "unknown", "receipt-outcome-invalid"),
    ("outcome", None, "receipt-outcome-invalid"),
    ("outcome", {}, "receipt-outcome-invalid"),
])
def test_receipt_contradictions_refute_by_name(monkeypatch, field, value, reason):
    objects = MemoryCAS()
    spec = _spec(objects)
    result = _edit_receipt(objects, _object_result(spec, objects), **{field: value})
    _refusal(monkeypatch, spec, result, objects, reason)


@pytest.mark.parametrize("role", ["obj", "receipt"])
def test_required_output_role_cannot_be_omitted(monkeypatch, role):
    objects = MemoryCAS()
    spec = _spec(objects)
    result = _object_result(spec, objects)
    result = dataclasses.replace(result, outputs={key: ref for key, ref in result.outputs.items() if key != role})
    _refusal(monkeypatch, spec, result, objects, role + "-missing")


@pytest.mark.parametrize("field,value,reason", [
    ("task_id", "c" * 64, "task-id-mismatch"),
    ("basis_hash", "c" * 64, "result-basis-mismatch"),
    *[("status", status, "result-not-claim") for status in ResultStatus if status != ResultStatus.OK],
])
def test_result_binding_and_nonclaims_refuse(monkeypatch, field, value, reason):
    objects = MemoryCAS()
    spec = _spec(objects)
    result = dataclasses.replace(_object_result(spec, objects), **{field: value})
    _refusal(monkeypatch, spec, result, objects, reason)


@pytest.mark.parametrize("field,value,reason", [
    ("kind", "other", "kind-mismatch:other!=compile-attempt"),
    ("kind_version", 2, "kind-version-mismatch:compile-attempt:2!=1"),
    ("basis_hash", "", "basis-required:compile-attempt"),
])
def test_check_kind_runs_before_evidence_reads(monkeypatch, field, value, reason):
    objects = MemoryCAS()
    spec = _spec(objects)
    result = _object_result(spec, objects)
    wrong_spec = dataclasses.replace(spec, **{field: value})
    _refusal(monkeypatch, wrong_spec, result, objects, reason)
    assert objects.reads == []


@pytest.mark.parametrize("role", ["obj", "receipt"])
@pytest.mark.parametrize("mode", ["absent", "unreadable", "corrupt", "integrity-error", "invalid-ref"])
def test_cas_read_failures_never_verify(monkeypatch, role, mode):
    objects = MemoryCAS()
    spec = _spec(objects)
    result = _object_result(spec, objects)
    ref = result.outputs[role]
    outcome = VerificationOutcome.REFUTED
    if mode == "absent":
        del objects.data[ref]
        reason, outcome = role + "-unavailable", VerificationOutcome.UNVERIFIABLE
    elif mode == "unreadable":
        objects.errors[ref] = PermissionError("synthetic unavailable evidence")
        reason, outcome = role + "-unavailable", VerificationOutcome.UNVERIFIABLE
    elif mode == "corrupt":
        objects.data[ref] = b"corrupt addressed bytes"
        reason = role + "-cas-integrity"
    elif mode == "integrity-error":
        objects.errors[ref] = IntegrityError("synthetic integrity failure")
        reason = role + "-cas-integrity"
    else:
        result = dataclasses.replace(result, outputs={**result.outputs, role: ObjectRef("bad-ref")})
        reason = role + "-ref-invalid"
    _refusal(monkeypatch, spec, result, objects, reason, outcome=outcome)


@pytest.mark.parametrize("data,reason", [
    (b"short", "coff-too-short"),
    (b"\x00\x00\xff\xff" + b"\x00" * 40, "coff-anonymous-object"),
])
def test_existing_limited_coff_guard_refusals(monkeypatch, data, reason):
    objects = MemoryCAS()
    spec = _spec(objects)
    _refusal(monkeypatch, spec, _object_result(spec, objects, data), objects, reason)


@pytest.mark.parametrize("data", [b"not json", b"\xff", b"[]", b"null", b"42"])
def test_malformed_receipts_refute(monkeypatch, data):
    objects = MemoryCAS()
    spec = _spec(objects)
    result = _object_result(spec, objects)
    result = dataclasses.replace(result, outputs={**result.outputs, "receipt": objects.put(data)})
    _refusal(monkeypatch, spec, result, objects, "receipt-malformed")


def test_truthful_but_different_recomputed_object_refutes(monkeypatch):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects)
    recomputed = _object_result(spec, objects, _coff(payload=b"\x91\x90\xc3"))
    _controlled_producer(monkeypatch, recomputed)
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused")
    assert verdict.outcome == VerificationOutcome.REFUTED
    assert verdict.evidence["why"] == "masked-coff-differs"
    assert verdict.evidence["masked_coff_sha256"]["proposal"] != verdict.evidence["masked_coff_sha256"]["recomputed"]


def test_inconsistent_recomputed_object_receipt_pair_cannot_verify(monkeypatch):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects)
    bad_ref = objects.put(_coff(payload=b"\x91\x90\xc3"))
    bad_recompute = dataclasses.replace(proposal, outputs={**proposal.outputs, "obj": bad_ref})
    _controlled_producer(monkeypatch, bad_recompute)
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused")
    assert verdict.outcome == VerificationOutcome.REFUTED
    assert verdict.evidence["reason"] == "recomputed-obj-sha256-mismatch"


@pytest.mark.parametrize("fault,reason,expected", [
    ("missing-obj", "recomputed-obj-missing", VerificationOutcome.REFUTED),
    ("missing-receipt", "recomputed-receipt-missing", VerificationOutcome.REFUTED),
    ("wrong-config", "recomputed-receipt-opt-mismatch", VerificationOutcome.REFUTED),
    ("wrong-task", "recomputed-task-id-mismatch", VerificationOutcome.REFUTED),
    ("nonclaim", "recomputed-result-not-claim", VerificationOutcome.REFUTED),
    ("unavailable-obj", "recomputed-obj-unavailable", VerificationOutcome.UNVERIFIABLE),
    ("unknown-outcome", "recomputed-receipt-outcome-invalid", VerificationOutcome.REFUTED),
])
def test_recomputation_is_subject_to_same_binding_checks(monkeypatch, fault, reason, expected):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects)
    recomputed = _object_result(spec, objects, _coff(timestamp=999))
    if fault.startswith("missing-"):
        role = fault.removeprefix("missing-")
        recomputed = dataclasses.replace(recomputed, outputs={key: ref for key, ref in recomputed.outputs.items() if key != role})
    elif fault == "wrong-config":
        recomputed = _edit_receipt(objects, recomputed, opt="/O1")
    elif fault == "wrong-task":
        recomputed = dataclasses.replace(recomputed, task_id="c" * 64)
    elif fault == "nonclaim":
        recomputed = dataclasses.replace(recomputed, status=ResultStatus.ERROR)
    elif fault == "unavailable-obj":
        del objects.data[recomputed.outputs["obj"]]
    else:
        recomputed = _edit_receipt(objects, recomputed, outcome="unknown")
    calls = _controlled_producer(monkeypatch, recomputed)
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused")
    assert verdict.outcome == expected
    assert verdict.evidence["reason"] == reason
    assert calls == [spec.task_id]


def test_missing_pinned_toolchain_remains_unverifiable(monkeypatch):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects)

    def unavailable(self, spec, objects, scratch):
        raise Refused("toolchain-not-present:" + "a" * 12)

    monkeypatch.setattr(lane.CompileAttempt, "run", unavailable)
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused")
    assert verdict.outcome == VerificationOutcome.UNVERIFIABLE
    assert verdict.evidence["reason"] == "toolchain-not-present:" + "a" * 12


def test_infrastructure_failure_still_propagates(monkeypatch):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects)

    def infra(self, spec, objects, scratch):
        raise Infra("synthetic-timeout")

    monkeypatch.setattr(lane.CompileAttempt, "run", infra)
    with pytest.raises(Infra, match="synthetic-timeout"):
        lane.CompileAttempt().verify(spec, proposal, objects, "unused")


@pytest.mark.parametrize("proposal_codes,recomputed_codes,expected", [
    (["C2065"], ["C2065"], VerificationOutcome.VERIFIED),
    (["C2065"], ["C2143"], VerificationOutcome.REFUTED),
])
def test_diagnostic_comparison_remains_diagnostic(monkeypatch, proposal_codes, recomputed_codes, expected):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _diagnostic_result(spec, objects, proposal_codes)
    recomputed = _diagnostic_result(spec, objects, recomputed_codes)
    _controlled_producer(monkeypatch, recomputed)
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused")
    assert verdict.outcome == expected
    assert verdict.evidence["why"].startswith("diagnostic-codes-")
    assert verdict.evidence["masked_coff_sha256"] == {"proposal": None, "recomputed": None}


def test_object_cannot_fall_through_to_diagnostic_comparison(monkeypatch):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _object_result(spec, objects)
    _controlled_producer(monkeypatch, _diagnostic_result(spec, objects, ["C2065"]))
    verdict = lane.CompileAttempt().verify(spec, proposal, objects, "unused")
    assert verdict.outcome == VerificationOutcome.REFUTED
    assert verdict.evidence["why"] == "outcome-differs"


@pytest.mark.parametrize("codes", [None, {}, "C2065", [1]])
def test_malformed_diagnostic_codes_cannot_verify(monkeypatch, codes):
    objects = MemoryCAS()
    spec = _spec(objects)
    proposal = _diagnostic_result(spec, objects, codes)
    _refusal(monkeypatch, spec, proposal, objects, "receipt-diagnostic-codes-malformed")


@pytest.mark.parametrize("poison", [False, True])
def test_sandbox_job_real_kind_dispatch_enforces_object_binding(monkeypatch, poison):
    objects = MemoryCAS()
    spec = _spec(objects)
    honest = _object_result(spec, objects)
    proposal = honest
    if poison:
        changed = _coff(payload=b"\x91\x90\xc3")
        proposal = dataclasses.replace(honest, outputs={**honest.outputs, "obj": objects.put(changed)})
        proposal = _edit_receipt(objects, proposal, obj_sha256=digest(changed))
    calls = _controlled_producer(monkeypatch, honest)
    monkeypatch.setattr(sandbox, "resolve_store", lambda locator: objects)
    job = sandbox.SandboxJob(
        job_id="synthetic-compile-binding", op="verify", spec=spec,
        key_id="synthetic-independent-verifier", lineage=("synthetic-independent-verifier",),
        deadline_s=60, store_locator={"adapter": "synthetic-memory"}, result=proposal,
    )
    record = sandbox.run_manifest(job.manifest("unused-scratch"))
    assert record["task_id"] == spec.task_id
    assert record["verifier_key"] == "synthetic-independent-verifier"
    assert record["outcome"] == ("refuted" if poison else "verified")
    if poison:
        assert record["evidence"]["reason"] == "obj-masked-coff-mismatch"
        assert calls == []
    else:
        assert record["evidence"]["why"] == "masked-coff-equal"
        assert calls == [spec.task_id]
