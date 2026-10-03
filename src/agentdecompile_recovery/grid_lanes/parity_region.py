"""Complete local emitted-region predicate for the fixed i386 register-leaf policy.

All outputs are proposals. Current source/admission/runtime closure is outside
this predicate. There is no trust in serialized verification records and no
indirect checker/provider hook: both retained prerequisite verifiers run here.
"""
from __future__ import annotations

import hashlib
import math
import os
import platform
import re
import stat
import struct
import tempfile
import time
from pathlib import Path

from agentdecompile_grid.core import (
    BudgetClass, ObjectRef, ObjectStore, Refused, ResultStatus, TaskResult, TaskSpec,
    Verification, VerificationOutcome, canonical_json, digest, task_kind,
)
from agentdecompile_grid.objects.base import InvalidRef, validate_ref
from agentdecompile_grid.objects.local import LocalDirStore
from ._common import PlannableKind
from .objdiff_v380 import (
    ASSET_SHA256, POLICY, PROFILE, RAW_LIMIT, UPSTREAM_COMMIT, VERIFIER_ID,
    ReportError, load_json, parse_report,
)
from .parity import ParityCheck
from .target import MkobjTarget

METHOD = "parity-region-coff-i386-leaf-v1"
SCHEMA = "agentdecompile.parity-region.v1"
INPUTS = ("target_task", "target_result", "parity_task", "parity_result", "target", "candidate")
OUTPUTS = ("receipt", "target_inventory", "candidate_inventory")
CAPABILITIES = (PROFILE, VERIFIER_ID)
OBJECT_LIMIT = 64 << 20
ENVELOPE_LIMIT = 64 << 10
RECEIPT_LIMIT = 1 << 20
INVENTORY_LIMIT = 1 << 20
REGION_LIMIT = 64 << 10
CHUNK = 64 << 10
PARAMS = {"checker_profile": PROFILE, "comparison_policy": POLICY}


class RegionError(ValueError):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason + (":" + detail if detail else ""))
        self.reason, self.detail = reason, detail


def _need(condition, reason, detail=""):
    if not condition:
        raise RegionError(reason, detail)


def _tick(deadline, reserve=0):
    _need(deadline - time.monotonic() > reserve, "deadline_exceeded")


def _ref(value):
    try:
        _need(isinstance(value, str) and len(value) == 71, "proposal_binding_invalid", "ref_type")
        validate_ref(value)
        return ObjectRef(value)
    except (InvalidRef, ValueError, TypeError) as exc:
        raise RegionError("proposal_binding_invalid", "ref") from exc


def _store(objects):
    _need(type(objects) is LocalDirStore and objects.size_cap_bytes == 0
          and os.name == "posix" and platform.system() == "Linux"
          and platform.machine().lower() in ("x86_64", "amd64")
          and all(hasattr(os, key) for key in ("O_NOFOLLOW", "O_DIRECTORY"))
          and os.open in os.supports_dir_fd, "transport_unsupported")


def _read(objects, ref, limit, deadline, *, retain=True):
    """Authenticate the actual ordinary single-link file through directory FDs."""
    _tick(deadline)
    ref = _ref(ref)
    directory = None
    try:
        root = Path(objects.root).absolute()
        relative = Path(objects.path_for(ref)).absolute().relative_to(root)
        _need(bool(relative.parts) and ".." not in relative.parts, "transport_unsupported")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in relative.parts[:-1]:
            _tick(deadline)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb", buffering=0) as stream:
            before = os.fstat(stream.fileno())
            _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "transport_unsupported", "ordinary_file")
            _need(before.st_size <= limit, "limit_exceeded")
            blocks, size, hasher = [], 0, hashlib.sha256()
            while True:
                _tick(deadline)
                chunk = stream.read(min(CHUNK, limit + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                _need(size <= limit, "limit_exceeded")
                if retain:
                    blocks.append(chunk)
                hasher.update(chunk)
            after = os.fstat(stream.fileno())
            _need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_nlink)
                  == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink)
                  and size == before.st_size and hasher.hexdigest() == ref.hex, "execution_changed")
        _tick(deadline)
        return b"".join(blocks)
    except RegionError:
        raise
    except (OSError, ValueError) as exc:
        raise RegionError("input_unavailable") from exc
    finally:
        if directory is not None:
            os.close(directory)


