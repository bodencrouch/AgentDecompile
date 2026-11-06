"""Region/fixup roundtrip on synthetic COFF objects.

Every object is built in-test, either by ``mkobj.build_object`` (the object
shape the recovery pipeline emits for a target region) or by the small
generic builder below. No product binary, compiler, linker or objdump runs.
"""

from __future__ import annotations

import json
import random
import struct

import pytest

from agentdecompile_recovery.corpus import coff_fixup_roundtrip as rt
from agentdecompile_recovery.corpus import mkobj

pytestmark = pytest.mark.unit

I386 = mkobj.MACHINE["coff-i386"]
AMD64 = mkobj.MACHINE["coff-x86-64"]
ORIGIN = 0x00401000


# ------------------------------------------------------------------ builders


def coff(machine, code, relocs, symbols, *, section_name=b".text"):
    """relocs: [(offset, symbol_index, type)]; symbols: [(name, value, secnum, klass)].

    Each symbol takes one record (no aux records). Long names go to the
    string table.
    """
    data_off = 20 + 40
    reloc_off = data_off + len(code)
    symtab_off = reloc_off + 10 * len(relocs)
    strtab = bytearray(b"\0\0\0\0")
    out = bytearray(struct.pack("<HHIIIHH", machine, 1, 0, symtab_off, len(symbols), 0, 0))
    out += section_name.ljust(8, b"\0")
    out += struct.pack("<IIIIIIHHI", 0, 0, len(code), data_off,
                       reloc_off if relocs else 0, 0, len(relocs), 0, 0x60500020)
    out += code
    for off, idx, kind in relocs:
        out += struct.pack("<IIH", off, idx, kind)
    for name, value, secnum, klass in symbols:
        out += mkobj.symbol_name_field(name, strtab)
        out += struct.pack("<IhHBB", value & 0xFFFFFFFF, secnum, 0, klass, 0)
    struct.pack_into("<I", strtab, 0, len(strtab))
    out += strtab
    return bytes(out)


def mkobj_region(code: bytes, call_targets: dict[int, int]) -> bytes:
    """What ``mkobj.write_object`` does after its decoder found ``call_targets``."""
    zeroed = bytearray(code)
    for disp in call_targets:
        zeroed[disp:disp + 4] = b"\0\0\0\0"
    return mkobj.build_object(bytes(zeroed), "_F", I386, call_targets)


def synthetic_region(rng: random.Random) -> tuple[bytes, dict[int, int]]:
    """Random filler with call/jmp rel32 sites to targets outside the region."""
    size = rng.randrange(16, 160)
    code = bytearray(rng.randrange(256) for _ in range(size))
    sites: dict[int, int] = {}
    pos = rng.randrange(0, 4)
    while pos + 5 <= size:
        if rng.random() < 0.4:
            target = rng.choice([rng.randrange(-0x200000, -1), rng.randrange(size, 0x200000)])
            disp = target - (pos + 5)
            code[pos] = rng.choice([0xE8, 0xE9])
            struct.pack_into("<i", code, pos + 1, disp)
            sites[pos + 1] = target
            pos += 5
        pos += rng.randrange(1, 6)
    return bytes(code), sites


def rel32_target(placed: bytes, place_va: int, disp_off: int) -> int:
    return place_va + disp_off + 4 + struct.unpack_from("<i", placed, disp_off)[0]


# ------------------------------------------------------------------ roundtrip


def test_mkobj_regions_roundtrip_at_origin_seeded() -> None:
    rng = random.Random(0x5EED)
    total_sites = 0
    for _ in range(60):
        code, sites = synthetic_region(rng)
        obj = mkobj_region(code, sites)
        symbols = rt.mkobj_external_symbols(obj, ORIGIN)
        receipt = rt.roundtrip_region(code, obj, ORIGIN, symbols)
        assert receipt["refusal"] is None, receipt
        assert receipt["byte_equal_at_origin"] is True
        assert receipt["relocation_count"] == len(sites)
        assert receipt["fixup_bytes"] == 4 * len(sites)
        total_sites += len(sites)
    assert total_sites > 100  # the seed actually exercised fixups


def test_backward_external_target_is_sign_extended() -> None:
    code = b"\x90\xe8" + struct.pack("<i", -0x1006) + b"\xc3"
    sites = {2: -0x1000}
    obj = mkobj_region(code, sites)
    symbols = rt.mkobj_external_symbols(obj, ORIGIN)
    assert symbols == {"EXT_fffff000": ORIGIN - 0x1000}
    assert rt.roundtrip_region(code, obj, ORIGIN, symbols)["byte_equal_at_origin"] is True


