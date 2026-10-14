"""Bounded standard COFF inventory, not function recovery or a linker.

All primary/auxiliary symbols and code/data sections remain separate. Parsing
does not infer function extents, choose COMDAT winners or apply relocations.
Bigobj, archives, optional headers and relocation-overflow tables refuse.
String-table names are memoized by offset, limited to 64 KiB each and 8 MiB
of decoded bytes across unique offsets; exceeding either limit refuses.
Format reference: https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
"""

from __future__ import annotations

import hashlib
import struct
from bisect import bisect_left

SCHEMA = 'agentdecompile.coff-object-inventory/v1'
MACHINE_I386 = 0x14c
MACHINE_AMD64 = 0x8664
MACHINE_NAMES = {MACHINE_I386: 'i386', MACHINE_AMD64: 'amd64'}
MAX_NAME_BYTES = 64 * 1024
MAX_TOTAL_NAME_BYTES = 8 * 1024**2

# Existing fixup capabilities only: name, operand width, operation, PC bias.
# Inventory of another relocation kind does not grant fixup support.
RELOCATIONS = {
    (MACHINE_I386, 0x6): ('IMAGE_REL_I386_DIR32', 4, 'abs', 0),
    (MACHINE_I386, 0x7): ('IMAGE_REL_I386_DIR32NB', 4, 'rva', 0),
    (MACHINE_I386, 0x14): ('IMAGE_REL_I386_REL32', 4, 'rel', 0),
    (MACHINE_AMD64, 0x1): ('IMAGE_REL_AMD64_ADDR64', 8, 'abs', 0),
    (MACHINE_AMD64, 0x2): ('IMAGE_REL_AMD64_ADDR32', 4, 'abs', 0),
    (MACHINE_AMD64, 0x3): ('IMAGE_REL_AMD64_ADDR32NB', 4, 'rva', 0),
    **{(MACHINE_AMD64, 0x4 + bias): (
        'IMAGE_REL_AMD64_REL32' + (f'_{bias}' if bias else ''), 4, 'rel', bias)
       for bias in range(6)},
}
RELOCATION_METADATA = {
    key: (name, width) for key, (name, width, _, _) in RELOCATIONS.items()
}
RELOCATION_METADATA.update({
    (machine, kind): (f'IMAGE_REL_{prefix}_{name}', width)
    for machine, prefix in ((MACHINE_I386, 'I386'), (MACHINE_AMD64, 'AMD64'))
    for kind, name, width in ((0x0, 'ABSOLUTE', 0), (0xa, 'SECTION', 2),
                              (0xb, 'SECREL', 4), (0xc, 'SECREL7', 1))
})
# I386 uses TOKEN=0xc and SECREL7=0xd; neither is a supported fixup.
RELOCATION_METADATA[(MACHINE_I386, 0xc)] = ('IMAGE_REL_I386_TOKEN', 4)
RELOCATION_METADATA[(MACHINE_I386, 0xd)] = ('IMAGE_REL_I386_SECREL7', 1)
RELOCATION_METADATA[(MACHINE_AMD64, 0xd)] = ('IMAGE_REL_AMD64_TOKEN', 4)


class CoffRefusal(ValueError):
    """A named structural or bounded-capacity refusal, never truncated output."""

    def __init__(self, reason: str, detail: str = ''):
        self.reason = reason
        super().__init__(reason if not detail else f'{reason}: {detail}')


