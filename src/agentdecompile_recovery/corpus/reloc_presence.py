"""Whether a build carries a relocation table (portable plan U52).

Old 32-bit images commonly set ``IMAGE_FILE_RELOCS_STRIPPED``. For such a build the
relocation half of "decode ∪ reloc" masking is empty and decode-only masking carries
the whole load, so coverage has to say which inputs masking actually had. This reads
the answer from the image bytes; a format it cannot read stays unknown, never a guess.
"""
from __future__ import annotations

import struct

IMAGE_FILE_RELOCS_STRIPPED = 0x0001
_BASERELOC_INDEX = 5
_ELF_SHT_RELA, _ELF_SHT_REL = 4, 9


def relocation_table(raw: bytes) -> dict:
    """``{"format", "present": True|False|None, "reason"}`` for one image."""
    if raw[:2] == b"MZ" and len(raw) >= 0x40:
        return _pe(raw)
    if raw[:4] == b"\x7fELF":
        return _elf(raw)
    return {"format": "unknown", "present": None, "reason": "image format has no relocation reader"}


def _pe(raw: bytes) -> dict:
    (pe_off,) = struct.unpack_from("<I", raw, 0x3C)
    if raw[pe_off:pe_off + 4] != b"PE\0\0":
        return {"format": "mz", "present": None, "reason": "no PE header"}
    coff = pe_off + 4
    (characteristics,) = struct.unpack_from("<H", raw, coff + 18)
    (opt_size,) = struct.unpack_from("<H", raw, coff + 16)
    if characteristics & IMAGE_FILE_RELOCS_STRIPPED:
        return {"format": "pe", "present": False, "reason": "IMAGE_FILE_RELOCS_STRIPPED"}
    opt = coff + 20
    (magic,) = struct.unpack_from("<H", raw, opt)
    dirs = opt + {0x10B: 96, 0x20B: 112}.get(magic, -1)
    if dirs < opt or opt_size < (dirs - opt) + 8 * (_BASERELOC_INDEX + 1):
        return {"format": "pe", "present": None, "reason": "optional header too short for the base-relocation directory"}
    (count,) = struct.unpack_from("<I", raw, dirs - 4)
    if count <= _BASERELOC_INDEX:
        return {"format": "pe", "present": False, "reason": "no base-relocation directory entry"}
    _, size = struct.unpack_from("<II", raw, dirs + 8 * _BASERELOC_INDEX)
    if size == 0:
        return {"format": "pe", "present": False, "reason": "empty base-relocation directory"}
    return {"format": "pe", "present": True, "reason": "base-relocation directory present"}


def _elf(raw: bytes) -> dict:
    klass, data = raw[4], raw[5]
    if klass not in (1, 2) or data not in (1, 2):
        return {"format": "elf", "present": None, "reason": "unsupported ELF class or data encoding"}
    e = "<" if data == 1 else ">"
    if klass == 1:
        shoff, = struct.unpack_from(e + "I", raw, 0x20)
        shentsize, shnum = struct.unpack_from(e + "HH", raw, 0x2E)
        entry = e + "IIIIII"
    else:
        shoff, = struct.unpack_from(e + "Q", raw, 0x28)
        shentsize, shnum = struct.unpack_from(e + "HH", raw, 0x3A)
        entry = e + "IIQQQQ"
    if not shoff or not shnum:
        return {"format": "elf", "present": None, "reason": "no section headers"}
    for index in range(shnum):
        start = shoff + index * shentsize
        if start + struct.calcsize(entry) > len(raw):
            return {"format": "elf", "present": None, "reason": "section headers truncated"}
        _name, sh_type, _flags, _addr, _offset, size = struct.unpack_from(entry, raw, start)
        if sh_type in (_ELF_SHT_REL, _ELF_SHT_RELA) and size:
            return {"format": "elf", "present": True, "reason": "REL/RELA section present"}
    return {"format": "elf", "present": False, "reason": "no REL/RELA section"}
