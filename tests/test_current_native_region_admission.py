"""P3.2 current-reader regression SOURCE ONLY; authored but never run here.

Fixtures are synthetic reader-authentication evidence only. They use real
Ed25519 signers and bounded owner-selected files. They do not execute P2,
objdiff, a captured runtime, a database, or assert source/whole-image acceptance.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import time

import pytest

from agentdecompile_grid.core import ObjectRef, RecordType, ResultStatus, TaskResult, Verification, VerificationOutcome
from agentdecompile_grid.log.records import build_record, encode_line
from agentdecompile_grid.log.signing import HAVE_CRYPTOGRAPHY
from agentdecompile_grid.worker.records import verification_body
from agentdecompile_recovery.grid_lanes import native_region_verify_plan as builder
from agentdecompile_recovery.corpus import current_native_region_admission as reader
from agentdecompile_recovery.grid_lanes.objdiff_v380 import parse_report
from agentdecompile_recovery.objdiff_verification import parse_objdiff_report

# Reuse the authored synthetic prerequisites, real signer keys, strict P2
# proposal shapes and owner-file writer from the paired P3.2 role-plan packet.
# That packet has the real donor producer / fleet verifier distinction.
from test_native_region_verify_plan import (BASIS, CHECKER, CHECKER_PROFILE, METHOD,
                                            PROFILE, fixture_at, put, put_json,
                                            publish_graph, repin, seal, sha)


pytestmark = pytest.mark.skipif(not HAVE_CRYPTOGRAPHY,
                                reason="actual Ed25519 required; never replace with a success callback")


def load(f):
    return reader.load_native_region_authority(f.cfg)


def read(f, selection=None):
    if selection is None:
        selection = getattr(f, "reader_selection", None)
    if selection is None:
        selection = reader.NativeRegionSelection(f.task.partition_key,
                                                 f.selection.task_record_ref,
                                                 f.selection.result_record_ref,
                                                 "sha256:" + "0" * 64)
    return reader.authenticate_native_region_execution(f.cfg, selection)


def _objdiff_side(tokens, other_tokens, *, left, grade):
    size = sum(row["length"] for row in tokens)
    section = {"name": ".text", "kind": "SECTION_CODE", "size": str(size), "address": "0",
               "data_diff": [], "reloc_diff": []}
    if left:
        section["match_percent"] = 100 if grade == "matched" else 80
    section_symbol = {"name": "[.text]", "address": "0", "size": "0",
                     "flags": {name: name == "local" for name in
                               ("global", "local", "weak", "common", "hidden", "ignored", "size_inferred")},
                     "kind": "SYMBOL_SECTION", "instructions": [], "data_diff": []}
    instructions = []
    for index, token in enumerate(tokens):
        op = token["operation"]
        if op == "xor":
            opcode = token["opcode"]
            parts = [{"opcode": {"mnemonic": "xor", "opcode": opcode}}, {"arg": {"opaque": "eax"}},
                     {"basic": ", "}, {"arg": {"opaque": "eax"}}]
            formatted = "xor eax, eax"
        else:
            parts = [{"opcode": {"mnemonic": "ret", "opcode": 0xC3}}]
            formatted = "ret "
        differs = token["opcode"] != other_tokens[index]["opcode"]
        diff_kind = "DIFF_OP_MISMATCH" if grade == "mismatched" and differs else "DIFF_NONE"
        instructions.append({"diff_kind": diff_kind,
                             "instruction": {"address": str(token["offset"]), "size": token["length"],
                                             "formatted": formatted, "parts": parts}, "arg_diff": []})
    function = {"name": "F_401000", "address": "0", "size": str(size),
                "flags": {name: name in ("global", "size_inferred") for name in
                          ("global", "local", "weak", "common", "hidden", "ignored", "size_inferred")},
                "kind": "SYMBOL_FUNCTION", "target_symbol": 1,
                "match_percent": 100 if grade == "matched" else 80,
                "instructions": instructions, "data_diff": []}
    return {"sections": [section], "symbols": [section_symbol, function]}


def _fixture_tokens(f, side):
    """Derive report rows from the fixture's stored COFF and inventory range."""
    object_ref = f.target_ref if side == "target" else f.candidate_ref
    inventory = f.inventories[side]
    object_bytes = f.stored[object_ref].read_bytes()
    start = inventory["region"]["file_offset"]
    code = object_bytes[start:start + inventory["region"]["length"]]
    if len(code) != inventory["region"]["length"] or code not in (b"\x31\xc0\xc3", b"\x33\xc0\xc3"):
        raise AssertionError("synthetic COFF fixture changed; rebuild the normalized report fixture")
    opcode = code[0]
    return [{"offset": 0, "length": 2, "operation": "xor", "opcode": opcode},
            {"offset": 2, "length": 1, "operation": "ret", "opcode": 0xC3}]


