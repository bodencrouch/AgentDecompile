"""P3.1 actual-crypto regression sources. Authored but not executed in the mission.

Fixtures use isolated synthetic public policy and deterministic TEST-ONLY signing seeds.
They never provision an owner configuration or assert runtime/source acceptance.
"""
from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from agentdecompile_grid.config import AdmissionConfig, ConfigError, GridConfig, KeyringConfig, PathsConfig, from_dict, to_dict
from agentdecompile_grid.core import NodeIdentity, ObjectRef, RecordType, ResultStatus, TaskResult, TaskSpec, Verification, VerificationOutcome, canonical_json
from agentdecompile_grid.log.records import build_record, encode_line
from agentdecompile_grid.log.signing import Ed25519Signer, HAVE_CRYPTOGRAPHY
from agentdecompile_grid.objects.base import Layout
from agentdecompile_grid.worker.identity import NodeKey, NodeSigner, key_id_for
from agentdecompile_grid.worker.records import result_body, verification_body
from agentdecompile_recovery.corpus import current_admission as admission

pytestmark = pytest.mark.skipif(not HAVE_CRYPTOGRAPHY, reason="actual Ed25519 support required")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(fixture):
    raw = canonical_json(fixture.policy)
    fixture.snapshot.write_bytes(raw)
    fixture.cfg = replace(fixture.cfg, admission=AdmissionConfig(str(fixture.snapshot), sha(raw),
                                                                fixture.policy["policy_id"], fixture.policy["generation"]))
    return fixture.cfg


