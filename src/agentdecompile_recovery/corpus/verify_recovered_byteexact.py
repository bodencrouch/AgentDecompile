"""Fresh, relocation-aware byte-exact reconciliation for recovered C.

Tier-2 verification (compile-and-check, zero search, zero LLM): recompile an
existing recovered `.c` with the era-exact VC7.1 toolchain and compare the
emitted function bytes to the shipped image, masking relocated operands the
way objdiff does. A raw `bytes == bytes` check (what `ghidra_verify.one`
uses) rejects every function that calls another function or references a
global, because the compiled `e8 <rel32>` / `<abs32>` operand is a link-time
placeholder that never equals the shipped value. Masking each COFF relocation
site in BOTH sides is exactly the relocation-aware comparison objdiff performs,
and it is what turns a historical "objdiff 0-diff" claim into a fresh,
receipt-backed proof produced in this run.

Not a test file: this is a verification pass that writes receipts. Run:

    python3 -m agentdecompile_recovery.corpus.verify_recovered_byteexact \\
        --verified-dir <.../source/verified_c> --raw <raw_image> \\
        --compiler <compile-msvc71.sh> --out <receipts.json> [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .recovered_c_preamble import PREAMBLE as _PREAMBLE


def _write_json_atomic(path: Path, value: object) -> None:
    """Replace a checkpoint only after its complete JSON is written beside it."""
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(value), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

_ADDR_RE = re.compile(r"address:\s*(0x[0-9a-fA-F]+)")
_SIZE_RE = re.compile(r"size:\s*(\d+)\s*bytes")
_FUNC_RE = re.compile(r"\b(F_[0-9a-fA-F]+)\s*\(")
# Some recovered-C pools (MizuchiRE/recovered-source, recovered_candidates)
# embed the shipped bytes and encode the address in the function name
# (e.g. `Unwind_00717140`) instead of an `address:` header + `F_<addr>` name.
_MC_RE = re.compile(r"original machine code:\s*([0-9a-fA-F]+)")
_NAMEADDR_RE = re.compile(r"\b[A-Za-z_]\w*_([0-9a-fA-F]{6,8})\s*\(")


def pe_mapper(blob: bytes):
    """VA -> file offset for a raw PE image dump (image-base relative)."""
    if blob[:2] != b"MZ":
        base = 0x00400000  # standard swkotor image base; raw dump starts at base
        return lambda va: va - base
    e_lfanew = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = e_lfanew + 24
    image_base = struct.unpack_from("<I", blob, opt + 28)[0]
    nsec = struct.unpack_from("<H", blob, e_lfanew + 6)[0]
    opt_sz = struct.unpack_from("<H", blob, e_lfanew + 20)[0]
    sect = opt + opt_sz
    secs = []
    for i in range(nsec):
        sh = blob[sect + i * 40: sect + i * 40 + 40]
        vaddr, _vs = struct.unpack_from("<II", sh, 12)[0], 0
        vsize = struct.unpack_from("<I", sh, 8)[0]
        vaddr = struct.unpack_from("<I", sh, 12)[0]
        rawptr = struct.unpack_from("<I", sh, 20)[0]
        secs.append((vaddr, vsize, rawptr))

    def f(va: int):
        rva = va - image_base
        for vaddr, vsize, rawptr in secs:
            if vaddr <= rva < vaddr + max(vsize, 1):
                return rawptr + (rva - vaddr)
        return None
    return f


def text_bytes_and_relocs(obj: bytes) -> tuple[bytes, list[int]] | None:
    """Return (.text raw bytes, [reloc offsets within .text])."""
    if len(obj) < 20 or len(obj) > 64 * 1024 * 1024:  # guard against a pathological object
        return None
    nsec, _t, _symptr, _nsym, opt, _flags = struct.unpack("<HIIIHH", obj[2:20])
    off = 20 + opt
    for _ in range(nsec):
        sh = obj[off:off + 40]
        off += 40
        name = sh[:8].rstrip(b"\x00").decode("latin1")
        if not name.startswith(".text"):
            continue
        srawsz, srawptr, relptr = struct.unpack_from("<III", sh, 16)
        nrel = struct.unpack_from("<H", sh, 32)[0]
        text = obj[srawptr:srawptr + srawsz]
        offs = []
        for r in range(nrel):
            rv = struct.unpack_from("<I", obj, relptr + r * 10)[0]
            offs.append(rv)
        return text, offs
    return None


def masked_diff_count(cand: bytes, target: bytes, reloc_offsets: list[int]) -> int:
    """Byte-diff count after masking relocated operands. 0 = byte-exact.

    A small nonzero count (1-5) is a near-miss the permuter can usually close in
    seconds; a large count means the recovered C is structurally different and
    belongs to the slow tier. Returning the distance (not just a bool) lets the
    finish pipeline rank the remainder and permute near-misses first.
    """
    n = len(target)
    if len(cand) < n:
        return n  # too short: treat as fully different
    a = bytearray(cand[:n])
    b = bytearray(target)
    for o in reloc_offsets:
        for i in range(o, min(o + 4, n)):  # REL32/DIR32 are 4-byte operands
            a[i] = 0
            b[i] = 0
    return sum(1 for i in range(n) if a[i] != b[i])


def masked_equal(cand: bytes, target: bytes, reloc_offsets: list[int]) -> bool:
    return masked_diff_count(cand, target, reloc_offsets) == 0


def _parse(src: str, raw: bytes, mapper, size_map: dict[int, int] | None = None) -> tuple[int, int, bytes] | None:
    """Return (addr, size, target_bytes). Handles multiple pool formats.

    ``size_map`` (addr -> size, from the func DB) supplies the size for
    candidate pools whose header carries an ``address:`` but no ``size:`` field
    (ghidra_bulk's whole-program candidates name the function e.g. ``return_void``
    and omit size). Without it those pools all fail to parse.
    """
    ms = _SIZE_RE.search(src)
    # Address from `address:` header, else from an `<name>_<hex>(` definition.
    ma = _ADDR_RE.search(src)
    addr = int(ma.group(1), 16) if ma else None
    if addr is None:
        mna = _NAMEADDR_RE.search(src)
        addr = int(mna.group(1), 16) if mna else None
    # Target bytes: embedded `original machine code:` hex, else sliced from image.
    mc = _MC_RE.search(src)
    if mc:
        target = bytes.fromhex(mc.group(1))
        return (addr if addr is not None else -1, len(target), target)
    if addr is not None:
        size = int(ms.group(1)) if ms else (size_map or {}).get(addr, 0)
        if size <= 0:
            return None
        o = mapper(addr)
        if o is None or o + size > len(raw):
            return None
        return (addr, size, raw[o:o + size])
    return None


def verify_one(cfile: Path, raw: bytes, mapper, compiler: str, size_map: dict[int, int] | None = None,
               bin_dir: Path | None = None, maxc_dir: Path | None = None) -> dict:
    src = cfile.read_text(errors="replace")
    # An asm-floor stub (__declspec(naked) + the original bytes) reproduces the
    # shipped bytes by construction -- it IS the original, not recovered C.
    # Counting it as byte-exact would launder the assembly floor into the
    # "decompiled" metric, so it is excluded here (and never emits a .bin).
    if "compile-only-asm" in src[:2000]:
        return {"file": cfile.name, "ok": False, "reason": "asm-floor", "asm_floor": True}
    parsed = _parse(src, raw, mapper, size_map)
    if parsed is None:
        return {"file": cfile.name, "ok": False, "reason": "unparsed-header"}
    addr, size, target = parsed
    with tempfile.TemporaryDirectory(prefix="recon-", dir="/tmp") as td:
        cpath = Path(td) / "in.c"
        opath = Path(td) / "out.obj"
        cpath.write_text(_PREAMBLE + src)
        fname = "recovered"  # symbol not needed; .text section is the function
        try:
            compile_result = subprocess.run(["bash", compiler, str(cpath), str(opath), fname],
                                            capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return {"file": cfile.name, "addr": hex(addr), "ok": False, "reason": "compile-timeout"}
        if not opath.exists():
            # Keep the compiler's own bounded explanation in the receipt.  The
            # result remains a failed verification; this only makes the next
            # readable-C repair actionable without re-running the compiler.
            diagnostic = (compile_result.stderr or compile_result.stdout or "").strip()
            return {"file": cfile.name, "addr": hex(addr), "ok": False,
                    "reason": "compile-failed", "compilerReturnCode": compile_result.returncode,
                    "compilerDiagnostic": diagnostic[-2000:]}
        tr = text_bytes_and_relocs(opath.read_bytes())
    if tr is None:
        return {"file": cfile.name, "addr": hex(addr), "ok": False, "reason": "no-text-section"}
    text, reloc_offsets = tr
    diff = masked_diff_count(text, target, reloc_offsets)
    byte_exact = diff == 0
    # Emit the substitution input (.bin) for whole_image_relink. A byte-exact
    # function's compiled instruction bytes equal the shipped bytes everywhere
    # except at relocation operands, which are fixed by the canonical layout,
    # not the source -- exactly what a linker resolves. Reconstruct the linked
    # bytes by taking each 4-byte reloc operand from the shipped image, then
    # REQUIRE the result to equal the shipped bytes before emitting. That gate
    # means a .bin can never break whole-image identity, and it lets every
    # byte-exact function (not just relocation-free ones) be physically placed.
    reloc_linked = False
    if byte_exact and bin_dir is not None and len(text) >= size:
        linked = bytearray(text[:size])
        for o in reloc_offsets:
            for i in range(o, min(o + 4, size)):
                linked[i] = target[i]
        if bytes(linked) == target:
            (bin_dir / f"{addr:08x}.bin").write_bytes(bytes(linked))
            reloc_linked = bool(reloc_offsets)
    # max-c substitution bytes: for the readable (not-necessarily-byte-exact)
    # build, place the recovered C's compiled bytes for ANY function whose
    # compile fits the original slot -- reloc operands taken from the shipped
    # image so calls/globals resolve. This maximizes real-C coverage; the image
    # is NOT byte-identical where the C differs from the original.
    if maxc_dir is not None and len(text) >= size:
        mc = bytearray(text[:size])
        for o in reloc_offsets:
            for i in range(o, min(o + 4, size)):
                mc[i] = target[i]
        (maxc_dir / f"{addr:08x}.bin").write_bytes(bytes(mc))
    return {"file": cfile.name, "addr": hex(addr), "size": size, "func": fname,
            "relocs": len(reloc_offsets), "ok": byte_exact, "diff": diff,
            "reloc_linked": reloc_linked,
            "reason": "byte-exact-relocation-masked" if byte_exact else "mismatch"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verified-dir", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--db", help="corpus DB for function sizes (pools whose header omits size:)")
    ap.add_argument("--binary-id", type=int, help="binary_id for the --db size lookup")
    ap.add_argument("--bin-dir", help="also emit <addr>.bin substitution inputs for "
                    "relocation-free byte-exact functions (feeds whole_image_relink)")
    ap.add_argument("--maxc-bin-dir", help="emit slot-fitting compiled bytes for ANY compiling "
                    "function (byte-exact or not) for the readable max-C image")
    ap.add_argument("--no-incremental", action="store_true",
                    help="recompile every function (disable the mtime result cache)")
    args = ap.parse_args(argv)

    bin_dir = None
    if args.bin_dir:
        bin_dir = Path(args.bin_dir)
        bin_dir.mkdir(parents=True, exist_ok=True)
    maxc_dir = None
    if getattr(args, "maxc_bin_dir", None):
        maxc_dir = Path(args.maxc_bin_dir)
        maxc_dir.mkdir(parents=True, exist_ok=True)

    raw = Path(args.raw).read_bytes()
    mapper = pe_mapper(raw)
    size_map: dict[int, int] = {}
    if args.db and args.binary_id is not None:
        import sqlite3
        con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        size_map = {int(a): int(s or 0) for a, s in con.execute(
            "SELECT addr, size FROM func WHERE binary_id=?", (args.binary_id,))}
        con.close()
        print(f"loaded {len(size_map)} function sizes from DB", flush=True)
    files = sorted(Path(args.verified_dir).glob("*.c"))
    if args.limit:
        files = files[:args.limit]

    # Incremental cache: a full re-verify recompiles ~24k functions every pass,
    # but between passes only the files the cascade/permuter/cross-place touched
    # change. Cache each result keyed by (name, mtime, size); reuse it when the
    # file is unchanged, recompile only new/changed files. This is cumulative
    # (never regresses -- old results persist) and turns an hours-long pass into
    # minutes once warm. Disable with --no-incremental.
    out_path = Path(args.out)
    state_path = out_path.with_suffix(out_path.suffix + ".state.json")
    cache: dict[str, dict] = {}
    if not args.no_incremental and state_path.is_file():
        try:
            cache = json.loads(state_path.read_text())
        except (OSError, ValueError):
            cache = {}

    def sig(f: Path) -> str:
        st = f.stat()
        return f"{int(st.st_mtime)}:{st.st_size}"

    fresh = [f for f in files if args.no_incremental or cache.get(f.name, {}).get("sig") != sig(f)]
    print(f"verifying {len(files)} recovered .c files; {len(fresh)} new/changed "
          f"(incremental{'-off' if args.no_incremental else ''}), "
          f"{len(files) - len(fresh)} cached", flush=True)

    from concurrent.futures import as_completed
    new_state: dict[str, dict] = dict(cache) if not args.no_incremental else {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(verify_one, f, raw, mapper, args.compiler, size_map, bin_dir, maxc_dir): f
                for f in fresh}
        done = 0
        for fut in as_completed(futs):
            f = futs[fut]
            try:
                r = fut.result()
            except Exception as exc:  # noqa: BLE001 - a bad function must not kill the pass
                r = {"file": f.name, "ok": False, "reason": f"error:{exc.__class__.__name__}"}
            new_state[f.name] = {"sig": sig(f), "result": r}
            done += 1
            if done % 50 == 0:
                ok = sum(1 for v in new_state.values() if v["result"].get("ok"))
                print(f"  {done}/{len(fresh)} recompiled  byte-exact total: {ok}", flush=True)
                _write_json_atomic(state_path, new_state)

    # Merge: every file's latest result (cached + fresh).
    results = [new_state[f.name]["result"] for f in files if f.name in new_state]
    ok = [r for r in results if r.get("ok")]
    _write_json_atomic(out_path, {"total": len(results), "byteExact": len(ok),
                                  "results": results})
    _write_json_atomic(state_path, new_state)
    from collections import Counter
    print(f"\nFRESH byte-exact (relocation-masked): {len(ok)}/{len(results)} "
          f"({100*len(ok)/max(len(results),1):.1f}%)")
    print("reasons:", dict(Counter(r.get("reason", "?") for r in results)))
    print("receipts:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