def _json(data, limit, deadline):
    try:
        value = load_json(data, limit=limit, tick=lambda: _tick(deadline), allow_null=True)
        _need(type(value) is dict and canonical_json(value) == data, "proposal_binding_invalid", "canonical_json")
        return value
    except ReportError as exc:
        raise RegionError("proposal_binding_invalid", exc.detail) from exc


def _publish(objects, data, limit, deadline):
    _tick(deadline)
    _need(len(data) <= limit, "limit_exceeded")
    expected = ObjectRef.of_bytes(data)
    try:
        _need(objects.put(data) == expected, "recomputed_binding_invalid", "put_ref")
        _need(_read(objects, expected, limit, deadline) == data, "recomputed_binding_invalid", "put_bytes")
    except RegionError as exc:
        if exc.reason == "deadline_exceeded":
            raise
        raise RegionError("recomputed_binding_invalid", "publication") from exc
    except Exception as exc:
        raise RegionError("recomputed_binding_invalid", "publication") from exc
    _tick(deadline)
    return expected


def scan_region(code: bytes, tick=lambda: None) -> list[dict]:
    """Finite byte grammar, not a general disassembler or address heuristic."""
    _need(0 < len(code) <= REGION_LIMIT, "region_unsupported", "region_size")
    tokens, offset, zero = [], 0, False
    singles = {0x90: "nop", 0x40: "inc", 0x48: "dec", 0xC3: "ret"}
    while offset < len(code):
        tick()
        if code[offset:offset + 2] in (b"\x31\xc0", b"\x33\xc0"):
            length, operation, zero = 2, "xor", True
        else:
            operation = singles.get(code[offset])
            _need(operation is not None, "region_unsupported", "instruction")
            length = 1
        _need(operation != "ret" or offset == len(code) - 1, "region_unsupported", "return_extent")
        tokens.append({"offset": offset, "length": length, "encoding": code[offset:offset + length].hex(),
                       "operation": operation})
        offset += length
    _need(zero and tokens[-1]["operation"] == "ret", "region_unsupported", "leaf_grammar")
    return tokens


