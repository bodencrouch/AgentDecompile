"""Thin N_FUN observation, admission and recorded-consumer regressions.

Authored for Task3.1; execution is deferred by the current mission constraints.
"""

import hashlib
import json
import sqlite3
import struct
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.coverage_evidence import bind_source
from agentdecompile_recovery.corpus.export_run_report import build
from agentdecompile_recovery.corpus.ingest_recovered import ingest
from agentdecompile_recovery.corpus.package_recovered import package_from_store
from agentdecompile_recovery.corpus.semantic_identity import (
    LOCAL_ONLY, STABS_ACCEPTED, STABS_CLAIM_SCOPE, evaluate_candidate, observe_target,
    recorded_export_name, recorded_name_witness, recorded_stabs_name,
)


def thin_image(*, bits=64, endian="<", names=None, mutation=None):
    base = 0x100000000 if bits == 64 else 0x1000
    cpu = 0x01000007 if bits == 64 else 7
    header = 32 if bits == 64 else 28
    segment_size = 72 if bits == 64 else 56
    segments = [(base, 0x800, 0, 0x600)]
    if mutation == "overlap":
        segments.append((base + 0x202, 0x10, 0x280, 0x10))
    names = [("Foo:F(0,1)", base + 0x200), ("Bar:F(0,1)", base + 0x220)] if names is None else names
    records = [("unit.cpp", 0x64, base), ("unit.o", 0x66, 0)]
    for name, va in names:
        records.extend([(name, 0x24, va), ("", 0x24, 3)])
    strings = bytearray(b"\0")
    blob = bytearray(0x600)
    command_size = len(segments) * segment_size + 24
    struct.pack_into(endian + "IiiIIII", blob, 0, 0xFEEDFACF if bits == 64 else 0xFEEDFACE,
                     cpu, 3, 2, len(segments) + 1, command_size, 0)
    off = header
    for vmaddr, vmsize, fileoff, filesize in segments:
        struct.pack_into(endian + "II", blob, off, 0x19 if bits == 64 else 1, segment_size)
        blob[off + 8:off + 14] = b"__TEXT"
        struct.pack_into(endian + ("QQQQ" if bits == 64 else "IIII"), blob, off + 24,
                         vmaddr, vmsize, fileoff, filesize)
        off += segment_size
    for index, (name, kind, va) in enumerate(records):
        strx = len(strings) if name else 0
        if name:
            strings.extend(name.encode("utf-8") + b"\0")
        struct.pack_into(endian + ("IBBHQ" if bits == 64 else "IBBHI"), blob,
                         0x300 + index * (16 if bits == 64 else 12), strx, kind, 0, 0, va)
    struct.pack_into(endian + "IIIIII", blob, off, 2, 24, 0x300, len(records), 0x400, len(strings))
    blob[0x400:0x400 + len(strings)] = strings
    blob[0x200:0x203] = blob[0x220:0x223] = b"\x33\xc0\xc3"
    if mutation == "short_command":
        struct.pack_into(endian + "I", blob, header + 4, 4)
    elif mutation == "command_tail":
        struct.pack_into(endian + "I", blob, 20, command_size + 8)
    elif mutation == "short_symbol_table":
        struct.pack_into(endian + "I", blob, off + 8, len(blob) - 4)
    elif mutation == "short_string_table":
        struct.pack_into(endian + "I", blob, off + 16, len(blob) - 4)
    elif mutation == "string_outside":
        struct.pack_into(endian + "I", blob, 0x300, len(strings))
    elif mutation == "unterminated":
        blob[0x400 + len(strings) - 1] = ord("X")
    elif mutation == "invalid_utf8":
        blob[0x401] = 0xff
    elif mutation == "table_overlap":
        struct.pack_into(endian + "I", blob, off + 16, 0x300)
    elif mutation == "header_overlap":
        struct.pack_into(endian + "I", blob, off + 8, header)
    elif mutation == "segment_extent":
        struct.pack_into(endian + ("Q" if bits == 64 else "I"), blob,
                         header + (48 if bits == 64 else 36), len(blob) + 1)
    elif mutation == "unknown_cpu":
        struct.pack_into(endian + "i", blob, 4, 99)
    elif mutation == "no_symtab":
        struct.pack_into(endian + "I", blob, off, 0xb)
    elif mutation == "object_file":
        struct.pack_into(endian + "I", blob, 12, 1)
    elif mutation == "ordinary_symbol":
        struct.pack_into("B", blob, 0x300 + 2 * (16 if bits == 64 else 12) + 4, 0x0f)
    elif mutation == "highvm":
        struct.pack_into(endian + "I", blob, header + (68 if bits == 64 else 52), 0x1)
    return bytes(blob), base


