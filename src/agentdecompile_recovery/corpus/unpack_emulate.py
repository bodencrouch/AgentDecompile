"""Unicorn-based generic unpacker: run a packed image until it self-decrypts.

A runtime packer's stub decrypts the real code into memory and then jumps to the
original entry point (OEP). We emulate x86 from the file entry point, track every
write into an executable region (the decryption), and call it the OEP the first
time execution lands on an address those writes produced -- i.e. control reaches
freshly-written code. At that point memory holds the unpacked image; we dump it
back into the PE's raw layout and write it out.

This handles simple self-decrypting packers. Heavy DRM (SecuROM/VMProtect) uses
anti-emulation, exceptions, and real API calls that a headless emulator cannot
satisfy; those return ok=False and the caller gates the binary for an external
runtime dump. 32-bit PE only (the KotOR-era targets).
"""
from __future__ import annotations

import struct
from pathlib import Path

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, \
        UC_HOOK_MEM_UNMAPPED
    from unicorn.x86_const import UC_X86_REG_ESP
    _HAVE_UC = True
except ImportError:  # pragma: no cover
    _HAVE_UC = False

_PAGE = 0x1000
_MAX_INSN = 20_000_000


def _pe(blob: bytes) -> dict:
    e = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = e + 24
    image_base = struct.unpack_from("<I", blob, opt + 28)[0]
    ep_rva = struct.unpack_from("<I", blob, opt + 16)[0]
    size_img = struct.unpack_from("<I", blob, opt + 56)[0]
    nsec = struct.unpack_from("<H", blob, e + 6)[0]
    opt_sz = struct.unpack_from("<H", blob, e + 20)[0]
    sect = opt + opt_sz
    secs = []
    for i in range(nsec):
        sh = blob[sect + i * 40: sect + i * 40 + 40]
        vaddr, vsize = struct.unpack_from("<II", sh, 12)
        rsize, rptr = struct.unpack_from("<II", sh, 16)
        secs.append({"vaddr": vaddr, "vsize": vsize, "rptr": rptr, "rsize": rsize})
    return {"image_base": image_base, "ep_rva": ep_rva, "size_img": size_img, "secs": secs}


def unpack_to_oep(blob: bytes, out: Path) -> dict:
    if not _HAVE_UC:
        return {"ok": False, "reason": "unicorn not installed"}
    if blob[:2] != b"MZ":
        return {"ok": False, "reason": "not a PE"}
    try:
        pe = _pe(blob)
    except struct.error:
        return {"ok": False, "reason": "malformed PE"}

    base = pe["image_base"]
    span = (pe["size_img"] + 0xFFFF) & ~0xFFFF
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    try:
        uc.mem_map(base, max(span, 0x100000))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"map failed: {exc}"}
    # load headers + sections at their virtual addresses
    uc.mem_write(base, blob[:pe["secs"][0]["rptr"] if pe["secs"] else 0x400])
    for s in pe["secs"]:
        raw = blob[s["rptr"]:s["rptr"] + s["rsize"]]
        if raw:
            uc.mem_write(base + s["vaddr"], raw)

    stack = 0x300000
    uc.mem_map(stack, 0x100000)
    uc.reg_write(UC_X86_REG_ESP, stack + 0x80000)

    written: set[int] = set()
    state = {"oep": None, "ep": base + pe["ep_rva"]}

    def on_write(_uc, _access, address, size, _value, _ud):
        for a in range(address, address + size):
            written.add(a)

    def on_code(u, address, _size, _ud):
        # OEP heuristic: control reaches code that this run decrypted, and we've
        # left the entry page (the stub). First such hit is the unpacked OEP.
        if state["oep"] is None and address in written and \
                abs(address - state["ep"]) > _PAGE:
            state["oep"] = address
            u.emu_stop()

    def on_unmapped(u, _access, address, _size, _value, _ud):
        # Map zero pages on demand so a stray access/API thunk does not abort the
        # whole run; the packer stub mostly touches its own image.
        try:
            u.mem_map(address & ~(_PAGE - 1), _PAGE)
            return True
        except Exception:  # noqa: BLE001
            return False

    uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
    uc.hook_add(UC_HOOK_CODE, on_code)
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)

    try:
        uc.emu_start(state["ep"], base + span, count=_MAX_INSN)
    except Exception as exc:  # noqa: BLE001
        if state["oep"] is None:
            return {"ok": False, "reason": f"emulation fault before OEP: {exc}"}

    if state["oep"] is None:
        return {"ok": False, "reason": "no OEP reached (anti-emulation or API-bound packer)"}

    # Dump the now-decrypted sections back into the PE raw layout.
    image = bytearray(blob)
    for s in pe["secs"]:
        if s["rsize"] == 0:
            continue
        try:
            mem = uc.mem_read(base + s["vaddr"], min(s["vsize"] or s["rsize"], s["rsize"]))
        except Exception:  # noqa: BLE001
            continue
        image[s["rptr"]:s["rptr"] + len(mem)] = mem
    # rewrite AddressOfEntryPoint to the recovered OEP
    e = struct.unpack_from("<I", blob, 0x3C)[0]
    struct.pack_into("<I", image, e + 24 + 16, state["oep"] - base)
    Path(out).write_bytes(bytes(image))
    return {"ok": True, "oep": hex(state["oep"])}