def put(fixture, raw):
    ref = ObjectRef.of_bytes(raw)
    path = fixture.objects / fixture.layout.relpath(ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return ref


def seal(fixture):
    prev, records = "", []
    for seq, (kind, body, signer, basis) in enumerate(fixture.statements, 1):
        record = build_record(fixture.spec.partition_key, seq, kind, body, prev, signer,
                              basis_hash=basis, validate=False)
        records.append(record)
        prev = record.digest()
    fixture.log.write_bytes(b"".join(encode_line(record) for record in records))
    fixture.records = records
    fixture.selection = admission.ObservationSelection(fixture.spec.partition_key, records[0].digest(),
                                                       records[1].digest(), records[2].digest(), str(fixture.result_ref))


def fixture_at(tmp_path, *, grade="matched", referenced=False):
    root = tmp_path / "grid"
    objects, keys = root / "objects", root / "trusted"
    objects.mkdir(parents=True)
    keys.mkdir()
    f = SimpleNamespace(objects=objects, keys=keys, layout=Layout(), snapshot=root / "admission.json")
    (objects / "layout.json").write_bytes(f.layout.to_json())
    f.operator = Ed25519Signer(bytes([1]) * 32)
    f.parents = [Ed25519Signer(bytes([i]) * 32) for i in (2, 3)]
    public_keys = []
    for i, signer in enumerate([f.operator, *f.parents]):
        name = f"operator-{i}.pub"
        (keys / name).write_bytes(signer.public_bytes)
        public_keys.append({"filename": name, "sha256": sha(signer.public_bytes), "key_id": signer.key_id,
                            "algorithm": "ed25519", "role": "operator", "lineage": []})
    signers, identities = [], []
    for i, role in enumerate(("donor", "fleet")):
        seed = bytes([i + 4]) * 32
        public = Ed25519Signer(seed).public_bytes
        key = NodeKey("ed25519", key_id_for("ed25519", public), seed, public, 0.0, 1e20)
        signer = NodeSigner(key)
        lineage = [f.parents[i].key_id]
        metadata = dict(key.public_record(), role=role, lineage=lineage)
        raw = canonical_json(metadata)
        name = f"node-{i}.json"
        (keys / name).write_bytes(raw)
        public_keys.append({"filename": name, "sha256": sha(raw), "key_id": key.key_id,
                            "algorithm": "ed25519", "role": role, "lineage": lineage})
        signers.append(signer)
        identities.append(NodeIdentity(key.key_id, (), lineage, role))
    f.producer, f.verifier = signers
    f.producer_identity, f.verifier_identity = identities
    # Minimal synthetic i386 COFF headers; this reader authenticates input bytes, not P2 coverage.
    inputs = {name: put(f, b"\x4c\x01" + bytes([i]) + b"\0" * 17) for i, name in enumerate(("target", "candidate"))}
    checker = "parity:" + "a" * 64
    f.spec = TaskSpec("parity-check", 1, inputs, {"verifier_id": checker, "symbol": "leaf"}, "basis-v1", partition="parity-check/test")
    if grade == "error":
        raw = b""
        report = {"schema": "agentdecompile.verify-objdiff.v1", "status": "error", "differences": -1,
                  "message": "objdiff produced empty output", "objdiffExit": 0}
    else:
        raw = canonical_json({"section": {"kind": "SECTION_CODE", "match_percent": 100 if grade == "matched" else 80}})
        report = {"schema": "agentdecompile.verify-objdiff.v1", "status": grade, "differences": 0 if grade == "matched" else 1,
                  "message": "Object files match" if grade == "matched" else "Object files do not match",
                  "objdiffExit": 0, "detailLevel": "scalar-only"}
    report.update(kind="parity-check", kind_version=1, verifier_id=checker, verifier="native",
                  sides={k: v.hex for k, v in inputs.items()}, symbol="leaf", grade=grade, basis_hash="basis-v1")
    f.receipt = report
    outputs = {"raw": put(f, raw), "receipt": put(f, canonical_json(report))}
    f.result = TaskResult(f.spec.task_id, ResultStatus.OK, outputs, f.producer.key_id, f.spec.basis_hash, 0.001,
                          metrics={"checker_wall_s": 0.001})
    f.result_ref = put(f, canonical_json(f.result.to_record()))
    f.evidence = {"reason": "receipt_equal", "compared": ["receipt"], "predicate": "authenticated-checker-observation-v1",
                  "comparison_scope": "native-reported-code", "checker_identity_scope": "registered-artifacts-v1",
                  "target_region_complete": False, "runtime_admission": "not_evaluated", "grade": grade,
                  "proposal_outputs": dict(outputs), "recomputed_outputs": dict(outputs)}
    verdict = Verification(f.spec.task_id, f.result_ref, VerificationOutcome.VERIFIED, f.verifier.key_id,
                           "parity-binding-v1", f.evidence)
    evidence_ref = put(f, canonical_json(f.evidence)) if referenced else None
    f.statements = [
        (RecordType.TASK, f.spec.to_record(), f.operator, f.spec.basis_hash),
        (RecordType.RESULT, result_body(f.spec, f.result, f.result_ref, f.producer_identity, deadline_s=60, nonce="r"), f.producer, f.spec.basis_hash),
        (RecordType.VERIFIED, verification_body(verdict, f.producer.key_id, f.verifier_identity, nonce="v", evidence_ref=evidence_ref), f.verifier, f.spec.basis_hash),
    ]
    f.log = root / "log" / f.spec.partition_key / "records.jsonl"
    f.log.parent.mkdir(parents=True)
    f.cfg = GridConfig(paths=PathsConfig(root=str(root)), keyring=KeyringConfig(key_dir=str(keys)))
    f.policy = {"schema": admission.SCHEMA, "policy_id": "test-policy", "generation": 1, "public_keys": public_keys,
                "revocations": {}, "independence_policy": "disjoint-lineage", "corpus_scope": None, "execution_profiles": [],
                "observations": [{"kind": "parity-check", "kind_version": 1, "method": "parity-binding-v1",
                                  "verifier_id": checker, "basis_hashes": ["basis-v1"], "task_operator_keys": [f.operator.key_id],
                                  "producer_keys": [f.producer.key_id], "verifier_keys": [f.verifier.key_id],
                                  "profile_id": "native-objdiff-observation-v1"}]}
    pinned(f)
    seal(f)
    return f


def read(f):
    return admission.authenticate_native_observation(f.cfg, f.selection)


@pytest.mark.parametrize("grade", ["matched", "mismatched", "error"])
@pytest.mark.parametrize("referenced", [False, True])
def test_real_ed25519_current_native_observation(tmp_path, grade, referenced):
    f = fixture_at(tmp_path, grade=grade, referenced=referenced)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    result = read(f)
    assert (result.status, result.reason, result.grade) == ("authenticated", "current_observation", grade)
    assert result.implementation_source_closure == result.implementation_runtime_closure == result.source_acceptance == "not_evaluated"
    assert result.task_bytes == canonical_json(f.spec.to_record())
    assert result.result_bytes == canonical_json(f.result.to_record())
    assert result.record_bytes == tuple(encode_line(r)[:-1] for r in f.records)
    assert result.evidence_bytes == canonical_json(f.evidence)
    assert result.admission_identity and result.observation_identity
    assert admission.load_current_admission(f.cfg).admission_identity == result.admission_identity
    with pytest.raises(FrozenInstanceError):
        result.grade = "matched"
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("which", ["producer", "verifier", "operator", "ancestor"])
def test_current_revocation_invalidates_previous_positive(tmp_path, which):
    f = fixture_at(tmp_path)
    assert read(f).status == "authenticated"
    key = f.parents[0].key_id if which == "ancestor" else getattr(f, which).key_id
    f.policy["revocations"][key] = {"at": 1.0, "by": f.operator.key_id, "reason": "withdrawn"}
    pinned(f)
    assert (read(f).status, read(f).reason) == ("stale", "key_revoked")


@pytest.mark.parametrize("change,reason", [("basis", "basis_disallowed"), ("checker", "checker_disallowed"),
                                          ("method", "method_disallowed"), ("role", "role_disallowed")])
def test_current_policy_change_is_stale_only_after_authentication(tmp_path, change, reason):
    f = fixture_at(tmp_path)
    assert read(f).status == "authenticated"
    if change == "basis":
        f.policy["observations"][0]["basis_hashes"] = ["different"]
    elif change == "checker":
        f.policy["observations"][0]["verifier_id"] = "parity:" + "b" * 64
    elif change == "method":
        f.cfg = replace(f.cfg, verifier=replace(f.cfg.verifier, default_method="hash-lookup"))
    else:
        entry = f.policy["public_keys"][-1]
        entry["role"] = "donor"
        path = f.keys / entry["filename"]
        metadata = admission._json(path.read_bytes())
        metadata["role"] = "donor"
        raw = canonical_json(metadata)
        path.write_bytes(raw)
        entry["sha256"] = sha(raw)
    pinned(f)
    result = read(f)
    assert (result.status, result.reason) == ("stale", reason)


def test_shared_ancestor_and_body_lineage_forgery(tmp_path):
    f = fixture_at(tmp_path)
    entry = f.policy["public_keys"][-1]
    entry["lineage"] = [f.parents[0].key_id]
    path = f.keys / entry["filename"]
    metadata = admission._json(path.read_bytes())
    metadata["lineage"] = entry["lineage"]
    raw = canonical_json(metadata)
    path.write_bytes(raw)
    entry["sha256"] = sha(raw)
    # Body still claims the old disjoint ancestor; current public metadata wins.
    pinned(f)
    result = read(f)
    assert (result.status, result.reason) == ("stale", "lineage_disallowed")


def test_missing_old_signer_is_unavailable_not_stale(tmp_path):
    f = fixture_at(tmp_path)
    assert read(f).status == "authenticated"
    (f.keys / f.policy["public_keys"][-1]["filename"]).unlink()
    assert (read(f).status, read(f).reason) == ("unavailable", "signer_not_available")


def test_forged_signature_is_not_masked_by_current_revocation(tmp_path):
    f = fixture_at(tmp_path)
    f.policy["revocations"][f.producer.key_id] = {"at": 1.0, "by": f.operator.key_id, "reason": "withdrawn"}
    pinned(f)
    forged = replace(f.records[2], signature=f.records[1].signature)
    f.log.write_bytes(b"".join(encode_line(r) for r in [*f.records[:2], forged]))
    assert (read(f).status, read(f).reason) == ("failed", "bad_signature")


@pytest.mark.parametrize("mode", ["both", "neither", "extra", "wrong_output", "wrong_grade", "wrong_producer", "wrong_basis"])
def test_signed_association_substitution_refuses(tmp_path, mode):
    f = fixture_at(tmp_path)
    body = f.statements[2][1]
    if mode == "both":
        body["evidence_ref"] = str(put(f, canonical_json(f.evidence)))
    elif mode == "neither":
        del body["evidence"]
    elif mode == "extra":
        body["evidence"]["accepted"] = True
    elif mode == "wrong_output":
        body["evidence"]["proposal_outputs"]["raw"] = str(put(f, b"different"))
    elif mode == "wrong_grade":
        body["evidence"]["grade"] = "mismatched"
    elif mode == "wrong_producer":
        body["producer_key"] = f.operator.key_id
    else:
        kind, value, signer, _ = f.statements[2]
        f.statements[2] = kind, value, signer, "other-basis"
    seal(f)
    assert read(f).status == "failed"


def test_trusted_refutation_cannot_be_erased_by_later_positive(tmp_path):
    f = fixture_at(tmp_path)
    negative = dict(f.statements[2][1], outcome="refuted", nonce="negative", evidence={"reason": "receipt_differs"})
    f.statements.append((RecordType.REFUTED, negative, f.verifier, f.spec.basis_hash))
    seal(f)
    assert (read(f).status, read(f).reason) == ("failed", "conflicting_verdict")


def test_retired_unrelated_record_does_not_require_a_key(tmp_path):
    f = fixture_at(tmp_path)
    retired = Ed25519Signer(bytes([9]) * 32)
    f.statements.append((RecordType.NOTE, {"note": "historical"}, retired, "retired-basis"))
    seal(f)
    assert read(f).status == "authenticated"


def test_untrusted_negative_does_not_gain_authority(tmp_path):
    f = fixture_at(tmp_path)
    retired = Ed25519Signer(bytes([9]) * 32)
    negative = dict(f.statements[2][1], outcome="refuted", verifier_key=retired.key_id, nonce="negative")
    f.statements.append((RecordType.REFUTED, negative, retired, f.spec.basis_hash))
    seal(f)
    assert read(f).status == "authenticated"


def test_duplicate_selected_tuple_refuses(tmp_path):
    f = fixture_at(tmp_path)
    f.statements.append(f.statements[2])
    seal(f)
    assert read(f).reason == "duplicate_selected_tuple"


@pytest.mark.parametrize("change", ["pin", "generation", "missing_revocations", "null", "local_nodes", "algorithm", "lineage_cycle"])
def test_owner_policy_refusals(tmp_path, change):
    f = fixture_at(tmp_path)
    if change == "pin":
        f.cfg = replace(f.cfg, admission=replace(f.cfg.admission, snapshot_sha256="0" * 64))
    elif change == "generation":
        f.cfg = replace(f.cfg, admission=replace(f.cfg.admission, generation=2))
    elif change == "missing_revocations":
        del f.policy["revocations"]
        pinned(f)
    elif change in ("null", "local_nodes"):
        f.cfg = replace(f.cfg, keyring=replace(f.cfg.keyring, **{("allow_null" if change == "null" else "trust_local_nodes"): True}))
    elif change == "algorithm":
        f.policy["public_keys"][-1]["algorithm"] = "hash-token"
        pinned(f)
    else:
        f.policy["public_keys"][-1]["lineage"] = [f.verifier.key_id]
        pinned(f)
    assert read(f).status in ("failed", "unavailable")


def test_unconfigured_authority_never_uses_a_request_policy(tmp_path):
    f = fixture_at(tmp_path)
    f.cfg = replace(f.cfg, admission=AdmissionConfig())
    assert (read(f).status, read(f).reason) == ("unavailable", "admission_not_configured")
    with pytest.raises(TypeError):
        admission.ObservationSelection("p", "a", "b", "c", "d", policy=f.policy)


@pytest.mark.parametrize("damage,reason", [("torn", "log_snapshot_unstable"), ("pruned", "raw_history_unavailable"),
                                          ("bool_seq", "invalid_record"), ("duplicate", "duplicate_json_key"), ("nan", "nonfinite_json_number")])
def test_log_strictness(tmp_path, damage, reason):
    f = fixture_at(tmp_path)
    raw = f.log.read_bytes()
    if damage == "torn":
        raw = raw[:-1]
    elif damage == "pruned":
        raw = raw.split(b"\n", 1)[1]
    elif damage == "bool_seq":
        raw = raw.replace(b'"seq":1', b'"seq":true', 1)
    elif damage == "duplicate":
        raw = raw.replace(b'"seq":1', b'"seq":1,"seq":1', 1)
    else:
        raw = raw.replace(b'"elapsed_s":0.001', b'"elapsed_s":NaN', 1)
    f.log.write_bytes(raw)
    assert read(f).reason == reason


def test_symlink_input_and_persistent_cas_mutation_fail_closed(tmp_path, monkeypatch):
    f = fixture_at(tmp_path)
    ref = f.spec.inputs["target"]
    path = f.objects / f.layout.relpath(ref)
    outside = tmp_path / "outside"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    assert read(f).status == "unavailable"
    path.unlink()
    path.write_bytes(outside.read_bytes())
    original = admission._Reader.revalidate

    def mutate(reader):
        path.write_bytes(b"changed")
        return original(reader)

    monkeypatch.setattr(admission._Reader, "revalidate", mutate)
    assert read(f).status == "unavailable"


def test_authority_changes_during_read_refuse(tmp_path, monkeypatch):
    f = fixture_at(tmp_path)
    original = admission._Reader.revalidate

    def mutate(reader):
        f.snapshot.write_bytes(f.snapshot.read_bytes() + b" ")
        return original(reader)

    monkeypatch.setattr(admission._Reader, "revalidate", mutate)
    assert read(f).reason == "files_unstable"


def test_deadline_and_snapshot_cap(tmp_path, monkeypatch):
    f = fixture_at(tmp_path)
    ticks = iter([0.0, 11.0])
    monkeypatch.setattr(admission.time, "monotonic", lambda: next(ticks, 11.0))
    assert read(f).reason == "deadline_exceeded"
    monkeypatch.undo()
    f.snapshot.write_bytes(b" " * (256 * 1024 + 1))
    assert read(f).reason == "limit_exceeded"


def test_bad_object_hash_cannot_reuse_prior_positive(tmp_path):
    f = fixture_at(tmp_path)
    assert read(f).status == "authenticated"
    path = f.objects / f.layout.relpath(f.result.outputs["raw"])
    path.write_bytes(b"different")
    assert (read(f).status, read(f).reason) == ("failed", "object_hash_mismatch")


def test_admission_config_is_optional_and_roundtrips(tmp_path):
    assert GridConfig().validate().admission == AdmissionConfig()
    cfg = fixture_at(tmp_path).cfg
    assert from_dict(to_dict(cfg)).admission == cfg.admission
    assert cfg.validate() is cfg
    for bad in (replace(cfg.admission, generation=True), replace(cfg.admission, snapshot_sha256="x"),
                replace(cfg.admission, snapshot_path="relative"), replace(cfg.admission, policy_id="")):
        with pytest.raises(ConfigError):
            replace(cfg, admission=bad).validate()


def replace_result(f, value):
    f.result_ref = put(f, canonical_json(value))
    f.statements[1][1]["result_ref"] = str(f.result_ref)
    f.statements[2][1]["result_ref"] = str(f.result_ref)
    seal(f)


def test_tagged_result_encoding_is_not_normalized_into_worker_authority(tmp_path):
    f = fixture_at(tmp_path)
    replace_result(f, dict(f.result.to_record(), schema="tagged-result"))
    assert (read(f).status, read(f).reason) == ("unavailable", "unsupported_result_encoding")


@pytest.mark.parametrize("damage", ["basis", "producer", "task", "outputs"])
def test_immutable_result_must_equal_signed_body(tmp_path, damage):
    f = fixture_at(tmp_path)
    value = f.result.to_record()
    if damage == "basis":
        value["basis_hash"] = "other"
    elif damage == "producer":
        value["producer_key"] = f.verifier.key_id
    elif damage == "task":
        value["task_id"] = "0" * 64
    else:
        value["outputs"]["raw"] = str(put(f, b"different"))
    replace_result(f, value)
    assert read(f).reason == "result_binding_mismatch"


def test_recomputed_receipt_and_raw_are_both_authenticated(tmp_path):
    f = fixture_at(tmp_path)
    bad = dict(f.receipt, symbol="different")
    f.statements[2][1]["evidence"]["recomputed_outputs"]["receipt"] = str(put(f, canonical_json(bad)))
    seal(f)
    assert read(f).reason == "receipt_binding_mismatch"
    f.statements[2][1]["evidence"]["recomputed_outputs"]["receipt"] = str(f.result.outputs["receipt"])
    f.statements[2][1]["evidence"]["recomputed_outputs"]["raw"] = str(put(f, b"different"))
    seal(f)
    assert read(f).reason == "raw_receipt_mismatch"


def test_referenced_evidence_missing_or_changed_never_uses_named_verdict(tmp_path):
    f = fixture_at(tmp_path, referenced=True)
    ref = ObjectRef(f.statements[2][1]["evidence_ref"])
    path = f.objects / f.layout.relpath(ref)
    original = path.read_bytes()
    path.unlink()
    assert read(f).reason == "evidence_unavailable"
    path.write_bytes(original + b" ")
    assert read(f).reason == "object_hash_mismatch"


def test_same_producer_verifier_key_never_counts_independent(tmp_path):
    f = fixture_at(tmp_path)
    f.policy["observations"][0]["verifier_keys"] = [f.producer.key_id]
    pinned(f)
    kind, body, _, basis = f.statements[2]
    body["verifier_key"] = f.producer.key_id
    body["verifier_lineage"] = list(f.producer_identity.invite_lineage)
    f.statements[2] = kind, body, f.producer, basis
    seal(f)
    assert (read(f).status, read(f).reason) == ("stale", "lineage_disallowed")


def test_new_generation_changes_identity_and_missing_pin_never_reuses_it(tmp_path):
    f = fixture_at(tmp_path)
    before = read(f)
    f.policy["generation"] += 1
    pinned(f)
    after = read(f)
    assert after.status == "authenticated"
    assert before.admission_identity != after.admission_identity
    assert before.observation_identity != after.observation_identity
    f.snapshot.unlink()
    assert read(f).reason == "admission_snapshot_unavailable"


def test_mutable_named_revocation_file_is_not_authority(tmp_path):
    f = fixture_at(tmp_path)
    named = f.objects / "named" / "policy" / "revoked"
    named.parent.mkdir(parents=True)
    named.write_bytes(b"not an admission snapshot")
    assert read(f).status == "authenticated"
    del f.policy["revocations"]
    pinned(f)
    assert read(f).reason == "invalid_admission_snapshot"


@pytest.mark.parametrize("damage", ["line", "result", "raw"])
def test_bounded_line_and_object_reads(tmp_path, damage):
    f = fixture_at(tmp_path)
    if damage == "line":
        f.log.write_bytes(b" " * (128 * 1024 + 1) + b"\n")
    elif damage == "result":
        path = f.objects / f.layout.relpath(f.result_ref)
        path.write_bytes(b" " * (64 * 1024 + 1))
    else:
        path = f.objects / f.layout.relpath(f.result.outputs["raw"])
        path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    assert read(f).reason == "limit_exceeded"


def test_unsafe_selection_and_public_key_names_refuse(tmp_path):
    f = fixture_at(tmp_path)
    original = f.selection
    f.selection = replace(f.selection, partition="../outside")
    assert read(f).reason == "unsafe_path"
    f.selection = original
    f.policy["public_keys"][0]["filename"] = "../operator.pub"
    pinned(f)
    assert read(f).reason == "unsafe_path"


def test_lifecycle_metadata_never_supplies_lineage_or_expiry_authority(tmp_path):
    f = fixture_at(tmp_path)
    entry = f.policy["public_keys"][-1]
    path = f.keys / entry["filename"]
    value = admission._json(path.read_bytes())
    # Existing Keyring public trust uses explicit role/lineage, not these lifecycle hints.
    value["expires_at"] = 0.0
    value["previous_key_ids"] = [f.producer.key_id]
    raw = canonical_json(value)
    path.write_bytes(raw)
    entry["sha256"] = sha(raw)
    pinned(f)
    assert read(f).status == "authenticated"
    del value["lineage"]
    raw = canonical_json(value)
    path.write_bytes(raw)
    entry["sha256"] = sha(raw)
    pinned(f)
    assert read(f).reason == "invalid_public_key"