def prepared(tmp_path, **kwargs):
    blob, base = thin_image(**kwargs)
    raw = tmp_path / "raw"
    raw.mkdir()
    target = raw / "fixture"
    target.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    binary = {"id": 1, "slug": "fixture", "content_sha256": digest, "arch": "x86_64" if kwargs.get("bits", 64) == 64 else "x86",
              "bits": kwargs.get("bits", 64), "format": "macho"}
    candidate = {"name": "Foo", "addr": base + 0x200, "size": 3, "machine_code": "33c0c3",
                 "target_offset": 0x200, "target_sha256": digest, "binary_id": 1}
    return target, blob, base, binary, candidate


def admitted(target, binary, candidate):
    return {**candidate, **evaluate_candidate(candidate, binary, observe_target(binary, target.parent))}


@pytest.mark.parametrize("bits,endian", [(32, "<"), (32, ">"), (64, "<"), (64, ">")])
def test_n_fun_positive_binds_exact_snapshot_architecture_and_raw_record(tmp_path, bits, endian):
    target, blob, base, binary, candidate = prepared(tmp_path, bits=bits, endian=endian)
    row = admitted(target, binary, candidate)
    assert row["semantic_status"] == STABS_ACCEPTED
    assert recorded_stabs_name(row) == "Foo"
    assert recorded_export_name(row) is None
    evidence = json.loads(row["semantic_evidence"])
    witness = evidence["witness"]
    assert evidence["claimScope"] == STABS_CLAIM_SCOPE
    assert witness["binaryId"] == binary["id"] and witness["targetSha256"] == hashlib.sha256(blob).hexdigest()
    assert witness["architecture"] == evidence["target"]["architecture"]
    assert witness["architecture"]["cpuSubtype"] == 3
    assert witness["architecture"]["endianness"] == ("little" if endian == "<" else "big")
    assert witness["slice"] == {"offset": 0, "size": len(blob)}
    assert witness["rawType"] == 0x24 and witness["nlistIndex"] == 2
    assert witness["recordOffset"] == 0x300 + 2 * (16 if bits == 64 else 12)
    assert witness["declaration"] == "Foo:F(0,1)" and witness["va"] == base + 0x200
    assert witness["sourceFile"] == "unit.cpp" and witness["objectFile"] == "unit.o"


def test_semantic_observation_reads_target_once_and_never_reopens_for_mapping(tmp_path, monkeypatch):
    target, blob, _, binary, candidate = prepared(tmp_path)
    original = Path.read_bytes
    reads = []
    def read(path):
        if path == target:
            reads.append(path)
            assert len(reads) == 1
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    observation = observe_target(binary, target.parent)
    target.write_bytes(b"changed after capture")
    row = {**candidate, **evaluate_candidate(candidate, binary, observation)}
    assert row["semantic_status"] == STABS_ACCEPTED and len(reads) == 1
    assert observation["snapshot"] == blob


def test_foo_label_on_bar_refuses_while_independent_bar_survives(tmp_path):
    target, _, base, binary, candidate = prepared(tmp_path)
    candidate["addr"], candidate["target_offset"] = base + 0x220, 0x220
    wrong = admitted(target, binary, candidate)
    assert wrong["semantic_status"] == LOCAL_ONLY and wrong["semantic_reason"] == "target_stabs_address_mismatch"
    correct = admitted(target, binary, {**candidate, "name": "Bar", "logical_id": None})
    assert correct["semantic_status"] == STABS_ACCEPTED and recorded_stabs_name(correct) == "Bar"


