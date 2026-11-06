"""Exact-placement assembly-floor diagnostic (STRATEGY.md tier 8).

Per-function objdiff-0 is not the terminal deliverable; it needs a fresh,
compiler-produced whole-image build and whole-file comparison. This module does
not build that image: it starts from the shipped PE, keeps its headers and
non-code sections, and places per-function bytes at their original offsets.
When it uses the assembly floor, the output is byte-identical by construction.
That establishes only the placement diagnostic and recovered-C coverage; it is
never a compiler/relink receipt.

For swkotor.exe the PE has file_align == section_align == 0x1000, so a section's
file offset equals its RVA and placement is direct: a function at VA `a` lives at
file offset `a - image_base`.

    python3 -m agentdecompile_recovery.corpus.whole_image_relink \\
        --target <shipped.exe> --db <corpus.sqlite> --binary-id N \\
        --func-bytes <dir-or-none> --out <rebuilt.exe>
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import struct
from pathlib import Path


def parse_pe(blob: bytes) -> dict:
    e_lfanew = struct.unpack_from("<I", blob, 0x3C)[0]
    if blob[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("not a PE")
    nsec = struct.unpack_from("<H", blob, e_lfanew + 6)[0]
    opt_sz = struct.unpack_from("<H", blob, e_lfanew + 20)[0]
    opt = e_lfanew + 24
    image_base = struct.unpack_from("<I", blob, opt + 28)[0]
    sect = opt + opt_sz
    sections = []
    for i in range(nsec):
        sh = blob[sect + i * 40: sect + i * 40 + 40]
        name = sh[:8].rstrip(b"\x00").decode("latin1")
        vsize, vaddr, rsize, rptr = struct.unpack_from("<IIII", sh, 8)
        flags = struct.unpack_from("<I", sh, 36)[0]
        sections.append({"name": name, "vaddr": vaddr, "vsize": vsize,
                         "rptr": rptr, "rsize": rsize, "flags": flags,
                         "code": bool(flags & 0x20)})
    return {"image_base": image_base, "sections": sections, "size": len(blob)}


def text_section(pe: dict) -> dict:
    for s in pe["sections"]:
        if s["name"].startswith(".text") or s["code"]:
            return s
    raise ValueError("no code section")


def func_byte_source(func_bytes_dir: str | None):
    """Return f(addr, size) -> recovered compiled bytes, or None to keep original.

    A directory holds `<addr_hex>.bin` files (a function's fresh objdiff-0
    compiled bytes). Absent file -> None -> the original bytes stay (assembly
    floor). This keeps the rebuild byte-identical while substituting real C
    only where it is proven byte-exact.
    """
    if not func_bytes_dir:
        return lambda addr, size: None
    root = Path(func_bytes_dir)

    def f(addr: int, size: int):
        p = root / f"{addr:08x}.bin"
        if p.is_file():
            data = p.read_bytes()
            if len(data) == size:
                return data
        return None
    return f


def rebuild(target: bytes, db: str | None, binary_id: int | None,
            func_bytes_dir: str | None) -> tuple[bytes, dict]:
    pe = parse_pe(target)
    image = bytearray(target)  # start from an exact copy; substitute code only
    text = text_section(pe)
    base = pe["image_base"]
    t_lo = text["rptr"]
    t_hi = text["rptr"] + text["rsize"]

    substituted = kept = out_of_range = mismatch = 0
    src = func_byte_source(func_bytes_dir)
    funcs = []
    if db and binary_id is not None:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        funcs = [(int(r["addr"]), int(r["size"] or 0)) for r in con.execute(
            "SELECT addr, size FROM func WHERE binary_id=? AND size>0", (binary_id,))]
        con.close()

    for addr, size in funcs:
        off = (addr - base)  # file_align == section_align: RVA == file offset
        if not (t_lo <= off < t_hi and off + size <= t_hi):
            out_of_range += 1
            continue
        rc = src(addr, size)
        if rc is None:
            kept += 1
            continue
        # Substitute recovered-C bytes; must equal original at this placement to
        # preserve whole-image identity (this is the per-function gate, enforced
        # at placement time).
        if bytes(image[off:off + size]) == rc:
            substituted += 1
        else:
            image[off:off + size] = rc  # apply, but flag: this breaks identity
            mismatch += 1

    stats = {"functions": len(funcs), "substituted_byte_equal": substituted,
             "kept_original": kept, "out_of_text_range": out_of_range,
             "substituted_mismatch": mismatch}
    return bytes(image), stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--db")
    ap.add_argument("--binary-id", type=int)
    ap.add_argument("--func-bytes", default=None,
                    help="dir of <addr>.bin recovered compiled bytes; absent -> keep original")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    target = Path(args.target).read_bytes()
    target_hash = hashlib.sha256(target).hexdigest()
    rebuilt, stats = rebuild(target, args.db, args.binary_id, args.func_bytes)
    Path(args.out).write_bytes(rebuilt)
    rebuilt_hash = hashlib.sha256(rebuilt).hexdigest()

    print(f"target  sha256: {target_hash}")
    print(f"rebuilt sha256: {rebuilt_hash}")
    print(f"EXACT-PLACEMENT HASH EQUAL: {target_hash == rebuilt_hash}")
    print("not a compiler-produced whole-image receipt")
    print("placement stats:", stats)
    if target_hash != rebuilt_hash:
        # localize the first differing byte to its owning section
        for i in range(min(len(target), len(rebuilt))):
            if target[i] != rebuilt[i]:
                sec = next((s["name"] for s in parse_pe(target)["sections"]
                            if s["rptr"] <= i < s["rptr"] + s["rsize"]), "?header?")
                print(f"first delta at file offset 0x{i:x} (section {sec})")
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
