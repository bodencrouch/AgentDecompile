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
from collections import deque

from .coff_object import RELOCATIONS, parse_object_inventory

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


def place_sections(obj: bytes, placements: dict[int, int], symbols: dict[str, int],
                   *, image_base: int | None = None) -> dict:
    """Place explicit COFF contributions, not a linked image or function proof.

    Numeric section identities prevent duplicate local names from aliasing.
    Callers own placement/external-binding provenance; this function never
    derives bindings from comparison bytes, selects COMDAT winners, interprets
    SafeSEH metadata or infers function extents. Unplaced sections stay explicit.
    """
    inventory = parse_object_inventory(obj)
    sections = {section['index']: section for section in inventory['sections']}
    limit = 1 << (32 if inventory['machine'] == MACHINE_I386 else 64)
    if not isinstance(placements, dict) or not placements:
        raise FixupRefusal('section_placements_required')
    if not isinstance(symbols, dict) or any(
            not isinstance(name, str) or type(value) is not int or not 0 <= value < limit
            for name, value in symbols.items()):
        raise FixupRefusal('invalid_external_bindings')
    if image_base is not None and (type(image_base) is not int or not 0 <= image_base < limit):
        raise FixupRefusal('invalid_image_base')
    spans = []
    for index, address in placements.items():
        if type(index) is not int or index not in sections or type(address) is not int:
            raise FixupRefusal('invalid_section_placement')
        section = sections[index]
        if not 0 <= address < limit or address + section['size'] > limit:
            raise FixupRefusal('section_placement_overflow', str(index))
        if len(section['data']) != section['size']:
            raise FixupRefusal('uninitialized_section_placement_unsupported', str(index))
        definition = inventory['sectionDefinitions'].get(index, {})
        if definition.get('selection') == 5 and definition['association'] not in placements:
            raise FixupRefusal('unplaced_comdat_parent', str(index))
        if section['size']:
            spans.append((address, address + section['size'], index))
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise FixupRefusal('overlapping_section_placements')

    output = []
    for index in sorted(placements):
        section = sections[index]
        resolved = {}
        relocations = []
        for relocation in section['relocations']:
            symbol_index = relocation['symbolIndex']
            symbol = inventory['symbols'].get(symbol_index)
            if symbol is None:
                raise FixupRefusal('bad_symbol_index', str(symbol_index))
            number, value = symbol['section'], symbol['value']
            if number > 0:
                if number not in placements:
                    raise FixupRefusal('unplaced_defined_symbol', symbol['name'])
                if value > sections[number]['size']:
                    raise FixupRefusal('symbol_outside_section', symbol['name'])
                value += placements[number]
                if value >= limit:
                    raise FixupRefusal('symbol_address_overflow', symbol['name'])
                number = SYM_ABSOLUTE
            elif number == 0 and (value or symbol['storageClass'] != 2 or symbol['auxiliaries']):
                raise FixupRefusal('unsupported_external_symbol', symbol['name'])
            elif number not in (0, SYM_ABSOLUTE, SYM_DEBUG):
                raise FixupRefusal('unsupported_symbol_section', symbol['name'])
            resolved[symbol_index] = {'name': symbol['name'], 'section': number,
                                      'value': value, 'class': symbol['storageClass']}
            relocations.append({'offset': relocation['offset'], 'symbol_index': symbol_index,
                                'type': relocation['type']})
        relocations.sort(key=lambda item: (item['offset'], item['symbol_index'], item['type']))
        parsed = {'machine': inventory['machine'], 'section_number': index,
                  'code': section['data'], 'symbols': resolved, 'relocations': relocations}
        # Every internal target was converted to an absolute symbol, preventing
        # an external name map from overriding an unplaced internal definition.
        data, records = _place(parsed, placements[index], symbols, image_base)
        output.append({'section': index, 'name': section['name'], 'address': placements[index],
                       'data': data, 'sha256': _sha256(data), 'relocations': records,
                       'comdat': inventory['sectionDefinitions'].get(index)})
    return {'schema': 'agentdecompile.coff-section-placement/v1',
            'objectSha256': inventory['sha256'], 'sections': output,
            'unplacedSections': sorted(set(sections) - set(placements)),
            'claim': 'Explicit section placement only; not linked closure, function extent or byte proof.'}


