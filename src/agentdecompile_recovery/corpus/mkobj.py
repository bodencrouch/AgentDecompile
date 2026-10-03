"""Wrap a slice of a raw binary image in a minimal COFF object.

The output layout was reverse-engineered from surviving objects rather than
written from the COFF spec. ``write_object`` takes required Path arguments;
there is no product-binary default.
"""

from __future__ import annotations

import pathlib
import re
import struct
import subprocess
import tempfile

MACHINE = {
    "coff-i386": 0x014C,
    "coff-x86-64": 0x8664,
}

TEXT_CHARACTERISTICS = 0x60500020

SYMBOL_SIZE = 18
FILE_HEADER_SIZE = 20
SECTION_HEADER_SIZE = 40

IMAGE_SYM_CLASS_EXTERNAL = 2
IMAGE_SYM_CLASS_STATIC = 3
IMAGE_SYM_DTYPE_FUNCTION = 0x20
IMAGE_REL_I386_REL32 = 0x14
IMAGE_REL_AMD64_REL32 = 0x04
RELOCATION_ENTRY_SIZE = 10

# The PC-relative 32-bit relocation type for each machine. Both are applied as
# S + A - (P + 4), where A is the field's existing content.
REL32_TYPE = {
    MACHINE["coff-i386"]: IMAGE_REL_I386_REL32,
    MACHINE["coff-x86-64"]: IMAGE_REL_AMD64_REL32,
}
OBJDUMP_ARCH = {
    MACHINE["coff-i386"]: "i386",
    MACHINE["coff-x86-64"]: "i386:x86-64",
}

# Opcode bytes that start a direct branch: jcc rel8, loop/jcxz, call/jmp rel32,
# jmp rel8, and the 0F escape of jcc rel32. A region containing none of them
# has no direct branch at all.
# C7 F8 is XBEGIN with a relative abort target; conservatively screen every C7.
_BRANCH_BYTES = frozenset([*range(0x70, 0x80), 0xE0, 0xE1, 0xE2, 0xE3, 0xE8, 0xE9, 0xEB, 0x0F, 0xC7])

_INSN = re.compile(r"^\s*([0-9a-f]+):\t([0-9a-f]{2}(?: [0-9a-f]{2})*)[ \t]*(.*)$")
_BRANCH_MNEMONIC = re.compile(r"(?:call|jmp|j[a-z]+|loop[a-z]*|xbegin)[lqw]?")
_HEX_OPERAND = re.compile(r"(?:0x)?([0-9a-f]+)")
_RIP_TARGET = re.compile(r"#\s*(?:0x)?([0-9a-f]+)")


class MkobjRefusal(ValueError):
    """A named reason mkobj will not write an object. ``reason`` is the name.

    Raised instead of writing an object whose PC-relative references were not
    all found, since such an object reproduces its region only where it was cut.
    """

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"mkobj refused: {reason}" + (f": {detail}" if detail else ""))
        self.reason = reason


def _pc_relative_impossible(code: bytes, machine: int) -> bool:
    """True when no byte could start a direct branch or (AMD64) a RIP-relative ModRM."""
    if any(b in _BRANCH_BYTES for b in code):
        return False
    if machine == MACHINE["coff-x86-64"] and any((b & 0xC7) == 0x05 for b in code):
        return False
    return True


def _run_objdump(code: bytes, machine: int) -> str:
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin") as tf:
            tf.write(code)
            tf.flush()
            p = subprocess.run(
                ["objdump", "-D", "-w", "-z", "-b", "binary", "-m", OBJDUMP_ARCH[machine], tf.name],
                capture_output=True,
                text=True,
            )
    except OSError as exc:
        raise MkobjRefusal("call_target_discovery_unavailable", f"objdump: {exc}") from exc
    if p.returncode != 0:
        raise MkobjRefusal(
            "call_target_discovery_unavailable",
            f"objdump exited {p.returncode}: {(p.stderr or '').strip()[:200]}",
        )
    return p.stdout


def _outside(target: int, size: int) -> bool:
    return not 0 <= target < size


