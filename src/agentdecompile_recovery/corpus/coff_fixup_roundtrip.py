"""Place a relocated COFF code section at a VA and compare it with the original region.

This is the region/fixup roundtrip predicate: an object carved from (or
compiled for) an image region, once its relocations are applied at the
region's VA, must reproduce the region byte for byte. ``check_replacement``
adds the relocatability predicate: placed elsewhere, every external rel32
reference must still land on the same absolute target.

Pure Python over bytes. No linker, compiler or objdump runs. Relocation
types are keyed by ``(machine, type)``; anything else is refused by name.
COFF addends are implicit: the field's existing content is added, never
overwritten.
"""

from __future__ import annotations

import hashlib
import re
import struct

SCHEMA = "agentdecompile.coff-fixup-roundtrip.v1"

MACHINE_I386 = 0x014C
MACHINE_AMD64 = 0x8664
MACHINE_NAMES = {MACHINE_I386: "i386", MACHINE_AMD64: "amd64"}

I386_DIR32 = 0x0006
I386_DIR32NB = 0x0007
I386_REL32 = 0x0014

AMD64_ADDR64 = 0x0001
AMD64_ADDR32 = 0x0002
AMD64_ADDR32NB = 0x0003
AMD64_REL32 = 0x0004  # REL32_1 .. REL32_5 are 0x0005 .. 0x0009

SCN_CNT_CODE = 0x00000020
SCN_LNK_NRELOC_OVFL = 0x01000000
SYM_ABSOLUTE = -1
SYM_DEBUG = -2

# (machine, type) -> (name, width, kind, extra) where kind is
# "abs" (S + A), "rva" (S - image_base + A) or "rel" (S + A - (P + 4 + extra)).
RELOCATIONS = {
    (MACHINE_I386, I386_DIR32): ("IMAGE_REL_I386_DIR32", 4, "abs", 0),
    (MACHINE_I386, I386_DIR32NB): ("IMAGE_REL_I386_DIR32NB", 4, "rva", 0),
    (MACHINE_I386, I386_REL32): ("IMAGE_REL_I386_REL32", 4, "rel", 0),
    (MACHINE_AMD64, AMD64_ADDR64): ("IMAGE_REL_AMD64_ADDR64", 8, "abs", 0),
    (MACHINE_AMD64, AMD64_ADDR32): ("IMAGE_REL_AMD64_ADDR32", 4, "abs", 0),
    (MACHINE_AMD64, AMD64_ADDR32NB): ("IMAGE_REL_AMD64_ADDR32NB", 4, "rva", 0),
    **{
        (MACHINE_AMD64, AMD64_REL32 + k): (
            "IMAGE_REL_AMD64_REL32" + (f"_{k}" if k else ""), 4, "rel", k)
        for k in range(6)
    },
}

_MKOBJ_EXTERNAL = re.compile(r"EXT_([0-9a-f]{8})")