def test_cpp_qualified_declaration_keeps_colons_in_name(tmp_path):
    target, _, _, binary, candidate = prepared(tmp_path, names=[("Widget::run(int):F(0,1)", 0x100000200)])
    candidate["name"] = "Widget::run(int)"
    assert recorded_stabs_name(admitted(target, binary, candidate)) == "Widget::run(int)"


@pytest.mark.parametrize("mutation,reason", [
    ("no_symtab", "target_stabs_symtab_missing"), ("object_file", "unsupported_macho_filetype"),
    ("ordinary_symbol", "target_stabs_name_missing"), ("unknown_cpu", "unsupported_macho_architecture"),
])
def test_unsupported_and_non_n_fun_roots_do_not_qualify(tmp_path, mutation, reason):
    target, _, _, binary, candidate = prepared(tmp_path, mutation=mutation)
    assert admitted(target, binary, candidate)["semantic_reason"] == reason


@pytest.mark.parametrize("names,reason", [
    ([("Foo:F1", 0x100000200), ("Foo:F1", 0x100000200)], "target_stabs_name_ambiguous"),
    ([("Foo:F1", 0x100000200), ("Foo:F1", 0x100000220)], "target_stabs_name_ambiguous"),
    ([("Foo:F1", 0x100000200), ("Bar:F1", 0x100000200)], "target_stabs_address_ambiguous"),
])
def test_repeated_and_conflicting_roots_are_not_deduplicated(tmp_path, names, reason):
    target, _, _, binary, candidate = prepared(tmp_path, names=names)
    assert admitted(target, binary, candidate)["semantic_reason"] == reason


@pytest.mark.parametrize("mutation", ["short_command", "command_tail", "short_symbol_table", "short_string_table",
                                      "string_outside", "unterminated", "invalid_utf8", "table_overlap", "header_overlap", "segment_extent"])
def test_malformed_whole_symbol_observation_fails_closed(tmp_path, mutation):
    target, _, _, binary, candidate = prepared(tmp_path, mutation=mutation)
    row = admitted(target, binary, candidate)
    assert row["semantic_status"] == LOCAL_ONLY
    assert row["semantic_reason"] == "malformed_macho_stabs_inventory"


@pytest.mark.parametrize("field,value,reason", [
    ("arch", None, "selected_macho_architecture_missing_or_unknown"),
    ("arch", "unknown", "selected_macho_architecture_missing_or_unknown"),
    ("arch", "arm64", "selected_macho_architecture_mismatch"),
    ("bits", 32, "selected_macho_width_mismatch"),
    ("format", "pe", "selected_macho_format_mismatch"),
    ("content_sha256", "a" * 64, "corpus_target_digest_mismatch"),
])
def test_selected_target_mismatch_refuses(tmp_path, field, value, reason):
    target, _, _, binary, candidate = prepared(tmp_path)
    binary[field] = value
    assert admitted(target, binary, candidate)["semantic_reason"] == reason


@pytest.mark.parametrize("mutation", [None, "overlap"])
def test_entire_region_must_have_one_exact_file_backed_mapping(tmp_path, mutation):
    target, _, _, binary, candidate = prepared(tmp_path, mutation=mutation)
    if mutation is None:
        candidate["target_offset"] += 1
    assert admitted(target, binary, candidate)["semantic_reason"] == "candidate_target_region_mismatch"


@pytest.mark.parametrize("offset", [0x5ff, 0x700])
def test_region_crossing_file_tail_and_virtual_only_address_are_refused(tmp_path, offset):
    target, _, base, binary, candidate = prepared(tmp_path, names=[("Foo:F1", 0x100000000 + offset)])
    candidate.update(addr=base + offset, target_offset=offset, machine_code="000000")
    assert admitted(target, binary, candidate)["semantic_reason"] == "candidate_target_region_mismatch"