def _synthetic_objdiff_report(grade, target_tokens, candidate_tokens):
    raw = reader.canonical_json({"left": _objdiff_side(target_tokens, candidate_tokens, left=True, grade=grade),
                                 "right": _objdiff_side(candidate_tokens, target_tokens, left=False, grade=grade)})
    normalized = parse_report(raw, "F_401000", target_tokens, candidate_tokens, checker_grade=grade)
    return raw, normalized


def qualified_fixture(f, *, closure_task_mismatch=False, conflicting_refutation=False,
                      donor_verifier=False, bad_mount_source_role=False):
    """Assemble signed synthetic reader evidence; never execute the claims."""
    target_tokens = _fixture_tokens(f, "target")
    candidate_tokens = _fixture_tokens(f, "candidate")
    raw_report, strict_report = _synthetic_objdiff_report(f.grade, target_tokens, candidate_tokens)
    f.raw_ref = put(f, raw_report)
    parsed = parse_objdiff_report(0, raw_report.decode("utf-8"))
    f.parity_receipt = {key: value for key, value in parsed.items() if key != "output"}
    f.parity_receipt.update({
        "kind": "parity-check", "kind_version": 1, "verifier_id": CHECKER, "verifier": "native",
        "sides": {"target": f.target_ref[7:], "candidate": f.candidate_ref[7:]},
        "symbol": "F_401000", "grade": f.grade, "basis_hash": BASIS,
    })
    # Rebind the actual signed P2 proposal to the normalized report bytes.
    publish_graph(f)
    f.receipt["strict_report_sha256"] = sha(reader.canonical_json(strict_report))
    result_outputs = f.result.to_record()["outputs"]
    result_outputs["receipt"] = put_json(f, f.receipt)
    f.result = TaskResult(f.task.task_id, ResultStatus.OK,
                          {name: ObjectRef(value) for name, value in result_outputs.items()},
                          f.producer.key_id, BASIS, 0.001)
    f.result_ref = put_json(f, f.result.to_record())
    seal(f)
    root_inventory = reader.canonical_json({
        "schema": "agentdecompile.native-root-inventory.v1",
        "entries": [{"path": "entry.py", "type": "file", "permission_class": "data",
                     "size": 1, "sha256": sha(b"x")}],
    })
    f.profile["root_inventory_ref"] = put(f, root_inventory)
    f.policy["execution_profiles"] = [f.profile]
    repin(f)
    plan = builder.build_native_region_verify_plan(
        builder.begin_native_region_verify(f.selection, profile_id=PROFILE,
                                          verifier_key=f.verifier.key_id),
        cfg=f.cfg, stage_started_at_ns=time.monotonic_ns(),
    )
    authority = load(f)
    profile_authority = next(row for row in authority.profiles if row.profile_id == PROFILE)
    outputs = f.result.to_record()["outputs"]
    prerequisite = {
        "target": {"task_id": f.target_task.task_id, "result_ref": f.task.to_record()["inputs"]["target_result"],
                   "method": "mkobj-target-reference-free-v1", "outcome": "verified"},
        "parity": {"task_id": f.parity_task.task_id, "result_ref": f.task.to_record()["inputs"]["parity_result"],
                   "method": "parity-binding-v1", "outcome": "verified"},
    }
    lane_evidence = {
        "prerequisites": prerequisite,
        "parity_raw_evidence": {
            "proposed": {"receipt": f.parity_result.to_record()["outputs"]["receipt"],
                         "raw": f.parity_result.to_record()["outputs"]["raw"]},
            "recomputed": {"receipt": f.parity_result.to_record()["outputs"]["receipt"],
                           "raw": f.parity_result.to_record()["outputs"]["raw"]},
        },
        "reason": "region_equal" if f.grade == "matched" else "region_differs",
        "proposal_outputs": outputs, "recomputed_outputs": outputs,
        "grade": f.grade, "target_region_complete": f.grade == "matched", "region_inventory_complete": True,
        "checker_profile": CHECKER_PROFILE, "comparison_policy": "coff-i386-register-leaf-v1",
        "verifier_id": CHECKER, "implementation_source_closure": "not_evaluated",
        "implementation_runtime_closure": "not_evaluated", "source_binding": "not_evaluated",
        "runtime_admission": "not_evaluated",
    }
    selected_verifier = f.producer if donor_verifier else f.verifier
    selected_verifier_identity = f.producer_identity if donor_verifier else f.verifier_identity
    v0 = {"task_id": f.task.task_id, "result_ref": f.result_ref, "outcome": "verified",
          "verifier_key": selected_verifier.key_id, "method": METHOD, "evidence": lane_evidence}
    v0_ref = put(f, reader.canonical_json(v0))
    enforcement = {
        "schema": "agentdecompile.native-region-enforcement.v1",
        "argv": ["/usr/bin/python3.12", "-I", "-S", "-B", "/app/native_closure_entry.py"],
        "environment": {"AGENT_DECOMPILE_OBJDIFF": "/tools/objdiff", "HOME": "/work/home",
                        "LANG": "C", "LC_ALL": "C", "PATH": "/tools", "TMPDIR": "/work/tmp", "TZ": "UTC"},
        "mounts": [
            {"target": "/", "source_role": "capture", "readonly": True, "noexec": False, "nosuid": True, "nodev": True},
            {"target": "/work", "source_role": "work", "readonly": False, "noexec": True, "nosuid": True, "nodev": True},
            {"target": "/dev/null", "source_role": "null", "readonly": True, "noexec": False, "nosuid": True, "nodev": True},
        ],
        "rlimits": {"core": 0, "nofile": 128, "fsize": 256 << 20, "as": 2 << 30, "nproc": 32, "cpu": 300},
        "no_new_privs": True, "filter_sha256": f.profile["filter_sha256"],
        "namespace_ids": {name: 1 for name in ("user", "pid", "mnt", "ipc", "net", "uts")},
        "work_limit_bytes": 1 << 30,
    }
    if bad_mount_source_role:
        enforcement["mounts"][0]["source_role"] = "work"
    diagnostics = []
    enforcement_ref = put(f, reader.canonical_json(enforcement))
    diagnostics_ref = put(f, reader.canonical_json(diagnostics))
    staged = []
    for role in plan.roles:
        if role.role == "p2_task":
            raw = reader.canonical_json(f.task.to_record())
        else:
            raw = f.stored[role.ref].read_bytes()
        staged.append({"role": role.role, "ref": role.ref, "size": len(raw), "cap": role.cap})
    staged.sort(key=lambda row: row["role"])
    exported_refs = {}
    for prefix, mapping in (("p2_proposed", outputs), ("p2_recomputed", outputs)):
        for name, value in mapping.items():
            exported_refs[prefix + "_" + name] = (value, 1 << 20)
    parity_outputs = f.parity_result.to_record()["outputs"]
    for stage in ("proposed", "recomputed"):
        for name, value in parity_outputs.items():
            exported_refs["parity_" + stage + "_" + name] = (value, (1 << 20) if name == "receipt" else 4 << 20)
    task_inputs = f.task.to_record()["inputs"]
    for name in ("target", "parity"):
        exported_refs[name + "_task"] = (task_inputs[name + "_task"], 64 << 10)
        exported_refs[name + "_result"] = (task_inputs[name + "_result"], 64 << 10)
    exported = []
    for role, (value, cap) in exported_refs.items():
        raw = f.stored[value].read_bytes()
        exported.append({"role": role, "ref": value, "size": len(raw), "cap": cap})
    exported.sort(key=lambda row: row["role"])
    task_line = encode_line(f.records[0])[:-1]
    result_line = encode_line(f.records[1])[:-1]
    c = {
        "schema": reader.EXECUTION_SCHEMA, "profile_id": PROFILE,
        "profile_sha256": f.profile["profile_sha256"],
        "admission_identity": profile_authority.effective_authority_digest,
        "admission_generation": authority.generation,
        "root_inventory_ref": f.profile["root_inventory_ref"],
        "implementation_source_sha256": f.profile["implementation_source_sha256"],
        "launcher_sha256": f.profile["launcher_sha256"], "filter_sha256": f.profile["filter_sha256"],
        "environment_sha256": f.profile["environment_sha256"], "entrypoint_sha256": f.profile["entrypoint_sha256"],
        "job_id": "synthetic-reader-job", "nonce": "9" * 64, "op": "verify", "kind": f.task.kind,
        "kind_version": 1, "dispatch": "kind", "method": METHOD, "task_ref": "sha256:" + sha(reader.canonical_json(f.task.to_record())),
        "task_id": f.task.task_id, "result_ref": f.result_ref, "basis_hash": BASIS,
        "producer_key": f.producer.key_id, "verifier_key": selected_verifier.key_id,
        "task_record_sha256": sha(task_line), "result_record_sha256": sha(result_line), "v0_ref": v0_ref,
        "processes": {name: {"pid": i, "start_ticks": i} for i, name in enumerate(("launcher", "namespace_init", "entrypoint"), 1)},
        "namespaces": {name: 1 for name in ("user", "pid", "mnt", "ipc", "net", "uts")},
        "enforcement_ref": enforcement_ref, "module_diagnostics_ref": diagnostics_ref,
        "ipc_transcript_sha256": "a" * 64, "elapsed_ms": 1,
        "stage_ms": {name: 1 for name in ("capture", "stage", "launch_barrier", "run", "tree_termination", "export")},
        "staged": staged, "exported": exported,
        "measurement_scope": "complete-permitted-runtime-root", "tree_gone": True, "collection_status": "complete",
    }
    if closure_task_mismatch:
        c["task_id"] = "b" * 64
    c_ref = put(f, reader.canonical_json(c))
    e = {"schema": reader.READER_RESULT_SCHEMA, "lane_evidence": lane_evidence,
         "execution_closure_ref": c_ref}
    e_ref = put(f, reader.canonical_json(e))
    verified_body = verification_body(
        Verification(f.task.task_id, ObjectRef(f.result_ref), VerificationOutcome.VERIFIED,
                     f.verifier.key_id, METHOD, lane_evidence),
        f.producer.key_id, selected_verifier_identity, nonce="synthetic-reader-verification",
        evidence_ref=ObjectRef(e_ref),
    )
    verified = build_record(f.task.partition_key, 3, RecordType.VERIFIED, verified_body,
                            f.records[1].digest(), selected_verifier, basis_hash=BASIS, validate=False)
    lines = [encode_line(row) for row in (*f.records, verified)]
    f.log.write_bytes(b"".join(lines))
    f.reader_selection = reader.NativeRegionSelection(
        f.task.partition_key, "sha256:" + sha(lines[0][:-1]), "sha256:" + sha(lines[1][:-1]),
        "sha256:" + sha(lines[2][:-1]))
    if conflicting_refutation:
        refutation_body = verification_body(
            Verification(f.task.task_id, ObjectRef(f.result_ref), VerificationOutcome.REFUTED,
                         f.verifier.key_id, METHOD, {"reason": "synthetic conflicting refutation"}),
            f.producer.key_id, f.verifier_identity, nonce="synthetic-reader-refutation")
        refutation = build_record(f.task.partition_key, 4, RecordType.REFUTED, refutation_body,
                                  verified.digest(), f.verifier, basis_hash=BASIS, validate=False)
        f.log.write_bytes(b"".join((*lines, encode_line(refutation))))
    return f


