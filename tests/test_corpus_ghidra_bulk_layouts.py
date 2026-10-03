"""Ghidra type-layout alignment for compile-complete leftovers."""

from __future__ import annotations

import hashlib
import shutil

import pytest

from agentdecompile_recovery.corpus import asm_seed, ghidra_bulk as gb

pytestmark = pytest.mark.unit

# asm_extent.decode() independently re-decodes the span with the system
# ``objdump`` as a second decoder (see asm_extent.decoder_identity). Without
# objdump installed in this environment that independent-decode step cannot
# run at all, which is an environment gap rather than a product defect.
_NEEDS_OBJDUMP = shutil.which("objdump") is None


def test_trailing_underscore_matches_exported_field() -> None:
    gb._TYPE_FIELDS = {"strref", "internal", "string_count", "field_8"}
    body = "if (this->strref_ != p->strref_) return this_00->string_count + this_00->field_8;"
    fixed = gb.fix_trailing_underscore_fields(body)
    assert "strref_" not in fixed
    assert "this->strref" in fixed
    assert "string_count" in fixed
    assert "field_8" in fixed
    gb._TYPE_FIELDS = set()


def test_trailing_underscore_leaves_unknown_suffix() -> None:
    gb._TYPE_FIELDS = {"strref"}
    body = "this->invented_ = 1;"
    assert gb.fix_trailing_underscore_fields(body) == body
    gb._TYPE_FIELDS = set()


def test_vtable_star_call_becomes_ghidra_call() -> None:
    src = "(*this->vtable->OnBlackButtonPressed)();"
    assert "ghidra_call()" in gb.fix_star_calls(src)
    assert "OnBlackButtonPressed" not in gb.fix_star_calls(src)


def test_emit_type_retargets_void_star_internal() -> None:
    types = {
        "CExoLocString": "typedef struct CExoLocString { void * internal; int strref; } CExoLocString;",
        "CExoLocStringInternal": (
            "typedef struct CExoLocStringInternal { int string_count; unsigned int field_8; } "
            "CExoLocStringInternal;"
        ),
    }
    emitted = gb._emit_type("CExoLocString", types)
    assert "struct CExoLocStringInternal * internal" in emitted
    wanted = gb._expand_wanted({"CExoLocString"}, types)
    assert "CExoLocStringInternal" in wanted
    assert gb._emit_order(wanted, types)[0] == "CExoLocStringInternal"


def test_should_skip_llm_only_huge_or_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # KTD5/R35-R38: targeted AI now defaults off (CLI > env > dashboard >
    # compiled-default off); _llm_allowed() also checks it. This test is
    # about the huge-body/stopped/over-bar gates, so force AI on.
    from agentdecompile_recovery.targeted_ai import TargetedAIState
    monkeypatch.setattr(gb, "resolve_targeted_ai", lambda: TargetedAIState(True, "test"))
    monkeypatch.setattr(gb, "LLM_CLEANUP", True)
    monkeypatch.setattr(gb, "_LLM_STOPPED", False)
    monkeypatch.setattr(gb, "_CORPUS_TOTAL", 100)
    monkeypatch.setattr(gb, "_COMPILED_COUNT", 10)
    monkeypatch.setattr(gb, "COMPILE_COMPLETE", 0.95)
    assert gb.should_skip_llm(body="int f(void) { return 0; }\n") is False
    huge = "int f(void) {\n" + ("  x++;\n" * 8000) + "}\n"
    assert gb.should_skip_llm(body=huge) is True
    monkeypatch.setattr(gb, "_LLM_STOPPED", True)
    assert gb.should_skip_llm(body="int f(void) { return 0; }\n") is True