@pytest.mark.parametrize("bits", [32, 64])
@pytest.mark.parametrize("va_offset,recorded_offset", [(0x100, 0x100), (0x420, 0x220), (0x420, 0x420)],
                         ids=["low-zero-filled", "shifted-file-backed", "unchecked-ordinary-offset"])
def test_highvm_layout_refuses_low_and_shifted_regions(tmp_path, bits, va_offset, recorded_offset):
    base = 0x100000000 if bits == 64 else 0x1000
    target, blob, base, binary, candidate = prepared(tmp_path, bits=bits, mutation="highvm",
                                                   names=[("Foo:F1", base + va_offset)])
    header = 32 if bits == 64 else 28
    _, vmsize, _, filesize = struct.unpack_from("<" + ("QQQQ" if bits == 64 else "IIII"), blob, header + 24)
    assert vmsize == 0x800 and filesize == 0x600 and vmsize > filesize
    # SG_HIGHVM zero-fills the low 0x200 bytes; VA+0x420 is backed at file+0x220.
    # Also cover the formerly unchecked ordinary offset for that shifted VA.
    candidate.update(addr=base + va_offset, target_offset=recorded_offset,
                     machine_code=blob[recorded_offset:recorded_offset + 3].hex())
    row = admitted(target, binary, candidate)
    assert row["semantic_status"] == LOCAL_ONLY
    assert row["semantic_reason"] == "unsupported_macho_highvm_layout"
    assert recorded_name_witness(row) is None


@pytest.mark.parametrize("field,value,reason", [
    ("target_sha256", "a" * 64, "candidate_target_digest_mismatch"),
    ("binary_id", 2, "candidate_target_binary_mismatch"),
    ("size", 0, "candidate_target_region_mismatch"),
    ("size", 0x401, "candidate_target_region_mismatch"),
    ("machine_code", "909090", "candidate_target_region_mismatch"),
])
def test_candidate_digest_bytes_and_positive_full_extent_are_required(tmp_path, field, value, reason):
    target, _, _, binary, candidate = prepared(tmp_path)
    candidate[field] = value
    if field == "size" and value > 0:
        candidate["machine_code"] = "00" * value
    assert admitted(target, binary, candidate)["semantic_reason"] == reason


