"""Bounded, observed C contribution to a PE reconstruction, never a linker receipt.

The reconstruction causal root is the owned native clang cc1 invocation below.
Only its objects and observations returned by our writer are admitted there.
Owned MSVC same-build captures have a separate emission-only capability; they
cannot enter the clang reconstruction or establish linked contribution proof.
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
# independently checked by rpm -V on 2026-10-13. The closure pin covers the
# compiler and all 14 resolved ELF loader/shared-library dependencies. Other
# builds need an explicitly reviewed supported profile; there is no auto-enroll.
SUPPORTED_COMPILER_SHA256 = "4ea85504401d9f5c05109d6cb05778b241aa8d56fde1da2e5bc7ba46cffd44f5"
SUPPORTED_TOOLCHAIN_CLOSURE_SHA256 = "56caa5af677c4569b31934bf77c6f56f299366ac5b8e2f829dcb41906b34f058"
# Identity registration is independent of caller-controlled JSON or booleans.
_COMPILES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_IMAGES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_NATIVE_COMPILES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_NATIVE_PLACEMENTS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_NATIVE_LINKS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


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
class NativeCompileObservation:
    """Process-local MSVC emission capability, never a clang acceptance token."""
    record_json: str

    @property
    def record(self):
        return json.loads(self.record_json)


def select_native_coff_closure(objects, placements, externals, *, image_base: int,
                               metadata_policy: dict) -> dict:
    """Select and relocate a bounded explicit reconstruction input closure.

    This is an owned reconstruction-link policy, not Microsoft's historical
    linker selection. Inputs are ordered {object: bytes, sha256: str} records;
    placements bind objectSha256, section and address. No target operands are
    consulted to choose winners. Only unique NODUPLICATES/ANY roots and their
    associations are supported. Default libraries are explicitly suppressed in
    favor of supplied external bindings; omitted SafeSEH/debug metadata is
    recorded, never silently treated as a complete native linker receipt.
    """
    from .coff_object import parse_object_inventory
    from .coff_fixup_roundtrip import place_sections

    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    require(isinstance(objects, (list, tuple)) and 0 < len(objects) <= 64,
            'native_closure_object_capacity')
    require(isinstance(placements, (list, tuple)) and 0 < len(placements) <= 4096,
            'native_closure_placement_capacity')
    require(type(image_base) is int and 0 <= image_base < 1 << 32,
            'native_closure_image_base')
    require(metadata_policy == {'defaultLibraries': 'suppress-explicit-externals',
                                'safeSEH': 'omit-table', 'debug': 'discard'},
            'native_closure_metadata_policy_unsupported')
    require(isinstance(externals, dict) and len(externals) <= 4096 and all(
        isinstance(name, str) and 0 < len(name) <= 4096 and '\0' not in name
        and type(address) is int and 0 <= address < 1 << 32
        for name, address in externals.items()), 'native_closure_external_bindings')
    inputs = []
    by_digest = {}
    total = section_count = symbol_count = relocation_count = 0
    for entry in objects:
        require(isinstance(entry, dict), 'native_closure_input_record')
        obj = entry.get('object')
        require(isinstance(obj, bytes) and 20 <= len(obj) <= 64 * 1024**2,
                'native_closure_input_bytes')
        total += len(obj)
        require(total <= 64 * 1024**2, 'native_closure_total_object_capacity')
        object_hash = digest(obj)
        require(entry.get('sha256') == object_hash and object_hash not in by_digest,
                'native_closure_object_digest_or_duplicate')
        inventory = parse_object_inventory(obj)
        require(inventory['machine'] == 0x14c and inventory['characteristics'] == 0,
                'native_closure_machine_or_object_flags')
        section_count += len(inventory['sections'])
        symbol_count += len(inventory['symbols'])
        relocation_count += sum(section['relocationCount'] for section in inventory['sections'])
        require(section_count <= 4096 and symbol_count <= 250000 and relocation_count <= 250000,
                'native_closure_inventory_capacity')
        public_by_section = {}
        for symbol in inventory['symbols'].values():
            require(symbol['storageClass'] != 105 and not (
                symbol['section'] == 0 and (symbol['value'] or symbol['auxiliaries'])),
                'native_closure_weak_common_or_aux_external')
            if symbol['storageClass'] == 2 and symbol['section'] > 0:
                public_by_section.setdefault(symbol['section'], []).append(symbol)
        item = {'object': obj, 'sha256': object_hash, 'inventory': inventory,
                'placements': {}, 'metadata': [], 'runtime': set(),
                'publicBySection': public_by_section}
        inputs.append(item)
        by_digest[object_hash] = item
    ranges = []
    for placement in placements:
        require(isinstance(placement, dict), 'native_closure_placement_record')
        require(isinstance(placement.get('objectSha256'), str),
                'native_closure_placement_digest')
        item = by_digest.get(placement['objectSha256'])
        section_index, address = placement.get('section'), placement.get('address')
        require(item is not None and type(section_index) is int
                and 1 <= section_index <= len(item['inventory']['sections'])
                and type(address) is int and 0 <= address < 1 << 32,
                'native_closure_placement_identity')
        require(section_index not in item['placements'], 'native_closure_duplicate_placement')
        section = item['inventory']['sections'][section_index - 1]
        require(section['size'] > 0 and address + section['size'] <= 1 << 32
                and len(section['data']) == section['size'],
                'native_closure_placement_bounds_or_uninitialized')
        alignment = (section['characteristics'] >> 20) & 15
        require(1 <= alignment <= 14 and address % (1 << (alignment - 1)) == 0,
                'native_closure_placement_alignment')
        item['placements'][section_index] = address
        ranges.append((address, address + section['size']))
    ranges.sort()
    require(all(left[1] <= right[0] for left, right in zip(ranges, ranges[1:])),
            'native_closure_overlapping_placements')

    roots = {}
    definitions = {}
    for item in inputs:
        inventory = item['inventory']
        for section in inventory['sections']:
            number, name = section['index'], section['name']
            if not section['size']:
                require(not section['relocations'], 'native_closure_empty_relocations')
                continue
            if name == '.drectve':
                require(section['characteristics'] & 0x800 and not section['relocations']
                        and not section['characteristics'] & (0x20 | 0x80 | 0x20000000 | 0x80000000)
                        and section['size'] <= 65536, 'native_closure_directive_section')
                try:
                    text = section['data'].decode('ascii')
                except UnicodeDecodeError as exc:
                    raise ValueError('native_closure_directive_encoding') from exc
                pattern = re.compile(r'\s*/DEFAULTLIB:(?:"([A-Za-z0-9_.-]+)"|([A-Za-z0-9_.-]+))', re.I)
                libraries, cursor = [], 0
                while cursor < len(text.rstrip()):
                    match = pattern.match(text, cursor)
                    require(match is not None, 'native_closure_directive_unsupported')
                    libraries.append(match.group(1) or match.group(2))
                    cursor = match.end()
                    require(len(libraries) <= 64, 'native_closure_directive_capacity')
                item['metadata'].append({'section': number, 'kind': 'directives',
                    'defaultLibraries': libraries, 'policy': 'suppressed; explicit external bindings only'})
            elif name in ('.debug$S', '.debug$F'):
                require(section['characteristics'] & 0x02000000
                        and section['characteristics'] & 0x40
                        and not section['characteristics'] & (0x20 | 0x80 | 0x20000000 | 0x80000000),
                        'native_closure_debug_not_discardable')
                item['metadata'].append({'section': number, 'kind': 'debug', 'policy': 'discard'})
            elif name == '.sxdata':
                require(section['characteristics'] & 0x200 and not section['relocations']
                        and not section['characteristics'] & (0x20 | 0x80 | 0x20000000 | 0x80000000)
                        and section['size'] % 4 == 0 and section['size'] <= 16384,
                        'native_closure_sxdata_structure')
                handlers = []
                for (index,) in struct.iter_unpack('<I', section['data']):
                    symbol = inventory['symbols'].get(index)
                    require(symbol is not None and symbol['section'] in item['placements'],
                            'native_closure_sxdata_unselected_handler')
                    owner = inventory['sections'][symbol['section'] - 1]
                    require(owner['characteristics'] & 0x20 and owner['characteristics'] & 0x20000000
                            and symbol['value'] < owner['size'], 'native_closure_sxdata_handler_bounds')
                    handlers.append({'symbolIndex': index, 'section': symbol['section'],
                        'offset': symbol['value'], 'address': item['placements'][symbol['section']] + symbol['value']})
                require(len({row['address'] for row in handlers}) == len(handlers),
                        'native_closure_sxdata_duplicate_handler')
                item['metadata'].append({'section': number, 'kind': 'safeSEH',
                    'handlers': handlers, 'policy': 'omit-table; target policy must be checked by publisher'})
            else:
                require(not section['characteristics'] & (0x200 | 0x800 | 0x02000000),
                        'native_closure_unknown_metadata')
                require(number in item['placements'], 'native_closure_unplaced_runtime_section')
                item['runtime'].add(number)
            definition = inventory['sectionDefinitions'].get(number, {})
            selection = definition.get('selection', 0)
            require(selection in (0, 1, 2, 5), 'native_closure_comdat_selection_unsupported')
            if selection == 5:
                parent = definition['association']
                seen = {number}
                while inventory['sectionDefinitions'].get(parent, {}).get('selection') == 5:
                    require(parent not in seen, 'native_closure_association_cycle')
                    seen.add(parent)
                    parent = inventory['sectionDefinitions'][parent]['association']
                require(parent in item['placements'], 'native_closure_unselected_association_root')
            elif selection:
                keys = [symbol['name'] for symbol in item['publicBySection'].get(number, ())
                        if symbol['value'] == 0]
                require(len(keys) == 1, 'native_closure_comdat_key_ambiguous')
                require(keys[0] not in roots, 'native_closure_duplicate_comdat_key')
                roots[keys[0]] = {'objectSha256': item['sha256'], 'section': number,
                                 'selection': selection, 'policy': 'unique explicit input'}
        require(set(item['placements']) == item['runtime'], 'native_closure_metadata_placement')
        for symbol in inventory['symbols'].values():
            if symbol['storageClass'] != 2 or symbol['section'] <= 0:
                continue
            require(symbol['section'] in item['runtime'] and not symbol['auxiliaries'],
                    'native_closure_public_definition_unsupported')
            require(symbol['name'] not in definitions and symbol['name'] not in externals,
                    'native_closure_duplicate_or_shadowed_definition')
            section = inventory['sections'][symbol['section'] - 1]
            require(symbol['value'] < section['size'], 'native_closure_public_definition_bounds')
            definitions[symbol['name']] = item['placements'][symbol['section']] + symbol['value']
    bindings = {**externals, **definitions}
    emitted = []
    for item in inputs:
        placed = place_sections(item['object'], item['placements'], bindings, image_base=image_base)
        emitted.extend({**section, 'objectSha256': item['sha256']} for section in placed['sections'])
    return {'schema': 'agentdecompile.native-coff-closure-selection/v1',
            'diagnosticOnly': True, 'accepted': False, 'byteVerified': False,
            'wholeImageVerified': False, 'closureSelected': True,
            'orderedObjectSha256': [item['sha256'] for item in inputs],
            'layoutSha256': digest(canonical(list(placements))),
            'externalBindingsSha256': digest(canonical(externals)),
            'metadataPolicy': dict(metadata_policy), 'roots': roots,
            'metadata': [{'objectSha256': item['sha256'], **entry}
                         for item in inputs for entry in item['metadata']],
            'sections': emitted,
            'claim': 'Explicit-input reconstruction selection and emitted fixups only; not producer authenticity, source acceptance, original linker selection or whole-image proof.'}


def _native_emitted_region(obj: bytes) -> dict:
    """Qualify one relocation-free primary range from compiler FPO metadata."""
    from .coff_object import compiler_function_extents, parse_object_inventory

    inventory = parse_object_inventory(obj)
    extents = compiler_function_extents(obj)['records']
    functions = [symbol for symbol in inventory['symbols'].values()
                 if symbol['section'] > 0 and (symbol['type'] & 0x30) == 0x20]
    if len(functions) != 1 or functions[0]['storageClass'] != 2:
        raise ValueError('native_ambiguous_primary_function')
    entry = functions[0]
    bound = [extent for extent in extents if extent['symbolIndex'] == entry['index']]
    if len(bound) != 1 or bound[0]['offset'] != entry['value']:
        raise ValueError('native_missing_independent_primary_extent')
    extent = bound[0]
    section = inventory['sections'][entry['section'] - 1]
    if not (section['characteristics'] & 0x20 and section['characteristics'] & 0x20000000):
        raise ValueError('native_primary_not_executable_code')
    if section['relocations']:
        raise ValueError('native_primary_relocations_unsupported')
    for other in inventory['sections']:
        if other['index'] == entry['section'] or not other['size']:
            continue
        # Object metadata is not runtime contribution. Associated code/data
        # (including EH and SafeSEH) requires a separate supported closure.
        if (other['characteristics'] & (0x200 | 0x800)
                or other['name'].startswith('.debug') and other['characteristics'] & 0x02000000):
            continue
        raise ValueError('native_associated_runtime_contribution_unsupported')
    return {**extent, 'symbol': entry['name'],
            'objectOffset': section['offset'] + extent['offset'],
            'sectionSize': section['size'],
            'unqualifiedSectionBytes': section['size'] - extent['size'],
            'comdatSelection': inventory['sectionDefinitions'].get(entry['section'], {}).get('selection', 0),
            'sha256': digest(section['data'][extent['offset']:extent['offset'] + extent['size']])}


def _issue_native_compile_observation(producer, event: dict) -> NativeCompileObservation:
    """Issue only from the owned compile/link capture, not caller JSON imports."""
    from . import compile_link, compiler_msvc71

    # The existing owned producer function is a stable process-local identity,
    # including across in-place code reloads; JSON does not confer membership.
    if producer is not compile_link.compile_and_link_tree:
        raise ValueError('unowned_native_emission_producer')
    invocation = event.get('invocation')
    if (not isinstance(invocation, dict) or invocation.get('script') is not True
            or not isinstance(invocation.get('compiler'), str)
            or Path(invocation['compiler']).resolve() != Path(compiler_msvc71.__file__).resolve()):
        raise ValueError('unsupported_native_emission_adapter')
    source, obj = event.get('sourceBytes'), event.get('objectBytes')
    normalized = event.get('normalizedInputBytes')
    if (not isinstance(source, bytes) or not isinstance(obj, bytes)
            or not isinstance(normalized, bytes) or not normalized
            or not source or not obj or max(len(source), len(obj), len(normalized)) > 64 * 1024**2
            or digest(source) != event.get('sourceSha256')
            or digest(normalized) != event.get('normalizedInputSha256')
            or digest(obj) != event.get('objectSha256')):
        raise ValueError('invalid_native_emission_capture')
    fresh, reused = event.get('freshCompilation'), event.get('reusedObject')
    if (type(fresh) is not bool or type(reused) is not bool or fresh == reused
            or invocation.get('compilerExecuted') is not fresh):
        raise ValueError('invalid_native_emission_execution_basis')
    record = {key: event.get(key) for key in (
        'sourcePath', 'objectPath', 'sourceSha256', 'normalizedInputSha256',
        'objectSha256', 'sourceLanguage', 'freshCompilation', 'reusedObject',
        'compilerIdentity', 'invocation')}
    record.update({'schema': 'agentdecompile.native-emission-observation/v1',
                   'diagnosticOnly': True, 'byteVerified': False,
                   'wholeImageVerified': False, 'accepted': False,
                   'emittedRegionQualified': False,
                   'claim': 'Owned same-build MSVC emission only; not complete toolchain, target binding, COMDAT selection or linked contribution proof.'})
    try:
        record['emittedRegion'] = _native_emitted_region(obj)
        record['emittedRegionQualified'] = True
    except ValueError as exc:
        record['emittedRegionRefusal'] = str(exc)
    payload = json.dumps(record, sort_keys=True, allow_nan=False)
    if len(payload.encode()) > 2 * 1024**2:
        raise ValueError('native_emission_metadata_capacity')
    observation = NativeCompileObservation(payload)
    _NATIVE_COMPILES[observation] = (payload, source, obj)
    return observation


def native_emitted_region(observation) -> tuple[dict | None, bytes | None, str | None]:
    """Read a producer-issued region; retained JSON cannot recreate authority."""
    if not isinstance(observation, NativeCompileObservation):
        return None, None, 'untrusted_native_compile_observation'
    captured = _NATIVE_COMPILES.get(observation)
    if captured is None or captured[0] != observation.record_json:
        return None, None, 'untrusted_native_compile_observation'
    record = observation.record
    if not record['emittedRegionQualified']:
        return record, None, record.get('emittedRegionRefusal', 'native_region_unqualified')
    try:
        region = _native_emitted_region(captured[2])
        if region != record['emittedRegion']:
            raise ValueError('native_emitted_region_changed')
        data = captured[2][region['objectOffset']:region['objectOffset'] + region['size']]
        return record, data, None
    except ValueError as exc:
        return record, None, str(exc)


def observe_native_target_region(observation, *, target_raw: bytes, address: int,
                                 size: int, db, binary_id: int) -> dict:
    """Compare a captured native range to an independently selected DB region.

    This is an emission comparison, not a reconstruction/writer capability.
    COMDAT selection, toolchain closure and linked-image causality are unproved.
    """
    result = {'schema': 'agentdecompile.native-target-observation/v1',
              'diagnosticOnly': True, 'accepted': False, 'byteVerified': False,
              'wholeImageVerified': False, 'rawEqual': False,
              'claim': 'Captured native emitted-range comparison only; not linked contribution proof.'}
    record, emitted, refusal = native_emitted_region(observation)
    if record is not None:
        result['compilation'] = record
    if refusal:
        return {**result, 'reason': refusal}
    try:
        if (not isinstance(target_raw, bytes) or not 0 < len(target_raw) <= 512 * 1024**2
                or type(address) is not int or type(size) is not int or size <= 0
                or db is None or type(binary_id) is not int):
            raise ValueError('invalid_native_selected_target_capture')
        target_sha = digest(target_raw)
        selected = _db_row(db, binary_id, address, size, target_sha256=target_sha)
        region = pe_region(target_raw, address, size)
        if record['emittedRegion']['size'] != size:
            raise ValueError('native_emitted_target_extent_mismatch')
        target = target_raw[region['offset']:region['offset'] + size]
        result.update({'selectedDatabaseRow': selected, 'targetSha256': target_sha,
                       'targetRegion': region, 'rawEqual': emitted == target,
                       'differentByteCount': sum(a != b for a, b in zip(emitted, target)),
                       'reason': 'native_emitted_range_equal' if emitted == target else 'native_emitted_range_differs'})
    except ValueError as exc:
        result['reason'] = str(exc)
    return result


@dataclass(frozen=True, eq=False)
class NativeLinkObservation:
    """Owned ordered-input/map capture; not complete native linker authority."""
    record_json: str

    @property
    def record(self):
        return json.loads(self.record_json)


def _issue_native_link_observation(producer, capture: dict) -> NativeLinkObservation:
    from . import compile_link

    if producer is not compile_link.link_msvc:
        raise ValueError('unowned_native_link_producer')
    mapping = capture.get('mapBytes')
    image = capture.get('imageBytes')
    output = capture.get('output')
    if (not isinstance(mapping, bytes) or not 0 < len(mapping) <= 8 * 1024**2
            or not isinstance(image, bytes) or not 0 < len(image) <= 256 * 1024**2
            or capture.get('freshLinkedCandidate') is not True
            or digest(mapping) != capture.get('map', {}).get('sha256')
            or not isinstance(output, dict) or output.get('size') != len(image)
            or output.get('sha256') != digest(image)):
        raise ValueError('invalid_native_link_capture')
    record = {key: value for key, value in capture.items()
              if key not in ('mapBytes', 'imageBytes')}
    record.update({'schema': 'agentdecompile.native-link-observation/v1',
                   'diagnosticOnly': True, 'accepted': False,
                   'linkedSourceContributionVerified': False,
                   'claim': 'Observed ordered explicit objects, linker image, map and output only; libraries/environment/dependencies and ICF selection remain uncertified.'})
    payload = canonical(record).decode()
    if len(payload.encode()) > 2 * 1024**2:
        raise ValueError('native_link_metadata_capacity')
    observation = NativeLinkObservation(payload)
    _NATIVE_LINKS[observation] = (payload, mapping, image)
    return observation


def native_link_selection_evidence(compilation, linking) -> dict:
    """Compare a fresh, relocation-free emission at the linker-mapped PE VA.

    The map and final-image bytes are retained only in process-local authority.
    A raw byte match proves this function's observed contribution in this one
    linked candidate, not complete linker closure, source correctness, target
    equivalence, or whole-image ownership. COMDAT and relocation-bearing code
    remain outside this narrow path.
    """
    result = {'selectedObjectMapped': False, 'comdatSelectionVerified': False,
              'nativeEligibleLinkClosure': False, 'diagnosticOnly': True,
              'accepted': False, 'reason': 'untrusted_native_link_observation'}
    if not isinstance(linking, NativeLinkObservation):
        return result
    captured = _NATIVE_LINKS.get(linking)
    if captured is None or captured[0] != linking.record_json:
        return result
    if not isinstance(compilation, NativeCompileObservation):
        return {**result, 'reason': 'untrusted_native_compile_observation'}
    compiled_capture = _NATIVE_COMPILES.get(compilation)
    if compiled_capture is None or compiled_capture[0] != compilation.record_json:
        return {**result, 'reason': 'untrusted_native_compile_observation'}
    compiled = compilation.record
    if compiled.get('freshCompilation') is not True or compiled.get('reusedObject') is not False:
        return {**result, 'reason': 'native_link_contribution_requires_fresh_compilation'}
    # A MAP records symbol selection independently of whether we can place the
    # function's relocations, unwind closure or emitted range. Do not require a
    # placement capability merely to inspect owned linker provenance.
    from .coff_object import parse_object_inventory

    try:
        inventory = parse_object_inventory(compiled_capture[2])
        functions = [entry for entry in inventory['symbols'].values()
                     if entry['storageClass'] == 2 and entry['section'] > 0
                     and (entry['type'] & 0x30) == 0x20
                     and entry['value'] < inventory['sections'][entry['section'] - 1]['size']
                     and inventory['sections'][entry['section'] - 1]['characteristics'] & 0x20
                     and inventory['sections'][entry['section'] - 1]['characteristics'] & 0x20000000]
        if len(functions) != 1:
            raise ValueError('native_map_primary_symbol_ambiguous')
        symbol = functions[0]['name']
    except ValueError as exc:
        return {**result, 'reason': str(exc)}
    _, _data, refusal = native_emitted_region(compilation)
    result.update({'emittedRegionQualified': refusal is None,
                   'emittedRegionRefusal': refusal})
    record = linking.record
    objects = record.get('objects')
    if not isinstance(objects, list) or len(objects) > 4096:
        return {**result, 'reason': 'native_link_object_inventory_unsupported'}
    matching = [entry for entry in objects
                if entry.get('sha256') == compiled['objectSha256']
                and entry.get('path') == compiled['objectPath']]
    if len(matching) != 1:
        return {**result, 'reason': 'native_compile_not_unique_link_input'}
    try:
        text = captured[1].decode('ascii')
    except UnicodeDecodeError:
        return {**result, 'reason': 'native_link_map_encoding_unsupported'}
    pattern = re.compile(r'^\s*([0-9A-Fa-f]{4}):([0-9A-Fa-f]{8,16})\s+(\S+)\s+([0-9A-Fa-f]{8,16})\s+f\s+(\S+)\s*$')
    rows = [match for line in text.splitlines() if (match := pattern.fullmatch(line))
            and match.group(3) == symbol]
    if len(rows) != 1:
        return {**result, 'reason': 'native_link_map_symbol_missing_or_ambiguous'}
    from pathlib import PureWindowsPath

    origin = rows[0].group(5)
    # Library-member notation is not an explicit object input. A basename is
    # accepted only when it uniquely resolves within the ordered owned inputs.
    drive_qualified_path = re.match(r'^[A-Za-z]:[\\/]', origin) is not None
    if ':' in origin and not drive_qualified_path:
        return {**result, 'reason': 'native_link_library_or_path_origin_unsupported'}
    basename = PureWindowsPath(origin).name.casefold()
    owners = [entry for entry in objects
              if PureWindowsPath(str(entry['path'])).name.casefold() == basename]
    if len(owners) != 1 or owners[0] != matching[0]:
        return {**result, 'reason': 'native_link_map_object_origin_ambiguous'}
    linked_address = int(rows[0].group(4), 16)
    _, emitted, refusal = native_emitted_region(compilation)
    if refusal or emitted is None:
        return {**result, 'reason': refusal or 'native_emitted_bytes_unavailable'}
    if symbol != compiled.get('emittedRegion', {}).get('symbol'):
        return {**result, 'reason': 'native_map_symbol_differs_from_emitted_function'}
    image = captured[2]
    if (not isinstance(image, bytes) or len(image) != record.get('output', {}).get('size')
            or digest(image) != record.get('output', {}).get('sha256')):
        return {**result, 'reason': 'native_linked_image_capture_invalid'}
    try:
        region = pe_region(image, linked_address, len(emitted))
        start = region['offset']
        linked_bytes = image[start:start + len(emitted)]
    except (ValueError, struct.error) as exc:
        return {**result, 'reason': f'native_linked_function_region_unmapped: {exc}'}
    raw_equal = linked_bytes == emitted
    return {**result, 'selectedObjectMapped': True,
            'symbol': symbol, 'linkedAddress': linked_address,
            'linkedSection': int(rows[0].group(1), 16),
            'linkedSectionOffset': int(rows[0].group(2), 16),
            'object': matching[0], 'map': record['map'], 'output': record['output'],
            'linkedImageRegion': region,
            'linkedContributionRawEqual': raw_equal,
            'linkedContributionSha256': digest(linked_bytes),
            'emittedRegionSha256': digest(emitted),
            'diagnosticOnly': True, 'accepted': False,
            'reason': ('fresh_compiled_function_bytes_observed_at_mapped_pe_address'
                       if raw_equal else 'mapped_pe_bytes_differ_from_fresh_compiler_emission')}


@dataclass(frozen=True, eq=False)
class NativePlacementObservation:
    """Owned memory-writer observation, separate from linked-image authority."""
    record_json: str

    @property
    def record(self):
        return json.loads(self.record_json)


def _native_placement_entry(observation, *, target_raw, address, size, db, binary_id):
    """Qualify one owned hole without allocating a whole preserved-floor image."""
    comparison = observe_native_target_region(observation, target_raw=target_raw,
                                              address=address, size=size, db=db,
                                              binary_id=binary_id)
    if not comparison['rawEqual']:
        raise ValueError(comparison['reason'])
    record, data, refusal = native_emitted_region(observation)
    if refusal:
        raise ValueError(refusal)
    if record['emittedRegion']['comdatSelection']:
        raise ValueError('native_comdat_link_selection_unproved')
    captured = _NATIVE_COMPILES[observation]
    if not is_real_c(captured[1].decode('utf-8')):
        raise ValueError('native_assembly_floor_not_source_contribution')
    identity = digest(canonical({'object': record['objectSha256'],
                                 'source': record['sourceSha256'],
                                 'address': address, 'size': size}))
    return {'identity': identity, 'region': comparison['targetRegion'], 'comparison': comparison,
            'objectOffset': record['emittedRegion']['objectOffset'], 'data': data}


def _native_closure_target(target_raw, image_base):
    """Check the supported PE policy before omitting compiler link metadata."""
    if not isinstance(target_raw, bytes) or not 0 < len(target_raw) <= 64 * 1024**2:
        raise ValueError('native_closure_target_capacity')
    try:
        pe = struct.unpack_from('<I', target_raw, 0x3c)[0]
        optional = pe + 24
        machine, count = struct.unpack_from('<HH', target_raw, pe + 4)
        optional_size = struct.unpack_from('<H', target_raw, pe + 20)[0]
        if (target_raw[:2] != b'MZ' or target_raw[pe:pe + 4] != b'PE\0\0'
                or machine != 0x14c or not 1 <= count <= 96 or optional_size < 96
                or struct.unpack_from('<H', target_raw, optional)[0] != 0x10b
                or struct.unpack_from('<I', target_raw, optional + 28)[0] != image_base):
            raise ValueError('native_closure_target_header_or_image_base')
        directories = struct.unpack_from('<I', target_raw, optional + 92)[0]
        if directories > 16 or 96 + directories * 8 > optional_size:
            raise ValueError('native_closure_target_directory_bounds')
        # This writer does not regenerate a base-relocation or SafeSEH table.
        # A preserved table would retain target-derived selection authority.
        for index in (5, 10):
            if directories > index and any(struct.unpack_from('<II', target_raw,
                                                             optional + 96 + index * 8)):
                raise ValueError('native_closure_target_relocation_or_load_config_unsupported')
        table = optional + optional_size
        if table + count * 40 > len(target_raw):
            raise ValueError('native_closure_target_section_table')
        sections = []
        for index in range(count):
            start = table + index * 40
            virtual_size, rva, raw_size, offset = struct.unpack_from('<IIII', target_raw, start + 8)
            flags = struct.unpack_from('<I', target_raw, start + 36)[0]
            if raw_size and (offset < table + count * 40 or offset + raw_size > len(target_raw)):
                raise ValueError('native_closure_target_raw_bounds')
            sections.append({'index': index + 1, 'offset': offset, 'size': raw_size,
                             'virtualSize': virtual_size, 'rva': rva, 'characteristics': flags})
        spans = sorted((item['offset'], item['offset'] + item['size'])
                       for item in sections if item['size'])
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            raise ValueError('native_closure_target_raw_overlap')
        return sections
    except struct.error as exc:
        raise ValueError('native_closure_target_truncated') from exc


def _native_closure_plan(closure, *, target_raw, db, binary_id):
    """Relocate authentic captures; JSON layout is never producer authority."""
    from .coff_object import parse_object_inventory

    if (not isinstance(closure, dict) or set(closure) != {
            'observations', 'placements', 'externals', 'image_base', 'metadata_policy',
            'primary_regions', 'target_sha256'} or not isinstance(target_raw, bytes)
            or closure['target_sha256'] != digest(target_raw)
            or db is None or type(binary_id) is not int):
        raise ValueError('native_closure_request_or_target_identity')
    capabilities = closure['observations']
    if not isinstance(capabilities, (list, tuple)) or not 0 < len(capabilities) <= 64:
        raise ValueError('native_closure_capture_capacity')
    objects, inventories = [], {}
    for capability in capabilities:
        captured = _NATIVE_COMPILES.get(capability) if isinstance(capability, NativeCompileObservation) else None
        if captured is None or captured[0] != capability.record_json:
            raise ValueError('untrusted_native_compile_observation')
        record = capability.record
        if (digest(captured[1]) != record['sourceSha256']
                or digest(captured[2]) != record['objectSha256']
                or not is_real_c(captured[1].decode('utf-8'))):
            raise ValueError('native_closure_source_or_object_identity')
        objects.append({'object': captured[2], 'sha256': record['objectSha256']})
        inventories[record['objectSha256']] = parse_object_inventory(captured[2])
    sections = _native_closure_target(target_raw, closure['image_base'])
    selection = select_native_coff_closure(objects, closure['placements'], closure['externals'],
        image_base=closure['image_base'], metadata_policy=closure['metadata_policy'])
    primary = closure['primary_regions']
    if not isinstance(primary, (list, tuple)) or len(primary) != len(capabilities):
        raise ValueError('native_closure_primary_capacity')
    selected = {}
    for entry in primary:
        if not isinstance(entry, dict) or set(entry) != {'objectSha256', 'section', 'address', 'size'}:
            raise ValueError('native_closure_primary_record')
        object_hash, number = entry['objectSha256'], entry['section']
        if not isinstance(object_hash, str):
            raise ValueError('native_closure_primary_identity')
        inventory = inventories.get(object_hash)
        if (inventory is None or object_hash in selected or type(number) is not int
                or not 1 <= number <= len(inventory['sections'])):
            raise ValueError('native_closure_primary_identity')
        owner = inventory['sections'][number - 1]
        functions = [symbol for symbol in inventory['symbols'].values()
                     if symbol['storageClass'] == 2 and symbol['section'] == number
                     and (symbol['type'] & 0x30) == 0x20]
        if (not owner['characteristics'] & 0x20 or not owner['characteristics'] & 0x20000000
                or len(functions) != 1 or functions[0]['value'] != 0
                or type(entry['address']) is not int or not 0 <= entry['address'] < 1 << 32
                or type(entry['size']) is not int or owner['size'] != entry['size']):
            raise ValueError('native_closure_primary_extent')
        selected[object_hash] = (entry, _db_row(db, binary_id, entry['address'], entry['size'],
                                            target_sha256=closure['target_sha256']))
    plan = []
    for emitted in selection['sections']:
        data, address = emitted['data'], emitted['address']
        offset = file_region_offset(target_raw, address, len(data))
        if offset is None:
            raise ValueError('native_closure_region_unmapped_or_ambiguous')
        mapped = [section for section in sections
                  if section['offset'] <= offset and offset + len(data) <= section['offset'] + section['size']]
        if len(mapped) != 1:
            raise ValueError('native_closure_region_raw_mapping')
        object_hash, number = emitted['objectSha256'], emitted['section']
        owner = inventories[object_hash]['sections'][number - 1]
        code = bool(owner['characteristics'] & 0x20)
        target_flags = mapped[0]['characteristics']
        if (code and not (target_flags & 0x20 and target_flags & 0x20000000)
                or not code and not target_flags & 0x40
                or (owner['characteristics'] & 0xe0000000) != (target_flags & 0xe0000000)):
            raise ValueError('native_closure_region_permissions')
        entry, database = selected[object_hash]
        is_primary = number == entry['section']
        if is_primary and (address != entry['address'] or len(data) != entry['size']):
            raise ValueError('native_closure_primary_placement_changed')
        if data != target_raw[offset:offset + len(data)]:
            raise ValueError('native_closure_placed_region_differs')
        identity = digest(canonical({'object': object_hash, 'section': number,
                                     'address': address, 'size': len(data)}))
        comparison = {'targetSha256': closure['target_sha256'], 'rawEqual': True,
                      'selectedDatabaseRow': database if is_primary else None}
        plan.append({'identity': identity, 'region': {'address': address, 'offset': offset,
                    'size': len(data), 'sha256': digest(data), 'sectionIndex': mapped[0]['index']},
                    'comparison': comparison, 'objectSha256': object_hash, 'objectSection': number,
                    'objectOffset': owner['offset'], 'data': data,
                    'contributionKind': 'primary-c' if is_primary else
                        'associated-code' if code else 'associated-data'})
    if sum(item['contributionKind'] == 'primary-c' for item in plan) != len(capabilities):
        raise ValueError('native_closure_primary_not_selected')
    audit = {key: value for key, value in selection.items() if key != 'sections'}
    audit['sections'] = []
    for section in selection['sections']:
        entry = {key: value for key, value in section.items() if key not in ('data', 'comdat')}
        definition = section['comdat']
        entry['comdat'] = ({key: value for key, value in definition.items()
                            if key not in ('raw', 'unused')} if definition else None)
        audit['sections'].append(entry)
    return plan, audit


def place_native_regions(*, target_raw: bytes, placements=(), db, binary_id: int,
                         overwrite_with_floor=(), native_closure=None) -> tuple[NativePlacementObservation, bytes]:
    """Reserve disjoint native holes and record actual in-memory byte writers.

    Entries are (issued native capability, independently selected address, size).
    The optional native_closure selects captured COFF code/data/EH sections.
    Output bytes are not a stock linker result; floor never receives C credit.
    """
    from itertools import islice

    entries = tuple(islice(iter(placements), 65))
    if len(entries) > 64 or (not entries and native_closure is None):
        raise ValueError('native_placement_capacity_or_empty')
    plan = []; metadata_size = 0
    for observation, address, size in entries:
        item = _native_placement_entry(observation, target_raw=target_raw, address=address,
                                       size=size, db=db, binary_id=binary_id)
        plan.append(item)
        metadata_size += len(canonical(item['comparison'])) + 1024
        if metadata_size > 8 * 1024**2:
            raise ValueError('native_placement_metadata_capacity')
    closure_audit = None
    if native_closure is not None:
        closure_plan, closure_audit = _native_closure_plan(native_closure, target_raw=target_raw,
                                                          db=db, binary_id=binary_id)
        plan.extend(closure_plan)
        # Store a detached snapshot of layout/policy, retaining only genuine
        # process-local capabilities. Caller mutation cannot change the plan.
        entries = {'legacy': entries, 'closure': {
            key: tuple(value) if key == 'observations' else json.loads(canonical(value))
            for key, value in native_closure.items()}}
    ordered = sorted(plan, key=lambda item: item['region']['offset'])
    if any(left['region']['offset'] + left['region']['size'] > right['region']['offset']
           for left, right in zip(ordered, ordered[1:])):
        raise ValueError('native_overlapping_replacement_holes')
    image = bytearray(len(target_raw)); writes = []; cursor = 0
    for item in ordered:
        lo, size = item['region']['offset'], item['region']['size']
        if cursor < lo:
            image[cursor:lo] = target_raw[cursor:lo]
            writes.append({'offset': cursor, 'size': lo - cursor, 'origin': 'preserved-floor'})
        image[lo:lo + size] = item['data']
        writes.append({'offset': lo, 'size': size, 'origin': 'compiled-object',
                       'invocation': item['identity'], 'objectOffset': item['objectOffset'],
                       'contributionKind': item.get('contributionKind', 'primary-c')})
        cursor = lo + size
    if cursor < len(image):
        image[cursor:] = target_raw[cursor:]
        writes.append({'offset': cursor, 'size': len(image) - cursor, 'origin': 'preserved-floor'})
    overwrite_requests = tuple(islice(iter(overwrite_with_floor), 4097))
    if len(overwrite_requests) > 4096:
        raise ValueError('native_floor_overwrite_capacity')
    if any(type(identity) is not str or len(identity) != 64
           or not re.fullmatch('[0-9a-f]{64}', identity) for identity in overwrite_requests):
        raise ValueError('native_invalid_floor_overwrite_identity')
    overwritten = set(overwrite_requests)
    if overwritten - {item['identity'] for item in plan}:
        raise ValueError('native_unknown_floor_overwrite')
    for item in ordered:
        if item['identity'] in overwritten:
            lo, size = item['region']['offset'], item['region']['size']
            image[lo:lo + size] = target_raw[lo:lo + size]
            writes.append({'offset': lo, 'size': size, 'origin': 'preserved-floor',
                           'reason': 'fallback_after_native_write'})
    image = bytes(image)
    record = {'schema': 'agentdecompile.native-placement-observation/v1',
              'targetSha256': digest(target_raw), 'outputSha256': digest(image),
              'size': len(image), 'writes': writes, 'finalWriters': final_writers(writes, len(image)),
              'plan': [{key: value for key, value in item.items() if key != 'data'} for item in plan],
              'closureSelection': closure_audit,
              'diagnosticOnly': True, 'accepted': False, 'sourceVerified': False,
              'linkedSourceContributionVerified': False, 'nativeEligibleLinkClosure': False,
              'wholeImageVerified': False,
              'claim': 'Observed in-memory native-object placement with explicit preserved floor; not toolchain closure or linked-image proof.'}
    payload = canonical(record).decode()
    if len(payload.encode()) > 8 * 1024**2:
        raise ValueError('native_placement_metadata_capacity')
    observation = NativePlacementObservation(payload)
    _NATIVE_PLACEMENTS[observation] = (payload, target_raw, image, entries)
    return observation, image


def evaluate_native_placement(observation, *, output_raw: bytes, db, binary_id: int) -> dict:
    """Replay the owned memory writer; withdraw credit after floor overwrites."""
    result = {'nativePlacedBytes': 0, 'nativePlacedRegions': 0, 'preservedFloorBytes': 0,
              'accepted': False, 'sourceVerified': False, 'wholeImageVerified': False,
              'linkedSourceContributionVerified': False, 'nativeEligibleLinkClosure': False,
              'diagnosticOnly': True, 'reason': 'untrusted_native_placement_observation'}
    if not isinstance(observation, NativePlacementObservation):
        return result
    captured = _NATIVE_PLACEMENTS.get(observation)
    if captured is None or captured[0] != observation.record_json:
        return result
    record = observation.record
    if not isinstance(output_raw, bytes) or output_raw != captured[2]:
        return {**result, 'reason': 'native_placement_output_changed'}
    try:
        writers = final_writers(record['writes'], len(output_raw))
        if writers != record['finalWriters']:
            raise ValueError('native_final_writer_accounting_changed')
        if isinstance(captured[3], dict):
            plan = [_native_placement_entry(capability, target_raw=captured[1],
                     address=address, size=size, db=db, binary_id=binary_id)
                    for capability, address, size in captured[3]['legacy']]
            closure_plan, selection = _native_closure_plan(captured[3]['closure'],
                target_raw=captured[1], db=db, binary_id=binary_id)
            plan.extend(closure_plan)
            if (selection != record['closureSelection'] or
                    [{key: value for key, value in item.items() if key != 'data'}
                     for item in plan] != record['plan']):
                raise ValueError('native_closure_selection_or_target_changed')
            counts = {'primaryCBytes': 0, 'associatedCodeBytes': 0, 'associatedDataBytes': 0}
            for item in plan:
                selected = [write for write in writers if write.get('invocation') == item['identity']
                            and write['origin'] == 'compiled-object']
                if not selected:
                    continue  # A later floor writer withdraws all contribution credit.
                region = item['region']
                if (len(selected) != 1 or selected[0]['offset'] != region['offset']
                        or selected[0]['size'] != region['size']
                        or selected[0]['objectOffset'] != item['objectOffset']
                        or selected[0]['contributionKind'] != item.get('contributionKind', 'primary-c')
                        or output_raw[region['offset']:region['offset'] + region['size']] != item['data']):
                    raise ValueError('native_closure_final_object_write_changed')
                result['nativePlacedRegions'] += 1
                result['nativePlacedBytes'] += len(item['data'])
                counts[{'primary-c': 'primaryCBytes', 'associated-code': 'associatedCodeBytes',
                        'associated-data': 'associatedDataBytes'}[item.get('contributionKind', 'primary-c')]] += len(item['data'])
            return {**result, **counts,
                    'preservedFloorBytes': sum(write['size'] for write in writers
                                               if write['origin'] == 'preserved-floor'),
                    'wholeFileByteIdentical': output_raw == captured[1],
                    'closureSelected': True,
                    'reason': 'observed_native_closure_memory_writer_preserved_floor'}
        for (capability, address, size), item in zip(captured[3], record['plan']):
            comparison = observe_native_target_region(capability, target_raw=captured[1],
                                                      address=address, size=size, db=db,
                                                      binary_id=binary_id)
            if comparison != item['comparison']:
                raise ValueError('native_selected_target_binding_changed')
            _, data, refusal = native_emitted_region(capability)
            if refusal:
                raise ValueError(refusal)
            selected = [write for write in writers if write.get('invocation') == item['identity']
                        and write['origin'] == 'compiled-object']
            if not selected:
                continue
            if len(selected) != 1:
                raise ValueError('native_fragmented_final_writer')
            write = selected[0]; region = item['region']
            if (write['offset'] != region['offset'] or write['size'] != region['size']
                    or write['objectOffset'] != item['objectOffset']
                    or output_raw[write['offset']:write['offset'] + write['size']] != data):
                raise ValueError('native_final_object_write_changed')
            result['nativePlacedRegions'] += 1
            result['nativePlacedBytes'] += len(data)
        result.update({'preservedFloorBytes': sum(write['size'] for write in writers
                                                  if write['origin'] == 'preserved-floor'),
                       'wholeFileByteIdentical': output_raw == captured[1],
                       'reason': 'observed_native_memory_writer_preserved_floor'})
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        result.update({'nativePlacedBytes': 0, 'nativePlacedRegions': 0, 'reason': str(exc)})
    return result


def publish_native_regions(*, target_path, output_path, target_raw, placements=(), db, binary_id,
                           native_closure=None):
    """Publish a new diagnostic reconstruction from owned native captures.

    This is not a stock linker result. Every nonselected byte is preserved
    target floor, not recovered source. A failed publication leaves any owned
    partial file diagnostic-only; an existing path is never overwritten.
    """
    from .compile_link import _read_observation_bytes

    if not isinstance(target_raw, bytes) or not 0 < len(target_raw) <= 64 * 1024**2:
        raise ValueError('native_publication_target_capacity')
    target = Path(target_path).resolve(strict=True)
    output = Path(output_path).absolute()
    if output.resolve() == target:
        raise ValueError('native_publication_output_conflicts_with_target')
    if _read_observation_bytes(target) != target_raw:
        raise ValueError('native_publication_target_changed')
    observation, image = place_native_regions(target_raw=target_raw, placements=placements,
                                              db=db, binary_id=binary_id,
                                              native_closure=native_closure)
    captured = _NATIVE_PLACEMENTS[observation]
    sources = []
    capabilities = (tuple(entry[0] for entry in captured[3]['legacy'])
                    + captured[3]['closure']['observations'] if isinstance(captured[3], dict)
                    else tuple(entry[0] for entry in captured[3]))
    for capability in capabilities:
        event = _NATIVE_COMPILES[capability]
        source = Path(capability.record['sourcePath'])
        if _read_observation_bytes(source) != event[1]:
            raise ValueError('native_publication_source_changed')
        sources.append((source, event[1]))
    checked = evaluate_native_placement(observation, output_raw=image, db=db, binary_id=binary_id)
    if checked.get('nativePlacedRegions') != len(observation.record['plan']):
        raise ValueError('native_publication_final_writer_refused:' + checked['reason'])
    # Exclusive creation is the existing reconstruction owner's publication
    # policy: no replacement of the linked candidate, input or retained output.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(output, flags, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(image)
        handle.flush()
        os.fsync(handle.fileno())
        written = os.fstat(handle.fileno())
    readback = _read_observation_bytes(output)
    current = output.stat(follow_symlinks=False)
    stable = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if (any(getattr(written, key) != getattr(current, key) for key in stable)
            or readback != image or _read_observation_bytes(target) != target_raw
            or any(_read_observation_bytes(source) != data for source, data in sources)):
        raise ValueError('native_publication_input_or_output_changed')
    checked = evaluate_native_placement(observation, output_raw=readback, db=db, binary_id=binary_id)
    if checked.get('nativePlacedRegions') != len(observation.record['plan']):
        raise ValueError('native_publication_readback_refused:' + checked['reason'])
    record = observation.record
    return {'schema': 'agentdecompile.native-placement-publication/v1',
            'status': 'published', 'output': {'path': str(output), 'size': len(readback),
                                             'sha256': digest(readback)},
            'targetSha256': digest(target_raw), 'placement': record, 'evaluation': checked,
            'coverageSha256': digest(canonical(record['finalWriters'])),
            'compilerProducedWholeImage': False, 'wholeImageVerified': False,
            'sourceVerified': False, 'linkedSourceContributionVerified': False,
            'accepted': False, 'diagnosticOnly': True,
            'claim': 'Published native-object diagnostic reconstruction; all other bytes are preserved target floor, not recovered source or stock linked output.'}


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


def _db_row(db, binary_id, address, size, *, target_sha256=None):
    if db is None:
        return None  # Explicit standalone fixture/unit scope; no database claim.
    reason = "missing_or_invalid_selected_binary_content_identity"
    if not isinstance(target_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", target_sha256):
        raise ValueError(reason)
    path = Path(db).resolve()
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            # Both facts belong to one selected-target snapshot, not the mutable
            # database file as a whole or unrelated semantic identity state.
            connection.execute("BEGIN")
            binaries = connection.execute("SELECT content_sha256 FROM binary WHERE id=?",
                                          (binary_id,)).fetchall()
            if (len(binaries) != 1 or not isinstance(binaries[0][0], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", binaries[0][0])):
                raise ValueError(reason)
            binary_sha256 = binaries[0][0]
            if binary_sha256 != target_sha256:
                raise ValueError("selected_binary_content_mismatch")
            reason = "selected_database_row_changed_or_ambiguous"
            rows = connection.execute("SELECT addr,size FROM func WHERE binary_id=? AND addr=?",
                                      (binary_id, address)).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(reason) from exc
    if rows != [(address, size)]:
        raise ValueError("selected_database_row_changed_or_ambiguous")
    return {"path": str(path), "binaryId": binary_id, "address": address, "size": size,
            "binarySha256": binary_sha256}


def compile_observation(*, source, target, address: int, size: int, workspace,
                        compiler="/usr/bin/clang", program="", name="", binary_id=None,
                        db=None, execution_fds=()) -> CompileObservation:
    """Fresh native cc1 invocation for a self-contained C TU, with no includes.

    No caller argv, shell, callback, precompiled object, environment, generated
    preamble or dependency-complete boolean enters this acceptance path. The
    empty preamble and fixed flags are deliberate first-backend limits.
    """
    if execution_fds:
        # Execution lifetime only; descriptors never provide semantic authority.
        from .cross_place_admission import lease_fds, _held_descriptor, _OWNERS
        if tuple(execution_fds) != lease_fds(): raise ValueError("unowned_execution_descriptors")
        _held_descriptor(execution_fds[0], _OWNERS.lease[0])
    source_path, target_path = Path(source).resolve(strict=True), Path(target).resolve(strict=True)
    source_raw, target_raw = source_path.read_bytes(), target_path.read_bytes()
    source_text = source_raw.decode("utf-8")
    # Reject preprocessing entirely, including digraph/trigraph/spliced forms.
    if (not is_real_c(source_text) or any(token in source_text for token in
            ("#", "%:", "??", "\\\n", "\\\r", "__attribute__", "__declspec"))):
        raise ValueError("unsupported_source_preprocessor_asm_or_attributes")
    region = pe_region(target_raw, address, size)
    selected_row = _db_row(db, binary_id, address, size, target_sha256=digest(target_raw))
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
                            capture_output=True, timeout=60, check=False, pass_fds=tuple(execution_fds))
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
    if _db_row(db, binary_id, address, size, target_sha256=digest(target_raw)) != selected_row:
        raise ValueError("selected_database_row_changed_or_ambiguous")
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
            if _db_row(row["path"], row["binaryId"], row["address"], row["size"],
                       target_sha256=record["target"]["sha256"]) != row:
                raise ValueError("selected_database_row_changed_or_ambiguous")
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
                    expected_row = _db_row(db, binary_id, item["region"]["address"], item["region"]["size"],
                                           target_sha256=item["target"]["sha256"])
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