def test_replacement_holds_absolute_targets_and_shifts_rel32() -> None:
    rng = random.Random(7)
    code, sites = synthetic_region(rng)
    while not sites:
        code, sites = synthetic_region(rng)
    obj = mkobj_region(code, sites)
    symbols = rt.mkobj_external_symbols(obj, ORIGIN)
    delta = 0x30000
    moved = rt.place(obj, ORIGIN + delta, symbols)
    for disp in sites:
        assert rel32_target(moved, ORIGIN + delta, disp) == ORIGIN + sites[disp]
        before = struct.unpack_from("<i", code, disp)[0]
        assert struct.unpack_from("<i", moved, disp)[0] == before - delta
    outside = set(range(len(code))) - {d + i for d in sites for i in range(4)}
    assert all(moved[i] == code[i] for i in outside)
    check = rt.check_replacement(code, obj, ORIGIN, symbols, rel32_sites=sorted(sites), delta=delta)
    assert check == {"relocatable": True, "delta": delta, "moved_sites": []}


def test_zero_relocation_object_passes_origin_but_is_not_relocatable() -> None:
    # mkobj.find_call_targets returns {} when objdump is absent, so write_object
    # keeps the raw displacement and emits no relocation.
    code = b"\x55\xe8" + struct.pack("<i", 0x2000) + b"\x5d\xc3"
    obj = mkobj.build_object(code, "_F", I386)
    receipt = rt.roundtrip_region(code, obj, ORIGIN, {})
    assert receipt["byte_equal_at_origin"] is True
    assert receipt["relocation_count"] == 0
    check = rt.check_replacement(code, obj, ORIGIN, {}, rel32_sites=[2], delta=0x1000)
    assert check["relocatable"] is False
    assert check["moved_sites"] == [2]


def test_mismatch_reports_first_offset_and_count() -> None:
    code, sites = b"\xe8" + struct.pack("<i", 0x100) + b"\x90\x90\xc3", {1: 0x105}
    obj = mkobj_region(code, sites)
    symbols = rt.mkobj_external_symbols(obj, ORIGIN)
    tampered = bytearray(code)
    tampered[6] = 0xCC
    receipt = rt.roundtrip_region(bytes(tampered), obj, ORIGIN, symbols)
    assert receipt["byte_equal_at_origin"] is False
    assert receipt["first_mismatch"] == 6
    assert receipt["mismatch_count"] == 1
    wrong_place = rt.roundtrip_region(code, obj, ORIGIN + 0x10, symbols)
    assert wrong_place["byte_equal_at_origin"] is False
    assert wrong_place["first_mismatch"] == 1


# ------------------------------------------------------- relocation semantics


def test_dir32_adds_implicit_addend() -> None:
    code = b"\xa1" + struct.pack("<I", 4) + b"\xc3"  # mov eax, [sym+4]
    obj = coff(I386, code, [(1, 0, rt.I386_DIR32)], [("_g_table", 0, 0, 2)])
    placed = rt.place(obj, ORIGIN, {"_g_table": 0x00830540})
    assert struct.unpack_from("<I", placed, 1)[0] == 0x00830544


def test_section_symbol_resolves_against_placement() -> None:
    code = b"\x68" + struct.pack("<I", 2) + b"\xc3\x90\x90"  # push offset .text+8
    obj = coff(I386, code, [(1, 0, rt.I386_DIR32)], [(".text", 6, 1, 3)])
    placed = rt.place(obj, ORIGIN, {})
    assert struct.unpack_from("<I", placed, 1)[0] == ORIGIN + 8
    moved = rt.place(obj, ORIGIN + 0x30000, {})
    assert struct.unpack_from("<I", moved, 1)[0] == ORIGIN + 0x30000 + 8


def test_dir32nb_needs_image_base() -> None:
    code = struct.pack("<I", 0)
    obj = coff(I386, code, [(0, 0, rt.I386_DIR32NB)], [("_x", 0, 0, 2)])
    with pytest.raises(rt.FixupRefusal, match="image_base_required"):
        rt.place(obj, ORIGIN, {"_x": 0x00402000})
    placed = rt.place(obj, ORIGIN, {"_x": 0x00402000}, image_base=0x00400000)
    assert struct.unpack_from("<I", placed, 0)[0] == 0x2000


def test_amd64_rel32_variants_and_addr64() -> None:
    # call rel32 ; lea rax,[rip+x] with REL32_4 (field followed by 4 more bytes) ; addr64
    code = (b"\xe8" + b"\0" * 4
            + b"\xc7\x05" + struct.pack("<i", 0) + b"\x01\x00\x00\x00"
            + struct.pack("<Q", 8))
    relocs = [(1, 0, rt.AMD64_REL32), (7, 1, rt.AMD64_REL32 + 4), (15, 1, rt.AMD64_ADDR64)]
    syms = [("callee", 0, 0, 2), ("data", 0, 0, 2)]
    obj = coff(AMD64, code, relocs, syms)
    base = 0x140001000
    placed = rt.place(obj, base, {"callee": 0x140005000, "data": 0x140020000})
    assert base + 1 + 4 + struct.unpack_from("<i", placed, 1)[0] == 0x140005000
    assert base + 7 + 4 + 4 + struct.unpack_from("<i", placed, 7)[0] == 0x140020000
    assert struct.unpack_from("<Q", placed, 15)[0] == 0x140020008