def test_shared_authority_accepts_donor_producer_but_not_donor_verifier(tmp_path):
    f = fixture_at(tmp_path)
    authority = load(f)
    assert authority.profiles[0].profile_id == f.profile["profile_id"]
    profile_authority = authority.profiles[0]
    assert profile_authority.effective_authority_digest == sha(reader.canonical_json({
        "predicate": reader.PREDICATE,
        "configuration_sha256": authority.owner_config_sha256,
        "snapshot_sha256": authority.snapshot_sha256,
        "public_key_files": sorted(
            ({"filename": key.filename, "sha256": key.sha256} for key in authority.public_keys),
            key=lambda row: row["filename"]),
        "execution_profile": f.profile,
    }))
    assert len(profile_authority.effective_authority_digest) == 64
    assert profile_authority.effective_authority_digest == profile_authority.effective_authority_digest.lower()
    assert f.producer_identity.role == "donor"
    assert f.verifier_identity.role == "fleet"

    # A donor is a permitted producer, but it cannot enter the verifier allowlist.
    f.profile["verifier_keys"] = [f.producer.key_id]
    f.policy["execution_profiles"] = [f.profile]
    repin(f)
    with pytest.raises(reader.NativeRegionAuthorityError):
        load(f)


def test_donor_verifier_is_rejected_at_reader_consumer_boundary(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path), donor_verifier=True)
    result = read(f)
    assert result.status == "stale"
    assert result.reason == "role_disallowed"
    assert result.verifier_execution_qualified is False
    assert result.producer_execution_qualified is False