def find_call_targets(code: bytes, machine: int, *, reference_free_only: bool = False) -> dict[int, int]:
    """{byte offset of the displacement field: target offset (may be outside code)}.

    Every direct branch whose target lands outside this region must be a
    plain ``call``/``jmp rel32`` (E8/E9) or ``jcc rel32`` (0F 8x); each gets a
    REL32 relocation. Anything else that reaches outside the region raises
    ``MkobjRefusal``: a short or prefixed external branch
    (``external_branch_unrelocatable``) or an AMD64 RIP-relative operand
    (``rip_relative_unsupported``). So does a missing or failing objdump
    (``call_target_discovery_unavailable``), a listing that does not decode
    the whole region, and an unsupported machine.

    Returns {} without running objdump only when the region contains no byte
    that could begin such a reference. ``reference_free_only=True`` refuses
    every other region before decoder discovery or execution.
    """
    if type(reference_free_only) is not bool:
        raise MkobjRefusal("invalid_reference_free_only")
    if machine not in REL32_TYPE:
        raise MkobjRefusal("unsupported_machine", f"0x{machine:04x}")
    if _pc_relative_impossible(code, machine):
        return {}
    if reference_free_only:
        raise MkobjRefusal("decoder_required")
    size = len(code)
    out: dict[int, int] = {}
    covered = 0
    for line in _run_objdump(code, machine).splitlines():
        m = _INSN.match(line)
        if not m:
            continue
        off = int(m.group(1), 16)
        raw = bytes.fromhex(m.group(2).replace(" ", ""))
        text = m.group(3).strip()
        if off != covered or code[off:off + len(raw)] != raw:
            raise MkobjRefusal("decode_incomplete", f"listing out of step at offset {off}")
        covered = off + len(raw)
        if not text or "(bad)" in text:
            raise MkobjRefusal("undecodable_instruction", f"offset {off}")
        if "%rip" in text:
            t = _RIP_TARGET.search(text)
            if t is None:
                raise MkobjRefusal("rip_relative_unsupported", f"offset {off}: no target in {text!r}")
            if _outside(int(t.group(1), 16), size):
                raise MkobjRefusal("rip_relative_unsupported", f"offset {off}: {text}")
        tokens = text.split()
        for i, tok in enumerate(tokens):
            if _BRANCH_MNEMONIC.fullmatch(tok):
                break
        else:
            continue
        operand = tokens[i + 1] if i + 1 < len(tokens) else ""
        h = _HEX_OPERAND.fullmatch(operand)
        if h is None:
            continue  # indirect (*...) or register operand
        if not _outside(int(h.group(1), 16), size):
            continue
        if len(raw) == 5 and raw[0] in (0xE8, 0xE9):
            field = off + 1
        elif len(raw) == 6 and raw[0] == 0x0F and 0x80 <= raw[1] <= 0x8F:
            field = off + 2
        else:
            raise MkobjRefusal("external_branch_unrelocatable", f"offset {off}: {raw.hex()} {text}")
        target = field + 4 + int.from_bytes(code[field:field + 4], "little", signed=True)
        if not _outside(target, size):
            raise MkobjRefusal("decode_incomplete", f"objdump and bytes disagree at offset {off}")
        out[field] = target
    if covered != size:
        raise MkobjRefusal("decode_incomplete", f"decoded {covered} of {size} bytes")
    return out


def symbol_name_field(name: str, strtab: bytearray) -> bytes:
    """8-byte name field: inline when it fits, else an offset into the string table."""
    raw = name.encode("ascii")
    if len(raw) <= 8:
        return raw.ljust(8, b"\0")
    offset = len(strtab)
    strtab.extend(raw + b"\0")
    return struct.pack("<II", 0, offset)


