"""P3.2 role-plan regression SOURCE ONLY: never imported, collected or run here.

Future positive fixtures use the real public authority loader and Ed25519
verification over synthetic signed proposals. They never mock trust or invoke
target/P1/P2 verifiers, a checker, SQLite, runtime capture or confinement. Manual
producer-shaped metadata below is planning input, not a qualified P2 result.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import json
import os
import struct
import time
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_grid.core import BudgetClass, NodeIdentity, ObjectRef, RecordType, ResultStatus, TaskResult, TaskSpec, canonical_json
from agentdecompile_grid.log.records import build_record, encode_line
from agentdecompile_grid.log.signing import Ed25519Signer, HAVE_CRYPTOGRAPHY
from agentdecompile_grid.objects.base import Layout
from agentdecompile_grid.worker.identity import NodeKey, NodeSigner, key_id_for
from agentdecompile_grid.worker.records import result_body
from agentdecompile_recovery.corpus import current_native_region_admission as authority
from agentdecompile_recovery.grid_lanes import native_region_verify_plan as builder


PROFILE = "linux-x86_64-native-objdiff-region-runtime-v1"
CHECKER_PROFILE = "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1"
POLICY = "coff-i386-register-leaf-v1"
ASSET = "bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81"
CHECKER = "parity:" + ASSET
METHOD = "parity-region-coff-i386-leaf-v1"
UPSTREAM = "784a16740a8a67b835b752ab867e76347d8a9691"
BASIS = "a" * 64
SYMBOL = "F_401000"
ROLE_CAPS = {
    "p2_task": 65536, "p2_result": 65536,
    "p2_proposed_receipt": 1 << 20, "p2_proposed_target_inventory": 1 << 20,
    "p2_proposed_candidate_inventory": 1 << 20,
    "target_task": 65536, "target_result": 65536, "parity_task": 65536, "parity_result": 65536,
    "target": 66560, "candidate": 64 << 20, "target_snapshot": 256 << 20,
    "target_image": 128 << 20, "target_proposed_receipt": 32768,
    "parity_proposed_receipt": 1 << 20, "parity_proposed_raw": 4 << 20,
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(raw):
    return "sha256:" + sha(raw)


def put(f, raw):
    """Future fixture writes directly; no source ObjectStore adapter is used."""
    key = ref(raw)
    path = f.objects / f.layout.relpath(ObjectRef(key))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    f.stored[key] = path
    return key


def put_json(f, value):
    return put(f, canonical_json(value))


def fixed_inventory(code):
    """Manual fixed-producer shape over a tiny benign COFF; no parser called."""
    aux = struct.pack("<IHHIhBBh", len(code), 0, 0, 0, 0, 0, 0, 0)
    section_symbol = b".text\0\0\0" + struct.pack("<IhHBB", 0, 1, 0, 3, 1) + aux
    function_symbol = SYMBOL.encode() + struct.pack("<IhHBB", 0, 1, 0x20, 2, 0)
    symptr = 60 + len(code)
    raw = (struct.pack("<HHIIIHH", 0x14C, 1, 0, symptr, 3, 0, 0)
           + struct.pack("<8sIIIIIIHHI", b".text\0\0\0", 0, 0, len(code), 60, 0, 0, 0, 0, 0x60500020)
           + code + section_symbol + function_symbol + struct.pack("<I", 4))
    strptr = symptr + 54
    intervals = [{"start": start, "end": end, "class": kind, "sha256": sha(raw[start:end])}
                 for start, end, kind in ((0, 20, "file_header"), (20, 60, "section_table"),
                                         (60, symptr, "region"), (symptr, strptr, "symbol_table"),
                                         (strptr, len(raw), "string_table"))]
    symbols = [
        dict(slot=0, end_slot=2, name=".text", name_field_hex=b".text\0\0\0".hex(), string_offset=None,
             value=0, section=1, type=0, storage_class=3, aux_count=1,
             **{"class": "section_definition", "auxiliary_hex": [aux.hex()]}),
        dict(slot=2, end_slot=3, name=SYMBOL, name_field_hex=SYMBOL.encode().hex(), string_offset=None,
             value=0, section=1, type=0x20, storage_class=2, aux_count=0,
             **{"class": "function", "auxiliary_hex": []}),
    ]
    inventory = {
        "schema": "agentdecompile.parity-region-inventory.v1", "policy": POLICY,
        "object_ref": ref(raw), "object_sha256": sha(raw), "object_size": len(raw),
        "header": dict(machine=0x14C, sections=1, timestamp=0, symbol_pointer=symptr, symbol_slots=3,
                       optional_header_size=0, characteristics=0),
        "section": dict(name=".text", physical_address=0, virtual_address=0, size=len(code), raw_pointer=60,
                        relocation_pointer=0, relocation_count=0, line_pointer=0, line_count=0, characteristics=0x60500020),
        "symbols": symbols, "strings": [], "string_table": {"offset": strptr, "size": 4}, "intervals": intervals,
        "region": dict(name=SYMBOL, section=".text", offset=0, file_offset=60, length=len(code), sha256=sha(code)),
        "relocations": [], "line_numbers": [], "dependencies": [], "file_metadata": None,
        "coverage_bytes": len(raw), "unclassified_bytes": 0, "metadata_differences": [],
    }
    return raw, inventory


def repin(f):
    raw = canonical_json(f.policy)
    f.snapshot.write_bytes(raw)
    f.owner_document["snapshot_sha256"] = sha(raw)
    f.owner_document["generation"] = f.policy["generation"]
    f.owner.write_bytes(canonical_json(f.owner_document))


def seal(f, *, extra=()):
    statements = [(RecordType.TASK, f.task.to_record(), f.operator, BASIS),
                  (RecordType.RESULT, result_body(f.task, f.result, ObjectRef(f.result_ref), f.producer_identity,
                                                 deadline_s=600, nonce="synthetic-result"), f.producer, BASIS)]
    statements.extend(extra)
    previous, records = "", []
    for seq, (kind, body, signer, basis) in enumerate(statements, 1):
        record = build_record(f.task.partition_key, seq, kind, body, previous, signer, basis_hash=basis, validate=False)
        previous = record.digest()  # Chain linkage is the unsigned-record hash.
        records.append(record)
    f.log.write_bytes(b"".join(encode_line(record) for record in records))
    f.records = records
    f.selection = builder.NativeRegionVerifySelection(f.task.partition_key, ref(encode_line(records[0])[:-1]),
                                                       ref(encode_line(records[1])[:-1]), f.result_ref)


def publish_graph(f):
    """Rebind each proposal bottom-up; signatures are recomputed by real signer."""
    target_receipt_ref = put_json(f, f.target_receipt)
    parity_receipt_ref = put_json(f, f.parity_receipt)
    f.target_result = TaskResult(f.target_task.task_id, ResultStatus.OK,
                                {"target": ObjectRef(f.target_ref), "receipt": ObjectRef(target_receipt_ref)},
                                f.producer.key_id, BASIS, 0.001)
    f.parity_result = TaskResult(f.parity_task.task_id, ResultStatus.OK,
                                {"receipt": ObjectRef(parity_receipt_ref), "raw": ObjectRef(f.raw_ref)},
                                f.producer.key_id, BASIS, 0.001)
    inputs = {"target_task": put_json(f, f.target_task.to_record()),
              "target_result": put_json(f, f.target_result.to_record()),
              "parity_task": put_json(f, f.parity_task.to_record()),
              "parity_result": put_json(f, f.parity_result.to_record()),
              "target": f.target_ref, "candidate": f.candidate_ref}
    f.task = TaskSpec("parity-region-check", 1, {k: ObjectRef(v) for k, v in inputs.items()},
                      {"checker_profile": CHECKER_PROFILE, "comparison_policy": POLICY}, BASIS,
                      capabilities=(CHECKER_PROFILE, CHECKER), budget=BudgetClass.MEDIUM, partition="native-region/synthetic")
    inventories = {side: put_json(f, f.inventories[side]) for side in ("target", "candidate")}
    selected = f.target_task.params["selection"]
    f.receipt = {
        "schema": "agentdecompile.parity-region.v1", "kind": f.task.kind, "kind_version": 1,
        "task_id": f.task.task_id, "basis_hash": BASIS, "checker_profile": CHECKER_PROFILE,
        "comparison_policy": POLICY, "verifier_id": CHECKER, "upstream_commit": UPSTREAM, "upstream_asset_sha256": ASSET,
        "inputs": inputs, "prerequisites": {
            "target": dict(task_id=f.target_task.task_id, result_ref=inputs["target_result"], method="mkobj-target-reference-free-v1"),
            "parity": dict(task_id=f.parity_task.task_id, result_ref=inputs["parity_result"], method="parity-binding-v1")},
        "target_receipt_ref": target_receipt_ref, "proposed_parity_receipt_ref": parity_receipt_ref,
        "proposed_parity_raw_ref": f.raw_ref,
        "objects": {side: {"sha256": inv["object_sha256"], "size": inv["object_size"]} for side, inv in f.inventories.items()},
        "target_selection": {key: selected[key] for key in ("image_sha256", "report_version", "binary_id", "func_id", "addr", "size")},
        "selection_sha256": f.target_task.params["selection_sha256"], "inventory_refs": inventories,
        "strict_report_sha256": sha(b"synthetic report proposal, not a verifier receipt"),
        "section": ".text", "symbol": SYMBOL, "region_length": 3,
        "region_sha256": {side: inv["region"]["sha256"] for side, inv in f.inventories.items()},
        "grade": f.grade, "checker_grade": f.grade, "byte_difference_count": 0 if f.grade == "matched" else 1,
        "instruction_count": {"target": 2, "candidate": 2}, "relocation_count": 0,
        "coverage_bytes": 3, "unclassified_bytes": 0, "metadata_differences": [],
        "comparison_scope": "complete-emitted-reference-free-region", "reference_policy": POLICY,
        "target_producer_scope": "conservative-pc-relative-byte-screen", "runtime_admission": "not_evaluated",
        "source_binding": "not_evaluated", "linked_image_metadata": "not_evaluated",
    }
    f.result = TaskResult(f.task.task_id, ResultStatus.OK,
                         {"receipt": ObjectRef(put_json(f, f.receipt)),
                          "target_inventory": ObjectRef(inventories["target"]),
                          "candidate_inventory": ObjectRef(inventories["candidate"])}, f.producer.key_id, BASIS, 0.001)
    f.result_ref = put_json(f, f.result.to_record())
    seal(f)


def fixture_at(tmp_path, *, grade="matched", timeout=False):
    if not HAVE_CRYPTOGRAPHY:
        pytest.skip("Actual Ed25519 required; no null/HMAC/signature-success substitute")
    root = tmp_path / "synthetic-plan"
    objects, keys, logs = (root / name for name in ("cas", "public", "logs"))
    for path in (objects, keys, logs):
        path.mkdir(parents=True)
    f = SimpleNamespace(root=root, objects=objects, keys=keys, logs=logs, layout=Layout(), stored={}, grade=grade,
                        owner=root / "owner.json", snapshot=root / "snapshot.json")
    (objects / "layout.json").write_bytes(f.layout.to_json())
    f.operator = Ed25519Signer(bytes([41]) * 32)  # TEST-ONLY seeds, generated only by future fixture invocation.
    public_keys = [dict(filename="operator.pub", sha256=sha(f.operator.public_bytes), key_id=f.operator.key_id,
                        algorithm="ed25519", role="operator", lineage=[])]
    (keys / "operator.pub").write_bytes(f.operator.public_bytes)
    for seed_number, label, role in ((42, "producer", "donor"), (43, "verifier", "fleet")):
        seed = bytes([seed_number]) * 32
        public = Ed25519Signer(seed).public_bytes
        key = NodeKey("ed25519", key_id_for("ed25519", public), seed, public, 0.0, 1e20)
        signer = NodeSigner(key)
        setattr(f, label, signer)
        setattr(f, label + "_identity", NodeIdentity(key.key_id, (), [], role))
        raw = canonical_json(dict(key.public_record(), role=role, lineage=[]))
        filename = label + ".json"
        (keys / filename).write_bytes(raw)
        public_keys.append(dict(filename=filename, sha256=sha(raw), key_id=key.key_id,
                                algorithm="ed25519", role=role, lineage=[]))
    f.profile = dict(profile_id=PROFILE, profile_sha256="b" * 64, kind="parity-region-check", kind_version=1,
                     dispatch="kind", method=METHOD, checker_profile=CHECKER_PROFILE, comparison_policy=POLICY,
                     verifier_id=CHECKER, root_inventory_ref="sha256:" + "c" * 64,
                     implementation_source_sha256="d" * 64, launcher_sha256="e" * 64,
                     filter_sha256="f" * 64, environment_sha256="1" * 64, entrypoint_sha256="2" * 64,
                     basis_hashes=[BASIS], task_operator_keys=[f.operator.key_id],
                     producer_keys=[f.producer.key_id], verifier_keys=[f.verifier.key_id])
    f.policy = dict(schema="agentdecompile.current-native-region-admission.v1", policy_id="synthetic-policy", generation=1,
                    public_keys=public_keys, revocations={}, independence_policy="disjoint-lineage",
                    execution_profiles=[f.profile], corpus_scope=None)
    f.owner_document = dict(schema="agentdecompile.current-native-region-reader-config.v1", configuration_revision=1,
                            snapshot_path=str(f.snapshot), snapshot_sha256="0" * 64, policy_id="synthetic-policy", generation=1,
                            objects_root=str(objects), log_root=str(logs), public_key_root=str(keys),
                            shard_width=f.layout.shard_width, shard_depth=f.layout.shard_depth)
    f.cfg = authority.NativeRegionReaderConfig(str(f.owner))
    repin(f)
    snapshot = put(f, b"opaque synthetic snapshot; never opened as SQLite")
    image_bytes = b"opaque synthetic image; never parsed as PE"
    image = put(f, image_bytes)
    target_bytes, target_inv = fixed_inventory(b"\x31\xc0\xc3")
    candidate_bytes, candidate_inv = fixed_inventory(b"\x31\xc0\xc3" if grade == "matched" else b"\x33\xc0\xc3")
    f.target_ref, f.candidate_ref = put(f, target_bytes), put(f, candidate_bytes)
    f.inventories = {"target": target_inv, "candidate": candidate_inv}
    selection = dict(schema="agentdecompile.mkobj-target-selection/v1", store_ref=snapshot, image_ref=image,
                     corpus_scope_sha256="3" * 64, generation_sha256="4" * 64, binary_id=1, func_id=2,
                     addr=0x401000, size=3, ranges=1, report_version=sha(image_bytes), image_sha256=sha(image_bytes))
    implementation = dict(schema="agentdecompile.mkobj-target-implementation/v1", kind="mkobj-target", kind_version=1,
                          decoder_mode="reference-free-only-v1", selection_schema="agentdecompile.mkobj-target-selection/v1",
                          receipt_schema="agentdecompile.mkobj-target/v1", sources={"synthetic.py": "5" * 64},
                          functions={"synthetic.function": "6" * 64}, constants={},
                          python=dict(implementation="cpython", cache_tag="cpython-312", version=[3, 12, 0, "final", 0], optimization=0),
                          sqlite_version="3.0.0", external_decoder=None, external_decoder_dependencies=[])
    params = dict(selection=selection, selection_sha256=sha(canonical_json(selection)), implementation_basis=implementation,
                  implementation_sha256=sha(canonical_json(implementation)), decoder_mode="reference-free-only-v1", timeout_s=60)
    f.target_task = TaskSpec("mkobj-target", 1, {"store": ObjectRef(snapshot), "image": ObjectRef(image)}, params, BASIS,
                             capabilities=("mkobj-target-reference-free:" + params["implementation_sha256"],), budget=BudgetClass.SMALL)
    f.target_receipt = dict(schema="agentdecompile.mkobj-target/v1", claim="raw_image_function_target_object", status="produced",
                            kind="mkobj-target", kind_version=1, task_id=f.target_task.task_id, basis_hash=BASIS,
                            **{key: value for key, value in params.items() if key != "timeout_s"},
                            mapping=dict(file_offset=512, machine=0x14C, optional_magic=0x10B, format="coff-i386"), symbol=SYMBOL,
                            target_ref=f.target_ref, target_sha256=sha(target_bytes), target_size=len(target_bytes),
                            region_sha256=target_inv["region"]["sha256"], relocation_count=0)
    parity_params = {"verifier_id": CHECKER, "symbol": SYMBOL}
    if timeout:
        parity_params["timeout_s"] = 60
    f.parity_task = TaskSpec("parity-check", 1, {"target": ObjectRef(f.target_ref), "candidate": ObjectRef(f.candidate_ref)},
                             parity_params, BASIS, capabilities=(CHECKER,), budget=BudgetClass.SMALL)
    f.raw_ref = put(f, b"opaque proposed checker output; builder must not normalize or execute it")
    f.parity_receipt = dict(schema="agentdecompile.verify-objdiff.v1", status=grade, differences=0 if grade == "matched" else 1,
                            message="Object files match" if grade == "matched" else "Object files do not match",
                            objdiffExit=0, detailLevel="scalar-only", kind="parity-check", kind_version=1,
                            verifier_id=CHECKER, verifier="native", sides={"target": f.target_ref[7:], "candidate": f.candidate_ref[7:]},
                            symbol=SYMBOL, grade=grade, basis_hash=BASIS)
    f.log = logs / "native-region" / "synthetic" / "records.jsonl"
    f.log.parent.mkdir(parents=True)
    publish_graph(f)
    return f


def begin(f):
    return builder.begin_native_region_verify(f.selection, profile_id=PROFILE, verifier_key=f.verifier.key_id)


def build(f, seed=None, stage_started_at_ns=None):
    seed = begin(f) if seed is None else seed
    start = time.monotonic_ns() if stage_started_at_ns is None else stage_started_at_ns
    return builder.build_native_region_verify_plan(seed, cfg=f.cfg, stage_started_at_ns=start)


def assert_error(f, status, reasons):
    with pytest.raises(builder.NativeRegionPlanError) as error:
        build(f)
    assert error.value.status == status
    assert error.value.reason in reasons
    assert set(error.value.__dict__) == {"status", "reason"}


def deeply_immutable(value):
    if is_dataclass(value):
        assert value.__dataclass_params__.frozen
        for item in fields(value):
            deeply_immutable(getattr(value, item.name))
    elif type(value) is tuple:
        for item in value:
            deeply_immutable(item)
    else:
        assert type(value) in (str, bytes, int, type(None))


@pytest.mark.parametrize("grade", ["matched", "mismatched"])
@pytest.mark.parametrize("timeout", [False, True])
def test_real_signed_loader_plan_has_all_roles_and_inline_only_task(tmp_path, grade, timeout):
    f = fixture_at(tmp_path, grade=grade, timeout=timeout)
    inline = canonical_json(f.task.to_record())
    inline_ref = ref(inline)
    assert inline_ref not in f.stored
    before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in
              [f.owner, f.snapshot, f.log, f.objects / "layout.json", *f.stored.values(), *f.keys.iterdir()]}
    names_before = {str(path.relative_to(f.root)) for path in f.root.rglob("*")}
    result = build(f)
    plan = result.plan
    assert result.inline_task_bytes == inline and plan.task_ref == inline_ref
    assert plan.task_id == f.task.task_id and plan.task_id != inline_ref[7:]
    assert plan.selection.task_record_ref == ref(encode_line(f.records[0])[:-1])
    assert plan.selection.task_record_ref != "sha256:" + f.records[0].digest()
    assert [(row.role, row.cap) for row in plan.roles] == sorted(ROLE_CAPS.items())
    assert len(plan.roles) == 16 and len({row.role for row in plan.roles}) == 16
    assert result.plan_bytes == canonical_json(plan.to_record()) and result.plan_sha256 == sha(result.plan_bytes)
    assert len(result.plan_bytes) <= 16 * 1024
    selected = next(row for row in result.authority.profiles if row.profile_id == PROFILE)
    assert plan.admission_identity == selected.effective_authority_digest
    assert plan.profile_row_sha256 == selected.profile_row_sha256 and plan.profile_sha256 == f.profile["profile_sha256"]
    assert plan.admission_generation == 1 and plan.verifier_key == f.verifier.key_id
    assert plan.stage_deadline_ns == min(plan.stage_started_at_ns + 100_000_000_000,
                                         plan.absolute_deadline_ns - 410_000_000_000)
    assert plan.absolute_deadline_ns - plan.admitted_at_ns == 600_000_000_000
    observations = result.source_objects
    assert tuple(row.ref for row in observations) == tuple(sorted({row.ref for row in observations}))
    assert inline_ref not in {row.ref for row in observations}
    assert result.log_observation.sha256 == sha(f.log.read_bytes())
    assert result.log_observation.size == len(f.log.read_bytes())
    deeply_immutable(result)
    with pytest.raises(FrozenInstanceError):
        plan.admission_generation = 99
    assert before == {name: (Path(name).read_bytes(), Path(name).stat().st_mtime_ns) for name in before}
    assert names_before == {str(path.relative_to(f.root)) for path in f.root.rglob("*")}
    assert inline_ref not in f.stored


def selection_shape():
    return builder.NativeRegionVerifySelection("native-region/synthetic", "sha256:" + "1" * 64,
                                               "sha256:" + "2" * 64, "sha256:" + "3" * 64)


def test_begin_is_timing_only_with_one_clock_sample_and_no_io_or_hash(monkeypatch):
    selection = selection_shape()
    sampled = []

    def clock():
        sampled.append(1)
        return 123

    def forbidden(*args, **kwargs):
        raise AssertionError("no-I/O seed touched a trust, file or hash boundary")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builder.time, "monotonic_ns", clock)
        patch.setattr(os, "open", forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(hashlib, "sha256", forbidden)
        patch.setattr(authority, "load_native_region_authority", forbidden)
        seed = builder.begin_native_region_verify(selection, profile_id=PROFILE, verifier_key="synthetic-verifier")
    assert sampled == [1] and seed.admitted_at_ns == 123 and seed.absolute_deadline_ns == 600_000_000_123
    assert seed.selection == selection and type(seed.selection) is builder.NativeRegionVerifySelection
    assert seed.to_record() == dict(schema="agentdecompile.native-region-verify-seed.v1",
                                    selection=dict(partition=selection.partition, task_record_ref=selection.task_record_ref,
                                                   result_record_ref=selection.result_record_ref, result_ref=selection.result_ref),
                                    profile_id=PROFILE, verifier_key="synthetic-verifier", admitted_at_ns=123,
                                    absolute_deadline_ns=600_000_000_123)
    assert len(canonical_json(seed.to_record())) <= 2048
    deeply_immutable(seed)


@pytest.mark.parametrize("field,value", [("partition", "../foreign"), ("partition", "/absolute"),
                                          ("partition", "a//b"), ("partition", "a" * 513),
                                          ("task_record_ref", "1" * 64), ("result_record_ref", "sha256:" + "A" * 64),
                                          ("result_ref", True)])
def test_begin_rejects_selection_coercions_and_unsafe_locators(field, value):
    selection = replace(selection_shape(), **{field: value})
    with pytest.raises(builder.NativeRegionPlanError) as error:
        builder.begin_native_region_verify(selection, profile_id=PROFILE, verifier_key="synthetic-verifier")
    assert (error.value.status, error.value.reason) == ("failed", "invalid_selection")


def test_begin_does_not_accept_a_selection_subclass():
    class Derived(builder.NativeRegionVerifySelection):
        pass
    base = selection_shape()
    with pytest.raises(builder.NativeRegionPlanError) as error:
        builder.begin_native_region_verify(Derived(base.partition, base.task_record_ref, base.result_record_ref, base.result_ref),
                                           profile_id=PROFILE, verifier_key="synthetic-verifier")
    assert error.value.reason == "invalid_selection"


@pytest.mark.parametrize("field,value", [("admitted_at_ns", True), ("admitted_at_ns", -1),
                                          ("absolute_deadline_ns", 600_000_000_001),
                                          ("absolute_deadline_ns", 2**63), ("schema", "other-seed")])
def test_invalid_seed_refuses_before_authority_read(monkeypatch, field, value):
    seed = builder.NativeRegionVerifySeed("agentdecompile.native-region-verify-seed.v1", selection_shape(),
                                          PROFILE, "synthetic-verifier", 0, 600_000_000_000)
    seed = replace(seed, **{field: value})

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid seed attempted a filesystem read")

    monkeypatch.setattr(os, "open", forbidden)
    with pytest.raises(builder.NativeRegionPlanError) as error:
        builder.build_native_region_verify_plan(seed, cfg=authority.NativeRegionReaderConfig(""), stage_started_at_ns=0)
    assert (error.value.status, error.value.reason) == ("failed", "invalid_seed")


def test_less_than_loader_five_seconds_refuses_without_reset_or_read(monkeypatch):
    seed = builder.NativeRegionVerifySeed("agentdecompile.native-region-verify-seed.v1", selection_shape(),
                                          PROFILE, "synthetic-verifier", 0, 600_000_000_000)
    now = 185_000_000_001
    monkeypatch.setattr(builder.time, "monotonic_ns", lambda: now)

    def forbidden(*args, **kwargs):
        raise AssertionError("under-five-second remainder attempted loader IO")

    monkeypatch.setattr(os, "open", forbidden)
    for start in (185_000_000_000, 189_000_000_000):
        # A later stage start still cannot move absolute-410s past190s.
        with pytest.raises(builder.NativeRegionPlanError) as error:
            builder.build_native_region_verify_plan(seed, cfg=authority.NativeRegionReaderConfig(""), stage_started_at_ns=start)
        if start <= now:
            assert (error.value.status, error.value.reason) == ("unavailable", "deadline_exceeded")
        else:
            assert error.value.status == "failed" and error.value.reason == "invalid_seed"


def replace_p2_output(f, role, raw):
    outputs = dict(f.result.outputs)
    outputs[role] = ObjectRef(put(f, raw))
    f.result = replace(f.result, outputs=outputs)
    f.result_ref = put_json(f, f.result.to_record())
    seal(f)


@pytest.mark.parametrize("fault", ["missing_inventory", "extra_output", "bool_version", "wrong_budget", "extra_input", "wrong_profile"])
def test_signed_p2_fixed_envelope_and_graph_rejects_drift(tmp_path, fault):
    f = fixture_at(tmp_path)
    if fault == "missing_inventory":
        f.result = replace(f.result, outputs={k: v for k, v in f.result.outputs.items() if k != "candidate_inventory"})
    elif fault == "extra_output":
        f.result = replace(f.result, outputs={**f.result.outputs, "extra": ObjectRef(f.raw_ref)})
    elif fault == "bool_version":
        f.task = replace(f.task, kind_version=True)
    elif fault == "wrong_budget":
        f.task = replace(f.task, budget=BudgetClass.SMALL)
    elif fault == "extra_input":
        f.task = replace(f.task, inputs={**f.task.inputs, "arbitrary": ObjectRef(f.raw_ref)})
    else:
        f.task = replace(f.task, params={**f.task.params, "checker_profile": "other"})
    f.result = replace(f.result, task_id=f.task.task_id)
    f.result_ref = put_json(f, f.result.to_record())
    seal(f)
    assert_error(f, "failed", {"schema_invalid", "unsupported_profile", "tuple_mismatch"})


@pytest.mark.parametrize("fault", ["extra", "duplicate", "whitespace", "nonfinite", "depth"])
def test_selected_cas_document_strict_json_precedes_constructors(tmp_path, fault):
    f = fixture_at(tmp_path)
    raw = canonical_json(f.receipt)
    if fault == "extra":
        raw = canonical_json(dict(f.receipt, callback="sha256:" + "9" * 64))
    elif fault == "duplicate":
        raw = raw.replace(b'"kind_version":1', b'"kind_version":1,"kind_version":1')
    elif fault == "whitespace":
        raw += b"\n"
    elif fault == "nonfinite":
        raw = raw.replace(b'"coverage_bytes":3', b'"coverage_bytes":NaN')
    else:
        raw = b'{"nested":' * 33 + b'0' + b'}' * 33
    replace_p2_output(f, "receipt", raw)
    assert_error(f, "unavailable" if fault == "depth" else "failed", {"limit_exceeded"} if fault == "depth" else {"schema_invalid"})


@pytest.mark.parametrize("document,field,value", [
    ("target_receipt", "selection_sha256", "0" * 64), ("target_receipt", "symbol", "F_foreign"),
    ("target_receipt", "basis_hash", "0" * 64), ("target_receipt", "implementation_sha256", "0" * 64),
    ("parity_receipt", "symbol", "F_foreign"), ("parity_receipt", "basis_hash", "0" * 64),
    ("parity_receipt", "objdiffExit", True), ("parity_receipt", "differences", -1),
    ("parity_receipt", "verifier", "node"),
])
def test_prerequisite_metadata_joins_are_required_without_running_verifiers(tmp_path, document, field, value):
    f = fixture_at(tmp_path)
    getattr(f, document)[field] = value
    publish_graph(f)
    assert_error(f, "failed", {"schema_invalid", "tuple_mismatch", "unsupported_profile"})


@pytest.mark.parametrize("side,fault", [("target", "object_hash"), ("candidate", "extra_section"),
                                       ("target", "bool_size"), ("candidate", "unknown_class"),
                                       ("target", "invented_ref")])
def test_inventory_exact_nested_shapes_cannot_expand_role_graph(tmp_path, side, fault):
    f = fixture_at(tmp_path)
    inventory = f.inventories[side]
    if fault == "object_hash":
        inventory["object_sha256"] = "0" * 64
    elif fault == "extra_section":
        inventory["section"]["extra"] = "sha256:" + "9" * 64
    elif fault == "bool_size":
        inventory["object_size"] = True
    elif fault == "unknown_class":
        inventory["intervals"][0]["class"] = "ignore-unclassified"
    else:
        inventory["external_ref"] = "sha256:" + "9" * 64
    publish_graph(f)
    assert_error(f, "failed", {"schema_invalid", "tuple_mismatch"})


@pytest.mark.parametrize("record_index", [0, 1])
def test_selected_signed_envelope_authentication_is_not_chain_hashing(tmp_path, record_index):
    f = fixture_at(tmp_path)
    forged = replace(f.records[record_index], signature=f.records[1 - record_index].signature)
    records = list(f.records)
    records[record_index] = forged
    f.log.write_bytes(b"".join(encode_line(record) for record in records))
    key = "task_record_ref" if record_index == 0 else "result_record_ref"
    f.selection = replace(f.selection, **{key: ref(encode_line(forged)[:-1])})
    # Chain unsigned hashes remain unchanged; the selected signed digest is
    # updated so only real signature verification rejects this specimen.
    assert_error(f, "failed", {"signature_invalid"})


@pytest.mark.parametrize("kind", ["task", "result"])
def test_later_duplicate_selected_identity_is_not_ignored(tmp_path, kind):
    f = fixture_at(tmp_path)
    if kind == "task":
        duplicate = (RecordType.TASK, f.task.to_record(), f.operator, BASIS)
    else:
        duplicate = (RecordType.RESULT, result_body(f.task, f.result, ObjectRef(f.result_ref), f.producer_identity,
                                                   deadline_s=600, nonce="duplicate"), f.producer, BASIS)
    seal(f, extra=[duplicate])
    assert_error(f, "failed", {"ambiguous_selection"})


@pytest.mark.parametrize("who", ["operator", "producer", "verifier"])
def test_fresh_owner_revocation_invalidates_new_plan_without_stale_success(tmp_path, who):
    f = fixture_at(tmp_path)
    assert build(f).plan.admission_generation == 1
    f.policy["revocations"][getattr(f, who).key_id] = dict(at=1.0, by=f.operator.key_id, reason="fixture withdrawal")
    repin(f)
    assert_error(f, "failed", {"signer_ineligible", "unsupported_profile"})


def set_public_lineage(f, label, lineage):
    entry = next(row for row in f.policy["public_keys"] if row["filename"] == label + ".json")
    path = f.keys / entry["filename"]
    public = json.loads(path.read_bytes())
    public["lineage"] = entry["lineage"] = list(lineage)
    raw = canonical_json(public)
    path.write_bytes(raw)
    entry["sha256"] = sha(raw)


@pytest.mark.parametrize("fault", [None, "shared_ancestor", "ancestor_revoked", "claimed_lineage"])
def test_closed_lineage_eligibility_and_claims_use_actual_public_metadata(tmp_path, fault):
    f = fixture_at(tmp_path)
    ancestor_seed = bytes([44]) * 32
    ancestor_public = Ed25519Signer(ancestor_seed).public_bytes
    ancestor_key = NodeKey("ed25519", key_id_for("ed25519", ancestor_public), ancestor_seed, ancestor_public, 0.0, 1e20)
    raw = canonical_json(dict(ancestor_key.public_record(), role="donor", lineage=[]))
    (f.keys / "ancestor.json").write_bytes(raw)
    f.policy["public_keys"].append(dict(filename="ancestor.json", sha256=sha(raw), key_id=ancestor_key.key_id,
                                       algorithm="ed25519", role="donor", lineage=[]))
    # Sharing TASK operator ancestry is permitted; independence concerns the
    # producer and intended verifier, including their closed trusted lineages.
    lineage = [ancestor_key.key_id, f.operator.key_id]
    set_public_lineage(f, "producer", lineage)
    f.producer_identity = NodeIdentity(f.producer.key_id, (), [] if fault == "claimed_lineage" else lineage, "donor")
    if fault == "shared_ancestor":
        set_public_lineage(f, "verifier", [ancestor_key.key_id])
    elif fault == "ancestor_revoked":
        f.policy["revocations"][ancestor_key.key_id] = dict(at=1.0, by=f.operator.key_id, reason="ancestor withdrawal")
    repin(f)
    seal(f)
    if fault is None:
        assert build(f).plan.producer_key == f.producer.key_id
    else:
        assert_error(f, "failed", {"tuple_mismatch"} if fault == "claimed_lineage" else {"signer_ineligible"})


@pytest.mark.parametrize("fault", ["missing_key", "corrupt_pin", "donor_verifier", "ambiguous_profile"])
def test_public_authority_failure_never_becomes_authenticated_hint(tmp_path, fault):
    f = fixture_at(tmp_path)
    if fault == "missing_key":
        (f.keys / "producer.json").unlink()
    elif fault == "corrupt_pin":
        f.owner_document["snapshot_sha256"] = "0" * 64
        f.owner.write_bytes(canonical_json(f.owner_document))
    elif fault == "donor_verifier":
        entry = next(row for row in f.policy["public_keys"] if row["filename"] == "verifier.json")
        entry["role"] = "donor"
        path = f.keys / entry["filename"]
        public = json.loads(path.read_bytes())
        public["role"] = "donor"
        raw = canonical_json(public)
        path.write_bytes(raw)
        entry["sha256"] = sha(raw)
        repin(f)
    else:
        f.policy["execution_profiles"].append(dict(f.profile, profile_sha256="7" * 64))
        repin(f)
    assert_error(f, "unavailable" if fault == "missing_key" else "failed",
                 {"authority_unavailable"} if fault == "missing_key" else {"authority_invalid", "signer_ineligible", "ambiguous_profile"})


@pytest.mark.parametrize("fault", ["missing", "corrupt", "symlink", "ancestor_symlink", "oversize"])
def test_source_object_authentication_refuses_without_repair_or_fallback(tmp_path, fault):
    f = fixture_at(tmp_path)
    path = f.stored[f.raw_ref]
    original = path.read_bytes()
    adjacent = tmp_path / "foreign-sentinel"
    adjacent.write_bytes(b"unchanged")
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"corrupt")
    elif fault == "symlink":
        path.unlink()
        path.symlink_to(adjacent)
    elif fault == "ancestor_symlink":
        moved = path.parent.with_name(path.parent.name + "-moved")
        path.parent.rename(moved)
        path.parent.symlink_to(moved, target_is_directory=True)
    else:
        with path.open("r+b") as stream:
            stream.truncate((4 << 20) + 1)
    assert_error(f, "failed" if fault == "corrupt" else "unavailable",
                 {"object_hash_mismatch"} if fault == "corrupt" else {"input_unavailable", "limit_exceeded"})
    assert adjacent.read_bytes() == b"unchanged"
    if fault == "corrupt":
        assert path.read_bytes() == b"corrupt"
    elif fault == "missing":
        assert not path.exists()
    assert original != b"corrupt"


@pytest.mark.parametrize("fault", ["torn", "noncanonical", "ancestor_symlink", "line_cap", "log_cap"])
def test_partition_snapshot_is_complete_bounded_and_nofollow(tmp_path, fault):
    f = fixture_at(tmp_path)
    if fault == "torn":
        f.log.write_bytes(f.log.read_bytes()[:-1])
    elif fault == "noncanonical":
        f.log.write_bytes(f.log.read_bytes().replace(b'{"', b'{ "', 1))
    elif fault == "ancestor_symlink":
        moved = f.log.parent.with_name("moved-synthetic")
        f.log.parent.rename(moved)
        f.log.parent.symlink_to(moved, target_is_directory=True)
    elif fault == "line_cap":
        f.log.write_bytes(b" " * (128 * 1024 + 1) + b"\n")
    else:
        with f.log.open("r+b") as stream:
            stream.truncate((16 << 20) + 1)
    assert_error(f, "failed" if fault == "noncanonical" else "unavailable",
                 {"invalid_log", "schema_invalid"} if fault == "noncanonical" else {"invalid_log", "input_unavailable", "limit_exceeded"})


def test_alias_rows_survive_deduplication_with_smallest_read_cap(tmp_path):
    f = fixture_at(tmp_path, grade="matched")
    assert f.target_ref == f.candidate_ref
    result = build(f)
    roles = {row.role: row for row in result.plan.roles}
    assert roles["target"].ref == roles["candidate"].ref == f.target_ref
    assert roles["target"].cap == 66560 and roles["candidate"].cap == 64 << 20
    observations = [row for row in result.source_objects if row.ref == f.target_ref]
    assert len(observations) == 1 and observations[0].cap == 66560
    assert observations[0].size == len(f.stored[f.target_ref].read_bytes())
    assert len(result.plan.roles) == 16


def test_no_policy_or_signature_callback_can_replace_cfg_argument(tmp_path):
    f = fixture_at(tmp_path)
    authentic = authority.load_native_region_authority(f.cfg)
    for substitution in (authentic, {}, lambda *args: True):
        with pytest.raises(builder.NativeRegionPlanError) as error:
            builder.build_native_region_verify_plan(begin(f), cfg=substitution, stage_started_at_ns=time.monotonic_ns())
        assert error.value.status in {"failed", "unavailable"}
        assert error.value.reason in {"invalid_seed", "authority_invalid", "authority_unavailable"}


@pytest.mark.parametrize("change", ["authority", "log", "object"])
def test_actual_rereads_detect_changed_authority_history_or_object(tmp_path, monkeypatch, change):
    """Negative read seam returns real bytes; it never supplies trusted values."""
    f = fixture_at(tmp_path)
    observed = f.stored[f.raw_ref]
    selected_inode = observed.stat().st_ino
    duplicate_body = result_body(f.task, f.result, ObjectRef(f.result_ref), f.producer_identity,
                                 deadline_s=600, nonce="concurrent-result")
    additional = build_record(f.task.partition_key, 3, RecordType.RESULT, duplicate_body, f.records[-1].digest(),
                              f.producer, basis_hash=BASIS, validate=False)
    appended = f.log.read_bytes() + encode_line(additional)
    real_read = os.read
    triggered = []

    def changed_after_read(fd, count):
        raw = real_read(fd, count)
        if raw and not triggered and os.fstat(fd).st_ino == selected_inode:
            triggered.append(True)
            if change == "authority":
                f.owner_document["configuration_revision"] += 1
                f.owner.write_bytes(canonical_json(f.owner_document))
            elif change == "log":
                f.log.write_bytes(appended)
            else:
                observed.write_bytes(b"z" * observed.stat().st_size)
        return raw

    monkeypatch.setattr(os, "read", changed_after_read)
    assert_error(f, "unavailable", {"authority_changed"} if change == "authority" else
                 {"log_changed"} if change == "log" else {"object_changed"})
    assert triggered == [True]


@pytest.mark.parametrize("missing", [False, True])
def test_inline_task_bytes_never_waive_an_ordinary_cas_read(tmp_path, missing):
    """Internal descriptor-read contract, not an invented cyclic signed graph.

    A complete content-addressed graph cannot casually fabricate its own TASK
    digest as a descendant. Exercise the actual ordinary-CAS seam separately
    using real loader authority and the same retained canonical task bytes.
    """
    f = fixture_at(tmp_path)
    completed = build(f)
    inline = completed.inline_task_bytes
    task_ref = completed.plan.task_ref
    if not missing:
        assert put(f, inline) == task_ref
    deadline = time.monotonic_ns() + 10_000_000_000
    io = [0]
    if missing:
        with pytest.raises(builder._Refusal) as error:
            builder._cas(completed.authority, task_ref, 65536, deadline, io)
        assert (error.value.status, error.value.reason) == ("unavailable", "input_unavailable")
    else:
        size, identity = builder._cas(completed.authority, task_ref, 65536, deadline, io)
        assert size == len(inline) and io == [len(inline)] and identity[2] == len(inline)


@pytest.mark.parametrize("over", [False, True])
def test_actual_cas_stream_budget_counts_returned_bytes_at_512_mib_boundary(tmp_path, over):
    """Accounting specification with real bounded read; no512MiB allocation."""
    f = fixture_at(tmp_path)
    actual_authority = authority.load_native_region_authority(f.cfg)
    raw = f.stored[f.raw_ref].read_bytes()
    budget = [(512 << 20) - len(raw) + int(over)]
    deadline = time.monotonic_ns() + 10_000_000_000
    if over:
        with pytest.raises(builder._Refusal) as error:
            builder._cas(actual_authority, f.raw_ref, 4 << 20, deadline, budget)
        assert (error.value.status, error.value.reason) == ("unavailable", "limit_exceeded")
    else:
        assert builder._cas(actual_authority, f.raw_ref, 4 << 20, deadline, budget)[0] == len(raw)
        assert budget == [512 << 20]


@pytest.mark.parametrize("over", [False, True])
def test_ordinary_cas_read_applies_tightened_alias_cap(tmp_path, over):
    f = fixture_at(tmp_path)
    actual_authority = authority.load_native_region_authority(f.cfg)
    raw = b"x" * (65536 + int(over))
    aliased = put(f, raw)
    deadline = time.monotonic_ns() + 10_000_000_000
    # First the wide role succeeds; that observation cannot waive the later
    #64KiB cap. The source bytes are still authenticated under the tighter cap.
    assert builder._cas(actual_authority, aliased, 1 << 20, deadline, [0])[0] == len(raw)
    if over:
        with pytest.raises(builder._Refusal) as error:
            builder._cas(actual_authority, aliased, 65536, deadline, [0])
        assert error.value.status == "unavailable" and error.value.reason in {"limit_exceeded", "input_unavailable"}
    else:
        assert builder._cas(actual_authority, aliased, 65536, deadline, [0])[0] == 65536


def test_builder_source_does_not_dispatch_or_bypass_public_loader():
    """AST source boundary only; no imported execution or signature behavior proof."""
    source = Path(builder.__file__).read_text()
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    forbidden = {"inventory_coff", "_observe", "_implementation", "_snapshot_selection",
                 "connect", "LocalDirStore", "LocalFileLog", "authenticate_native_region_execution"}
    assert not any((isinstance(node.func, ast.Attribute) and node.func.attr in forbidden)
                   or (isinstance(node.func, ast.Name) and node.func.id in forbidden) for node in calls)
    loader = [node for node in calls if (isinstance(node.func, ast.Name) and node.func.id == "load_native_region_authority")
              or (isinstance(node.func, ast.Attribute) and node.func.attr == "load_native_region_authority")]
    assert loader, "builder must actually call the shared loader; no alternate parser"