def parse_object_inventory(obj: bytes) -> dict:
    """Return deterministic records; byte fields preserve original contents.

    Sections and relocations keep file order. ``symbols`` keys are original
    primary COFF indices; auxiliary indices are never addressable symbols.
    Unknown relocation operands stay unclassified with raw records intact.
    """
    def require(condition, reason, detail=''):
        if not condition:
            raise CoffRefusal(reason, detail)

    require(isinstance(obj, bytes) and 20 <= len(obj) <= 64 * 1024**2,
            'invalid_coff_size')
    machine, count, timestamp, symbol_offset, symbol_count, optional, flags = struct.unpack_from('<HHIIIHH', obj)
    require(machine in MACHINE_NAMES, 'unsupported_coff_machine')
    require(optional == 0, 'unsupported_coff_optional_header')
    header_end = 20 + count * 40
    require(0 < count <= 4096 and header_end <= len(obj), 'invalid_coff_section_table')
    require(symbol_count <= 250_000, 'coff_symbol_capacity_exceeded')
    ranges = [{'kind': 'headers', 'offset': 0, 'size': header_end}]
    intervals = [(0, header_end)]

    def span(offset, size, kind):
        require(offset >= header_end and 0 <= size <= len(obj) - offset,
                'invalid_coff_range', kind)
        if size:
            insertion = bisect_left(intervals, (offset, offset + size))
            require((insertion == 0 or intervals[insertion - 1][1] <= offset)
                    and (insertion == len(intervals) or offset + size <= intervals[insertion][0]),
                    'overlapping_coff_ranges', kind)
            intervals.insert(insertion, (offset, offset + size))
            ranges.append({'kind': kind, 'offset': offset, 'size': size})
        return obj[offset:offset + size]

    strings = b''
    if symbol_offset:
        span(symbol_offset, symbol_count * 18, 'symbols')
        string_offset = symbol_offset + symbol_count * 18
        require(string_offset + 4 <= len(obj), 'truncated_coff_string_table')
        string_size = struct.unpack_from('<I', obj, string_offset)[0]
        require(string_size >= 4, 'invalid_coff_string_table')
        strings = span(string_offset, string_size, 'strings')
    else:
        require(symbol_count == 0, 'missing_coff_symbol_table')

    name_cache = {}
    decoded_name_bytes = 0

    def string_name(offset):
        nonlocal decoded_name_bytes
        require(4 <= offset < len(strings), 'invalid_coff_string_offset')
        if offset in name_cache:
            return name_cache[offset]
        end = strings.find(b'\0', offset, offset + MAX_NAME_BYTES + 1)
        require(end >= 0 or len(strings) - offset <= MAX_NAME_BYTES,
                'coff_individual_name_capacity_exceeded')
        require(end >= 0, 'unterminated_coff_string')
        length = end - offset
        require(decoded_name_bytes + length <= MAX_TOTAL_NAME_BYTES,
                'coff_total_name_capacity_exceeded')
        name = strings[offset:end].decode('latin1')
        name_cache[offset] = name
        decoded_name_bytes += length
        return name

    def symbol_name(field):
        return (string_name(struct.unpack_from('<I', field, 4)[0])
                if field[:4] == b'\0' * 4 else field.split(b'\0', 1)[0].decode('latin1'))

    sections = []
    total_relocations = 0
    for index in range(count):
        offset = 20 + index * 40
        header = obj[offset:offset + 40]
        name = header[:8].split(b'\0', 1)[0]
        if name.startswith(b'/'):
            require(name[1:].isdigit(), 'unsupported_coff_section_name_encoding')
            decoded_name = string_name(int(name[1:]))
        else:
            decoded_name = name.decode('latin1')
        physical, virtual, size, raw_offset, reloc_offset, line_offset, nrel, nline, chars = struct.unpack_from('<IIIIIIHHI', header, 8)
        require(not chars & 0x1000000, 'coff_relocation_overflow_unsupported')
        total_relocations += nrel
        require(total_relocations <= 250_000, 'coff_relocation_capacity_exceeded')
        # Standard object relocations use section offsets. Nonzero VA requires
        # another explicit coordinate contract; retain no guessed subtraction.
        require(virtual == 0, 'unsupported_coff_section_virtual_address')
        if size and raw_offset == 0:
            require(chars & 0x80 and not chars & 0x60, 'missing_coff_section_data')
            data = b''  # Declared uninitialized storage, not missing raw bytes.
        else:
            data = span(raw_offset, size, f'section:{index + 1}:data') if size else b''
        reloc_raw = span(reloc_offset, nrel * 10, f'section:{index + 1}:relocations') if nrel else b''
        line_raw = span(line_offset, nline * 6, f'section:{index + 1}:lines') if nline else b''
        sections.append({'index': index + 1, 'name': decoded_name, 'rawHeader': header,
            'physicalSize': physical, 'virtualAddress': virtual, 'size': size,
            'offset': raw_offset, 'characteristics': chars, 'data': data,
            'sha256': hashlib.sha256(data).hexdigest(), 'relocationOffset': reloc_offset,
            'relocationCount': nrel, 'rawRelocations': reloc_raw, 'relocations': [],
            'lineOffset': line_offset, 'lineCount': nline, 'rawLines': line_raw})

    symbols = {}
    definitions = {}
    first_section_symbols = {}
    index = 0
    while index < symbol_count:
        offset = symbol_offset + index * 18
        record = obj[offset:offset + 18]
        name = symbol_name(record[:8])
        value, section, kind, storage, auxiliary_count = struct.unpack_from('<IhHBB', record, 8)
        require(index + auxiliary_count < symbol_count, 'truncated_coff_auxiliary_symbols')
        require(-2 <= section <= count, 'invalid_coff_symbol_section')
        auxiliaries = [{'index': index + 1 + number,
                        'raw': obj[offset + 18 * (number + 1):offset + 18 * (number + 2)]}
                       for number in range(auxiliary_count)]
        symbol = {'index': index, 'name': name, 'value': value, 'section': section,
                  'type': kind, 'storageClass': storage, 'raw': record, 'auxiliaries': auxiliaries}
        symbols[index] = symbol
        if section > 0:
            first_section_symbols.setdefault(section, index)
        if storage == 3 and kind == 0 and 1 <= section <= count and name == sections[section - 1]['name'] and auxiliaries:
            require(auxiliary_count == 1 and value == 0 and section not in definitions,
                    'invalid_coff_section_definition')
            length, relocations, lines, checksum, association, selection = struct.unpack_from('<IHHIHB', auxiliaries[0]['raw'])
            current = sections[section - 1]
            require(length == current['size'] and relocations == current['relocationCount']
                    and lines == current['lineCount'], 'coff_section_definition_mismatch')
            require(selection <= 7, 'unsupported_coff_comdat_selection')
            require(bool(selection) == bool(current['characteristics'] & 0x1000),
                    'coff_comdat_definition_mismatch')
            if selection == 5:
                require(1 <= association <= count and association != section
                        and sections[association - 1]['characteristics'] & 0x1000,
                        'invalid_coff_comdat_association')
            definitions[section] = {'symbolIndex': index, 'length': length,
                'relocationCount': relocations, 'lineCount': lines, 'checksum': checksum,
                'selection': selection, 'association': association,
                'reserved': auxiliaries[0]['raw'][15], 'unused': auxiliaries[0]['raw'][15:18],
                'raw': auxiliaries[0]['raw']}
        index += auxiliary_count + 1

    for section in sections:
        if section['characteristics'] & 0x1000:
            require(section['index'] in definitions, 'missing_coff_comdat_definition')
            require(first_section_symbols.get(section['index']) == definitions[section['index']]['symbolIndex'],
                    'invalid_coff_comdat_symbol_order')
        seen = set()
        current = section['index']
        while current in definitions and definitions[current]['selection'] == 5:
            require(current not in seen, 'cyclic_coff_comdat_association')
            seen.add(current)
            current = definitions[current]['association']
        for number in range(section['relocationCount']):
            record = section['rawRelocations'][number * 10:(number + 1) * 10]
            operand, symbol_index, kind = struct.unpack('<IIH', record)
            metadata = RELOCATION_METADATA.get((machine, kind))
            name, width = metadata if metadata else (None, None)
            if metadata and kind != 0:
                require(symbol_index in symbols, 'invalid_coff_relocation_symbol')
            if width:
                require(operand + width <= len(section['data']), 'invalid_coff_relocation_operand')
            section['relocations'].append({'index': number, 'offset': operand,
                'symbolIndex': symbol_index, 'type': kind, 'name': name, 'operandWidth': width,
                'symbolBinding': 'primary' if metadata and kind != 0 else 'ignored' if kind == 0 else 'unclassified',
                'addendBytes': section['data'][operand:operand + width] if width else b'' if width == 0 else None,
                'fixupSupported': (machine, kind) in RELOCATIONS, 'raw': record})

    ranges.sort(key=lambda item: (item['offset'], item['kind']))
    require(all(left['offset'] + left['size'] <= right['offset']
                for left, right in zip(ranges, ranges[1:])), 'overlapping_coff_ranges')
    unclaimed = []
    end = 0
    for item in ranges:
        if end < item['offset']:
            unclaimed.append({'offset': end, 'size': item['offset'] - end,
                              'data': obj[end:item['offset']]})
        end = item['offset'] + item['size']
    if end < len(obj):
        unclaimed.append({'offset': end, 'size': len(obj) - end, 'data': obj[end:]})
    return {'schema': SCHEMA, 'sha256': hashlib.sha256(obj).hexdigest(), 'size': len(obj),
        'machine': machine, 'timestamp': timestamp, 'characteristics': flags,
        'sectionCount': count, 'symbolOffset': symbol_offset, 'symbolCount': symbol_count,
        'sections': sections, 'symbols': symbols, 'sectionDefinitions': definitions,
        'stringTable': strings, 'ranges': ranges, 'unclaimedRanges': unclaimed,
        'claim': 'Object inventory only; no function extent, link result or byte-equivalence proof.'}