def derive_section_bindings(obj: bytes, entry_section: int, entry_address: int,
                            target_region, *, image_base: int) -> dict:
    """Derive diagnostic bindings from target operands, never independent proof.

    Only relocation-reachable sections are visited. Every non-relocation byte
    must match before a section can supply outgoing bindings. The seed names a
    section base, not a recovered function extent; no COMDAT winner, SafeSEH
    interpretation or unreferenced contribution placement is inferred.
    """
    inventory = parse_object_inventory(obj)
    sections = {section['index']: section for section in inventory['sections']}
    limit = 1 << (32 if inventory['machine'] == MACHINE_I386 else 64)
    if type(entry_section) is not int or entry_section not in sections:
        raise FixupRefusal('invalid_entry_section')
    if type(image_base) is not int or not 0 <= image_base < limit:
        raise FixupRefusal('invalid_image_base')
    if not callable(target_region):
        raise FixupRefusal('target_region_reader_required')
    placements = {}
    externals = {}
    section_provenance = {}
    external_provenance = {}
    symbol_addresses = {}
    pending = deque()

    def bind_section(index, address, provenance):
        if type(address) is not int or not 0 <= address < limit:
            raise FixupRefusal('section_placement_overflow', str(index))
        if index in placements:
            if placements[index] != address:
                raise FixupRefusal('conflicting_section_binding', str(index))
            return
        section = sections[index]
        if not section['size'] or len(section['data']) != section['size']:
            raise FixupRefusal('uninitialized_section_placement_unsupported', str(index))
        end = address + section['size']
        if end > limit:
            raise FixupRefusal('section_placement_overflow', str(index))
        if any(address < base + sections[other]['size'] and base < end
               for other, base in placements.items()):
            raise FixupRefusal('overlapping_section_placements')
        placements[index] = address
        section_provenance[index] = provenance
        pending.append(index)

    bind_section(entry_section, entry_address, 'Explicit captured target section-base seed; not function extent proof.')
    while pending:
        index = pending.popleft()
        section = sections[index]
        address = placements[index]
        code = section['data']
        captured = target_region(address, len(code))
        if not isinstance(captured, bytes) or len(captured) != len(code):
            raise FixupRefusal('missing_target_section_data', str(index))
        fields = []
        last_end = 0
        for relocation in sorted(section['relocations'], key=lambda row: (row['offset'], row['symbolIndex'], row['type'])):
            spec = RELOCATIONS.get((inventory['machine'], relocation['type']))
            if spec is None:
                raise FixupRefusal('unsupported_relocation_type', str(relocation['type']))
            name, width, kind, extra = spec
            offset = relocation['offset']
            if offset < last_end:
                raise FixupRefusal('overlapping_fixups', str(offset))
            if offset + width > len(code):
                raise FixupRefusal('fixup_out_of_bounds', str(offset))
            if captured[last_end:offset] != code[last_end:offset]:
                raise FixupRefusal('target_section_shape_mismatch', str(index))
            fields.append((relocation, name, width, kind, extra))
            last_end = offset + width
        if captured[last_end:] != code[last_end:]:
            raise FixupRefusal('target_section_shape_mismatch', str(index))
        # No propagation until the entire contribution's fixed bytes match.
        for relocation, name, width, kind, extra in fields:
            offset = relocation['offset']
            addend_format = '<q' if width == 8 else '<i' if kind == 'rel' else '<I'
            addend = struct.unpack_from(addend_format, code, offset)[0]
            operand_format = '<i' if kind == 'rel' else '<Q' if width == 8 else '<I'
            operand = struct.unpack_from(operand_format, captured, offset)[0]
            target = operand - addend
            if kind == 'rel':
                target += address + offset + 4 + extra
            elif kind == 'rva':
                target += image_base
            if not 0 <= target < limit:
                raise FixupRefusal('symbol_address_overflow', str(relocation['symbolIndex']))
            symbol_index = relocation['symbolIndex']
            symbol = inventory['symbols'].get(symbol_index)
            if symbol is None:
                raise FixupRefusal('bad_symbol_index', str(symbol_index))
            if symbol['storageClass'] not in (2, 3, 6):
                raise FixupRefusal('unsupported_symbol_storage', str(symbol_index))
            if symbol_index in symbol_addresses and symbol_addresses[symbol_index] != target:
                raise FixupRefusal('conflicting_symbol_binding', str(symbol_index))
            symbol_addresses[symbol_index] = target
            provenance = f'Target-derived {name} at section {index} +0x{offset:x}; implicit addend {addend}; not independent identity proof.'
            number, value = symbol['section'], symbol['value']
            if number > 0:
                if value > sections[number]['size']:
                    raise FixupRefusal('symbol_outside_section', symbol['name'])
                bind_section(number, target - value, provenance)
            elif number == SYM_ABSOLUTE:
                if target != value:
                    raise FixupRefusal('absolute_symbol_mismatch', symbol['name'])
            elif number == SYM_DEBUG:
                raise FixupRefusal('debug_symbol_target', symbol['name'])
            elif number == 0:
                if value or symbol['storageClass'] != 2 or symbol['auxiliaries']:
                    raise FixupRefusal('unsupported_external_symbol', symbol['name'])
                if symbol['name'] in externals and externals[symbol['name']] != target:
                    raise FixupRefusal('conflicting_external_binding', symbol['name'])
                externals[symbol['name']] = target
                external_provenance.setdefault(symbol['name'], provenance)
            else:
                raise FixupRefusal('unsupported_symbol_section', symbol['name'])
    return {'placements': dict(sorted(placements.items())),
            'externals': dict(sorted(externals.items())),
            'sectionProvenance': dict(sorted(section_provenance.items())),
            'externalProvenance': dict(sorted(external_provenance.items())),
            'objectSha256': inventory['sha256'],
            'claim': 'Target-derived diagnostic bindings only; not independent identity, extent or byte proof.'}


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