def test_queue_skips_tried_leftovers_not_seed_asm(tmp_path) -> None:
    blob = bytes.fromhex("90")
    seed = tmp_path / "Seed_00000001.c"
    seed.write_text(asm_seed.asm_banner("Seed_00000001", "00000001") + asm_seed.emit_naked_asm("Seed", blob))
    tried = tmp_path / "Tried_00000002.c"
    tried.write_text(
        asm_seed.asm_banner("Tried_00000002", "00000002")
        + " * source: ghidra_bulk.py asm-fallback\n"
        + asm_seed.emit_naked_asm("Tried", blob)
    )
    # Banner closer is before the alias line — stamp via helper for a real tried file.
    asm_seed.mark_c_replace_tried(tried)
    # Files already containing asm-fallback in the first 800 bytes count as tried.
    dirty = tmp_path / "Dirty_00000003.c"
    dirty.write_text(
        "/*\n * compile-only-asm\n * address: 0x00000003\n"
        " * source: ghidra_bulk.py asm-fallback\n */\n"
        + asm_seed.emit_naked_asm("Dirty", blob)
    )
    real = tmp_path / "Real_00000004.c"
    real.write_text("/* address: 0x00000004 */\nint Real(void) { return 0; }\n")

    assert gb.existing_kind(tmp_path, "Seed", "00000001") == "asm-seed"
    assert gb.existing_kind(tmp_path, "Tried", "00000002") == "asm-tried"
    assert gb.existing_kind(tmp_path, "Dirty", "00000003") == "asm-tried"
    assert gb.existing_kind(tmp_path, "Real", "00000004") == "real-c"
    assert gb.existing_kind(tmp_path, "Missing", "00000005") == "missing"

    assert gb.should_queue("asm-seed", "skip-existing")
    assert not gb.should_queue("asm-tried", "skip-existing")
    assert not gb.should_queue("real-c", "skip-existing")
    assert gb.should_queue("missing", "skip-existing")
    assert gb.should_queue("asm-tried", "force-c-replace")
    assert not gb.should_queue("real-c", "force-c-replace")
    assert gb.should_queue("real-c", "force")
    assert gb.resolve_queue_policy(skip_existing=True, force_c_replace=False) == "skip-existing"
    assert gb.resolve_queue_policy(skip_existing=True, force_c_replace=True) == "force-c-replace"
    assert gb.resolve_queue_policy(skip_existing=False, force_c_replace=True) == "force"


def test_mark_c_replace_tried_is_idempotent(tmp_path) -> None:
    dest = tmp_path / "Seed_00000001.c"
    dest.write_text(asm_seed.asm_banner("Seed_00000001", "00000001") + asm_seed.emit_naked_asm("Seed", b"\x90"))
    assert not asm_seed.is_c_replace_tried(dest)
    asm_seed.mark_c_replace_tried(dest)
    assert asm_seed.is_c_replace_tried(dest)
    first = dest.read_text()
    asm_seed.mark_c_replace_tried(dest)
    assert dest.read_text() == first


def test_asm_seed_is_default_substrate_not_real_c(tmp_path) -> None:
    blob = bytes.fromhex("e9ebfeffff")
    body = asm_seed.emit_naked_asm("Compare", blob)
    assert "__declspec(naked)" in body
    assert "_emit 0xE9" in body
    dest = tmp_path / "Compare_005ea020.c"
    dest.write_text(asm_seed.asm_banner("Compare_005ea020", "005ea020") + body)
    assert asm_seed.is_compile_only_asm(dest)
    real = tmp_path / "ok.c"
    real.write_text("/* compiled from Ghidra */\nint f(void) { return 0; }\n")
    assert not asm_seed.is_compile_only_asm(real)
    assert asm_seed.slice_image(b"\x00\x01\x02\x03", 1, 2) == b"\x01\x02"


def test_sibling_of_real_c_logical_id_is_skipped(tmp_path) -> None:
    from agentdecompile_recovery.corpus.ingest_recovered import ensure_recovered_schema
    from agentdecompile_recovery.corpus.store import connect

    con = connect(tmp_path / "store.sqlite")
    ensure_recovered_schema(con)
    con.execute("INSERT INTO binary(id, repo_path, slug) VALUES (1,'/a/win.exe','win')")
    con.execute(
        "INSERT INTO logical_function(id, canon_key, best_name) VALUES (9, 'C::F', 'C::F')"
    )
    con.execute(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence, method) "
        "VALUES (9, 1, 4198400, 1.0, 'name')"
    )
    source = tmp_path / "C_F.c"
    content = b"int C_F(void) { return 1; }\n"
    source.write_bytes(content)
    con.execute(
        "INSERT INTO recovered_function(program, name, real_c, logical_id, path, source_sha256) "
        "VALUES ('/a/win.exe', 'C::F', 1, 9, ?, ?)",
        (str(source), hashlib.sha256(content).hexdigest()),
    )
    con.commit()
    assert 9 in gb.logical_ids_with_real_c(con)
    assert gb.addr_to_logical(con, 1).get(4198400) == 9
    assert gb.skip_real_c_sibling(9, {9}, "asm-seed")
    assert gb.skip_real_c_sibling(9, {9}, "missing")
    assert not gb.skip_real_c_sibling(9, {9}, "real-c")
    assert not gb.skip_real_c_sibling(8, {9}, "asm-seed")
    con.close()


