"""VA -> file-offset mapping across container formats, on synthetic images.

Every image here is assembled in-test from the header fields the mappers
read. No product binaries are involved. Each format covers: a known VA,
both sides of a section boundary, out-of-image VAs, and (where the
format can be relocated) a ``load_base`` that differs from the header.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import exact_universal as eu
from agentdecompile_recovery.corpus import export_hookpack as hp
from agentdecompile_recovery.corpus.extract import stamp_analyzer_identity
from agentdecompile_recovery.corpus.store import connect
from agentdecompile_recovery.targets import inspect_magic

pytestmark = pytest.mark.unit


# ------------------------------------------------------------- image builders
#
# Each builder takes ``sections`` as a list of ``(vaddr, raw_off, size)``
# in format-relative terms (RVA for PE, absolute for ELF/Mach-O/XBE) and
# fills each section's file bytes with a distinct pattern.


def _fill(total: int, sections: list[tuple[int, int, int]]) -> bytearray:
    body = bytearray(total)
    for i, (_va, off, size) in enumerate(sections):
        body[off : off + size] = bytes([0x10 + i]) * size
    return body


def build_pe(sections, *, image_base: int, plus: bool) -> bytes:
    """Minimal PE32 (``plus=False``) or PE32+ (``plus=True``) image."""
    pe = 0x80
    opt_size = 0xF0 if plus else 0xE0
    hdr_end = pe + 24 + opt_size + 40 * len(sections)
    total = max(off + size for _va, off, size in sections)
    assert hdr_end <= min(off for _va, off, size in sections)
    img = _fill(total, sections)
    img[0:2] = b"MZ"
    struct.pack_into("<I", img, 0x3C, pe)
    img[pe : pe + 4] = b"PE\0\0"
    struct.pack_into("<HH", img, pe + 4, 0x8664 if plus else 0x014C, len(sections))
    struct.pack_into("<H", img, pe + 20, opt_size)
    opt = pe + 24
    struct.pack_into("<H", img, opt, 0x20B if plus else 0x10B)
    if plus:
        struct.pack_into("<Q", img, opt + 24, image_base)
    else:
        struct.pack_into("<I", img, opt + 28, image_base)
    for i, (rva, off, size) in enumerate(sections):
        o = opt + opt_size + i * 40
        img[o : o + 8] = b".s%d" % i + b"\0" * 5
        struct.pack_into("<IIII", img, o + 8, size, rva, size, off)
    return bytes(img)


def build_elf(sections, *, bits: int) -> bytes:
    """Minimal ELF with one PT_LOAD per section, plus one non-load header."""
    is64 = bits == 64
    ehdr = 64 if is64 else 52
    phent = 56 if is64 else 32
    phnum = len(sections) + 1
    total = max(off + size for _va, off, size in sections)
    assert ehdr + phent * phnum <= min(off for _va, off, size in sections)
    img = _fill(total, sections)
    img[0:4] = b"\x7fELF"
    img[4] = 2 if is64 else 1
    img[5] = 1
    img[6] = 1
    if is64:
        struct.pack_into("<Q", img, 0x20, ehdr)
        struct.pack_into("<HH", img, 0x36, phent, phnum)
    else:
        struct.pack_into("<I", img, 0x1C, ehdr)
        struct.pack_into("<HH", img, 0x2A, phent, phnum)
    entries = [(1, va, off, size) for va, off, size in sections] + [(6, 0, 0, 0)]  # PT_PHDR
    for i, (ptype, va, off, size) in enumerate(entries):
        o = ehdr + i * phent
        if is64:
            struct.pack_into("<IIQQQQQQ", img, o, ptype, 5, off, va, va, size, size, 0x1000)
        else:
            struct.pack_into("<IIIIIIII", img, o, ptype, off, va, va, size, size, 5, 0x1000)
    return bytes(img)


def build_macho64(sections) -> bytes:
    """Minimal 64-bit Mach-O with a zero-filesize first segment (like a zero page)."""
    hdr = 32
    cmd = 72
    segs = [(0, 0, 0)] + list(sections)
    total = max(off + size for _va, off, size in sections)
    assert hdr + cmd * len(segs) <= min(off for _va, off, size in sections)
    img = _fill(total, sections)
    struct.pack_into("<IiiIIII", img, 0, 0xFEEDFACF, 0x01000007, 3, 2, len(segs), cmd * len(segs), 0)
    for i, (va, off, size) in enumerate(segs):
        o = hdr + i * cmd
        struct.pack_into("<II", img, o, 0x19, cmd)
        img[o + 8 : o + 24] = b"__SEG%d" % i + b"\0" * 10
        struct.pack_into("<QQQQiiII", img, o + 24, va, size or 0x1000, off, size, 7, 5, 0, 0)
    return bytes(img)


XBE_FLAG_EXEC = 0x4


def build_xbe(sections, *, base: int, flags=None, table: int = 0x200) -> bytes:
    """Minimal XBE: header fields the mapper reads, then the section table."""
    total = max(off + size for _va, off, size in sections)
    assert table + 56 * len(sections) <= min(off for _va, off, size in sections)
    img = _fill(total, sections)
    img[0:4] = b"XBEH"
    struct.pack_into("<I", img, 0x104, base)
    struct.pack_into("<I", img, 0x11C, len(sections))
    struct.pack_into("<I", img, 0x120, base + table)
    flags = flags or [XBE_FLAG_EXEC] + [0] * (len(sections) - 1)
    for i, (va, off, size) in enumerate(sections):
        o = table + i * 56
        struct.pack_into("<IIIII", img, o, flags[i], va, size, off, size)
    return bytes(img)


# ---------------------------------------------------------------- assertions


def check_sections(va2off, sections, *, va_base: int = 0) -> None:
    """Known VA, both sides of each boundary, and out-of-image VAs."""
    for va, off, size in sections:
        assert va2off(va_base + va) == off
        assert va2off(va_base + va + 7) == off + 7
        assert va2off(va_base + va + size - 1) == off + size - 1
        assert va2off(va_base + va + size) is None
        assert va2off(va_base + va - 1) is None
    assert va2off(va_base) is None
    assert va2off(va_base + 0x7FFF_0000) is None
    assert va2off(0) is None


PE_SECTIONS = [(0x1000, 0x400, 0x200), (0x3000, 0x600, 0x100), (0x5000, 0x800, 0x80)]
ABS_SECTIONS = [(0x401000, 0x400, 0x200), (0x403000, 0x600, 0x100), (0x405000, 0x800, 0x80)]
PIE_SECTIONS = [(0x1000, 0x400, 0x200), (0x3000, 0x600, 0x100)]


# ----------------------------------------------------------------------- PE


def test_pe32_header_base() -> None:
    raw = build_pe(PE_SECTIONS, image_base=0x400000, plus=False)
    f, kind = eu.mapper_for(raw)
    assert kind == "pe_mapper"
    check_sections(f, PE_SECTIONS, va_base=0x400000)


def test_pe32plus_header_base_reads_64bit_image_base() -> None:
    raw = build_pe(PE_SECTIONS, image_base=0x1_4000_0000, plus=True)
    f, kind = eu.mapper_for(raw)
    assert kind == "pe_mapper"
    check_sections(f, PE_SECTIONS, va_base=0x1_4000_0000)


def test_pe32plus_load_base_override() -> None:
    raw = build_pe(PE_SECTIONS, image_base=0x1_4000_0000, plus=True)
    loaded = 0x7FF6_1234_0000
    f, _ = eu.mapper_for(raw, load_base=loaded)
    check_sections(f, PE_SECTIONS, va_base=loaded)
    # The header base no longer resolves once the image is relocated.
    assert f(0x1_4000_1000) is None


def test_pe32_load_base_equal_to_header_is_identity() -> None:
    raw = build_pe(PE_SECTIONS, image_base=0x400000, plus=False)
    plain = eu.pe_mapper(raw)
    same = eu.pe_mapper(raw, load_base=0x400000)
    for rva, off, size in PE_SECTIONS:
        for d in (0, 1, size - 1, size):
            assert plain(0x400000 + rva + d) == same(0x400000 + rva + d)


def test_pe_truncated_or_bad_signature_is_none() -> None:
    assert eu.pe_mapper(b"MZ") is None
    raw = bytearray(build_pe(PE_SECTIONS, image_base=0x400000, plus=False))
    raw[0x80:0x84] = b"XX\0\0"
    assert eu.pe_mapper(bytes(raw)) is None


# ---------------------------------------------------------------------- ELF


@pytest.mark.parametrize("bits", [32, 64])
def test_elf_non_pie_absolute_segments(bits: int) -> None:
    raw = build_elf(ABS_SECTIONS, bits=bits)
    f, kind = eu.mapper_for(raw)
    assert kind == "elf_mapper"
    check_sections(f, ABS_SECTIONS)


@pytest.mark.parametrize("bits", [32, 64])
def test_elf_non_pie_matching_load_base_unchanged(bits: int) -> None:
    raw = build_elf(ABS_SECTIONS, bits=bits)
    f = eu.elf_mapper(raw, load_base=0x401000)
    check_sections(f, ABS_SECTIONS)


@pytest.mark.parametrize("bits", [32, 64])
def test_elf_pie_load_base_shifts_lookup(bits: int) -> None:
    raw = build_elf(PIE_SECTIONS, bits=bits)
    unshifted = eu.elf_mapper(raw)
    check_sections(unshifted, PIE_SECTIONS)
    loaded = 0x5555_5555_4000 if bits == 64 else 0x5655_4000
    shifted = eu.elf_mapper(raw, load_base=loaded)
    # PIE format base is the lowest PT_LOAD vaddr (0x1000 here), so the
    # analyzer's load base maps onto that segment.
    for va, off, size in PIE_SECTIONS:
        delta = va - PIE_SECTIONS[0][0]
        assert shifted(loaded + delta) == off
        assert shifted(loaded + delta + size - 1) == off + size - 1
        assert shifted(loaded + delta + size) is None
    assert shifted(0x1000) is None


def test_elf_without_load_segments_maps_nothing() -> None:
    raw = bytearray(build_elf(ABS_SECTIONS, bits=64))
    # Flip every PT_LOAD to PT_NULL: mapper exists but resolves nothing.
    for i in range(len(ABS_SECTIONS) + 1):
        struct.pack_into("<I", raw, 64 + i * 56, 0)
    f = eu.elf_mapper(bytes(raw), load_base=0x400000)
    assert f is not None
    assert f(0x401000) is None


# ------------------------------------------------------------------- Mach-O


def test_macho64_ignores_zero_page_for_format_base() -> None:
    raw = build_macho64(ABS_SECTIONS)
    f, kind = eu.mapper_for(raw)
    assert kind == "macho_mapper"
    check_sections(f, ABS_SECTIONS)
    loaded = 0x1_0000_0000
    shifted = eu.macho_mapper(raw, load_base=loaded)
    for va, off, size in ABS_SECTIONS:
        delta = va - ABS_SECTIONS[0][0]
        assert shifted(loaded + delta) == off
        assert shifted(loaded + delta + size) is None
    assert shifted(0x401000) is None


# ---------------------------------------------------------------------- XBE


XBE_BASE = 0x10000
XBE_SECTIONS = [(0x11000, 0x1000, 0x200), (0x13000, 0x1400, 0x100), (0x15000, 0x1800, 0x80)]


def test_xbe_header_base() -> None:
    raw = build_xbe(XBE_SECTIONS, base=XBE_BASE)
    f, kind = eu.mapper_for(raw)
    assert kind == "xbe_mapper"
    check_sections(f, XBE_SECTIONS)


def test_xbe_load_base_override() -> None:
    raw = build_xbe(XBE_SECTIONS, base=XBE_BASE)
    loaded = 0x8001_0000
    f = eu.xbe_mapper(raw, load_base=loaded)
    for va, off, size in XBE_SECTIONS:
        assert f(loaded + (va - XBE_BASE)) == off
        assert f(loaded + (va - XBE_BASE) + size - 1) == off + size - 1
        assert f(loaded + (va - XBE_BASE) + size) is None
    assert f(XBE_SECTIONS[0][0]) is None


def test_xbe_exposes_section_flags() -> None:
    flags = [XBE_FLAG_EXEC | 0x1, 0x1, XBE_FLAG_EXEC]
    raw = build_xbe(XBE_SECTIONS, base=XBE_BASE, flags=flags)
    f = eu.xbe_mapper(raw)
    assert [s[0] for s in f.sections] == flags
    assert [s[1] for s in f.sections] == [va for va, _off, _size in XBE_SECTIONS]
    execu = [s for s in f.sections if s[0] & XBE_FLAG_EXEC]
    assert len(execu) == 2
    assert eu.xbe_sections(raw) == (XBE_BASE, list(f.sections))


def test_xbe_bad_table_pointer_is_none() -> None:
    raw = bytearray(build_xbe(XBE_SECTIONS, base=XBE_BASE))
    struct.pack_into("<I", raw, 0x120, XBE_BASE - 4)  # below the header base
    assert eu.xbe_mapper(bytes(raw)) is None
    struct.pack_into("<I", raw, 0x120, XBE_BASE + len(raw))  # past the end
    assert eu.xbe_mapper(bytes(raw)) is None
    assert eu.xbe_mapper(b"XBEH" + b"\0" * 16) is None


def test_unknown_image_has_no_mapper() -> None:
    assert eu.mapper_for(b"\0" * 0x400) == (None, None)
    assert eu.mapper_for(b"\0" * 0x400, load_base=0x1000) == (None, None)


def test_inspect_magic_recognizes_xbe(tmp_path: Path) -> None:
    path = tmp_path / "image.xbe"
    path.write_bytes(build_xbe(XBE_SECTIONS, base=XBE_BASE))
    assert inspect_magic(path) == ("xbe", "x86")


# -------------------------------------------------------- hookpack regression


def test_hookpack_file_offset_pe32plus_uses_64bit_base() -> None:
    """Before this change the hookpack path read a 32-bit ImageBase field
    unconditionally, which on a PE32+ image is the base's high dword."""
    raw = build_pe(PE_SECTIONS, image_base=0x1_4000_0000, plus=True)
    rva, off, _size = PE_SECTIONS[1]
    assert hp._file_offset(raw, 0x1_4000_0000 + rva + 0x10) == off + 0x10
    assert hp._file_offset(raw, 0x1_4000_0000 + rva + 0x10, 0x1_4000_0000) == off + 0x10
    loaded = 0x7FF6_0000_0000
    assert hp._file_offset(raw, loaded + rva + 0x10, loaded) == off + 0x10
    assert hp._file_offset(raw, 0x1_4000_0000 + rva + 0x10, loaded) is None


