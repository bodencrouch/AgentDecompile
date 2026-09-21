#!/usr/bin/env python3
"""Matching-decompilation status for a single binary.

Fuses three sources into one honest per-function ledger and a whole-image
byte-identity check:

  * the fresh relocation-aware byte-exact receipts
    (verify_recovered_byteexact --out), which prove a function's recovered C
    compiles to the shipped bytes (objdiff-0),
  * the corpus DB func list (the denominator: every code function with a size),
  * the recovered-source tree on disk (real C vs original-byte asm floor).

A function is counted "recovered" only when its receipt is byte-exact. Compiling
but not byte-exact is NOT recovery for a matching build; original-byte asm floor
is the substrate that keeps the rebuild runnable until real C lands.

Emits the byte-identical rebuilt image via whole_image_relink (assembly floor)
so the number is always paired with a runnable proof, plus a per-function
manifest for dr-down.

No hardcoded paths; every location is an argument.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from agentdecompile_recovery.corpus import whole_image_relink as wir

_HEX = re.compile(r"([0-9a-fA-F]{6,8})")


def load_receipts(path: Path) -> dict[int, dict]:
    """addr(int) -> receipt. Tolerates partial (still-running) receipt files."""
    if not path or not path.is_file():
        return {}
    doc = json.loads(path.read_text())
    out: dict[int, dict] = {}
    for r in doc.get("results", []):
        a = r.get("addr")
        if a is None:
            continue
        try:
            out[int(str(a), 16) if isinstance(a, str) else int(a)] = r
        except ValueError:
            continue
    return out


def index_disk(src_dir: Path) -> dict[int, str]:
    """Scan the recovered-source dir ONCE: addr(int) -> real-c / asm-floor.

    The trailing hex token in a stem is the function address (e.g.
    ``FindRoom_00452b10`` -> 0x452b10). Real C where the shim marker is absent.
    """
    idx: dict[int, str] = {}
    for f in src_dir.glob("*.c"):
        m = _HEX.findall(f.stem)
        if not m:
            continue
        addr = int(m[-1], 16)
        head = f.read_text(errors="replace")[:2000]
        kind = "asm-floor" if "compile-only-asm" in head else "real-c"
        # real-c wins if an address somehow has both
        if idx.get(addr) != "real-c":
            idx[addr] = kind
    return idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="shipped PE (raw image)")
    ap.add_argument("--db", required=True)
    ap.add_argument("--binary-id", type=int, required=True)
    ap.add_argument("--src-dir", required=True, help="recovered-source dir for this program")
    ap.add_argument("--receipts", help="verify_recovered_byteexact --out JSON (may be partial)")
    ap.add_argument("--out-exe", help="write the byte-identical rebuilt image here")
    ap.add_argument("--out-manifest", help="write the per-function manifest JSON here")
    args = ap.parse_args()

    target = Path(args.target).read_bytes()
    receipts = load_receipts(Path(args.receipts)) if args.receipts else {}
    disk = index_disk(Path(args.src_dir))

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    funcs = [(int(r["addr"]), int(r["size"] or 0)) for r in con.execute(
        "SELECT addr, size FROM func WHERE binary_id=? AND size>0", (args.binary_id,))]
    con.close()

    pe = wir.parse_pe(target)
    text = wir.text_section(pe)
    base = pe["image_base"]
    t_lo, t_hi = text["rptr"], text["rptr"] + text["rsize"]

    manifest = []
    counts = {"byte_exact": 0, "compiles_not_exact": 0, "asm_floor": 0,
              "absent_c": 0, "out_of_text": 0, "verified_reloc_free": 0}
    for addr, size in funcs:
        off = addr - base
        in_text = t_lo <= off < t_hi and off + size <= t_hi
        rc = receipts.get(addr)
        kind = disk.get(addr, "absent") if in_text else "data/thunk"
        if not in_text:
            counts["out_of_text"] += 1
            status = "out-of-text"
        elif kind == "asm-floor":
            # Assembly floor: original bytes in a naked stub. It is the
            # substrate, never counted as recovery even if it "verifies".
            counts["asm_floor"] += 1
            status = "asm-floor"
        elif rc and rc.get("ok") and kind == "real-c":
            counts["byte_exact"] += 1
            if not rc.get("relocs"):
                counts["verified_reloc_free"] += 1
            status = "byte-exact"
        elif kind == "real-c":
            counts["compiles_not_exact"] += 1
            status = "compiles-not-exact"
        else:
            counts["absent_c"] += 1
            status = "absent"
        manifest.append({"addr": f"0x{addr:08x}", "size": size, "status": status,
                         "relocs": (rc or {}).get("relocs"), "disk": kind})

    code_total = len(funcs) - counts["out_of_text"]
    bx = counts["byte_exact"]
    print(f"binary_id={args.binary_id}  code functions={code_total}  (out-of-text={counts['out_of_text']})")
    print(f"  byte-exact (recovered)      : {bx:6d}  ({100*bx/max(code_total,1):.1f}%)")
    print(f"    of which relocation-free  : {counts['verified_reloc_free']:6d}  (raw-substitutable today)")
    print(f"  compiles, not byte-exact    : {counts['compiles_not_exact']:6d}")
    print(f"  asm floor only              : {counts['asm_floor']:6d}")
    print(f"  no C yet                    : {counts['absent_c']:6d}")
    if args.receipts:
        print(f"  (receipts cover {len(receipts)} functions"
              f"{' — PARTIAL, verify still running' if len(receipts) < code_total else ''})")

    if args.out_exe:
        rebuilt, stats = wir.rebuild(target, args.db, args.binary_id, None)
        Path(args.out_exe).write_bytes(rebuilt)
        import hashlib
        same = hashlib.sha256(rebuilt).hexdigest() == hashlib.sha256(target).hexdigest()
        print(f"  rebuilt image byte-identical: {same}  -> {args.out_exe}")

    if args.out_manifest:
        Path(args.out_manifest).write_text(json.dumps(
            {"binary_id": args.binary_id, "code_total": code_total,
             "counts": counts, "functions": manifest}, indent=1))
        print(f"  manifest -> {args.out_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
