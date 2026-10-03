"""Strict thin-image qualification for the retained Mach-O/STABS reader.

Exploratory MachO success is not authority: validate the whole snapshot's load
commands, symbol records and bounded UTF-8 strings before using that reader.
Only embedded N_FUN observations are returned; attribution is context only.
"""

from __future__ import annotations

import struct

from .machostabs import CPU_NAMES, LC_SEGMENT, LC_SEGMENT_64, LC_SYMTAB, MachO, parse_stabs

FAT_MAGICS = {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
THIN_LAYOUTS = {b"\xce\xfa\xed\xfe": (32, "<"), b"\xfe\xed\xfa\xce": (32, ">"),
                b"\xcf\xfa\xed\xfe": (64, "<"), b"\xfe\xed\xfa\xcf": (64, ">")}


class WitnessError(ValueError):
    """A closed qualification refusal, safe to persist as its reason."""


def normalise_arch(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    value = {"x86": "i386", "x86_32": "i386", "amd64": "x86_64", "aarch64": "arm64",
             "powerpc": "ppc", "powerpc64": "ppc64"}.get(value, value)
    return value if value in CPU_NAMES.values() else None


def _extent(data: bytes, offset: int, size: int, *, floor: int = 0) -> None:
    if offset < floor or size < 0 or offset > len(data) or size > len(data) - offset:
        raise WitnessError("malformed_macho_stabs_inventory")


def observe_snapshot(data: bytes, binary: dict) -> dict:
    """Qualify exactly one requested architecture, with no file reads or slices."""
    if data[:4] in FAT_MAGICS:
        raise WitnessError("unsupported_macho_fat_image")
    layout = THIN_LAYOUTS.get(data[:4])
    if layout is None:
        raise WitnessError("unsupported_macho_layout")
    selected = normalise_arch(binary.get("arch"))
    if selected is None:
        raise WitnessError("selected_macho_architecture_missing_or_unknown")
    bits, endian = layout
    header_size = 32 if bits == 64 else 28
    _extent(data, 0, header_size)
    _, cpu, subtype, filetype, ncmds, command_size, _ = struct.unpack_from(endian + "IiiIIII", data)
    arch = CPU_NAMES.get(cpu)
    if arch is None or (bits == 64) != bool(cpu & 0x01000000):
        raise WitnessError("unsupported_macho_architecture")
    if selected != arch:
        raise WitnessError("selected_macho_architecture_mismatch")
    if binary.get("bits") is not None and (type(binary["bits"]) is not int or binary["bits"] != bits):
        raise WitnessError("selected_macho_width_mismatch")
    if binary.get("format") not in (None, "", "macho"):
        raise WitnessError("selected_macho_format_mismatch")
    # Relocatable objects and non-image file types do not qualify this VA lane.
    if filetype not in (2, 6, 8):
        raise WitnessError("unsupported_macho_filetype")
    _extent(data, header_size, command_size)
    command_end = header_size + command_size
    if ncmds > command_size // 8:
        raise WitnessError("malformed_macho_stabs_inventory")
    off = header_size
    symtab = None
    for _ in range(ncmds):
        if off + 8 > command_end:
            raise WitnessError("malformed_macho_stabs_inventory")
        cmd, size = struct.unpack_from(endian + "II", data, off)
        if size < 8 or size % (8 if bits == 64 else 4) or size > command_end - off:
            raise WitnessError("malformed_macho_stabs_inventory")
        if cmd == LC_SYMTAB:
            if size != 24 or symtab is not None:
                raise WitnessError("malformed_macho_stabs_inventory")
            symtab = struct.unpack_from(endian + "IIII", data, off + 8)
        elif cmd in (LC_SEGMENT, LC_SEGMENT_64):
            if cmd != (LC_SEGMENT_64 if bits == 64 else LC_SEGMENT):
                raise WitnessError("unsupported_macho_layout")
            fixed, section_size = (72, 80) if bits == 64 else (56, 68)
            if size < fixed:
                raise WitnessError("malformed_macho_stabs_inventory")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from(endian + ("QQQQ" if bits == 64 else "IIII"), data, off + 24)
            nsects = struct.unpack_from(endian + "I", data, off + (64 if bits == 64 else 48))[0]
            if size != fixed + nsects * section_size or filesize > vmsize or vmaddr + vmsize > 1 << bits:
                raise WitnessError("malformed_macho_stabs_inventory")
            _extent(data, fileoff, filesize)
            for index in range(nsects):
                section = off + fixed + index * section_size
                addr, section_len, section_off = struct.unpack_from(endian + ("QQI" if bits == 64 else "III"), data, section + 32)
                flags = struct.unpack_from(endian + "I", data, section + (64 if bits == 64 else 56))[0]
                reloff, nreloc = struct.unpack_from(endian + "II", data, section + (56 if bits == 64 else 48))
                _extent(data, reloff, nreloc * 8)
                if addr < vmaddr or section_len > vmaddr + vmsize - addr:
                    raise WitnessError("malformed_macho_stabs_inventory")
                if (flags & 0xff) not in (1, 0xc, 0x12):  # zero-fill sections have no file extent
                    _extent(data, section_off, section_len)
                    if section_off < fileoff or section_len > fileoff + filesize - section_off:
                        raise WitnessError("malformed_macho_stabs_inventory")
        off += size
    if off != command_end:
        raise WitnessError("malformed_macho_stabs_inventory")
    if symtab is None:
        raise WitnessError("target_stabs_symtab_missing")
    symoff, nsyms, stroff, strsize = symtab
    record_size = 16 if bits == 64 else 12
    _extent(data, symoff, nsyms * record_size, floor=command_end)
    _extent(data, stroff, strsize, floor=command_end)
    if strsize < 1 or data[stroff] != 0 or (nsyms and symoff < stroff + strsize and stroff < symoff + nsyms * record_size):
        raise WitnessError("malformed_macho_stabs_inventory")
    raw_rows = []
    for index in range(nsyms):
        record_off = symoff + index * record_size
        strx, ntype, _, _, value = struct.unpack_from(endian + ("IBBHQ" if bits == 64 else "IBBHI"), data, record_off)
        if strx >= strsize:
            raise WitnessError("malformed_macho_stabs_inventory")
        string_off = stroff + strx
        end = data.find(b"\0", string_off, stroff + strsize)
        if end < 0:
            raise WitnessError("malformed_macho_stabs_inventory")
        try:
            declaration = data[string_off:end].decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise WitnessError("malformed_macho_stabs_inventory") from exc
        if ntype == 0x24 and declaration:
            raw_rows.append({"nlistIndex": index, "recordOffset": record_off, "stringIndex": strx,
                             "stringOffset": string_off, "stringEnd": end, "rawType": ntype,
                             "declaration": declaration, "va": value})
    # All reads performed by these retained producers have now been bounded.
    mo = MachO(data)
    functions = parse_stabs(mo)["functions"]
    if len(functions) != len(raw_rows):
        raise WitnessError("malformed_macho_stabs_inventory")
    for raw, function in zip(raw_rows, functions):
        if not function["name"]:
            raise WitnessError("malformed_macho_stabs_inventory")
        raw.update(name=function["name"], sourceFile=function["source_file"], objectFile=function["object_file"])
    return {"architecture": {"name": arch, "cpuType": cpu, "cpuSubtype": subtype, "bits": bits,
                             "endianness": "little" if endian == "<" else "big"},
            "selectedArchitecture": selected, "slice": {"offset": 0, "size": len(data)},
            "stabs": raw_rows, "segments": mo.segments, "snapshot": data,
            "symbolTable": {"commandEnd": command_end, "offset": symoff, "count": nsyms, "recordSize": record_size,
                            "stringOffset": stroff, "stringSize": strsize}}


def region_offset(observation: dict, address: int, size: int) -> int:
    """Require one full file-backed mapping and no overlapping alternative."""
    if type(address) is not int or address < 0 or type(size) is not int or size <= 0:
        raise ValueError("invalid candidate region")
    end = address + size
    if end > 1 << observation["architecture"]["bits"]:
        raise ValueError("candidate exceeds address space")
    overlaps = [seg for seg in observation["segments"] if seg["filesize"] > 0
                and address < seg["vmaddr"] + seg["filesize"] and seg["vmaddr"] < end]
    if len(overlaps) != 1:
        raise ValueError("ambiguous or missing candidate mapping")
    seg = overlaps[0]
    if address < seg["vmaddr"] or end > seg["vmaddr"] + seg["filesize"]:
        raise ValueError("candidate not wholly file-backed")
    offset = seg["fileoff"] + address - seg["vmaddr"]
    _extent(observation["snapshot"], offset, size)
    return offset
