"""P2 regressions authored UNRUN. Pure fixtures exercise parsing and refusals.

The explicit native fixture uses the real target producer and both real retained
verifiers. Enable only during a separately authorized execution; no mocked
checker, provider, or serialized VERIFIED claim can satisfy its positive case.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import struct
import time
from pathlib import Path

import pytest

from agentdecompile_grid.core import BudgetClass, ObjectRef, Refused, ResultStatus, TaskSpec, VerificationOutcome, canonical_json
from agentdecompile_grid.objects.local import LocalDirStore
from agentdecompile_recovery.grid_lanes import parity, parity_region as region, target


SYMBOL = "F_401000"
CODE = b"\x31\xc0\xc3"


def coff(code=CODE, *, timestamp=0, filename=None, function_first=False, long_name=False, align=False):
    """Independent minimal COFF fixture with controllable legal metadata."""
    symbols, strtab = [], bytearray(b"\0\0\0\0")
    if long_name or len(SYMBOL) > 8:
        name = struct.pack("<II", 0, 4)
        strtab.extend(SYMBOL.encode() + b"\0")
    else:
        name = SYMBOL.encode().ljust(8, b"\0")
    function = name + struct.pack("<IhHBB", 0, 1, 0x20, 2, 0)
    section = b".text\0\0\0" + struct.pack("<IhHBB", 0, 1, 0, 3, 1) + struct.pack("<IHH", len(code), 0, 0) + b"\0" * 10
    symbols.extend([function, section] if function_first else [section, function])
    if filename is not None:
        payload = filename.encode() + b"\0"
        slots = (len(payload) + 17) // 18
        symbols.append(b".file\0\0\0" + struct.pack("<IhHBB", 0, -2, 0, 103, slots) + payload.ljust(slots * 18, b"\0"))
    symbytes = b"".join(symbols)
    rawptr = 60
    gap = (-len(code)) % 4 if align else 0
    symptr = rawptr + len(code) + gap
    header = struct.pack("<HHIIIHH", 0x14C, 1, timestamp, symptr, len(symbytes) // 18, 0, 0)
    section_header = struct.pack("<8sIIIIIIHHI", b".text\0\0\0", 0, 0, len(code), rawptr, 0, 0, 0, 0, 0x60500020)
    struct.pack_into("<I", strtab, 0, len(strtab))
    return header + section_header + code + b"\0" * gap + symbytes + strtab


def inventory(data, size=3):
    return region.inventory_coff(data, SYMBOL, size)


@pytest.mark.parametrize("code", [CODE, b"\x33\xc0\x40\xc3", b"\x90\x31\xc0\x40\x48\xc3"])
def test_complete_grammar_and_actual_byte_coverage(code):
    inv, actual, tokens = inventory(coff(code), len(code))
    assert actual == code and sum(t["length"] for t in tokens) == len(code)
    assert sum(i["end"] - i["start"] for i in inv["intervals"]) == inv["object_size"]
    assert inv["unclassified_bytes"] == 0 and inv["relocations"] == inv["dependencies"] == []
    assert inv["region"]["sha256"] == ObjectRef.of_bytes(code).hex


def test_metadata_equal_region_and_private_file_name():
    left, a, _ = inventory(coff())
    right, b, _ = inventory(coff(timestamp=123, filename="private/path/worker.c", function_first=True, long_name=True, align=True))
    assert a == b and left["object_sha256"] != right["object_sha256"]
    assert "private/path" not in canonical_json(right).decode()
    assert {"timestamp", "optional_file_metadata", "symbol_order", "zero_alignment"} <= set(region.metadata_differences(left, right))


@pytest.mark.parametrize("code", [b"\xa1\x10\x20\x30\x40\xc3", b"\xff\xd0\xc3", b"\x8b\x00", b"\xff\xe0",
    b"\xc2\x04\x00", b"\x66\x31\xc0\xc3", b"\xc7\xf8\0\0\0\0", b"\xe9\0\0\0\0", b"\x48\x31\xc0\xc3\x90",
    b"\xb8\x10\x20\x30\x40\xc3", b"\x31\xc0\xc3\x90", b"\xc3", b"\x31\xc0", b"\x31\xc0\xc3\xc3"])
def test_reference_dependencies_prefixes_and_tail_refuse(code):
    with pytest.raises(region.RegionError, match="region_unsupported"):
        inventory(coff(code), len(code))


@pytest.mark.parametrize("offset,fmt,value", [
    (0, "H", 0x8664), (2, "H", 2), (16, "H", 1), (18, "H", 2),
    (28, "I", 1), (32, "I", 1), (36, "I", 4), (40, "I", 59),
    (44, "I", 60), (48, "I", 60), (52, "H", 1), (54, "H", 1),
    (56, "I", 0x61500020), (56, "I", 0x60501020), (56, "I", 0xE0500020),
    (8, "I", 60), (12, "I", 257), (12, "I", 2),
])
def test_header_extent_relocation_comdat_and_extra_section_refusals(offset, fmt, value):
    raw = bytearray(coff())
    struct.pack_into("<" + fmt, raw, offset, value)
    with pytest.raises(region.RegionError):
        inventory(bytes(raw))


@pytest.mark.parametrize("offset,value", [(63 + 17, 255), (63 + 18 + 8, 1), (63 + 18 + 14, 2),
                                         (63 + 36 + 16, 105), (63 + 36 + 17, 1)])
def test_auxiliary_overrun_association_weak_and_function_aux(offset, value):
    raw = bytearray(coff())
    raw[offset] = value
    with pytest.raises(region.RegionError):
        inventory(bytes(raw))


def test_string_suffix_unreferenced_trailer_and_hidden_payload():
    raw = bytearray(coff(long_name=True))
    struct.pack_into("<I", raw, 63 + 36 + 4, 5)
    with pytest.raises(region.RegionError, match="string_entry_start"):
        inventory(bytes(raw))
    for payload in (coff() + b"hidden", coff(align=True)[:63] + b"X" + coff(align=True)[64:]):
        with pytest.raises(region.RegionError):
            inventory(payload)


@pytest.mark.parametrize("name", [b".data\0\0\0", b".pdata\0\0", b".xdata\0\0", b".tls\0\0\0\0", b".drectve", b".debug\0\0"])
def test_no_ignored_section_name_can_hide_payload(name):
    raw = bytearray(coff())
    raw[20:28] = name
    with pytest.raises(region.RegionError, match="section"):
        inventory(bytes(raw))


def test_missing_extent_and_oversize_grammar_refuse():
    with pytest.raises(region.RegionError, match="region_association"):
        inventory(coff(b"\x31\xc0\x40\xc3"))
    with pytest.raises(region.RegionError):
        region.scan_region(b"\x90" * (64 << 10) + CODE)


def test_local_descriptor_limits_links_and_capped_store(tmp_path):
    store = LocalDirStore(tmp_path / "cas")
    ref = store.put(CODE)
    assert region._read(store, ref, 3, time.monotonic() + 5) == CODE
    with pytest.raises(region.RegionError, match="limit_exceeded"):
        region._read(store, ref, 2, time.monotonic() + 5)
    path = Path(store.path_for(ref))
    os.link(path, tmp_path / "hardlink")
    with pytest.raises(region.RegionError, match="transport_unsupported"):
        region._read(store, ref, 3, time.monotonic() + 5)
    (tmp_path / "hardlink").unlink()
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(region.RegionError, match="input_unavailable"):
        region._read(store, ref, 3, time.monotonic() + 5)
    capped = LocalDirStore(tmp_path / "capped", size_cap_bytes=1)
    with pytest.raises(region.RegionError, match="transport_unsupported"):
        region._store(capped)
    with pytest.raises(region.RegionError, match="transport_unsupported"):
        region._store(object())


def test_corrupt_existing_cas_put_and_deadline_reservations(tmp_path):
    store = LocalDirStore(tmp_path / "cas")
    ref = store.put(CODE)
    Path(store.path_for(ref)).write_bytes(b"bad")
    with pytest.raises(region.RegionError, match="recomputed_binding_invalid"):
        region._publish(store, CODE, 1024, time.monotonic() + 5)
    with pytest.raises(region.RegionError, match="deadline_exceeded"):
        region._tick(time.monotonic() + 119, 120)
    with pytest.raises(region.RegionError, match="deadline_exceeded"):
        region._tick(time.monotonic() + 59, 60)


@pytest.fixture
def native_case(tmp_path, request):
    executable = os.environ.get("ADGRID_P2_QUALIFIED_NATIVE")
    if not executable:
        pytest.skip("Requires separately authorized actual pinned native checker")
    # Reuse only the synthetic physical-target setup; neither verifier is mocked.
    from test_grid_target_binding import planned
    code = getattr(request, "param", CODE)
    objects, target_spec = planned(tmp_path, code=code)
    target_result = target.MkobjTarget().run(target_spec, objects, str(tmp_path / "target"))
    owned_executable = tmp_path / "qualified-native-copy"
    shutil.copy2(executable, owned_executable)
    checker = parity.register_native(owned_executable)
    assert checker.verifier_id == region.VERIFIER_ID
    candidate = objects.put(coff(code, timestamp=99, filename="fixture.c", function_first=True))
    parity_spec = TaskSpec("parity-check", 1, {"target": target_result.outputs["target"], "candidate": candidate},
                           {"verifier_id": checker.verifier_id, "symbol": SYMBOL}, target_spec.basis_hash,
                           capabilities=(checker.verifier_id,))
    scratch = tmp_path / "parity"
    scratch.mkdir()
    parity_result = parity.ParityCheck().run(parity_spec, objects, str(scratch))
    inputs = {"target_task": objects.put(canonical_json(target_spec.to_record())),
              "target_result": objects.put(canonical_json(target_result.to_record())),
              "parity_task": objects.put(canonical_json(parity_spec.to_record())),
              "parity_result": objects.put(canonical_json(parity_result.to_record())), **parity_spec.inputs}
    spec = region.plan_parity_regions(objects, None, target_spec.basis_hash, 1, inputs=inputs)[0]
    return objects, spec, tmp_path, target_spec, target_result, parity_spec, parity_result


def test_real_i386_leaf_equal_independent_verify_and_legacy_p1(native_case):
    objects, spec, tmp, _, _, p_spec, p_result = native_case
    lane = region.ParityRegionCheck()
    result = lane.run(spec, objects, str(tmp / "region-run"))
    verified = lane.verify(spec, result, objects, str(tmp / "region-verify"))
    assert verified.outcome == VerificationOutcome.VERIFIED
    assert verified.method == region.METHOD and verified.evidence["target_region_complete"] is True
    assert verified.evidence["implementation_source_closure"] == "not_evaluated"
    assert verified.evidence["implementation_runtime_closure"] == "not_evaluated"
    assert verified.evidence["prerequisites"]["target"]["method"] == "mkobj-target-reference-free-v1"
    assert verified.evidence["prerequisites"]["parity"]["method"] == "parity-binding-v1"
    receipt = json.loads(objects.get(result.outputs["receipt"]))
    assert receipt["objects"]["target"]["sha256"] != receipt["objects"]["candidate"]["sha256"]
    assert receipt["region_sha256"]["target"] == receipt["region_sha256"]["candidate"]
    assert receipt["byte_difference_count"] == 0 and receipt["coverage_bytes"] == 3
    (tmp / "old-p1").mkdir()
    old = parity.ParityCheck().verify(p_spec, p_result, objects, str(tmp / "old-p1"))
    assert old.outcome == VerificationOutcome.VERIFIED and old.evidence["target_region_complete"] is False


@pytest.mark.parametrize("field", ["target_task", "target_result", "parity_task", "parity_result"])
def test_forged_envelopes_and_lying_verified_json(native_case, field):
    objects, spec, tmp, *_ = native_case
    record = json.loads(objects.get(spec.inputs[field]))
    record["verification"] = {"outcome": "verified", "method": region.METHOD}
    changed = dataclasses.replace(spec, inputs={**spec.inputs, field: objects.put(canonical_json(record))})
    with pytest.raises(Refused, match="proposal_binding_invalid"):
        region.ParityRegionCheck().run(changed, objects, str(tmp / "forged"))


@pytest.mark.parametrize("mutation", ["basis", "swapped", "receipt", "raw", "region_digest"])
def test_foreign_basis_stale_receipt_raw_swap_and_target_digest(native_case, mutation):
    objects, spec, tmp, _, target_result, _, parity_result = native_case
    inputs = dict(spec.inputs)
    if mutation == "basis":
        spec = dataclasses.replace(spec, basis_hash="foreign")
    elif mutation == "swapped":
        inputs["target"], inputs["candidate"] = inputs["candidate"], inputs["target"]
    else:
        result = target_result if mutation == "region_digest" else parity_result
        role = "raw" if mutation == "raw" else "receipt"
        raw = objects.get(result.outputs[role])
        doc = json.loads(raw)
        if mutation == "region_digest":
            doc["region_sha256"] = "0" * 64
        elif mutation == "receipt":
            doc["sides"]["target"] = "0" * 64
        else:
            doc = {"left": {"sections": [{"kind": "SECTION_CODE", "match_percent": 100}]}}
        result = dataclasses.replace(result, outputs={**result.outputs, role: objects.put(canonical_json(doc))})
        inputs["target_result" if mutation == "region_digest" else "parity_result"] = objects.put(canonical_json(result.to_record()))
    spec = dataclasses.replace(spec, inputs=inputs)
    with pytest.raises(Refused):
        region.ParityRegionCheck().run(spec, objects, str(tmp / "bad"))


def test_forged_inventory_cannot_replace_independent_inventory(native_case):
    objects, spec, tmp, *_ = native_case
    lane = region.ParityRegionCheck()
    result = lane.run(spec, objects, str(tmp / "producer"))
    inventory_doc = json.loads(objects.get(result.outputs["candidate_inventory"]))
    inventory_doc["coverage_bytes"] = 0
    forged = dataclasses.replace(result, outputs={**result.outputs, "candidate_inventory": objects.put(canonical_json(inventory_doc))})
    checked = lane.verify(spec, forged, objects, str(tmp / "verifier"))
    assert checked.outcome == VerificationOutcome.REFUTED and checked.evidence["reason"] == "receipt_differs"


def with_candidate(native_case, candidate):
    objects, spec, tmp, _, _, p_spec, _ = native_case
    p_spec = dataclasses.replace(p_spec, inputs={**p_spec.inputs, "candidate": objects.put(candidate)})
    scratch = tmp / "alternate-parity"
    scratch.mkdir(exist_ok=True)
    p_result = parity.ParityCheck().run(p_spec, objects, str(scratch))
    inputs = {**spec.inputs, "candidate": p_spec.inputs["candidate"],
              "parity_task": objects.put(canonical_json(p_spec.to_record())),
              "parity_result": objects.put(canonical_json(p_result.to_record()))}
    return dataclasses.replace(spec, inputs=inputs)


def test_real_xor_encoding_difference_never_passes_bytes(native_case):
    objects, _, tmp, *_ = native_case
    spec = with_candidate(native_case, coff(b"\x33\xc0\xc3"))
    result = region.ParityRegionCheck().run(spec, objects, str(tmp / "alias"))
    receipt = json.loads(objects.get(result.outputs["receipt"]))
    assert receipt["grade"] == "mismatched" and receipt["byte_difference_count"] == 1
    verified = region.ParityRegionCheck().verify(spec, result, objects, str(tmp / "alias-verify"))
    assert verified.outcome == VerificationOutcome.VERIFIED and verified.evidence["target_region_complete"] is False


@pytest.mark.parametrize("native_case", [b"\x31\xc0\x40\xc3"], indirect=True)
def test_real_complete_same_extent_different_leaf(native_case):
    objects, _, tmp, *_ = native_case
    spec = with_candidate(native_case, coff(b"\x31\xc0\x48\xc3"))
    result = region.ParityRegionCheck().run(spec, objects, str(tmp / "different"))
    receipt = json.loads(objects.get(result.outputs["receipt"]))
    assert receipt["grade"] == "mismatched" and receipt["byte_difference_count"] == 1
    assert region.ParityRegionCheck().verify(spec, result, objects, str(tmp / "different-verify")).outcome == VerificationOutcome.VERIFIED


def test_recomputed_partial_report_is_checked_after_real_p1_verification(native_case, monkeypatch):
    objects, spec, tmp, *_ = native_case
    original = parity.ParityCheck.verify
    calls = []

    def corrupt_raw_after_real_verify(self, p_spec, p_result, store, scratch):
        verified = original(self, p_spec, p_result, store, scratch)
        assert verified.outcome == VerificationOutcome.VERIFIED
        calls.append(verified)
        refs = dict(verified.evidence["recomputed_outputs"])
        # Tamper only the returned raw evidence AFTER the actual checker and P1
        # verifier ran; never fabricate a positive provider or verifier outcome.
        raw = json.loads(store.get(refs["raw"]))
        raw["right"]["symbols"][1]["instructions"].pop()
        refs["raw"] = store.put(canonical_json(raw))
        return dataclasses.replace(verified, evidence={**verified.evidence, "recomputed_outputs": refs})

    monkeypatch.setattr(parity.ParityCheck, "verify", corrupt_raw_after_real_verify)
    with pytest.raises(Refused, match="report_incomplete"):
        region.ParityRegionCheck().run(spec, objects, str(tmp / "fresh-partial"))
    assert len(calls) == 1


def test_changed_actual_checker_bytes_are_unavailable_not_proposal_penalty(native_case):
    objects, spec, tmp, *_ = native_case
    lane = region.ParityRegionCheck()
    result = lane.run(spec, objects, str(tmp / "before-change"))
    checker = parity.PARITY_CHECKERS.get(region.VERIFIER_ID)
    # The fixture registers an owned copy, never the user's installed binary.
    assert checker.path.parent == tmp
    with checker.path.open("ab") as output:
        output.write(b"changed")
    checked = lane.verify(spec, result, objects, str(tmp / "after-change"))
    assert checked.outcome == VerificationOutcome.UNVERIFIABLE
    assert checked.evidence["reason"] == "checker_identity_mismatch"


@pytest.mark.parametrize("change", [{"budget": BudgetClass.SMALL}, {"capabilities": ()},
                                    {"params": {**region.PARAMS, "size": 3}}, {"kind_version": True}])
def test_budget_capability_and_caller_override_refused_before_io(change):
    ref = ObjectRef.of_bytes(b"unused")
    spec = TaskSpec("parity-region-check", 1, {name: ref for name in region.INPUTS}, dict(region.PARAMS), "basis",
                    capabilities=region.CAPABILITIES, budget=BudgetClass.MEDIUM)
    with pytest.raises(region.RegionError, match="task_profile"):
        region._spec(dataclasses.replace(spec, **change))


def test_envelope_typed_fields_and_task_id_do_not_trust_constructor_defaults():
    ref = ObjectRef.of_bytes(b"unused")
    spec = TaskSpec("parity-check", 1, {"target": ref, "candidate": ref}, {}, "basis")
    for changes in ({"task_id": "0" * 64}, {"kind_version": True}, {"kind_version": "1"}, {"capabilities": "native"}):
        with pytest.raises(region.RegionError):
            region._task({**spec.to_record(), **changes})
    with pytest.raises(region.RegionError):
        region._ref(str(ref) + "\n")