# Reused byte evidence, not a fresh game-image or recovery run.
_SPARSE_EXTENT_CASES = [('8b4104568d70ff8bc685c07c178b11578b7c240c8d1482393a74084883ea0485c07df45f3bc68971047d18eb038d49008b118b7482048d148289328b5104403bc27ced5ec20400', '# Remove  void __thiscall Remove(CExoArrayList * this, void * param_1)\n00445080: 8b 41 04                 MOV EAX,dword ptr [ECX + 0x4]\n00445083: 56                       PUSH ESI\n00445084: 8d 70 ff                 LEA ESI,[EAX + -0x1]\n00445087: 8b c6                    MOV EAX,ESI\n00445089: 85 c0                    TEST EAX,EAX\n0044508b: 7c 17                    JL LAB_004450a4  ; -> LAB_004450a4 (004450a4)\n0044508d: 8b 11                    MOV EDX,dword ptr [ECX]\n0044508f: 57                       PUSH EDI\n00445090: 8b 7c 24 0c              MOV EDI,dword ptr [ESP + param_1]\n00445094: 8d 14 82                 LEA EDX,[EDX + EAX*0x4]\nLAB_00445097:\n00445097: 39 3a                    CMP dword ptr [EDX],EDI\n00445099: 74 08                    JZ LAB_004450a3  ; -> LAB_004450a3 (004450a3)\n0044509b: 48                       DEC EAX\n0044509c: 83 ea 04                 SUB EDX,0x4\n0044509f: 85 c0                    TEST EAX,EAX\n004450a1: 7d f4                    JGE LAB_00445097  ; -> LAB_00445097 (00445097)\nLAB_004450a3:\n004450a3: 5f                       POP EDI\nLAB_004450a4:\n004450a4: 3b c6                    CMP EAX,ESI\n004450a6: 89 71 04                 MOV dword ptr [ECX + 0x4],ESI\n004450a9: 7d 18                    JGE LAB_004450c3  ; -> LAB_004450c3 (004450c3)\n004450ab: eb 03                    JMP LAB_004450b0  ; -> LAB_004450b0 (004450b0)\nLAB_004450b0:\n004450b0: 8b 11                    MOV EDX,dword ptr [ECX]\n004450b2: 8b 74 82 04              MOV ESI,dword ptr [EDX + EAX*0x4 + 0x4]\n004450b6: 8d 14 82                 LEA EDX,[EDX + EAX*0x4]\n004450b9: 89 32                    MOV dword ptr [EDX],ESI\n004450bb: 8b 51 04                 MOV EDX,dword ptr [ECX + 0x4]\n004450be: 40                       INC EAX\n004450bf: 3b c2                    CMP EAX,EDX\n004450c1: 7c ed                    JL LAB_004450b0  ; -> LAB_004450b0 (004450b0)\nLAB_004450c3:\n004450c3: 5e                       POP ESI\n004450c4: c2 04 00                 RET 0x4\n', 68, 71, 4477056), ('8b442404568bf1894608578b3ec1e00250e810a411008b4e04890683c40433c085c97e108b0e8b14878914818b4e04403bc17cf085ff740957e8929f110083c4045f5ec20400', '# Allocate  void __thiscall Allocate(CExoArrayList * this, int new_capacity)\n005e03c0: 8b 44 24 04              MOV EAX,dword ptr [ESP + new_capacity]\n005e03c4: 56                       PUSH ESI\n005e03c5: 8b f1                    MOV ESI,ECX\n005e03c7: 89 46 08                 MOV dword ptr [ESI + 0x8],EAX\n005e03ca: 57                       PUSH EDI\n005e03cb: 8b 3e                    MOV EDI,dword ptr [ESI]\n005e03cd: c1 e0 02                 SHL EAX,0x2\n005e03d0: 50                       PUSH EAX\n005e03d1: e8 10 a4 11 00           CALL operator_new  ; -> operator_new (006fa7e6)\n005e03d6: 8b 4e 04                 MOV ECX,dword ptr [ESI + 0x4]\n005e03d9: 89 06                    MOV dword ptr [ESI],EAX\n005e03db: 83 c4 04                 ADD ESP,0x4\n005e03de: 33 c0                    XOR i,i\n005e03e0: 85 c9                    TEST ECX,ECX\n005e03e2: 7e 10                    JLE LAB_005e03f4  ; -> LAB_005e03f4 (005e03f4)\nLAB_005e03e4:\n005e03e4: 8b 0e                    MOV ECX,dword ptr [ESI]\n005e03e6: 8b 14 87                 MOV EDX,dword ptr [EDI + EAX*0x4]\n005e03e9: 89 14 81                 MOV dword ptr [ECX + EAX*0x4],EDX\n005e03ec: 8b 4e 04                 MOV ECX,dword ptr [ESI + 0x4]\n005e03ef: 40                       INC EAX\n005e03f0: 3b c1                    CMP EAX,ECX\n005e03f2: 7c f0                    JL LAB_005e03e4  ; -> LAB_005e03e4 (005e03e4)\nLAB_005e03f4:\n005e03f4: 85 ff                    TEST EDI,EDI\n005e03f6: 74 09                    JZ LAB_005e0401  ; -> LAB_005e0401 (005e0401)\n005e03f8: 57                       PUSH EDI\n005e03f9: e8 92 9f 11 00           CALL _free  ; -> _free (006fa390)\nLAB_005e0401:\n005e0401: 5f                       POP EDI\n005e0402: 5e                       POP ESI\n005e0403: c2 04 00                 RET 0x4\n', 67, 70, 6161344)]