def test_amd64_object_with_i386_rel32_type_is_refused() -> None:
    # 0x14 is IMAGE_REL_I386_REL32; it is not an AMD64 relocation type.
    obj = coff(AMD64, b"\xe8\0\0\0\0\xc3", [(1, 0, 0x14)], [("_a", 0, 0, 2)])
    with pytest.raises(rt.FixupRefusal, match="unsupported_relocation_type"):
        rt.place(obj, 0x140001000, {"_a": 0x140001040})


def test_mkobj_amd64_object_uses_amd64_rel32_and_roundtrips() -> None:
    # mkobj.build_object packs the REL32 type for the object's machine (P2-d).
    # The call at offset 0 targets region offset 0x40: rel32 = 0x40 - 5 = 0x3b.
    original = b"\xe8\x3b\0\0\0\xc3"
    obj = mkobj.build_object(b"\xe8\0\0\0\0\xc3", "F", AMD64, {1: 0x40})
    symbols = rt.mkobj_external_symbols(obj, 0x140001000)
    assert rt.place(obj, 0x140001000, symbols) == original
    receipt = rt.roundtrip_region(original, obj, 0x140001000, symbols)
    assert receipt["byte_equal_at_origin"] is True


# ------------------------------------------------------------------ refusals


@pytest.mark.parametrize(
    ("relocs", "symbols", "resolver", "reason"),
    [
        ([(0, 0, 0x14), (2, 0, 0x14)], [("_a", 0, 0, 2)], {"_a": 0x500000}, "overlapping_fixups"),
        ([(6, 0, 0x14)], [("_a", 0, 0, 2)], {"_a": 0x500000}, "fixup_out_of_bounds"),
        ([(0, 0, 0x14)], [("_a", 0, 0, 2)], {}, "unresolved_symbol"),
        ([(0, 5, 0x14)], [("_a", 0, 0, 2)], {"_a": 0x500000}, "bad_symbol_index"),
        ([(0, 0, 0x14)], [("_far", 0, 0, 2)], {"_far": ORIGIN + 0x90000000}, "fixup_overflow"),
    ],
)
def test_refusals_are_named(relocs, symbols, resolver, reason) -> None:
    obj = coff(I386, b"\0" * 8, relocs, symbols)
    with pytest.raises(rt.FixupRefusal, match=reason):
        rt.place(obj, ORIGIN, resolver)
    receipt = rt.roundtrip_region(b"\0" * 8, obj, ORIGIN, resolver)
    assert receipt["refusal"] == reason
    assert receipt["byte_equal_at_origin"] is None


def test_relocation_against_an_aux_record_is_refused() -> None:
    # build_object gives .text one aux record at symbol index 1.
    code = b"\xe8\0\0\0\0\xc3"
    obj = bytearray(mkobj.build_object(code, "_F", I386, {1: 0x40}))
    struct.pack_into("<I", obj, 20 + 40 + len(code) + 4, 1)
    with pytest.raises(rt.FixupRefusal, match="bad_symbol_index"):
        rt.place(bytes(obj), ORIGIN, {"EXT_00000040": ORIGIN + 0x40})


def test_nsym_without_symptr_is_refused() -> None:
    # RN-B-11: a header claiming symbols (nsym > 0) but no symbol table
    # pointer (symptr == 0) must be refused, not read as garbage at
    # offset 18*index from the start of the object.
    obj = bytearray(coff(I386, b"\0" * 8, [], [("_a", 0, 0, 2)]))
    struct.pack_into("<I", obj, 8, 0)  # zero out symptr; nsym stays 1
    with pytest.raises(rt.FixupRefusal, match="truncated_object"):
        rt.parse_object(bytes(obj))


def test_receipt_is_deterministic_and_carries_no_bytes() -> None:
    code, sites = synthetic_region(random.Random(11))
    obj = mkobj_region(code, sites)
    symbols = rt.mkobj_external_symbols(obj, ORIGIN)
    a = rt.roundtrip_region(code, obj, ORIGIN, symbols)
    b = rt.roundtrip_region(code, obj, ORIGIN, dict(reversed(list(symbols.items()))))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema"] == rt.SCHEMA
    assert a["region_sha256"] and a["object_sha256"] and a["placed_sha256"]
    assert all(not isinstance(v, (bytes, bytearray)) for v in a.values())
