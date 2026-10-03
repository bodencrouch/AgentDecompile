"""Task 11.2 regressions: authored source only; execution requires authorization.

Fixtures use synthetic PE bytes and a minimal immutable SQLite snapshot. No
compiler, decoder, Ghidra, service, or recovery worker is needed by this file.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
import struct
import time
from pathlib import Path

import pytest

from agentdecompile_grid.core import BudgetClass, ObjectRef, Refused, VerificationOutcome, canonical_json
from agentdecompile_grid.objects.local import LocalDirStore
from agentdecompile_recovery.corpus import determinism_basis, mkobj
from agentdecompile_recovery.grid_lanes import splitter, target


def pe_image(machine=0x14c, code=b"\x90\xc3", *, virtual_size=None, raw_size=None):
    raw = bytearray(0x400 + len(code))
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3c, 0x80)
    raw[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", raw, 0x84, machine, 1)
    struct.pack_into("<H", raw, 0x94, 0xf0)
    optional = 0x98
    magic = 0x10b if machine == 0x14c else 0x20b
    struct.pack_into("<H", raw, optional, magic)
    base = 0x400000 if machine == 0x14c else 0x140000000
    struct.pack_into("<I" if machine == 0x14c else "<Q", raw, optional + (28 if machine == 0x14c else 24), base)
    struct.pack_into("<IIII", raw, optional + 0xf0 + 8,
                     len(code) if virtual_size is None else virtual_size, 0x1000,
                     len(code) if raw_size is None else raw_size, 0x400)
    raw[0x400:] = code
    return bytes(raw), base + 0x1000


def snapshot(path, image_hash, addr, size, *, mutate=None):
    basis = determinism_basis.basis_hash_for("synthetic-target-v1")
    con = sqlite3.connect(path)
    try:
        # Deliberately no uniqueness/type constraints: the lane must enforce them.
        con.execute("CREATE TABLE binary(id, content_sha256, slug, md5, analyzer_version, processor_spec_hash, basis_hash)")
        con.execute("CREATE TABLE func(id, binary_id, addr, size, ranges)")
        con.execute("INSERT INTO binary VALUES(1,?,'fixture',NULL,'synthetic-target-v1','fixture-spec',?)", (image_hash, basis))
        con.execute("INSERT INTO func VALUES(7,1,?,?,1)", (addr, size))
        if mutate:
            mutate(con)
        con.commit()
    finally:
        con.close()
    return basis


def planned(tmp_path, *, machine=0x14c, code=b"\x90\xc3", mutate=None, raw=None, **options):
    objects = LocalDirStore(tmp_path / "cas")
    image, addr = pe_image(machine, code)
    if raw is not None:
        image = raw
    image_ref = objects.put(image)
    db = tmp_path / "snapshot.sqlite"
    basis = snapshot(db, image_ref.hex, addr, len(code), mutate=mutate)
    store_ref = objects.put(db.read_bytes())
    opts = {"binary_id": 1, "addr": addr, "image_ref": str(image_ref),
            "corpus_scope_sha256": "1" * 64, "generation_sha256": "2" * 64, "report_version": image_ref.hex,
            **options}
    specs = splitter.plan_tasks(target.KIND, store_ref, basis, 999, objects=objects, **opts)
    assert len(specs) == 1
    return objects, specs[0]


def changed_selection(spec, **changes):
    selection = {**spec.params["selection"], **changes}
    return dataclasses.replace(spec, params={**spec.params, "selection": selection,
        "selection_sha256": hashlib.sha256(canonical_json(selection)).hexdigest()})


def forbidden(*args, **kwargs):
    raise AssertionError("external decoder reached")


@pytest.mark.parametrize("machine", [0x14c, 0x8664])
def test_real_object_and_independent_exact_receipt_recompute(tmp_path, monkeypatch, machine):
    monkeypatch.setattr(mkobj, "_run_objdump", forbidden)
    objects, spec = planned(tmp_path, machine=machine)
    lane = target.MkobjTarget()
    result = lane.run(spec, objects, str(tmp_path / "producer"))
    assert set(result.outputs) == {"target", "receipt"}
    output = objects.get(result.outputs["target"])
    assert struct.unpack_from("<H", output)[0] == machine
    assert struct.unpack_from("<I", output, 4)[0] == 0  # deterministic timestamp
    assert struct.unpack_from("<H", output, 20 + 32)[0] == 0
    assert output[60:62] == b"\x90\xc3"
    receipt_bytes = objects.get(result.outputs["receipt"])
    receipt = json.loads(receipt_bytes)
    assert canonical_json(receipt) == receipt_bytes
    assert receipt["target_ref"] == result.outputs["target"]
    assert receipt["selection"]["func_id"] == 7
    assert receipt["implementation_basis"]["external_decoder"] is None
    assert "accepted" not in receipt
    assert lane.verify(spec, result, objects, str(tmp_path / "independent")).outcome == VerificationOutcome.VERIFIED
    assert objects.get(spec.inputs["image"]) == pe_image(machine)[0]


@pytest.mark.parametrize("code", [b"\xc7\xf8\0\0\0\0", b"\xe8\0\0\0\0", b"\xe9\0\0\0\0",
                                      b"\x70\0", b"\xeb\0", b"\xe2\0", b"\x0f\x1f\0"])
def test_reference_free_refuses_before_decoder(tmp_path, monkeypatch, code):
    monkeypatch.setattr(mkobj, "_run_objdump", forbidden)
    objects, spec = planned(tmp_path, code=code)
    with pytest.raises(Refused, match="mkobj_target_decoder_required"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_amd64_possible_rip_modrm_refuses(monkeypatch):
    monkeypatch.setattr(mkobj, "_run_objdump", forbidden)
    with pytest.raises(mkobj.MkobjRefusal, match="decoder_required"):
        mkobj.find_call_targets(b"\x48\x8b\x05\0\0\0\0", 0x8664, reference_free_only=True)


def test_legacy_default_still_uses_decoder_for_xbegin(monkeypatch):
    def seen(*args):
        raise RuntimeError("legacy decoder called")
    monkeypatch.setattr(mkobj, "_run_objdump", seen)
    with pytest.raises(RuntimeError, match="legacy decoder called"):
        mkobj.find_call_targets(b"\xc7\xf8\0\0\0\0", 0x14c)


@pytest.mark.parametrize("value", [1, "yes", None, []])
def test_reference_free_keyword_requires_boolean(value):
    with pytest.raises(mkobj.MkobjRefusal, match="invalid_reference_free_only"):
        mkobj.find_call_targets(b"\x90", 0x14c, reference_free_only=value)


@pytest.mark.parametrize("field,value", [("func_id", 8), ("size", 1), ("addr", 0x401001),
    ("binary_id", 2), ("image_sha256", "f" * 64), ("report_version", "e" * 64)])
def test_declared_selection_cannot_override_snapshot(tmp_path, field, value):
    objects, spec = planned(tmp_path)
    changed = changed_selection(spec, **{field: value})
    assert changed.task_id != spec.task_id
    with pytest.raises(Refused):
        target.MkobjTarget().run(changed, objects, str(tmp_path / "run"))


@pytest.mark.parametrize("field,value", [("binary_id", True), ("addr", "4198400"), ("func_id", 7.0),
                                        ("size", 0), ("size", -1), ("ranges", 2), ("addr", 1 << 63)])
def test_exact_integer_and_extent_validation(tmp_path, field, value):
    objects, spec = planned(tmp_path)
    with pytest.raises(Refused):
        target.MkobjTarget().run(changed_selection(spec, **{field: value}), objects, str(tmp_path / "run"))


@pytest.mark.parametrize("sql,reason", [
    ("DELETE FROM func", "selection_missing"),
    ("INSERT INTO func SELECT * FROM func", "selection_ambiguous"),
    ("INSERT INTO binary SELECT * FROM binary", "selection_ambiguous"),
    ("UPDATE func SET size=NULL", "extent_unsupported"),
    ("UPDATE func SET ranges=2", "extent_unsupported"),
    ("UPDATE func SET size=2.0", "extent_unsupported"),
    ("UPDATE func SET size='2'", "extent_unsupported"),
    ("UPDATE func SET ranges=NULL", "extent_unsupported"),
    ("UPDATE binary SET content_sha256=NULL", "image_mismatch"),
    ("UPDATE func SET size=65537", "input_limit_exceeded"),
    ("ALTER TABLE func RENAME TO old_func;", "snapshot_unsupported"),
])
def test_snapshot_membership_extent_and_schema_refusal(tmp_path, sql, reason):
    with pytest.raises(Refused, match="mkobj_target_" + reason):
        planned(tmp_path, mutate=lambda con: con.execute(sql))


@pytest.mark.parametrize("extra", [{"offset": 0}, {"machine": 0x14c}, {"size": 1},
                                    {"decoder": "objdump"}, {"target_ref": "sha256:" + "f" * 64}])
def test_planner_rejects_caller_output_and_mapping_authority(tmp_path, extra):
    with pytest.raises(Refused, match="invalid_spec"):
        planned(tmp_path, **extra)


@pytest.mark.parametrize("timeout", [True, 0, -1, 61, float("nan"), float("inf"), "1"])
def test_timeout_caps(tmp_path, timeout):
    with pytest.raises(Refused, match="invalid_spec"):
        planned(tmp_path, timeout_s=timeout)


@pytest.mark.parametrize("mutation,reason", [
    (lambda raw: raw.__setitem__(slice(0, 2), b"NO"), "format_unsupported"),
    (lambda raw: struct.pack_into("<H", raw, 0x84, 0x8664), "format_unsupported"),
    (lambda raw: struct.pack_into("<I", raw, 0x98 + 0xf0 + 8, 1), "mapping_unsupported"),
    (lambda raw: struct.pack_into("<I", raw, 0x98 + 0xf0 + 16, 1), "mapping_unsupported"),
])
def test_image_format_and_mapping_refusals(tmp_path, mutation, reason):
    raw = bytearray(pe_image()[0])
    mutation(raw)
    with pytest.raises(Refused, match=reason):
        planned(tmp_path, raw=bytes(raw))


def test_immutable_ref_planner_rederives_basis(tmp_path):
    objects, spec = planned(tmp_path)
    options = {key: spec.params["selection"][key] for key in
               ("binary_id", "addr", "image_ref", "corpus_scope_sha256", "generation_sha256", "report_version")}
    with pytest.raises(Refused, match="basis_mismatch"):
        splitter.plan_tasks(target.KIND, spec.inputs["store"], "f" * 64, 1, objects=objects, **options)


@pytest.mark.parametrize("field,value", [("budget", BudgetClass.MEDIUM), ("capabilities", ()),
                                         ("capabilities", ("mkobj-target-reference-free:any",))])
def test_scheduler_fields_outside_task_id_are_validated(tmp_path, field, value):
    objects, spec = planned(tmp_path)
    changed = dataclasses.replace(spec, **{field: value})
    assert changed.task_id == spec.task_id
    with pytest.raises(Refused, match="invalid_spec"):
        target.MkobjTarget().run(changed, objects, str(tmp_path / "run"))


@pytest.mark.parametrize("change", ["task", "basis", "missing", "extra", "object", "receipt", "duplicate", "corrupt"])
def test_proposal_actual_bytes_and_binding_are_both_checked(tmp_path, change):
    objects, spec = planned(tmp_path)
    lane = target.MkobjTarget()
    result = lane.run(spec, objects, str(tmp_path / "run"))
    outputs = dict(result.outputs)
    if change == "task":
        result = dataclasses.replace(result, task_id="f" * 64)
    elif change == "basis":
        result = dataclasses.replace(result, basis_hash="f" * 64)
    elif change == "missing":
        outputs.pop("target")
    elif change == "extra":
        outputs["other"] = outputs["target"]
    elif change == "object":
        outputs["target"] = objects.put(b"changed object")
    elif change == "corrupt":
        Path(objects.path_for(outputs["target"])).write_bytes(b"corrupt transport")
    elif change == "duplicate":
        outputs["receipt"] = objects.put(b'{"schema":"a","schema":"b"}')
    else:
        receipt = json.loads(objects.get(outputs["receipt"]))
        receipt["symbol"] = "caller_symbol"
        outputs["receipt"] = objects.put(canonical_json(receipt))
    result = dataclasses.replace(result, outputs=outputs)
    assert lane.verify(spec, result, objects, str(tmp_path / "verify")).outcome == VerificationOutcome.REFUTED


def test_missing_proposal_is_unverifiable(tmp_path):
    objects, spec = planned(tmp_path)
    lane = target.MkobjTarget()
    result = lane.run(spec, objects, str(tmp_path / "run"))
    Path(objects.path_for(result.outputs["target"])).unlink()
    assert lane.verify(spec, result, objects, str(tmp_path / "verify")).outcome == VerificationOutcome.UNVERIFIABLE


@pytest.mark.parametrize("name", ["write_object", "build_object", "_pc_relative_impossible"])
def test_monkeypatched_loaded_helper_cannot_inherit_identity(tmp_path, monkeypatch, name):
    objects, spec = planned(tmp_path)
    monkeypatch.setattr(mkobj, name, forbidden)
    with pytest.raises(Refused, match="loaded_source_mismatch"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_changed_machine_constants_refuse_existing_task(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    monkeypatch.setattr(mkobj, "MACHINE", {"coff-i386": 0x8664, "coff-x86-64": 0x14c})
    with pytest.raises(Refused, match="implementation_mismatch"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_source_is_loaded_module_relative_not_cwd(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))
    assert result.outputs["target"]


def test_nonlocal_adapter_without_bounded_read_is_unavailable(tmp_path):
    objects, spec = planned(tmp_path)
    class UnboundedAdapter:
        def get(self, ref):
            raise AssertionError("unbounded allocation")
    with pytest.raises(Refused, match="input_unavailable"):
        target.MkobjTarget().run(spec, UnboundedAdapter(), str(tmp_path / "run"))


def test_local_object_symlink_is_unavailable(tmp_path):
    objects, spec = planned(tmp_path)
    path = Path(objects.path_for(spec.inputs["image"]))
    external = tmp_path / "outside"
    external.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(Refused, match="input_unavailable"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_deadline_refuses_without_an_output_pair():
    with pytest.raises(Refused, match="deadline_exceeded"):
        target._tick(time.monotonic() - 1)


def test_source_edit_without_reimport_is_unavailable(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    replacement = tmp_path / "mkobj-edited.py"
    original = Path(mkobj.__file__).read_text()
    replacement.write_text(original.replace("return True\n", "return False\n", 1))
    monkeypatch.setattr(mkobj, "__file__", str(replacement))
    with pytest.raises(Refused, match="loaded_source_mismatch"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_source_unavailable_refuses(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    monkeypatch.setattr(mkobj, "__file__", str(tmp_path / "missing.py"))
    with pytest.raises(Refused, match="implementation_unavailable"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_task_cannot_self_assert_an_implementation(tmp_path):
    objects, spec = planned(tmp_path)
    manifest = {**spec.params["implementation_basis"], "external_decoder": "objdump"}
    manifest_hash = hashlib.sha256(canonical_json(manifest)).hexdigest()
    changed = dataclasses.replace(spec, params={**spec.params, "implementation_basis": manifest,
        "implementation_sha256": manifest_hash}, capabilities=("mkobj-target-reference-free:" + manifest_hash,))
    with pytest.raises(Refused, match="implementation_mismatch"):
        target.MkobjTarget().run(changed, objects, str(tmp_path / "run"))


def test_new_generation_changes_task_id(tmp_path):
    objects, spec = planned(tmp_path)
    changed = changed_selection(spec, generation_sha256="3" * 64)
    assert changed.task_id != spec.task_id
    result = target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))
    assert target.MkobjTarget().verify(changed, result, objects, str(tmp_path / "verify")).outcome == VerificationOutcome.REFUTED


def test_transport_declared_size_does_not_replace_actual_digest(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    path = Path(objects.path_for(spec.inputs["image"]))
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(Refused, match="input_integrity_failed"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_adapter_cannot_return_a_foreign_publication_reference(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    monkeypatch.setattr(objects, "put", lambda data: ObjectRef("sha256:" + "f" * 64))
    with pytest.raises(Refused, match="input_integrity_failed"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_size_route_cannot_bypass_input_cap(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    monkeypatch.setattr(objects, "size", lambda ref: target.SNAPSHOT_LIMIT + 1)
    with pytest.raises(Refused, match="input_limit_exceeded"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_recompute_refutes_self_consistent_foreign_output(tmp_path):
    objects, spec = planned(tmp_path)
    lane = target.MkobjTarget()
    result = lane.run(spec, objects, str(tmp_path / "run"))
    output = bytearray(objects.get(result.outputs["target"]))
    output[-1] ^= 1
    foreign = objects.put(bytes(output))
    receipt = json.loads(objects.get(result.outputs["receipt"]))
    receipt.update(target_ref=str(foreign), target_sha256=foreign.hex, target_size=len(output))
    forged = dataclasses.replace(result, outputs={"target": foreign, "receipt": objects.put(canonical_json(receipt))})
    verdict = lane.verify(spec, forged, objects, str(tmp_path / "verify"))
    assert verdict.outcome == VerificationOutcome.REFUTED
    assert set(verdict.evidence["mismatched"]) == {"target", "receipt"}


def test_missing_input_is_unverifiable_during_recompute(tmp_path):
    objects, spec = planned(tmp_path)
    lane = target.MkobjTarget()
    result = lane.run(spec, objects, str(tmp_path / "run"))
    Path(objects.path_for(spec.inputs["image"])).unlink()
    verdict = lane.verify(spec, result, objects, str(tmp_path / "verify"))
    assert verdict.outcome == VerificationOutcome.UNVERIFIABLE
    assert verdict.evidence["reason"] == "mkobj_target_input_unavailable"


def test_snapshot_view_replacement_refuses(tmp_path):
    def mutate(con):
        con.execute("ALTER TABLE func RENAME TO actual_func")
        con.execute("CREATE VIEW func AS SELECT * FROM actual_func")
    with pytest.raises(Refused, match="snapshot_unsupported"):
        planned(tmp_path, mutate=mutate)


def test_overlap_mapping_refuses(tmp_path):
    raw = bytearray(pe_image()[0])
    section = 0x98 + 0xf0
    raw[section + 40:section + 80] = raw[section:section + 40]
    struct.pack_into("<H", raw, 0x86, 2)
    with pytest.raises(Refused, match="mapping_unsupported"):
        planned(tmp_path, raw=bytes(raw))


def test_image_truncation_refuses(tmp_path):
    with pytest.raises(Refused, match="format_unsupported"):
        planned(tmp_path, raw=b"MZ")


def test_source_default_edit_without_reimport_refuses(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    replacement = tmp_path / "mkobj-default-edited.py"
    replacement.write_text(Path(mkobj.__file__).read_text().replace('symbol_prefix: str = "_"', 'symbol_prefix: str = "changed"'))
    monkeypatch.setattr(mkobj, "__file__", str(replacement))
    with pytest.raises(Refused, match="loaded_source_mismatch"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_changed_scratch_input_is_detected_after_writer(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    write = Path.write_bytes
    def change_after_output(path, data):
        size = write(path, data)
        if path.name == "target.obj":
            image = path.parent / "image.bin"
            altered = bytearray(image.read_bytes())
            altered[-1] ^= 1
            write(image, altered)
        return size
    monkeypatch.setattr(Path, "write_bytes", change_after_output)
    with pytest.raises(Refused, match="input_integrity_failed"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))
    assert objects.get(spec.inputs["image"]) == pe_image()[0]


def test_changed_constants_during_generation_refuse(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    write = Path.write_bytes
    def change_after_output(path, data):
        size = write(path, data)
        if path.name == "target.obj":
            monkeypatch.setattr(mkobj, "TEXT_CHARACTERISTICS", 0)
        return size
    monkeypatch.setattr(Path, "write_bytes", change_after_output)
    with pytest.raises(Refused, match="implementation_changed"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_sqlite_execution_failure_produces_no_pair(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("injected unavailable database")
    monkeypatch.setattr(sqlite3, "connect", unavailable)
    with pytest.raises(Refused, match="execution_unavailable"):
        target.MkobjTarget().run(spec, objects, str(tmp_path / "run"))


def test_storage_failure_is_unverifiable(tmp_path, monkeypatch):
    objects, spec = planned(tmp_path)
    lane = target.MkobjTarget()
    result = lane.run(spec, objects, str(tmp_path / "run"))
    def unavailable(*args):
        raise OSError("injected storage error")
    monkeypatch.setattr(objects, "size", unavailable)
    verdict = lane.verify(spec, result, objects, str(tmp_path / "verify"))
    assert verdict.outcome == VerificationOutcome.UNVERIFIABLE
    assert verdict.evidence["reason"] == "mkobj_target_proposal_unavailable"


def test_i386_address_width_overflow_refuses():
    image, _ = pe_image()
    with pytest.raises(Refused, match="extent_unsupported"):
        target._mapping(image, {"addr": (1 << 32) - 1, "size": 2})


def test_snapshot_membership_changes_receipt_identity(tmp_path):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    _, first = planned(first_dir)
    _, second = planned(second_dir, mutate=lambda con: con.execute("INSERT INTO func VALUES(8,1,4198402,1,1)"))
    assert first.basis_hash == second.basis_hash
    assert first.params["selection"]["store_ref"] != second.params["selection"]["store_ref"]
    assert first.task_id != second.task_id


@pytest.mark.parametrize("extra", [{"offset": 0}, {"accepted": True}, {"output_object": "caller"}])
def test_runtime_unknown_params_refuse(tmp_path, extra):
    objects, spec = planned(tmp_path)
    changed = dataclasses.replace(spec, params={**spec.params, **extra})
    with pytest.raises(Refused, match="invalid_spec"):
        target.MkobjTarget().run(changed, objects, str(tmp_path / "run"))


def test_cross_section_region_refuses(tmp_path):
    raw = bytearray(pe_image(code=b"\x90\xc3")[0])
    section = 0x98 + 0xf0
    struct.pack_into("<H", raw, 0x86, 2)
    struct.pack_into("<IIII", raw, section + 8, 1, 0x1000, 1, 0x400)
    struct.pack_into("<IIII", raw, section + 48, 1, 0x1001, 1, 0x401)
    with pytest.raises(Refused, match="mapping_unsupported"):
        planned(tmp_path, raw=bytes(raw))