def test_hookpack_file_offset_pe32_unchanged() -> None:
    raw = build_pe(PE_SECTIONS, image_base=0x400000, plus=False)
    for rva, off, size in PE_SECTIONS:
        assert hp._file_offset(raw, 0x400000 + rva) == off
        assert hp._file_offset(raw, 0x400000 + rva, 0x400000) == off
        assert hp._file_offset(raw, 0x400000 + rva + size) is None
    assert hp._file_offset(b"\0" * 64, 0x401000) is None


def _hookpack_store(path: Path, *, image_base: int | None):
    con = connect(path)
    con.execute(
        "INSERT INTO binary(id, repo_path, slug, image_base) VALUES (1, '/a', 'build32', ?)",
        (image_base,),
    )
    con.execute("UPDATE binary SET language_id='x86:LE:32:default'")
    stamp_analyzer_identity(con, analyzer_version="test-analyzer")
    con.execute(
        "INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (3, 'Run', 'void Run()', 1)"
    )
    rva, _off, _size = PE_SECTIONS[1]
    addr = 0x400000 + rva
    con.execute(
        "INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (3, 1, ?, 1.0, 'stabs')",
        (addr,),
    )
    con.execute(
        "INSERT INTO func(binary_id, addr, name, signature, size) VALUES (1, ?, 'Run', 'void Run()', 16)",
        (addr,),
    )
    con.commit()
    return con


def test_hookpack_pe32_output_identical_with_and_without_store_base(tmp_path: Path, monkeypatch) -> None:
    raw = bytearray(build_pe(PE_SECTIONS, image_base=0x400000, plus=False))
    _rva, off, _size = PE_SECTIONS[1]
    raw[off : off + 8] = bytes.fromhex("535556578B7C2414")
    monkeypatch.setattr(hp, "_raw_image", lambda repo: bytes(raw))

    out_null = tmp_path / "null.json"
    hp.export_hookpack(_hookpack_store(tmp_path / "null.sqlite", image_base=None), out_null)
    out_base = tmp_path / "base.json"
    hp.export_hookpack(_hookpack_store(tmp_path / "base.sqlite", image_base=0x400000), out_base)

    # The mapper claim: a NULL store base and the header base map every site identically.
    # binaries[] now carries image_base from the row (U1), so compare the sites only.
    pack = json.loads(out_null.read_text(encoding="utf-8"))
    assert pack["sites"] == json.loads(out_base.read_text(encoding="utf-8"))["sites"]
    assert pack["sites"]["Run"]["expected_bytes"] == "535556578B7C2414"