def compiler_function_extents(obj: bytes) -> dict:
    """Read symbol-bound x86 FPO extents independently of target image bytes.

    Supported metadata is an initialized ``.debug$F`` array of 16-byte
    FPO_DATA records with one DIR32NB relocation at each record's start.
    This records emitted primary ranges, not COMDAT selection, associated
    funclet extents, target identity, linked contribution or source acceptance.
    Layout: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-fpo_data
    """
    inventory = parse_object_inventory(obj)
    sections = {section['index']: section for section in inventory['sections']}
    records = []
    bindings = set()
    spans = {}
    metadata_sections = [section for section in inventory['sections']
                         if section['name'] == '.debug$F']
    if metadata_sections and inventory['machine'] != MACHINE_I386:
        raise CoffRefusal('unsupported_fpo_machine')
    total_records = 0
    for metadata in metadata_sections:
        data = metadata['data']
        if not metadata['size'] or len(data) != metadata['size'] or len(data) % 16:
            raise CoffRefusal('invalid_fpo_record_array')
        total_records += len(data) // 16
        if total_records > 250_000:
            raise CoffRefusal('fpo_record_capacity_exceeded')
        relocations = {}
        for relocation in metadata['relocations']:
            offset = relocation['offset']
            if (relocation['type'] != 0x7 or offset % 16
                    or offset in relocations or offset + 16 > len(data)):
                raise CoffRefusal('invalid_fpo_record_relocation')
            relocations[offset] = relocation
        if len(relocations) != len(data) // 16:
            raise CoffRefusal('missing_fpo_record_relocation')
        for offset in range(0, len(data), 16):
            relocation = relocations[offset]
            symbol_index = relocation['symbolIndex']
            symbol = inventory['symbols'].get(symbol_index)
            if (symbol is None or symbol['section'] <= 0
                    or (symbol['type'] & 0x30) != 0x20
                    or symbol['storageClass'] not in (2, 3, 6)):
                raise CoffRefusal('invalid_fpo_function_symbol')
            code = sections[symbol['section']]
            if not code['characteristics'] & 0x20 or len(code['data']) != code['size']:
                raise CoffRefusal('invalid_fpo_code_section')
            implicit_start, size, _locals, _params, flags = struct.unpack_from('<IIIHH', data, offset)
            start = symbol['value'] + implicit_start
            if (symbol['value'] >= code['size'] or start >= 1 << 32
                    or not size or start + size > code['size']):
                raise CoffRefusal('invalid_fpo_function_range')
            if flags & 0x2000 or (flags & 0xff) > size:
                raise CoffRefusal('invalid_fpo_record_flags')
            association = metadata['index']
            associated = False
            while (association in inventory['sectionDefinitions']
                   and inventory['sectionDefinitions'][association]['selection'] == 5):
                associated = True
                association = inventory['sectionDefinitions'][association]['association']
            if associated and association != symbol['section']:
                raise CoffRefusal('fpo_association_function_mismatch')
            if symbol_index in bindings:
                raise CoffRefusal('ambiguous_fpo_function_binding')
            bindings.add(symbol_index)
            spans.setdefault(symbol['section'], []).append((start, start + size))
            records.append({'symbolIndex': symbol_index, 'section': symbol['section'],
                            'offset': start, 'size': size,
                            'metadataSection': metadata['index'], 'recordOffset': offset,
                            'source': 'FPO_DATA'})
    for ranges in spans.values():
        ordered = sorted(ranges)
        if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
            raise CoffRefusal('overlapping_fpo_function_extents')
    return {'schema': 'agentdecompile.compiler-function-extents/v1',
            'objectSha256': inventory['sha256'], 'records': records,
            'claim': 'Compiler-emitted FPO extents only; not target identity, COMDAT selection, linked closure or recovered-source proof.'}
