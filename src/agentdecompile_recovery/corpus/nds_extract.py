"""Split a Nintendo DS ROM (.nds) into its ARM9 and ARM7 executables.

A .nds ROM is a container, not a single executable: the fixed 0x200-byte header
gives the ROM offset, RAM load address, entry point, and size for each of the
two processors (ARM9 = main CPU, ARM7 = the audio/IO coprocessor). Ghidra has
no Nintendo-DS loader, but its ARM processor module (ARMv5T for ARM9, ARMv4T
for ARM7) analyzes a raw binary correctly once it is imported at the right base
address. So "importing" sonic_chronicles.nds for real recovery means: extract
the two CPU images here, then hand each to the normal raw-binary import path
with --base-address/--language set from the header -- not the .nds file itself.

Reference: GBATEK "DS Cartridge Header" (public, no proprietary tooling needed).
Offsets are little-endian per the DS ABI.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

_HEADER_FIELDS = {
    # name: (offset, format)
    "arm9_rom_offset": (0x20, "<I"),
    "arm9_entry_addr": (0x24, "<I"),
    "arm9_ram_addr":   (0x28, "<I"),
    "arm9_size":       (0x2C, "<I"),
    "arm7_rom_offset": (0x30, "<I"),
    "arm7_entry_addr": (0x34, "<I"),
    "arm7_ram_addr":   (0x38, "<I"),
    "arm7_size":       (0x3C, "<I"),
}


def read_header(blob: bytes) -> dict:
    if len(blob) < 0x200:
        raise ValueError("not a valid NDS ROM (shorter than header)")
    game_code = blob[0x0C:0x10].decode("ascii", "replace")
    title = blob[0x00:0x0C].split(b"\x00", 1)[0].decode("ascii", "replace")
    fields = {k: struct.unpack_from(fmt, blob, off)[0] for k, (off, fmt) in _HEADER_FIELDS.items()}
    return {"title": title, "game_code": game_code, **fields}


def extract(nds_path: Path, out_dir: Path) -> dict:
    """Write {out_dir}/arm9.bin and arm7.bin. Returns manifest with load info.

    Each CPU's ARM binary starts executing far from its ROM offset -- code
    that references the ROM offset as a load address will disassemble wrong.
    `ram_addr` is the real base address Ghidra must import at.
    """
    blob = nds_path.read_bytes()
    hdr = read_header(blob)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"source": str(nds_path), "title": hdr["title"], "game_code": hdr["game_code"], "cpus": {}}
    for cpu, lang in (("arm9", "ARM:LE:32:v5t"), ("arm7", "ARM:LE:32:v4t")):
        off, entry, ram, size = (hdr[f"{cpu}_rom_offset"], hdr[f"{cpu}_entry_addr"],
                                  hdr[f"{cpu}_ram_addr"], hdr[f"{cpu}_size"])
        if size == 0 or off + size > len(blob):
            manifest["cpus"][cpu] = {"ok": False, "reason": "empty or out-of-range in header"}
            continue
        img = blob[off:off + size]
        dest = out_dir / f"{cpu}.bin"
        dest.write_bytes(img)
        manifest["cpus"][cpu] = {
            "ok": True, "path": str(dest), "size": size,
            "rom_offset": off, "ram_addr": ram, "entry_addr": entry, "language": lang,
            # This is what a raw-binary Ghidra import needs: base = ram_addr,
            # not 0 and not rom_offset -- pointers/branches are RAM-relative.
        }
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nds", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    manifest = extract(args.nds, args.out_dir)
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))
    ok = all(c.get("ok") for c in manifest["cpus"].values())
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