def test_authority_is_frozen_and_nested_values_are_immutable(tmp_path):
    f = fixture_at(tmp_path)
    authority = load(f)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        authority.generation = 999
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        authority.public_keys[0].role = "fleet"
    assert isinstance(authority.public_keys, tuple)
    assert isinstance(authority.profiles, tuple)
    assert all(isinstance(key.raw_bytes, bytes) and isinstance(key.public_material, bytes)
               for key in authority.public_keys)


def test_effective_digest_tracks_owner_and_snapshot_bytes(tmp_path):
    f = fixture_at(tmp_path)
    before = load(f).profiles[0].effective_authority_digest
    f.policy["generation"] += 1
    repin(f)
    after = load(f).profiles[0].effective_authority_digest
    assert before != after


@pytest.mark.parametrize("bad_revision", [True, "1", 1.0, -1])
def test_owner_revision_requires_exact_nonnegative_integer(tmp_path, bad_revision):
    f = fixture_at(tmp_path)
    f.owner_document["configuration_revision"] = bad_revision
    f.owner.write_bytes(reader.canonical_json(f.owner_document))
    with pytest.raises(reader.NativeRegionAuthorityError):
        load(f)


@pytest.mark.parametrize("bad_generation", [True, "1", 1.0, -1])
def test_snapshot_generation_requires_exact_nonnegative_integer(tmp_path, bad_generation):
    f = fixture_at(tmp_path)
    f.policy["generation"] = bad_generation
    repin(f)
    with pytest.raises(reader.NativeRegionAuthorityError):
        load(f)