def inventory_coff(data: bytes, symbol: str, expected_size: int, tick=lambda: None) -> tuple[dict, bytes, list[dict]]:
    """Inventory every byte of the admitted standard COFF subset, without fixups."""
    malformed, unsupported = "object_malformed", "region_unsupported"
    _need(type(data) is bytes and len(data) <= OBJECT_LIMIT, "limit_exceeded")
    _need(type(symbol) is str and re.fullmatch(r"F_[0-9a-f]+", symbol) is not None
          and len(symbol) <= 4096 and type(expected_size) is int, "proposal_binding_invalid", "region_identity")

    def extent(start, count, width=1):
        tick()
        _need(0 <= start <= len(data) and 0 <= count <= (len(data) - start) // width, malformed, "extent")
        return data[start:start + count * width]

    _need(len(data) >= 20, malformed, "header")
    machine, sections, timestamp, symptr, slots, optional, characteristics = struct.unpack_from("<HHIIIHH", data)
    _need(machine == 0x14C, unsupported, "machine")
    extent(20, sections, 40)
    _need(optional == 0 and sections == 1 and characteristics in (0, 0x100), unsupported, "file_form")
    raw_name, physical, address, size, rawptr, relptr, lineptr, relcount, linecount, flags = struct.unpack_from("<8sIIIIIIHHI", data, 20)
    _need(raw_name == b".text\0\0\0" and physical == address == 0, unsupported, "section")
    extent(rawptr, size)
    # Inspect declared relocation/line extents before refusing a valid unsupported declaration.
    extent(relptr, relcount, 10)
    extent(lineptr, linecount, 6)
    _need(flags == 0x60500020 and relptr == relcount == lineptr == linecount == 0, unsupported, "section_dependencies")
    _need(0 < size <= REGION_LIMIT, unsupported, "region_size")
    _need(size == expected_size, unsupported, "region_association")
    _need(0 < slots <= 256, "limit_exceeded" if slots > 256 else malformed, "symbol_slots")
    _need(symptr > 0, malformed, "symbol_pointer")
    extent(symptr, slots, 18)
    strptr = symptr + slots * 18
    extent(strptr, 4)
    strsize = struct.unpack_from("<I", data, strptr)[0]
    _need(4 <= strsize <= 16 << 10, "limit_exceeded" if strsize > 16 << 10 else malformed, "string_size")
    strings_raw = extent(strptr, strsize)
    _need(strptr + strsize == len(data), malformed, "trailing_payload")
    entries, position, names = {}, 4, set()
    while position < strsize:
        tick()
        end = strings_raw.find(b"\0", position)
        _need(end != -1, malformed, "string_termination")
        value = strings_raw[position:end]
        _need(0 < len(value) <= 4096 and value.isascii(), malformed, "string_name")
        name = value.decode("ascii")
        _need(name not in names, malformed, "duplicate_string")
        names.add(name)
        entries[position] = {"offset": position, "size": len(value) + 1, "name": name, "references": []}
        position = end + 1

    intervals = []
    def interval(start, end, classification):
        payload = extent(start, end - start)
        intervals.append({"start": start, "end": end, "class": classification, "sha256": digest(payload)})

    def gap(start, end):
        _need(0 <= end - start <= 3 and (start == end or end % 4 == 0), malformed, "file_gap")
        if end > start:
            _need(not any(extent(start, end - start)), malformed, "nonzero_gap")
            interval(start, end, "zero_alignment")

    interval(0, 20, "file_header")
    interval(20, 60, "section_table")
    gap(60, rawptr)
    interval(rawptr, rawptr + size, "region")
    gap(rawptr + size, symptr)
    interval(symptr, strptr, "symbol_table")
    interval(strptr, len(data), "string_table")
    primaries, seen, slot, file_metadata = [], set(), 0, None
    while slot < slots:
        tick()
        start = symptr + slot * 18
        name_raw, value, section, typ, storage, aux_count = struct.unpack_from("<8sIhHBB", data, start)
        _need(slot + 1 + aux_count <= slots, malformed, "aux_count")
        long_offset = None
        if name_raw[:4] == b"\0" * 4:
            long_offset = struct.unpack_from("<I", name_raw, 4)[0]
            _need(long_offset in entries, malformed, "string_entry_start")
            name = entries[long_offset]["name"]
            entries[long_offset]["references"].append(slot)
        else:
            short, separator, padding = name_raw.partition(b"\0")
            _need(bool(short) and short.isascii() and not any(padding), malformed, "inline_name")
            name = short.decode("ascii")
        _need(name not in seen, malformed, "duplicate_symbol")
        seen.add(name)
        auxiliary = data[start + 18:start + (aux_count + 1) * 18]
        record = {"slot": slot, "end_slot": slot + 1 + aux_count, "name": name,
                  "name_field_hex": name_raw.hex(), "string_offset": long_offset,
                  "value": value, "section": section, "type": typ, "storage_class": storage, "aux_count": aux_count}
        if name == symbol:
            _need(value == 0 and section == 1 and typ == 0x20 and storage == 2 and aux_count == 0,
                  unsupported, "function_symbol")
            record.update({"class": "function", "auxiliary_hex": []})
        elif name == ".text":
            _need(long_offset is None and value == 0 and section == 1 and typ == 0 and storage == 3 and aux_count == 1,
                  unsupported, "section_symbol")
            expected_aux = struct.pack("<IHHIhBBh", size, 0, 0, 0, 0, 0, 0, 0)
            _need(auxiliary == expected_aux, unsupported, "section_auxiliary")
            record.update({"class": "section_definition", "auxiliary_hex": [auxiliary.hex()]})
        elif name == ".file":
            _need(long_offset is None and value == 0 and section == -2 and typ == 0 and storage == 103
                  and 1 <= aux_count <= 228, unsupported, "file_symbol")
            filename, terminator, fill = auxiliary.partition(b"\0")
            _need(bool(terminator) and 0 < len(filename) <= 4096 and all(32 <= b <= 126 for b in filename)
                  and not any(fill) and (len(filename) + 1 + 17) // 18 == aux_count, malformed, "file_auxiliary")
            file_metadata = {"length": len(filename), "sha256": digest(filename), "class": "file_metadata"}
            record.update({"class": "file", "filename": file_metadata})
        else:
            raise RegionError(unsupported, "extra_symbol")
        primaries.append(record)
        slot += 1 + aux_count
    _need(seen in ({symbol, ".text"}, {symbol, ".text", ".file"}), unsupported, "symbol_inventory")
    _need(all(entry["name"] == symbol and len(entry["references"]) == 1 for entry in entries.values()),
          malformed, "unreferenced_string")
    code = data[rawptr:rawptr + size]
    tokens = scan_region(code, tick)
    inventory = {
        "schema": "agentdecompile.parity-region-inventory.v1", "policy": POLICY,
        "object_ref": str(ObjectRef.of_bytes(data)), "object_sha256": digest(data), "object_size": len(data),
        "header": {"machine": machine, "sections": sections, "timestamp": timestamp, "symbol_pointer": symptr,
                   "symbol_slots": slots, "optional_header_size": optional, "characteristics": characteristics},
        "section": {"name": ".text", "physical_address": physical, "virtual_address": address, "size": size,
                    "raw_pointer": rawptr, "relocation_pointer": relptr, "relocation_count": relcount,
                    "line_pointer": lineptr, "line_count": linecount, "characteristics": flags},
        "symbols": primaries, "strings": list(entries.values()), "string_table": {"offset": strptr, "size": strsize},
        "intervals": intervals, "region": {"name": symbol, "section": ".text", "offset": 0, "file_offset": rawptr,
                                           "length": size, "sha256": digest(code)},
        "relocations": [], "line_numbers": [], "dependencies": [], "file_metadata": file_metadata,
        "coverage_bytes": len(data), "unclassified_bytes": 0,
    }
    tick()
    return inventory, code, tokens


def metadata_differences(left, right):
    """Finite classifications derived only from the fully admitted inventories."""
    checks = {
        "timestamp": (left["header"]["timestamp"], right["header"]["timestamp"]),
        "redundant_i386_characteristic": (left["header"]["characteristics"], right["header"]["characteristics"]),
        "file_offsets": ([left["section"]["raw_pointer"], left["header"]["symbol_pointer"], left["string_table"]["offset"]],
                         [right["section"]["raw_pointer"], right["header"]["symbol_pointer"], right["string_table"]["offset"]]),
        "zero_alignment": ([i for i in left["intervals"] if i["class"] == "zero_alignment"],
                           [i for i in right["intervals"] if i["class"] == "zero_alignment"]),
        "symbol_order": ([s["name"] for s in left["symbols"]], [s["name"] for s in right["symbols"]]),
        "function_name_representation": ([s["name_field_hex"] for s in left["symbols"] if s["class"] == "function"],
                                         [s["name_field_hex"] for s in right["symbols"] if s["class"] == "function"]),
        "string_table_layout": (left["strings"], right["strings"]),
        "optional_file_metadata": (left["file_metadata"], right["file_metadata"]),
    }
    return sorted(key for key, (a, b) in checks.items() if a != b)


def _task(record):
    fields = {"task_id", "kind", "kind_version", "inputs", "params", "basis_hash", "capabilities", "budget", "partition"}
    _need(set(record) == fields and all(type(record[k]) is str for k in ("task_id", "kind", "basis_hash", "budget", "partition"))
          and type(record["kind_version"]) is int and record["kind_version"] == 1
          and type(record["inputs"]) is dict and type(record["params"]) is dict
          and type(record["capabilities"]) is list and all(type(c) is str for c in record["capabilities"]),
          "proposal_binding_invalid", "task_envelope")
    for value in record["inputs"].values():
        _ref(value)
    try:
        spec = TaskSpec.from_record(record)
    except (KeyError, ValueError, TypeError) as exc:
        raise RegionError("proposal_binding_invalid", "task_envelope") from exc
    _need(spec.to_record() == record and spec.task_id == record["task_id"], "proposal_binding_invalid", "task_id")
    return spec


def _result(record, spec, outputs):
    fields = {"task_id", "status", "outputs", "producer_key", "basis_hash", "elapsed_s", "reason", "candidates", "metrics"}
    _need(set(record) == fields and all(type(record[k]) is str for k in ("task_id", "status", "producer_key", "basis_hash", "reason"))
          and type(record["outputs"]) is dict and set(record["outputs"]) == set(outputs)
          and type(record["elapsed_s"]) in (int, float) and 0 <= record["elapsed_s"] <= 600 and math.isfinite(record["elapsed_s"])
          and type(record["candidates"]) is list and all(type(c) is dict for c in record["candidates"])
          and type(record["metrics"]) is dict and record["reason"] == "" and record["status"] == "ok"
          and record["task_id"] == spec.task_id and record["basis_hash"] == spec.basis_hash,
          "proposal_binding_invalid", "result_envelope")
    result = TaskResult(record["task_id"], ResultStatus.OK, {k: _ref(v) for k, v in record["outputs"].items()},
                        record["producer_key"], record["basis_hash"], record["elapsed_s"],
                        record["reason"], record["candidates"], record["metrics"])
    _need(canonical_json(result.to_record()) == canonical_json(record), "proposal_binding_invalid", "result_encoding")
    return result


def _spec(spec):
    _need(type(spec) is TaskSpec and spec.kind == "parity-region-check" and type(spec.kind_version) is int
          and spec.kind_version == 1 and type(spec.inputs) is dict and set(spec.inputs) == set(INPUTS)
          and type(spec.params) is dict and spec.params == PARAMS and type(spec.basis_hash) is str
          and bool(spec.basis_hash) and spec.budget is BudgetClass.MEDIUM
          and isinstance(spec.capabilities, (tuple, list)) and tuple(spec.capabilities) == CAPABILITIES
          and type(spec.partition) is str, "region_unsupported", "task_profile")
    for value in spec.inputs.values():
        _ref(value)
    spec.task_id


def _prerequisite(verification, spec, result, method):
    _need(type(verification) is Verification and verification.task_id == spec.task_id
          and verification.result_ref == ObjectRef.of_value(result.to_record()) and verification.method == method,
          "prerequisite_refuted", "verification_binding")
    if verification.outcome == VerificationOutcome.REFUTED:
        raise RegionError("prerequisite_refuted", method)
    if verification.outcome != VerificationOutcome.VERIFIED:
        reason = verification.evidence.get("reason", "")
        if reason in ("checker_unavailable", "checker_identity_mismatch", "execution_changed", "deadline_exceeded", "limit_exceeded"):
            raise RegionError(reason, method)
        raise RegionError("prerequisite_unavailable", method)
    return {"task_id": spec.task_id, "result_ref": str(verification.result_ref), "method": method,
            "outcome": verification.outcome.value}


def _observe(spec, objects, scratch, deadline):
    """One complete operation; the caller owns its single 300-second deadline."""
    _spec(spec)
    _store(objects)
    retained = {}

    def read(ref, limit, *, retain=True):
        value = _read(objects, ref, limit, deadline, retain=retain)
        retained[str(ref)] = min(limit, retained.get(str(ref), limit))
        return value

    records = {key: _json(read(spec.inputs[key], ENVELOPE_LIMIT), ENVELOPE_LIMIT, deadline) for key in INPUTS[:4]}
    target_spec, parity_spec = _task(records["target_task"]), _task(records["parity_task"])
    _need(target_spec.kind == "mkobj-target" and parity_spec.kind == "parity-check"
          and target_spec.basis_hash == parity_spec.basis_hash == spec.basis_hash,
          "proposal_binding_invalid", "prerequisite_task_basis")
    target_result = _result(records["target_result"], target_spec, ("target", "receipt"))
    parity_result = _result(records["parity_result"], parity_spec, ("raw", "receipt"))
    _need(set(target_spec.inputs) == {"store", "image"} and set(parity_spec.inputs) == {"target", "candidate"}
          and target_result.outputs["target"] == spec.inputs["target"]
          and parity_spec.inputs == {key: spec.inputs[key] for key in ("target", "candidate")},
          "proposal_binding_invalid", "object_join")
    target_receipt = _json(read(target_result.outputs["receipt"], 32 << 10), 32 << 10, deadline)
    parity_receipt = _json(read(parity_result.outputs["receipt"], RECEIPT_LIMIT), RECEIPT_LIMIT, deadline)
    raw = read(parity_result.outputs["raw"], RAW_LIMIT)
    try:
        selection, mapping = target_receipt["selection"], target_receipt["mapping"]
        _need(type(selection) is dict and type(mapping) is dict and type(selection["addr"]) is int
              and selection["addr"] >= 0 and type(selection["size"]) is int and selection["size"] > 0,
              "proposal_binding_invalid", "selection")
        symbol = f'F_{selection["addr"]:x}'
        _need(target_receipt["target_ref"] == spec.inputs["target"] and target_receipt["symbol"] == symbol
              and target_receipt["task_id"] == target_spec.task_id and target_receipt["basis_hash"] == spec.basis_hash
              and target_receipt["selection_sha256"] == digest(canonical_json(selection))
              and selection == target_spec.params["selection"], "proposal_binding_invalid", "target_receipt")
        _need(mapping["machine"] == 0x14C and mapping["optional_magic"] == 0x10B and mapping["format"] == "coff-i386",
              "region_unsupported", "target_mapping")
        _need(parity_spec.params.get("verifier_id") == VERIFIER_ID and parity_spec.params.get("symbol") == symbol
              and parity_spec.budget is BudgetClass.SMALL and tuple(parity_spec.capabilities) == (VERIFIER_ID,),
              "region_unsupported", "native_profile")
        _need(parity_receipt["verifier_id"] == VERIFIER_ID and parity_receipt["verifier"] == "native"
              and parity_receipt["sides"] == {k: _ref(spec.inputs[k]).hex for k in ("target", "candidate")}
              and parity_receipt["symbol"] == symbol and parity_receipt["basis_hash"] == spec.basis_hash,
              "proposal_binding_invalid", "parity_receipt")
        grade = parity_receipt["grade"]
        _need(grade in ("matched", "mismatched") and parity_receipt["status"] == grade
              and type(parity_receipt["objdiffExit"]) is int and parity_receipt["objdiffExit"] == 0
              and type(parity_receipt["differences"]) is int and not parity_receipt.get("fallback")
              and ((grade == "matched" and parity_receipt["differences"] == 0)
                   or (grade == "mismatched" and parity_receipt["differences"] > 0)),
              "report_incomplete", "checker_observation")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, RegionError):
            raise
        raise RegionError("proposal_binding_invalid", "receipt_fields") from exc
    inventories, codes, tokens = {}, {}, {}
    for side in ("target", "candidate"):
        data = read(spec.inputs[side], OBJECT_LIMIT)
        inventories[side], codes[side], tokens[side] = inventory_coff(data, symbol, selection["size"], lambda: _tick(deadline))
    _need(inventories["target"]["region"]["sha256"] == target_receipt["region_sha256"]
          and inventories["target"]["object_sha256"] == target_receipt["target_sha256"]
          and inventories["target"]["object_size"] == target_receipt["target_size"],
          "proposal_binding_invalid", "target_bytes")
    proposed_report = parse_report(raw, symbol, tokens["target"], tokens["candidate"], checker_grade=grade,
                                   tick=lambda: _tick(deadline))
    # Every indirect input is independently bounded before entering the retained
    # verifier. The target verifier still rederives the physical DB/image join.
    read(target_spec.inputs["store"], 256 << 20, retain=False)
    read(target_spec.inputs["image"], 128 << 20, retain=False)
    _tick(deadline, 120)
    Path(scratch).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="region-target-", dir=scratch) as target_scratch:
        target_verification = MkobjTarget().verify(target_spec, target_result, objects, target_scratch)
    _tick(deadline)
    target_summary = _prerequisite(target_verification, target_spec, target_result, "mkobj-target-reference-free-v1")
    _tick(deadline, 60)
    with tempfile.TemporaryDirectory(prefix="region-parity-", dir=scratch) as parity_scratch:
        parity_verification = ParityCheck().verify(parity_spec, parity_result, objects, parity_scratch)
    _tick(deadline)
    parity_summary = _prerequisite(parity_verification, parity_spec, parity_result, "parity-binding-v1")
    evidence = parity_verification.evidence
    _need(evidence.get("proposal_outputs") == dict(parity_result.outputs)
          and type(evidence.get("recomputed_outputs")) is dict
          and set(evidence["recomputed_outputs"]) == {"raw", "receipt"}, "prerequisite_refuted", "recomputed_outputs")
    recomputed = {key: _ref(value) for key, value in evidence["recomputed_outputs"].items()}
    fresh_receipt = _json(read(recomputed["receipt"], RECEIPT_LIMIT), RECEIPT_LIMIT, deadline)
    _need(fresh_receipt == parity_receipt, "prerequisite_refuted", "fresh_receipt")
    fresh_report = parse_report(read(recomputed["raw"], RAW_LIMIT), symbol, tokens["target"], tokens["candidate"],
                               checker_grade=grade, tick=lambda: _tick(deadline))
    _need(proposed_report == fresh_report, "prerequisite_refuted", "raw_semantics")
    differences = sum(a != b for a, b in zip(codes["target"], codes["candidate"]))
    _need(differences > 0 or grade == "matched", "checker_disagrees")
    metadata = metadata_differences(inventories["target"], inventories["candidate"])
    for inventory in inventories.values():
        inventory["metadata_differences"] = metadata
    # Rehash every retained source/evidence object, including large indirect
    # inputs, after nested calls and before publishing any P2 output.
    for ref, limit in retained.items():
        _read(objects, ref, limit, deadline, retain=False)
    inventory_refs = {side: _publish(objects, canonical_json(inventories[side]), INVENTORY_LIMIT, deadline)
                      for side in ("target", "candidate")}
    receipt = {
        "schema": SCHEMA, "kind": spec.kind, "kind_version": 1, "task_id": spec.task_id, "basis_hash": spec.basis_hash,
        "checker_profile": PROFILE, "comparison_policy": POLICY, "verifier_id": VERIFIER_ID,
        "upstream_commit": UPSTREAM_COMMIT, "upstream_asset_sha256": ASSET_SHA256,
        "inputs": dict(spec.inputs), "prerequisites": {
            name: {key: value for key, value in summary.items() if key != "outcome"}
            for name, summary in (("target", target_summary), ("parity", parity_summary))},
        "target_receipt_ref": str(target_result.outputs["receipt"]),
        "proposed_parity_receipt_ref": str(parity_result.outputs["receipt"]), "proposed_parity_raw_ref": str(parity_result.outputs["raw"]),
        "objects": {side: {"sha256": inventories[side]["object_sha256"], "size": inventories[side]["object_size"]}
                    for side in ("target", "candidate")},
        "target_selection": {key: selection[key] for key in ("image_sha256", "report_version", "binary_id", "func_id", "addr", "size")},
        "selection_sha256": target_receipt["selection_sha256"], "inventory_refs": inventory_refs,
        "strict_report_sha256": digest(canonical_json(proposed_report)), "section": ".text", "symbol": symbol,
        "region_length": selection["size"], "region_sha256": {side: digest(code) for side, code in codes.items()},
        "grade": "mismatched" if differences else "matched", "checker_grade": grade, "byte_difference_count": differences,
        "instruction_count": {side: len(value) for side, value in tokens.items()}, "relocation_count": 0,
        "coverage_bytes": selection["size"], "unclassified_bytes": 0, "metadata_differences": metadata,
        "comparison_scope": "complete-emitted-reference-free-region", "reference_policy": POLICY,
        "target_producer_scope": "conservative-pc-relative-byte-screen", "runtime_admission": "not_evaluated",
        "source_binding": "not_evaluated", "linked_image_metadata": "not_evaluated",
    }
    outputs = {"receipt": _publish(objects, canonical_json(receipt), RECEIPT_LIMIT, deadline),
               "target_inventory": inventory_refs["target"], "candidate_inventory": inventory_refs["candidate"]}
    for ref in outputs.values():
        _json(_read(objects, ref, RECEIPT_LIMIT, deadline), RECEIPT_LIMIT, deadline)
    _tick(deadline)
    return outputs, receipt, {"prerequisites": {"target": target_summary, "parity": parity_summary},
                              "parity_raw_evidence": {"proposed": dict(parity_result.outputs), "recomputed": recomputed}}