def build_object(
    code: bytes,
    symbol: str,
    machine: int,
    call_targets: dict[int, int] | None = None,
) -> bytes:
    """``call_targets`` is ``{displacement-field offset: target offset}``.

    None/empty reproduces the original zero-relocation layout. This is the
    raw layout primitive: callers that cut a region should use
    ``write_object``, which refuses rather than drop a relocation.
    """
    size = len(code)
    if call_targets and machine not in REL32_TYPE:
        raise MkobjRefusal("unsupported_machine", f"0x{machine:04x}")
    data_off = FILE_HEADER_SIZE + SECTION_HEADER_SIZE

    call_targets = call_targets or {}
    targets = sorted(set(call_targets.values()))
    n_relocs = len(call_targets)
    reloc_off = data_off + size
    symtab_off = reloc_off + n_relocs * RELOCATION_ENTRY_SIZE
    n_symbols = 3 + len(targets)

    strtab = bytearray(b"\0\0\0\0")

    out = bytearray()
    out += struct.pack(
        "<HHIIIHH",
        machine,
        1,
        0,
        symtab_off,
        n_symbols,
        0,
        0,
    )
    out += b".text".ljust(8, b"\0")
    out += struct.pack(
        "<IIIIIIHHI",
        0,
        0,
        size,
        data_off,
        reloc_off if n_relocs else 0,
        0,
        n_relocs,
        0,
        TEXT_CHARACTERISTICS,
    )
    assert len(out) == data_off, (len(out), data_off)
    out += code
    assert len(out) == reloc_off, (len(out), reloc_off)

    target_index = {addr: 3 + i for i, addr in enumerate(targets)}
    for disp_off in sorted(call_targets):
        sym_idx = target_index[call_targets[disp_off]]
        out += struct.pack("<IIH", disp_off, sym_idx, REL32_TYPE[machine])
    assert len(out) == symtab_off, (len(out), symtab_off)

    out += b".text".ljust(8, b"\0")
    out += struct.pack("<IhHBB", 0, 1, 0, IMAGE_SYM_CLASS_STATIC, 1)
    out += struct.pack("<IHH", size, n_relocs, 0) + b"\0" * 10
    out += symbol_name_field(symbol, strtab)
    out += struct.pack(
        "<IhHBB", 0, 1, IMAGE_SYM_DTYPE_FUNCTION, IMAGE_SYM_CLASS_EXTERNAL, 0
    )
    for addr in targets:
        out += symbol_name_field(f"EXT_{addr & 0xffffffff:08x}", strtab)
        out += struct.pack(
            "<IhHBB", 0, 0, IMAGE_SYM_DTYPE_FUNCTION, IMAGE_SYM_CLASS_EXTERNAL, 0
        )

    struct.pack_into("<I", strtab, 0, len(strtab))
    out += strtab
    return bytes(out)


def write_object(
    *,
    binary: pathlib.Path | str,
    offset: int,
    size: int,
    name: str,
    output: pathlib.Path | str,
    symbol_prefix: str = "_",
    format: str = "coff-i386",
    reference_free_only: bool = False,
) -> pathlib.Path:
    """Slice *binary* and write a COFF object to *output*. All paths required.

    Raises ``MkobjRefusal`` (a ValueError) and writes nothing when the
    region's external references cannot all be found and relocated.
    """
    if type(reference_free_only) is not bool:
        raise MkobjRefusal("invalid_reference_free_only")
    if size <= 0:
        raise ValueError(f"mkobj: refusing zero/negative size {size}")
    if format not in MACHINE:
        raise ValueError(f"mkobj: unknown format {format!r}")

    raw = pathlib.Path(binary).read_bytes()
    end = offset + size
    if offset < 0 or end > len(raw):
        raise ValueError(f"mkobj: slice {offset}..{end} outside {binary} ({len(raw)} bytes)")

    code = raw[offset:end]
    machine = MACHINE[format]
    call_targets = find_call_targets(code, machine, reference_free_only=reference_free_only)
    if call_targets:
        code = bytearray(code)
        for disp_off in call_targets:
            code[disp_off : disp_off + 4] = b"\0\0\0\0"
        code = bytes(code)
    obj = build_object(code, symbol_prefix + name, machine, call_targets)
    dest = pathlib.Path(output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(obj)
    return dest


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=pathlib.Path, required=True)
    ap.add_argument("--offset", type=int, required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("-o", "--output", type=pathlib.Path, required=True)
    ap.add_argument("--symbol-prefix", default="_")
    ap.add_argument("--format", choices=sorted(MACHINE), default="coff-i386")
    args = ap.parse_args(argv)
    try:
        write_object(
            binary=args.binary,
            offset=args.offset,
            size=args.size,
            name=args.name,
            output=args.output,
            symbol_prefix=args.symbol_prefix,
            format=args.format,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