def test_missing_declared_public_key_is_unavailable_without_partial_authority(tmp_path):
    f = fixture_at(tmp_path)
    (f.keys / "producer.json").unlink()
    with pytest.raises(reader.NativeRegionAuthorityError) as error:
        load(f)
    assert error.value.status == "unavailable"


@pytest.mark.parametrize("selection", [None, "not-a-selection", object()])
def test_invalid_selection_never_returns_qualified_status(tmp_path, selection):
    f = fixture_at(tmp_path)
    chosen = selection if selection is not None else reader.NativeRegionSelection("bad partition", "", "", "")
    result = read(f, chosen)
    assert result.status in {"failed", "unavailable"}
    assert result.verifier_execution_qualified is False
    assert result.producer_execution_qualified is False
    assert result.region_equal is False
    assert result.source_acceptance == "not_evaluated"


@pytest.mark.parametrize("corruption", ["missing_newline", "truncated", "noncanonical"])
def test_incomplete_or_noncanonical_partition_fails_closed(tmp_path, corruption):
    f = fixture_at(tmp_path)
    raw = f.log.read_bytes()
    if corruption == "missing_newline":
        f.log.write_bytes(raw[:-1])
    elif corruption == "truncated":
        f.log.write_bytes(raw[:-7])
    else:
        f.log.write_bytes(raw.replace(b'"seq":1', b'"seq":01', 1))
    result = read(f)
    assert result.status in {"failed", "unavailable"}
    assert result.verifier_execution_qualified is False
    assert result.producer_execution_qualified is False


def test_reader_is_read_only_for_owner_snapshot_keys_log_and_cas(tmp_path):
    f = fixture_at(tmp_path)
    files = [f.owner, f.snapshot, f.log, *(f.keys / row["filename"] for row in f.policy["public_keys"]),
             *f.stored.values()]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    read(f)
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    assert after == before


def test_invalid_signer_role_or_revocation_never_qualifies_current_reader(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path))
    assert read(f).status == "authenticated"
    # A current policy may revoke a previously valid producer; the reader must
    # authenticate first and then return stale, never reuse a previous positive.
    f.policy["revocations"][f.producer.key_id] = {
        "at": 1.0, "by": f.operator.key_id, "reason": "withdrawn"
    }
    repin(f)
    result = read(f)
    assert result.status == "stale"
    assert result.reason == "key_revoked"
    assert result.producer_execution_qualified is False
    assert result.source_acceptance == "not_evaluated"


