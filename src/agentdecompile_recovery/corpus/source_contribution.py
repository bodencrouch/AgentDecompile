"""Bounded, observed C contribution to a PE reconstruction, never a linker receipt.

The causal root is the owned native clang cc1 invocation below. Only objects
returned by that invocation and observations returned by our writer are admitted.
Exported JSON is an audit record, not an import/authentication format. Trust is
process-local: after restart, retained artifacts remain diagnostic until a new
supported invocation. This deliberately fails closed on cache/store loss.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import tempfile
import time
import uuid
import weakref

from .verify_recovered_byteexact import file_region_offset
from .source_claims import is_real_c
from . import source_claims, verify_recovered_byteexact

BACKEND = "pe-coff-relocation-free-exact-placement-v1"
SCHEMA = "agentdecompile.source-contribution/v1"
ADAPTER = "native-clang-cc1-self-contained-c-v1"
# Repository-owned authority, not a caller's compiler name/version assertion.
# Fedora Project clang/clang-libs/llvm-libs 22.1.8-4.fc44, package payloads
# independently checked by rpm -V on 2026-09-27. The closure pin covers the
# compiler and all 14 resolved ELF loader/shared-library dependencies. Other
# builds need an explicitly reviewed supported profile; there is no auto-enroll.
SUPPORTED_COMPILER_SHA256 = "4ea85504401d9f5c05109d6cb05778b241aa8d56fde1da2e5bc7ba46cffd44f5"
SUPPORTED_TOOLCHAIN_CLOSURE_SHA256 = "b63b975150d1d36e0c3e3186eea2d5886aba7e77ba1ecdee7789671f310f21a8"
# Identity registration is independent of caller-controlled JSON or booleans.
_COMPILES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_IMAGES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def fingerprint(path) -> dict:
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {"path": str(path), "size": len(raw), "sha256": digest(raw)}


def current(record: dict) -> bool:
    try:
        return fingerprint(record["path"]) == record
    except (OSError, ValueError, KeyError, TypeError):
        return False


def pe_region(raw: bytes, address: int, size: int) -> dict:
    offset = file_region_offset(raw, address, size)
    if offset is None:
        raise ValueError("target_region_unmapped_or_ambiguous")
    pe = struct.unpack_from("<I", raw, 0x3c)[0]
    machine, count = struct.unpack_from("<HH", raw, pe + 4)
    optional_size = struct.unpack_from("<H", raw, pe + 20)[0]
    magic = struct.unpack_from("<H", raw, pe + 24)[0]
    if (machine, magic) not in ((0x14c, 0x10b), (0x8664, 0x20b)):
        raise ValueError("unsupported_pe_machine_pair")
    sections = pe + 24 + optional_size
    hits = []
    for index in range(count):
        start = sections + index * 40
        raw_size, raw_offset = struct.unpack_from("<II", raw, start + 16)
        if raw_size and (raw_offset < sections + count * 40 or raw_offset + raw_size > len(raw)):
            raise ValueError("invalid_target_raw_section_bounds")
        if max(offset, raw_offset) < min(offset + size, raw_offset + raw_size):
            hits.append((index, start))
    if len(hits) != 1:
        raise ValueError("target_raw_sections_overlap")
    index, start = hits[0]
    flags = struct.unpack_from("<I", raw, start + 36)[0]
    if not flags & 0x20 or not flags & 0x20000000:
        raise ValueError("target_region_not_executable_code")
    return {"address": address, "offset": offset, "size": size,
            "sha256": digest(raw[offset:offset + size]), "machine": machine,
            "sectionIndex": index + 1,
            "section": raw[start:start + 8].rstrip(b"\0").decode("ascii")}


def parse_coff(raw: bytes) -> dict:
    """Parse the complete supported standard COFF tables, not first-.text bytes.

    One external function starts at zero and owns the entire single code section.
    Empty data/bss and discardable, relocation-free CodeView compiler records are
    allowed. Any other data, relocation, alias, COMDAT, metadata or body refuses.
    Bigobj, archives, bitcode/LTCG and COFF executable optional headers refuse.
    """
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    require(20 <= len(raw) <= 64 * 1024 * 1024, "invalid_coff_size")
    machine, nsec, timestamp, symptr, nsym, opt, flags = struct.unpack_from("<HHIIIHH", raw)
    require(machine in (0x14c, 0x8664) and opt == 0 and flags == 0,
            "unsupported_coff_header_or_ltcg")
    require(1 <= nsec <= 64 and 20 + 40 * nsec <= len(raw), "invalid_section_table")
    header_end = 20 + 40 * nsec
    require(nsym > 0 and symptr >= header_end and symptr + nsym * 18 + 4 <= len(raw),
            "invalid_symbol_table")
    string_start = symptr + nsym * 18
    string_size = struct.unpack_from("<I", raw, string_start)[0]
    require(string_size >= 4 and string_start + string_size == len(raw), "invalid_string_table")
    spans = [(0, header_end), (symptr, len(raw))]
    def name(field):
        if field[:4] == b"\0" * 4:
            pos = struct.unpack_from("<I", field, 4)[0]
            require(4 <= pos < string_size, "invalid_symbol_name")
            end = raw.find(b"\0", string_start + pos, string_start + string_size)
            require(end >= 0, "unterminated_symbol_name")
            return raw[string_start + pos:end].decode("ascii")
        return field.rstrip(b"\0").decode("ascii")
    sections = []
    for index in range(nsec):
        sh = header_end - nsec * 40 + index * 40
        section_name = raw[sh:sh + 8].rstrip(b"\0").decode("ascii")
        require(not section_name.startswith("/"), "unsupported_long_section_name")
        physical, va, size, pointer, relocptr, lineptr, nrel, nline, chars = struct.unpack_from("<IIIIIIHHI", raw, sh + 8)
        require(not (physical or va or nline or lineptr), "unsupported_section_metadata")
        require(not (chars & (0x1000 | 0x1000000)), "unsupported_comdat_or_relocation_overflow")
        require(nrel == 0 and relocptr == 0, "unsupported_relocations")
        if size:
            require(pointer >= header_end and pointer + size <= symptr, "invalid_section_bounds")
            spans.append((pointer, pointer + size))
        require(not chars & 0x20 or section_name == ".text", "unsupported_split_code")
        if not chars & 0x20:
            require((section_name in (".data", ".bss") and size == 0)
                    or (section_name == ".debug$S" and chars & 0x2000000),
                    "unsupported_data_or_link_metadata")
        sections.append({"index": index + 1, "name": section_name, "size": size,
                         "offset": pointer, "characteristics": chars})
    spans.sort()
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "overlapping_coff_tables")
    require(all(not any(raw[a[1]:b[0]]) for a, b in zip(spans, spans[1:])), "unparsed_coff_data")
    code = [s for s in sections if s["characteristics"] & 0x20]
    require(len(code) == 1 and code[0]["size"] > 0, "ambiguous_or_missing_code")
    section = code[0]
    require(bool(section["characteristics"] & 0x20000000), "nonexecutable_code_section")
    functions = []
    section_symbols = set()
    index = 0
    while index < nsym:
        pos = symptr + index * 18
        symbol_name = name(raw[pos:pos + 8])
        value, secnum, typ, storage, aux = struct.unpack_from("<IhHBB", raw, pos + 8)
        require(index + aux < nsym, "truncated_aux_symbols")
        if storage == 3 and 1 <= secnum <= nsec and aux == 1 and typ == 0:
            sec = sections[secnum - 1]
            length, relocations, lines = struct.unpack_from("<IHH", raw, pos + 18)
            selection = raw[pos + 18 + 14]
            require(symbol_name == sec["name"] and value == 0 and length == sec["size"]
                    and not (relocations or lines or selection) and secnum not in section_symbols,
                    "invalid_section_aux_or_comdat")
            section_symbols.add(secnum)
        elif storage == 2 and secnum == section["index"] and typ == 0x20 and aux == 0:
            functions.append({"name": symbol_name, "value": value, "index": index})
        elif storage == 103 and secnum == -2 and typ == 0 and aux > 0:
            pass  # Filename auxiliary bytes, never code or link input.
        elif storage == 3 and secnum == -1 and symbol_name == "@feat.00" and aux == 0:
            require(value in (0, 1), "unsupported_feature_metadata")
        else:
            raise ValueError("unsupported_symbol_alias_external_or_body")
        index += 1 + aux
    require(len(functions) == 1 and functions[0]["value"] == 0,
            "ambiguous_function_extent")
    require(section_symbols == set(range(1, nsec + 1)), "missing_section_aux")
    data = raw[section["offset"]:section["offset"] + section["size"]]
    return {"machine": machine, "sections": sections, "symbol": functions[0],
            "section": section, "offset": section["offset"], "size": len(data),
            "sha256": digest(data), "relocations": [], "bytes": data}


@dataclass(frozen=True, eq=False)
class CompileObservation:
    """Opaque producer capability; constructing one yourself confers no trust."""
    record_json: str

    @property
    def record(self):
        return json.loads(self.record_json)


@dataclass(frozen=True, eq=False)
class ReconstructionObservation:
    record_json: str
    candidates: tuple[CompileObservation, ...]

    @property
    def record(self):
        return json.loads(self.record_json)


def _implementation():
    return fingerprint(__file__)


def _toolchain(compiler: Path) -> list[dict]:
    compiler = compiler.resolve(strict=True)
    if not re.fullmatch(r"clang(?:-\d+)?", compiler.name) or compiler.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("unsupported_compiler_wrapper_or_binary")
    if fingerprint(compiler)["sha256"] != SUPPORTED_COMPILER_SHA256:
        raise ValueError("unapproved_compiler_identity")
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    result = subprocess.run(["/usr/bin/ldd", str(compiler)], capture_output=True,
                            text=True, env=env, check=False, timeout=15)
    if result.returncode or "not found" in result.stdout:
        raise ValueError("unsupported_toolchain_dependency_closure")
    paths = re.findall(r"(?:=>\s+|^\s*)(/\S+)\s+\(", result.stdout, re.M)
    if not paths:
        raise ValueError("unsupported_toolchain_dependency_closure")
    closure = [fingerprint(p) for p in sorted({str(compiler), *paths})]
    if digest(canonical(sorted(item["sha256"] for item in closure))) != SUPPORTED_TOOLCHAIN_CLOSURE_SHA256:
        raise ValueError("unapproved_toolchain_dependency_closure")
    return closure


def _db_row(db, binary_id, address, size):
    if db is None:
        return None  # Explicit standalone fixture/unit scope; no database claim.
    with sqlite3.connect(f"file:{Path(db).resolve()}?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT addr,size FROM func WHERE binary_id=? AND addr=?",
                                  (binary_id, address)).fetchall()
    if rows != [(address, size)]:
        raise ValueError("selected_database_row_changed_or_ambiguous")
    return {"path": str(Path(db).resolve()), "binaryId": binary_id, "address": address, "size": size}


def compile_observation(*, source, target, address: int, size: int, workspace,
                        compiler="/usr/bin/clang", program="", name="", binary_id=None,
                        db=None) -> CompileObservation:
    """Fresh native cc1 invocation for a self-contained C TU, with no includes.

    No caller argv, shell, callback, precompiled object, environment, generated
    preamble or dependency-complete boolean enters this acceptance path. The
    empty preamble and fixed flags are deliberate first-backend limits.
    """
    source_path, target_path = Path(source).resolve(strict=True), Path(target).resolve(strict=True)
    source_raw, target_raw = source_path.read_bytes(), target_path.read_bytes()
    source_text = source_raw.decode("utf-8")
    # Reject preprocessing entirely, including digraph/trigraph/spliced forms.
    if (not is_real_c(source_text) or any(token in source_text for token in
            ("#", "%:", "??", "\\\n", "\\\r", "__attribute__", "__declspec"))):
        raise ValueError("unsupported_source_preprocessor_asm_or_attributes")
    region = pe_region(target_raw, address, size)
    selected_row = _db_row(db, binary_id, address, size)
    implementation = _implementation()
    implementation_dependencies = [fingerprint(module.__file__) for module in
                                   (source_claims, verify_recovered_byteexact)]
    toolchain = _toolchain(Path(compiler))
    executable = Path(compiler).resolve(strict=True)
    root = Path(workspace).resolve(); root.mkdir(parents=True, exist_ok=True)
    owned = Path(tempfile.mkdtemp(prefix="contribution-", dir=root))
    snapshot = owned / "unit.c"; snapshot.write_bytes(source_raw)
    obj = owned / "unit.obj"
    triple = {0x14c: "i686-pc-windows-msvc", 0x8664: "x86_64-pc-windows-msvc"}[region["machine"]]
    argv = [str(executable), "-cc1", "-triple", triple, "-emit-obj", "-O1", "-ffreestanding",
            "-fno-builtin", "-o", str(obj), "-x", "c", str(snapshot)]
    started = time.time()
    result = subprocess.run(argv, cwd=owned, env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                            capture_output=True, timeout=60, check=False)
    (owned / "compiler.stderr").write_bytes(result.stderr)
    if result.returncode != 0 or not obj.is_file():
        raise ValueError("compiler_failed:" + str(result.returncode))
    parsed = parse_coff(obj.read_bytes())
    if parsed["machine"] != region["machine"] or parsed["bytes"] != target_raw[region["offset"]:region["offset"] + size]:
        raise ValueError("compiler_object_not_raw_equal")
    record = {"schema": SCHEMA, "backend": BACKEND, "adapter": ADAPTER,
              "invocation": uuid.uuid4().hex, "evidenceState": "fresh", "started": started,
              "completed": time.time(), "implementation": implementation,
              "implementationDependencies": implementation_dependencies,
              "source": {"path": str(source_path), "size": len(source_raw), "sha256": digest(source_raw)},
              "target": {"path": str(target_path), "size": len(target_raw), "sha256": digest(target_raw)},
              "candidate": {"program": program, "name": name, "binary_id": binary_id,
                            "addr": address, "path": str(source_path), "source_sha256": digest(source_raw)},
              "selectedRow": selected_row, "region": region, "snapshot": fingerprint(snapshot),
              "preamble": "", "toolchain": toolchain, "argv": argv, "cwd": str(owned),
              "returncode": result.returncode, "object": fingerprint(obj),
              "coff": {key: value for key, value in parsed.items() if key != "bytes"}}
    if (source_path.read_bytes() != source_raw or target_path.read_bytes() != target_raw
            or snapshot.read_bytes() != source_raw or not all(current(dep) for dep in
               [implementation, *implementation_dependencies, *toolchain])):
        raise ValueError("inputs_changed_during_compilation")
    _db_row(db, binary_id, address, size)
    observation = CompileObservation(canonical(record).decode())
    # Publication happens last; an orphan object/audit JSON is never a capability.
    (owned / "compile-observation.json").write_bytes(canonical(record))
    _COMPILES[observation] = observation.record_json
    return observation


def validate_compile(observation) -> tuple[dict | None, bytes | None, str | None]:
    if not isinstance(observation, CompileObservation) or _COMPILES.get(observation) != observation.record_json:
        return None, None, "untrusted_imported_compile_observation"
    record = observation.record
    try:
        for key in ("implementation", "source", "target", "snapshot", "object"):
            if not current(record[key]):
                raise ValueError(key + "_changed")
        if not all(current(dep) for dep in record["implementationDependencies"]):
            raise ValueError("implementation_dependency_changed")
        if not all(current(dep) for dep in record["toolchain"]):
            raise ValueError("toolchain_changed")
        if record["source"]["sha256"] != record["snapshot"]["sha256"]:
            raise ValueError("input_snapshot_mismatch")
        row = record["selectedRow"]
        if row:
            _db_row(row["path"], row["binaryId"], row["address"], row["size"])
        parsed = parse_coff(Path(record["object"]["path"]).read_bytes())
        if {key: value for key, value in parsed.items() if key != "bytes"} != record["coff"]:
            raise ValueError("object_extraction_changed")
        region = pe_region(Path(record["target"]["path"]).read_bytes(), record["region"]["address"], record["region"]["size"])
        if region != record["region"] or parsed["sha256"] != region["sha256"] or parsed["size"] != region["size"]:
            raise ValueError("target_region_mismatch")
        return record, parsed["bytes"], None
    except (OSError, ValueError, KeyError, TypeError, struct.error, sqlite3.Error) as exc:
        return record, None, str(exc)


def empty_evaluation(reason="no_trusted_reconstruction") -> dict:
    return {"backend": BACKEND, "placedCompiledRegions": 0, "placedCompiledBytes": 0,
            "wholeFileByteIdentical": None, "compilerProducedWholeImage": False,
            "linkedSourceContributionVerified": False, "candidates": [], "reason": reason}


def final_writers(writes: list[dict], size: int) -> list[dict]:
    """Replay ordered writes and derive ownership, including later overwrites."""
    boundaries = {0, size}
    for write in writes:
        lo, length = write["offset"], write["size"]
        if type(lo) is not int or type(length) is not int or lo < 0 or length <= 0 or lo + length > size:
            raise ValueError("invalid_write_bounds")
        if write["origin"] not in ("compiled-object", "preserved-floor"):
            raise ValueError("unknown_write_origin")
        boundaries.update((lo, lo + length))
    points = sorted(boundaries)
    final = []
    for lo, hi in zip(points, points[1:]):
        owner = next((w for w in reversed(writes) if w["offset"] <= lo and w["offset"] + w["size"] >= hi), None)
        if owner is None:
            raise ValueError("incomplete_final_writers")
        record = {**owner, "offset": lo, "size": hi - lo}
        if owner["origin"] == "compiled-object":
            record["objectOffset"] += lo - owner["offset"]
        final.append(record)
    return final


def evaluate_reconstruction(observation, *, target_path=None, output_path=None, db=None, binary_id=None) -> dict:
    """Reopen object, current inputs, target and output; derive final-writer credit."""
    result = empty_evaluation()
    if not isinstance(observation, ReconstructionObservation) or _IMAGES.get(observation) != observation.record_json:
        return result
    record = observation.record
    try:
        if target_path is not None and Path(target_path).resolve() != Path(record["target"]["path"]):
            raise ValueError("required_target_mismatch")
        if output_path is not None and Path(output_path).resolve() != Path(record["output"]["path"]):
            raise ValueError("required_output_mismatch")
        if not current(record["target"]) or not current(record["implementation"]):
            raise ValueError("target_or_implementation_changed")
        target = Path(record["target"]["path"]).read_bytes()
        output = Path(record["output"]["path"]).read_bytes()
        if len(output) != len(target) or digest(canonical(record["plan"])) != record["planHash"]:
            raise ValueError("output_size_or_plan_changed")
        writes = final_writers(record["writes"], len(output))
        if writes != record["finalWriters"]:
            raise ValueError("final_writer_accounting_changed")
        cursor = 0
        for write in sorted(writes, key=lambda w: w["offset"]):
            if write["offset"] != cursor or write["size"] <= 0:
                raise ValueError("incomplete_or_overlapping_final_writers")
            cursor += write["size"]
        if cursor != len(output):
            raise ValueError("incomplete_final_writers")
        result["wholeFileByteIdentical"] = output == target
        result["outputSnapshotCurrent"] = digest(output) == record["output"]["sha256"]
        for observation_item in observation.candidates:
            item, data, error = validate_compile(observation_item)
            identity = observation_item.record["invocation"]
            selected = [w for w in writes if w.get("invocation") == identity and w["origin"] == "compiled-object"]
            credit = 0
            if error is None and db is not None:
                try:
                    expected_row = _db_row(db, binary_id, item["region"]["address"], item["region"]["size"])
                    if item["selectedRow"] != expected_row or item["candidate"]["binary_id"] != binary_id:
                        error = "required_database_candidate_identity_mismatch"
                except (OSError, ValueError, sqlite3.Error) as exc:
                    error = "required_database_binding_failed:" + str(exc)
            if error is None and len(selected) == 1:
                write = selected[0]; region = item["region"]
                if (write["offset"] != region["offset"] or write["size"] != region["size"]
                        or write["objectOffset"] != item["coff"]["offset"]
                        or output[write["offset"]:write["offset"] + write["size"]] != data):
                    error = "final_output_region_changed"
                else:
                    credit = len(data)
            elif error is None:
                error = "not_selected_final_writer"
            result["candidates"].append({"invocation": identity, "candidate": observation_item.record["candidate"],
                                         "contributedBytes": credit, "accepted": credit > 0, "semanticIdentityVerified": False,
                                         "reason": error or "observed_compiled_object_final_writer"})
        result["placedCompiledRegions"] = sum(row["accepted"] for row in result["candidates"])
        result["placedCompiledBytes"] = sum(row["contributedBytes"] for row in result["candidates"])
        result["linkedSourceContributionVerified"] = result["placedCompiledRegions"] > 0
        result["reason"] = "evaluated_current_regions_preserved_floor_reconstruction"
        result["scope"] = "anonymous-source-to-target-contribution; semantic identity unverified"
        return result
    except (OSError, ValueError, KeyError, TypeError, struct.error, sqlite3.Error) as exc:
        result["reason"] = str(exc)
        return result


def reconstruct(*, target, output, observations=(), discard=(), fallback=True, overwrite_with_floor=()) -> ReconstructionObservation:
    """Own every byte write; reserve holes before copying any preserved floor.

    Equal-range collisions choose the valid candidate with lexicographically
    smallest complete candidate identity, independent of arrival order. Partial
    overlaps reject only involved ranges. Discarded/invalid candidates fall back
    explicitly or refuse the entire incomplete image when fallback is disabled.
    """
    target_path = Path(target).resolve(strict=True)
    output_path = Path(output).resolve()
    if output_path == target_path:
        raise ValueError("output_must_not_replace_target")
    target_raw = target_path.read_bytes()
    target_record = fingerprint(target_path)
    inputs = tuple(dict.fromkeys(observations))
    if any(not isinstance(obs, CompileObservation) or _COMPILES.get(obs) != obs.record_json for obs in inputs):
        raise ValueError("untrusted_imported_compile_observation")
    groups = {}; plan = []
    for obs in inputs:
        rec, data, error = validate_compile(obs)
        region = obs.record["region"]
        if obs.record["target"] != target_record:
            error = "required_target_mismatch"
        if obs.record["invocation"] in discard:
            error = "intentionally_discarded"
        key = (region["offset"], region["size"])
        if key[0] < 0 or key[0] + key[1] > len(target_raw):
            raise ValueError("invalid_requested_hole")
        groups.setdefault(key, []).append((obs, data, error))
    ranges = sorted(groups)
    overlaps = {key for key in ranges for other in ranges if key != other
                and max(key[0], other[0]) < min(sum(key), sum(other))}
    selected = {}
    for key in ranges:
        entries = groups[key]
        valid = sorted((entry for entry in entries if entry[2] is None),
                       key=lambda entry: (canonical(entry[0].record["candidate"]), entry[0].record["invocation"]))
        winner = valid[0][0] if valid and key not in overlaps else None
        for obs, data, error in entries:
            reason = error or ("overlapping_requested_intervals" if key in overlaps else
                               "selected" if obs is winner else "candidate_collision")
            plan.append({"invocation": obs.record["invocation"], "offset": key[0], "size": key[1], "reason": reason})
            if obs is winner:
                selected[key] = (obs, data)
        if winner is None and not fallback:
            raise ValueError("unsatisfied_replacement_hole")
    # Partition into disjoint boundaries. Original bytes never initialize a
    # selected hole. Observed write records are appended after the actual write.
    boundaries = sorted({0, len(target_raw), *(point for key in ranges for point in (key[0], sum(key)))})
    image = bytearray(len(target_raw)); writes = []
    for lo, hi in zip(boundaries, boundaries[1:]):
        entry = selected.get((lo, hi - lo))
        if entry:
            obs, data = entry
            image[lo:hi] = data
            writes.append({"offset": lo, "size": hi - lo, "origin": "compiled-object",
                           "invocation": obs.record["invocation"], "objectOffset": obs.record["coff"]["offset"]})
        else:
            image[lo:hi] = target_raw[lo:hi]
            writes.append({"offset": lo, "size": hi - lo, "origin": "preserved-floor"})
    # An explicit fallback after placement is a later actual writer; the
    # evaluator replays this log and withdraws the overwritten contribution.
    for key, (obs, _data) in sorted(selected.items()):
        if obs.record["invocation"] in overwrite_with_floor:
            lo, size = key
            image[lo:lo + size] = target_raw[lo:lo + size]
            writes.append({"offset": lo, "size": size, "origin": "preserved-floor",
                           "reason": "fallback_after_compiled_write"})
    # Never overwrite source, object, snapshots or shared dependencies.
    protected = {Path(rec["path"]) for obs in inputs for rec in
                 [obs.record[key] for key in ("source", "object", "snapshot")] + obs.record["toolchain"]}
    if output_path in protected:
        raise ValueError("output_conflicts_with_input")
    with output_path.open("xb") as handle:
        handle.write(image)
    if output_path.read_bytes() != image or target_path.read_bytes() != target_raw:
        raise ValueError("output_or_target_changed_before_publication")
    plan.sort(key=lambda row: (row["offset"], row["size"], row["invocation"]))
    record = {"schema": SCHEMA, "backend": BACKEND, "implementation": _implementation(),
              "target": target_record, "output": fingerprint(output_path), "plan": plan,
              "planHash": digest(canonical(plan)), "writes": writes,
              "finalWriters": final_writers(writes, len(image)),
              "evidenceState": "observed-in-producer-process", "compilerProducedWholeImage": False}
    result = ReconstructionObservation(canonical(record).decode(), inputs)
    _IMAGES[result] = result.record_json
    checked = evaluate_reconstruction(result)
    if checked["wholeFileByteIdentical"] is not True:
        _IMAGES.pop(result, None)
        raise ValueError("reconstruction_observation_failed")
    output_path.with_name(output_path.name + ".contribution.json").write_bytes(canonical(record))
    return result