class FixupRefusal(ValueError):
    """A named reason the object cannot be placed. ``str()`` is the reason."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason if not detail else f"{reason}: {detail}")
        self.reason = reason


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_object(obj: bytes) -> dict:
    """The single code section, its relocations and the symbol table."""
    if len(obj) < 20:
        raise FixupRefusal("truncated_object")
    machine, nsec, _stamp, symptr, nsym, optsz, _chars = struct.unpack_from("<HHIIIHH", obj, 0)
    if machine not in MACHINE_NAMES:
        raise FixupRefusal("unsupported_machine", f"0x{machine:04x}")
    if nsym and not symptr:
        raise FixupRefusal("truncated_object", "symbol table")
    strtab_off = symptr + 18 * nsym
    if symptr and strtab_off + 4 > len(obj):
        raise FixupRefusal("truncated_object", "symbol table")

    def name_of(field: bytes) -> str:
        if field[:4] == b"\0\0\0\0" and nsym:
            offset = struct.unpack_from("<I", field, 4)[0]
            end = obj.find(b"\0", strtab_off + offset)
            if offset < 4 or end < 0:
                raise FixupRefusal("bad_symbol_name")
            return obj[strtab_off + offset:end].decode("latin1")
        return field.rstrip(b"\0").decode("latin1")

    code_sections = []
    for i in range(nsec):
        sh = 20 + optsz + 40 * i
        if sh + 40 > len(obj):
            raise FixupRefusal("truncated_object", "section table")
        _vs, _va, size, raw, relptr, _lp, nrel, _nl, chars = struct.unpack_from("<IIIIIIHHI", obj, sh + 8)
        if chars & SCN_CNT_CODE:
            code_sections.append((i + 1, obj[sh:sh + 8].rstrip(b"\0").decode("latin1"),
                                  size, raw, relptr, nrel, chars))
    if len(code_sections) != 1:
        raise FixupRefusal("ambiguous_code_section", f"{len(code_sections)} code sections")
    secnum, secname, size, raw, relptr, nrel, chars = code_sections[0]
    if chars & SCN_LNK_NRELOC_OVFL:
        raise FixupRefusal("relocation_overflow_unsupported")
    if size == 0 or raw + size > len(obj):
        raise FixupRefusal("empty_code_section" if size == 0 else "truncated_object")
    if nrel and relptr + 10 * nrel > len(obj):
        raise FixupRefusal("truncated_object", "relocations")

    symbols: dict[int, dict] = {}
    index = 0
    while index < nsym:
        rec = symptr + 18 * index
        value, sec, _type, klass, naux = struct.unpack_from("<IhHBB", obj, rec + 8)
        symbols[index] = {"name": name_of(obj[rec:rec + 8]), "value": value, "section": sec, "class": klass}
        index += 1 + naux  # aux records are not addressable symbols

    relocations = []
    for r in range(nrel):
        offset, symidx, kind = struct.unpack_from("<IIH", obj, relptr + 10 * r)
        relocations.append({"offset": offset, "symbol_index": symidx, "type": kind})
    relocations.sort(key=lambda x: (x["offset"], x["symbol_index"], x["type"]))
    return {"machine": machine, "section": secname, "section_number": secnum,
            "code": obj[raw:raw + size], "relocations": relocations, "symbols": symbols}


def _resolve(sym: dict, parsed: dict, place_va: int, symbols: dict[str, int]) -> int:
    if sym["section"] == parsed["section_number"]:
        return place_va + sym["value"]
    if sym["section"] == SYM_ABSOLUTE:
        return sym["value"]
    if sym["section"] == SYM_DEBUG:
        raise FixupRefusal("debug_symbol_target", sym["name"])
    if sym["name"] in symbols:
        return int(symbols[sym["name"]])
    raise FixupRefusal("unresolved_symbol", sym["name"])


def _fixups(parsed: dict, place_va: int, symbols: dict[str, int], image_base: int | None):
    """Yield (offset, width, new_value_bytes, record) for every relocation, validated."""
    code = parsed["code"]
    last_end = 0
    for rel in parsed["relocations"]:
        spec = RELOCATIONS.get((parsed["machine"], rel["type"]))
        if spec is None:
            raise FixupRefusal("unsupported_relocation_type",
                               f"{MACHINE_NAMES[parsed['machine']]} 0x{rel['type']:04x}")
        name, width, kind, extra = spec
        offset = rel["offset"]
        if offset + width > len(code):
            raise FixupRefusal("fixup_out_of_bounds", f"offset {offset}")
        if offset < last_end:
            raise FixupRefusal("overlapping_fixups", f"offset {offset}")
        last_end = offset + width
        sym = parsed["symbols"].get(rel["symbol_index"])
        if sym is None:
            raise FixupRefusal("bad_symbol_index", str(rel["symbol_index"]))
        target = _resolve(sym, parsed, place_va, symbols)
        if width == 8:
            addend = struct.unpack_from("<q", code, offset)[0]
        elif kind == "rel":
            addend = struct.unpack_from("<i", code, offset)[0]
        else:
            addend = struct.unpack_from("<I", code, offset)[0]
        if kind == "abs":
            value = target + addend
        elif kind == "rva":
            if image_base is None:
                raise FixupRefusal("image_base_required", name)
            value = target - image_base + addend
        else:
            value = target + addend - (place_va + offset + 4 + extra)
        if kind == "rel":
            if not -(1 << 31) <= value < (1 << 31):
                raise FixupRefusal("fixup_overflow", f"offset {offset}")
            packed = struct.pack("<i", value)
        elif width == 8:
            if not 0 <= value < (1 << 64):
                raise FixupRefusal("fixup_overflow", f"offset {offset}")
            packed = struct.pack("<Q", value)
        else:
            if not 0 <= value < (1 << 32):
                raise FixupRefusal("fixup_overflow", f"offset {offset}")
            packed = struct.pack("<I", value)
        yield offset, width, packed, {"offset": offset, "type": name, "symbol": sym["name"], "target": target}


def place(obj: bytes, place_va: int, symbols: dict[str, int], *, image_base: int | None = None) -> bytes:
    """The code section with every relocation applied as if linked at ``place_va``."""
    return _place(parse_object(obj), place_va, symbols, image_base)[0]


def _place(parsed: dict, place_va: int, symbols: dict[str, int], image_base: int | None):
    out = bytearray(parsed["code"])
    records = []
    for offset, width, packed, record in _fixups(parsed, place_va, symbols, image_base):
        out[offset:offset + width] = packed
        records.append(record)
    return bytes(out), records


def mkobj_external_symbols(obj: bytes, origin_va: int) -> dict[str, int]:
    """Resolve ``mkobj``'s ``EXT_xxxxxxxx`` names against the region's original VA.

    ``mkobj.build_object`` names each external call target by its offset from
    the region start (masked to 32 bits), not by its VA.
    """
    parsed = parse_object(obj)
    out = {}
    for sym in parsed["symbols"].values():
        m = _MKOBJ_EXTERNAL.fullmatch(sym["name"])
        if m and sym["section"] == 0:
            rel = int(m.group(1), 16)
            if rel & 0x80000000:
                rel -= 1 << 32
            out[sym["name"]] = origin_va + rel
    return dict(sorted(out.items()))


def roundtrip_region(original: bytes, obj: bytes, place_va: int, symbols: dict[str, int],
                     *, image_base: int | None = None) -> dict:
    """Receipt for "the object, placed at ``place_va``, reproduces ``original``".

    ``byte_equal_at_origin`` is None when the object is refused. Equality at
    the origin alone does not show relocatability; see ``check_replacement``.
    """
    receipt = {
        "schema": SCHEMA, "place_va": place_va, "image_base": image_base,
        "region_size": len(original), "region_sha256": _sha256(original), "object_sha256": _sha256(obj),
        "machine": None, "section": None, "relocation_count": None, "fixup_bytes": None,
        "relocations": None, "placed_sha256": None, "byte_equal_at_origin": None,
        "size_equal": None, "first_mismatch": None, "mismatch_count": None, "refusal": None,
    }
    try:
        parsed = parse_object(obj)
        placed, records = _place(parsed, place_va, symbols, image_base)
    except FixupRefusal as exc:
        receipt["refusal"] = exc.reason
        return receipt
    widths = {r["offset"]: RELOCATIONS[(parsed["machine"], rel["type"])][1]
              for r, rel in zip(records, parsed["relocations"])}
    n = min(len(placed), len(original))
    diffs = [i for i in range(n) if placed[i] != original[i]]
    extra = abs(len(placed) - len(original))
    receipt.update(
        machine=MACHINE_NAMES[parsed["machine"]], section=parsed["section"],
        relocation_count=len(records), fixup_bytes=sum(widths.values()), relocations=records,
        placed_sha256=_sha256(placed), size_equal=len(placed) == len(original),
        byte_equal_at_origin=placed == original,
        first_mismatch=diffs[0] if diffs else (n if extra else None),
        mismatch_count=len(diffs) + extra,
    )
    return receipt


def check_replacement(original: bytes, obj: bytes, origin_va: int, symbols: dict[str, int],
                      *, rel32_sites: list[int], delta: int, image_base: int | None = None) -> dict:
    """Place at ``origin_va + delta`` with absolute targets held fixed.

    ``rel32_sites`` are displacement-field offsets that a decoder (not this
    object) says reference code outside the region. Each must resolve to the
    same absolute target as in ``original`` at ``origin_va``. A site whose
    target moved means the object froze a PC-relative reference without a
    relocation: it only reproduces the region where it was carved.
    """
    moved_va = origin_va + delta
    placed = place(obj, moved_va, symbols, image_base=image_base)
    moved = []
    for site in sorted(rel32_sites):
        before = origin_va + site + 4 + struct.unpack_from("<i", original, site)[0]
        after = moved_va + site + 4 + struct.unpack_from("<i", placed, site)[0]
        if before != after:
            moved.append(site)
    return {"relocatable": not moved, "delta": delta, "moved_sites": moved}