def test_log_envelope_uint_and_canonical_types_are_not_coerced(tmp_path):
    f = fixture_at(tmp_path)
    raw = f.log.read_bytes().replace(b'"seq":1', b'"seq":true', 1)
    f.log.write_bytes(raw)
    result = read(f)
    assert result.status == "failed"
    assert result.reason in {"invalid_record", "record_encoding_mismatch"}


def test_loader_reread_detects_owner_file_change(tmp_path, monkeypatch):
    f = fixture_at(tmp_path)
    original = reader._BoundedFiles.read
    changed = False

    def replacing_read(self, path, cap, role):
        nonlocal changed
        result = original(self, path, cap, role)
        if role == "snapshot" and not changed:
            changed = True
            replacement = dict(f.policy)
            replacement["generation"] += 1
            f.policy = replacement
            repin(f)
        return result

    monkeypatch.setattr(reader._BoundedFiles, "read", replacing_read)
    with pytest.raises(reader.NativeRegionAuthorityError) as error:
        load(f)
    assert error.value.status == "unavailable"


def test_reader_result_never_claims_producer_or_source_acceptance(tmp_path):
    f = fixture_at(tmp_path)
    result = read(f)
    assert result.producer_execution_qualified is False
    assert result.source_acceptance == "not_evaluated"
    assert result.status != "authenticated"


def test_complete_real_signature_reader_path_authenticates_synthetic_verified_tuple(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns)
              for path in [f.owner, f.snapshot, f.log, *(f.keys / row["filename"] for row in f.policy["public_keys"]),
                           *f.stored.values()]}
    result = read(f)
    assert result.status == "authenticated"
    assert result.reason == "current_qualified_native_region"
    assert result.verifier_execution_qualified is True
    assert result.producer_execution_qualified is False
    assert result.region_equal is True
    assert result.source_acceptance == "not_evaluated"
    assert result.record_refs.task == f.reader_selection.task_record_ref
    assert result.record_refs.result == f.reader_selection.result_record_ref
    assert result.record_refs.verified == f.reader_selection.verified_record_ref
    assert result.closure_ref
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns)
             for path in [f.owner, f.snapshot, f.log, *(f.keys / row["filename"] for row in f.policy["public_keys"]),
                          *f.stored.values()]}
    assert after == before


@pytest.mark.parametrize(("grade", "region_equal"), [("matched", True), ("mismatched", False)])
def test_verified_tuple_preserves_matched_vs_mismatched_region_result(tmp_path, grade, region_equal):
    f = qualified_fixture(fixture_at(tmp_path, grade=grade))
    result = read(f)
    assert result.status == "authenticated"
    assert result.verifier_execution_qualified is True
    assert result.region_equal is region_equal
    assert result.producer_execution_qualified is False
    assert result.source_acceptance == "not_evaluated"


def test_closure_task_tuple_mismatch_fails_after_real_signatures_authenticate(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path), closure_task_mismatch=True)
    result = read(f)
    assert result.status == "failed"
    assert result.reason in {"closure_tuple_mismatch", "invalid_native_region_evidence"}
    assert result.verifier_execution_qualified is False


def test_current_policy_revocation_invalidates_previously_authentic_tuple(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path))
    assert read(f).status == "authenticated"
    f.policy["revocations"][f.producer.key_id] = {
        "at": 1.0, "by": f.operator.key_id, "reason": "withdrawn"
    }
    repin(f)
    result = read(f)
    assert result.status == "stale"
    assert result.reason == "key_revoked"
    assert result.producer_execution_qualified is False


def test_current_independent_refutation_cannot_be_erased_by_verified_record(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path), conflicting_refutation=True)
    result = read(f)
    assert result.status == "failed"
    assert result.reason == "conflicting_refutation"
    assert result.verifier_execution_qualified is False


def test_old_enforcement_profile_pin_is_stale_after_full_authentication(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path))
    assert read(f).status == "authenticated"
    f.profile["launcher_sha256"] = "4" * 64
    f.policy["execution_profiles"] = [f.profile]
    repin(f)
    result = read(f)
    assert result.status == "stale"
    assert result.reason == "profile_pin_mismatch"
    assert result.verifier_execution_qualified is False


def test_enforcement_mount_source_role_must_match_fixed_target(tmp_path):
    f = qualified_fixture(fixture_at(tmp_path), bad_mount_source_role=True)
    result = read(f)
    assert result.status == "failed"
    assert result.reason in {"invalid_enforcement", "invalid_native_region_evidence"}
    assert result.verifier_execution_qualified is False