@pytest.mark.parametrize("magic", [b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"])
def test_fat_images_never_select_first_slice(tmp_path, magic):
    target, blob, _, binary, candidate = prepared(tmp_path)
    fat = magic + b"\0" * 28 + blob
    target.write_bytes(fat)
    binary["content_sha256"] = candidate["target_sha256"] = hashlib.sha256(fat).hexdigest()
    assert admitted(target, binary, candidate)["semantic_reason"] == "unsupported_macho_fat_image"


@pytest.mark.parametrize("section,field,value", [
    ("target", "sha256", "a" * 64), ("target", "selectedArchitecture", "arm64"),
    ("witness", "architecture", {"name": "arm64"}), ("witness", "slice", {"offset": 1, "size": 0x600}),
    ("witness", "binaryId", 2), ("witness", "va", 0x100000220),
    ("witness", "name", "Bar"), ("witness", "declaration", "Bar:F1"),
    ("witness", "recordOffset", 0x301), ("witness", "stringOffset", 0x401),
])
def test_recorded_reader_refuses_incoherent_binding(tmp_path, section, field, value):
    target, _, _, binary, candidate = prepared(tmp_path)
    row = admitted(target, binary, candidate)
    evidence = json.loads(row["semantic_evidence"])
    evidence[section][field] = value
    row["semantic_evidence"] = json.dumps(evidence)
    assert recorded_name_witness(row) is None


def test_real_ingestion_status_and_consumers_use_recorded_stabs_scope(tmp_path):
    target, blob, base, binary, _ = prepared(tmp_path)
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""CREATE TABLE binary(id,repo_path,slug,content_sha256,arch,bits,format);
        CREATE TABLE identity(logical_id,binary_id,addr,method);
        CREATE TABLE logical_function(id,canon_key);
        CREATE TABLE func(binary_id,addr,name,canon_key);""")
    con.execute("INSERT INTO binary VALUES (?,?,?,?,?,?,?)", (1, "/fixture", "fixture", binary["content_sha256"], "x86_64", 64, "macho"))
    recovered, coverage = tmp_path / "recovered", tmp_path / "coverage"
    folder = recovered / "fixture"
    folder.mkdir(parents=True)
    coverage.mkdir()
    rows = []
    for name, offset in [("Foo", 0x220), ("Bar", 0x220)]:
        source = folder / f"{name}.c"
        source.write_text("int candidate(void) { return 0; }\n")
        rows.append(bind_source({"function": name, "byteExact": True, "size": 3, "originalBytes": blob[offset:offset + 3].hex(),
                                 "targetSnapshot": {"path": str(target), "size": len(blob), "sha256": binary["content_sha256"]},
                                 "targetRegion": {"address": base + offset, "offset": offset, "size": 3,
                                                  "sha256": hashlib.sha256(blob[offset:offset + 3]).hexdigest()}}, source.read_bytes()))
    (coverage / "fixture.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    summary = ingest(con, recovered_dir=recovered, coverage_dir=coverage, out_dir=tmp_path / "summary",
                     raw_dir=target.parent, program_to_repo={"fixture": "/fixture"})
    assert summary["recovered_without_identity"] == 1
    assert summary["recovered_named_target_stabs"] == 1 and summary["recovered_named_target_exports"] == 0
    stored = {row["name"]: dict(row) for row in con.execute("SELECT * FROM recovered_function")}
    assert stored["Foo"]["semantic_status"] == LOCAL_ONLY and stored["Bar"]["semantic_status"] == STABS_ACCEPTED
    # Withdrawal of an unrelated seed/family edge does not own this raw root.
    con.execute("INSERT INTO identity VALUES (?,?,?,?)", (99, 2, base + 0x200, "unrelated-seed-family"))
    unrelated = (99, 2, base + 0x200, "unrelated-seed-family")
    assert tuple(con.execute("SELECT logical_id,binary_id,addr,method FROM identity WHERE logical_id=99").fetchone()) == unrelated
    assert recorded_stabs_name(stored["Bar"]) == "Bar"
    con.execute("DELETE FROM identity WHERE logical_id=99 AND binary_id=2 AND addr=? AND method='unrelated-seed-family'", (base + 0x200,))
    assert con.execute("SELECT COUNT(*) FROM identity WHERE logical_id=99").fetchone()[0] == 0
    after_withdrawal = dict(con.execute("SELECT * FROM recovered_function WHERE name='Bar'").fetchone())
    assert recorded_stabs_name(after_withdrawal) == "Bar"
    target.unlink()
    report = build(con)
    bar = next(row for row in report["results"] if row["functionName"] == "Bar")
    identity = bar["postMatchPhase"]["pluginResults"][0]
    assert identity["status"] == "success" and STABS_CLAIM_SCOPE in identity["output"]
    assert "not rechecked" in identity["output"] and "STABS N_FUN" in identity["pluginName"]
    assert bar["success"] is False and bar["byte_exact"] is None
    package = package_from_store(con, tmp_path / "package")
    assert package["files"] == 2 and package["named_files"] == package["target_local_files"] == 1
    assert {path.name for path in (tmp_path / "package").rglob("*.c")} == {"Bar.c", "sub_100000220.c"}
    assert STABS_CLAIM_SCOPE in package["named_claim"] and "not rechecked" in package["named_claim"]
    # Source freshness remains an independent packaging gate.
    (folder / "Bar.c").write_text("int changed(void) { return 1; }\n")
    stale = package_from_store(con, tmp_path / "stale")
    assert stale["named_files"] == 0 and stale["source_binding_rejections"]
    con.close()