def _extent_pe(blob, address):
    import struct
    image = bytearray(0x200 + len(blob))
    image[:2] = b'MZ'; struct.pack_into('<I', image, 0x3c, 0x80)
    image[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', image, 0x84, 0x14c, 1)
    struct.pack_into('<H', image, 0x94, 0xe0)
    struct.pack_into('<H', image, 0x98, 0x10b)
    struct.pack_into('<I', image, 0x98+28, 0x400000)
    section = 0x178; image[section:section+8] = b'.text\0\0\0'
    struct.pack_into('<IIII', image, section+8, len(blob), address-0x400000, len(blob), 0x200)
    struct.pack_into('<I', image, section+36, 0x60000020)
    image[0x200:] = blob
    return bytes(image)


@pytest.mark.skipif(_NEEDS_OBJDUMP, reason="requires the objdump binary for asm_extent's independent decode; not installed in this environment")
@pytest.mark.parametrize('hex_bytes,assembly,count,extent,address', _SPARSE_EXTENT_CASES)
def test_sparse_original_extent_preserves_terminal_ret(tmp_path, monkeypatch, hex_bytes, assembly, count, extent, address):
    from agentdecompile_recovery.corpus import asm_extent
    blob = bytes.fromhex(hex_bytes); image = _extent_pe(blob, address)
    proof = asm_extent.qualify(image, address, 0x200, count, assembly, hashlib.sha256(image).hexdigest())
    assert proof['size'] == extent and proof['coveredBytes'] == count
    assert len(proof['uncoveredOffsets']) == 3 and blob[-3:] == b'\xc2\x04\x00'
    key = f'{address:08x}'
    monkeypatch.setattr(gb, '_RAW_IMAGE', image)
    monkeypatch.setattr(gb, '_ASM_IMAGE_SHA256', hashlib.sha256(image).hexdigest())
    monkeypatch.setattr(gb, '_ASM_ROWS', {key: (0x200, count, assembly)})
    monkeypatch.setattr(gb, '_ASM_EXTENTS', {})
    monkeypatch.setattr(gb, '_ASM_UNAVAILABLE', {})
    monkeypatch.setattr(gb, '_FUNC_FILE', {})
    assert gb.qualified_asm_blob(key) == blob
    monkeypatch.setattr(asm_extent, 'decode', lambda *a: pytest.fail('Exact in-memory extent should reuse decoder observation'))
    assert gb.qualified_asm_blob(key) == blob
    dest = tmp_path / 'sources'; dest.mkdir()
    assert gb.seed_asm_corpus([{'entry_hex': key, 'name': 'Leaf'}], dest) == 1
    text = next(dest.glob('*.c')).read_text()
    assert text.count('_emit') == extent and '_emit 0xC2' in text
    bodies = []
    monkeypatch.setattr(gb, 'ctx_text', lambda: '')
    monkeypatch.setattr(gb, '_compile_text', lambda src, obj, name, header, body: (bodies.append(body) or True, 'fixture-only'))
    assert gb.try_asm_fallback(dest/'fallback.c', dest/'fallback.obj', 'Leaf', key)[0]
    assert len(bodies) == 1 and bodies[0].count('_emit') == extent


@pytest.mark.parametrize('change', ['no-asm', 'wrong-image', 'wrong-offset', 'wrong-byte', 'truncated', 'mid-branch', 'indirect'])
def test_unqualified_extent_never_writes_or_compiles(tmp_path, monkeypatch, change):
    from agentdecompile_recovery.corpus import asm_extent
    address = 0x401000; blob = b'\x90\xc3'
    assembly = '00401000: 90  nop\n00401001: c3  ret'
    count = 2; offset = 0x200
    if change == 'no-asm': assembly = None
    if change == 'wrong-offset': offset += 1
    if change == 'wrong-byte': assembly = assembly.replace('90 ', '91 ')
    if change == 'truncated': blob = b'\x90'; assembly = '00401000: 90  nop'; count = 1
    if change == 'mid-branch':
        blob = b'\xeb\x01\xb8\x00\x00\x00\x00\xc3'; count = 8
        assembly = '00401000: eb 01  jmp\n00401002: b8 00 00 00 00  mov\n00401007: c3  ret'
    if change == 'indirect':
        blob = b'\xff\xe0'; count = 2; assembly = '00401000: ff e0  jmp eax'
    image = _extent_pe(blob, address); key = f'{address:08x}'
    monkeypatch.setattr(gb, '_RAW_IMAGE', image)
    monkeypatch.setattr(gb, '_ASM_IMAGE_SHA256', '0'*64 if change == 'wrong-image' else hashlib.sha256(image).hexdigest())
    monkeypatch.setattr(gb, '_ASM_ROWS', {key: (offset, count, assembly)})
    monkeypatch.setattr(gb, '_ASM_EXTENTS', {})
    monkeypatch.setattr(gb, '_ASM_UNAVAILABLE', {})
    monkeypatch.setattr(gb, '_compile_text', lambda *a: pytest.fail('Unqualified extent reached compiler'))
    dest = tmp_path / 'sources'; dest.mkdir()
    sentinel = dest / 'authored.c'; sentinel.write_text('authored sentinel')
    assert gb.seed_asm_corpus([{'entry_hex': key, 'name': 'Leaf'}], dest) == 0
    assert list(dest.iterdir()) == [sentinel] and sentinel.read_text() == 'authored sentinel'
    ok, error, _, _ = gb.try_asm_fallback(dest/'candidate.c', dest/'candidate.obj', 'Leaf', key)
    assert not ok and error.startswith('ASM unavailable: ') and gb._ASM_UNAVAILABLE[key]


def test_extent_metadata_load_is_lazy(tmp_path, monkeypatch):
    import sqlite3
    from agentdecompile_recovery.corpus import asm_extent
    db = tmp_path / 'knowledge.sqlite'
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE func_knowledge(program,entry_hex,file_offset,size,asm)')
    con.execute('INSERT INTO func_knowledge VALUES(?,?,?,?,?)', ('fixture', '00401000', 0x200, 2, '00401000: 90  nop\n00401001: c3  ret'))
    con.commit(); con.close()
    image = _extent_pe(b'\x90\xc3', 0x401000)
    raw = tmp_path / 'raw'; raw.write_bytes(image)
    monkeypatch.setattr(gb, 'KB', db)
    monkeypatch.setattr(gb, 'raw_image_path', lambda _: raw)
    monkeypatch.setattr(asm_extent, 'decode', lambda *a: pytest.fail('Metadata loading must not launch decoder'))
    gb.load_asm_fallback('fixture', '/fixture', image_sha256=hashlib.sha256(image).hexdigest())
    assert gb._ASM_ROWS['00401000'] == (0x200, 2) and not gb._FUNC_FILE and not gb._ASM_EXTENTS


def test_selected_extent_rejects_changed_metadata_before_decode(tmp_path, monkeypatch):
    import sqlite3
    from agentdecompile_recovery.corpus import asm_extent
    db = tmp_path / 'knowledge.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE func_knowledge(program,entry_hex,file_offset,size,asm)')
        con.execute('INSERT INTO func_knowledge VALUES(?,?,?,?,?)', ('fixture', '00401000', 0x201, 2, '00401000: 90  nop\n00401001: c3  ret'))
    monkeypatch.setattr(gb, '_ASM_KB', db)
    monkeypatch.setattr(gb, '_ASM_PROGRAM', 'fixture')
    monkeypatch.setattr(gb, '_ASM_ROWS', {'00401000': (0x200, 2)})
    monkeypatch.setattr(gb, '_RAW_IMAGE', _extent_pe(b'\x90\xc3', 0x401000))
    monkeypatch.setattr(gb, '_ASM_UNAVAILABLE', {})
    monkeypatch.setattr(asm_extent, 'decode', lambda *a: pytest.fail('Changed cache must refuse before decoder'))
    assert gb.qualified_asm_blob('00401000') is None
    assert gb._ASM_UNAVAILABLE['00401000'] == 'selected_cache_metadata_changed_or_ambiguous'