@task_kind
class ParityRegionCheck(PlannableKind):
    name = "parity-region-check"
    version = 1
    budget = BudgetClass.MEDIUM
    capabilities = CAPABILITIES
    INPUTS = {name: "immutable prerequisite envelope" if name.endswith(("task", "result")) else "complete COFF object" for name in INPUTS}
    OUTPUTS = {name: "canonical authenticated emitted-region evidence" for name in OUTPUTS}
    INPUT_ROLES = {name: "restricted" for name in INPUTS}
    OUTPUT_ROLES = {name: "restricted" for name in OUTPUTS}

    @staticmethod
    def required_capabilities(spec):
        return CAPABILITIES

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        started = time.monotonic()
        try:
            outputs, _, _ = _observe(spec, objects, scratch, started + 300)
            return TaskResult(spec.task_id, ResultStatus.OK, outputs, "", spec.basis_hash, time.monotonic() - started)
        except (RegionError, ReportError) as exc:
            raise Refused("parity_region_" + exc.reason + (":" + exc.detail if exc.detail else "")) from exc
        except Exception as exc:
            raise Refused("parity_region_prerequisite_unavailable") from exc

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        deadline = time.monotonic() + 300
        outcome, evidence = VerificationOutcome.UNVERIFIABLE, {}
        try:
            _spec(spec)
            _store(objects)
            _need(type(result) is TaskResult and result.status is ResultStatus.OK
                  and type(result.elapsed_s) in (int, float) and type(result.outputs) is dict,
                  "proposal_binding_invalid", "result_types")
            _result(result.to_record(), spec, OUTPUTS)
            proposed = {name: _json(_read(objects, result.outputs[name], RECEIPT_LIMIT, deadline), RECEIPT_LIMIT, deadline)
                        for name in OUTPUTS}
            outputs, receipt, evidence = _observe(spec, objects, scratch, deadline)
            # All three documents must independently reproduce. Merely equal
            # booleans/digests in the proposed receipt carry no authority.
            equal = dict(result.outputs) == outputs
            for name in OUTPUTS:
                value = _json(_read(objects, result.outputs[name], RECEIPT_LIMIT, deadline), RECEIPT_LIMIT, deadline)
                _need(value == proposed[name], "execution_changed")
            _tick(deadline)
            outcome = VerificationOutcome.VERIFIED if equal else VerificationOutcome.REFUTED
            evidence.update({"reason": ("region_equal" if receipt["grade"] == "matched" else "region_differs") if equal else "receipt_differs",
                             "proposal_outputs": dict(result.outputs), "recomputed_outputs": outputs,
                             "grade": receipt["grade"], "target_region_complete": equal and receipt["grade"] == "matched",
                             "region_inventory_complete": True})
        except (RegionError, ReportError) as exc:
            contradiction = exc.reason in {"proposal_binding_invalid", "prerequisite_refuted", "object_malformed",
                                            "report_schema_invalid", "report_incomplete"}
            outcome = VerificationOutcome.REFUTED if contradiction else VerificationOutcome.UNVERIFIABLE
            evidence = {"reason": "proposal_binding_invalid" if contradiction and exc.reason not in {"proposal_binding_invalid", "prerequisite_refuted"}
                        else exc.reason, "detail": exc.detail, "target_region_complete": False}
        except Exception:
            evidence = {"reason": "prerequisite_unavailable", "target_region_complete": False}
        evidence.update({"checker_profile": PROFILE, "comparison_policy": POLICY, "verifier_id": VERIFIER_ID,
                         "implementation_source_closure": "not_evaluated", "implementation_runtime_closure": "not_evaluated",
                         "source_binding": "not_evaluated", "runtime_admission": "not_evaluated"})
        return Verification(task_id=result.task_id, result_ref=ObjectRef.of_value(result.to_record()),
                            outcome=outcome, verifier_key="", method=METHOD, evidence=evidence)

    @classmethod
    def describe(cls):
        return {"kind": cls.name, "version": cls.version, "budget": cls.budget.value, "capabilities": list(cls.capabilities),
                "inputs": cls.INPUTS, "outputs": cls.OUTPUTS, "input_roles": cls.INPUT_ROLES, "output_roles": cls.OUTPUT_ROLES,
                "params": PARAMS, "verify": METHOD, "status": "source_only",
                "implementation_source_closure": "not_evaluated", "implementation_runtime_closure": "not_evaluated"}


def plan_parity_regions(objects, snapshot, basis_hash, shard_size, **options):
    """One explicit immutable envelope set; no DB lookup or recorded VERIFIED shortcut."""
    try:
        _need(set(options) == {"inputs"} and type(options["inputs"]) is dict, "region_unsupported", "planner_inputs")
        spec = TaskSpec(kind=ParityRegionCheck.name, kind_version=1, inputs=dict(options["inputs"]), params=dict(PARAMS),
                        basis_hash=basis_hash, capabilities=CAPABILITIES, budget=BudgetClass.MEDIUM)
        _spec(spec)
        return [spec]
    except RegionError as exc:
        raise Refused("parity_region_" + exc.reason + ":" + exc.detail) from exc
