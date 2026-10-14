"""Close near-miss functions to byte-exact with an LLM edit.

The text-permuter only rearranges existing tokens, so it stalls on functions
whose recovered C is *almost* right (a wrong cast, a swapped operand, a missing
`& 0xff`). Those show up in the verify receipts as small masked-diff mismatches.
This pass hands each such function to the LLM with the recovered C, the shipped
machine code, and the exact byte-diff, and asks for an edit that reproduces the
target bytes. Every candidate is re-verified the same relocation-aware way; only
a genuine objdiff-0 result is kept (and emits a .bin), so this can only ever add
real byte-exact C -- never regress the byte-accurate build.

Easiest first (smallest diff). Persistent state skips already-tried functions.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm_cleanup
from .verify_recovered_byteexact import (
    pe_mapper, text_bytes_and_relocs, masked_diff_count, _parse,
)
from .recovered_c_preamble import preamble_for_source

_PROMPT = """\
You are fixing a decompiled C function so it compiles to EXACT target bytes.

The function below compiles, but its machine code differs from the shipped
binary at {ndiff} byte position(s) (relocation operands already ignored). Edit
the C so a straight `cl /O2 /Gd` compile reproduces the target bytes EXACTLY.
Keep it real C (no __asm, no _emit, no byte arrays). Change only what the diff
requires -- a cast width, an operand order, a signed/unsigned choice, a missing
mask, a constant. Output ONLY the corrected C in one ```c block.

--- recovered C ---
{body}

--- target machine code (hex, {size} bytes) ---
{target_hex}

--- your current compiled bytes (hex) ---
{cand_hex}
"""


def _compile(src_text: str, compiler: str) -> tuple[bytes, list[int]] | None:
    with tempfile.TemporaryDirectory(prefix="nm-", dir="/tmp") as td:
        c = Path(td) / "in.c"
        o = Path(td) / "o.obj"
        c.write_text(preamble_for_source(src_text) + src_text)
        try:
            subprocess.run(["bash", compiler, str(c), str(o), "recovered"],
                           capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return None
        if not o.exists():
            return None
        return text_bytes_and_relocs(o.read_bytes())


def close_one(cfile: Path, raw: bytes, mapper, compiler: str, size_map, bin_dir, model):
    src = cfile.read_text(errors="replace")
    if "compile-only-asm" in src[:2000]:
        return {"file": cfile.name, "closed": False, "reason": "asm-floor"}
    parsed = _parse(src, raw, mapper, size_map)
    if parsed is None:
        return {"file": cfile.name, "closed": False, "reason": "unparsed"}
    addr, size, target = parsed
    tr = _compile(src, compiler)
    if tr is None:
        return {"file": cfile.name, "closed": False, "reason": "compile-failed"}
    text, relocs = tr
    diff = masked_diff_count(text, target, relocs)
    if diff == 0:
        return {"file": cfile.name, "closed": True, "reason": "already-exact"}
    prompt = _PROMPT.format(ndiff=diff, body=src, size=size,
                            target_hex=target.hex(), cand_hex=text[:size].hex())
    cmd = llm_cleanup.build_cli_command(model=model)
    try:
        res = llm_cleanup._subprocess_runner(cmd, prompt, 180)
    except Exception as exc:  # noqa: BLE001
        return {"file": cfile.name, "closed": False, "reason": f"llm-error:{exc.__class__.__name__}"}
    if res.returncode != 0:
        return {"file": cfile.name, "closed": False, "reason": "llm-nonzero"}
    edited = llm_cleanup._extract_c(res.stdout) if hasattr(llm_cleanup, "_extract_c") else None
    if not edited:
        import re
        m = re.search(r"```(?:c|cpp)?\n(.*?)```", res.stdout, re.S)
        edited = m.group(1) if m else None
    if not edited or "compile-only-asm" in edited or "_emit" in edited or "__asm" in edited:
        return {"file": cfile.name, "closed": False, "reason": "no-valid-edit"}
    tr2 = _compile(edited, compiler)
    if tr2 is None:
        return {"file": cfile.name, "closed": False, "reason": "edit-compile-failed"}
    text2, relocs2 = tr2
    if masked_diff_count(text2, target, relocs2) != 0:
        return {"file": cfile.name, "closed": False, "reason": "edit-not-exact"}
    # Success: keep the improved C, emit the substitution .bin (reloc-linked).
    # Preserve the original provenance header (addr/size), then stamp the close
    # marker so this stays traceable even when the LLM body opens with a comment.
    header = src.split("*/", 1)[0] + "*/\n" if src.startswith("/*") else ""
    cfile.write_text(header + "/* LLM near-miss closed to byte-exact */\n" + edited)
    if bin_dir is not None and len(text2) >= size:
        linked = bytearray(text2[:size])
        for o in relocs2:
            for i in range(o, min(o + 4, size)):
                linked[i] = target[i]
        if bytes(linked) == target:
            (bin_dir / f"{addr:08x}.bin").write_bytes(bytes(linked))
    return {"file": cfile.name, "closed": True, "addr": hex(addr), "from_diff": diff}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verified-dir", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--receipts", type=Path, required=True)
    ap.add_argument("--compiler", type=Path, required=True)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--binary-id", type=int)
    ap.add_argument("--bin-dir", type=Path)
    ap.add_argument("--max-diff", type=int, default=8, help="only attempt diffs <= this")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--model", default=None)
    ap.add_argument("--state", type=Path)
    args = ap.parse_args(argv)

    raw = args.raw.read_bytes()
    mapper = pe_mapper(raw)
    size_map = {}
    if args.db and args.binary_id is not None:
        import sqlite3
        con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        size_map = {int(a): int(s or 0) for a, s in con.execute(
            "SELECT addr, size FROM func WHERE binary_id=?", (args.binary_id,))}
        con.close()
    bin_dir = None
    if args.bin_dir:
        bin_dir = args.bin_dir
        bin_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.state or args.receipts.with_suffix(".nearmiss.json")
    tried = set()
    if state_path.is_file():
        try:
            tried = set(json.loads(state_path.read_text()).get("tried", []))
        except (OSError, ValueError):
            tried = set()

    doc = json.loads(args.receipts.read_text())
    cands = [r for r in doc.get("results", [])
             if r.get("reason") == "mismatch" and isinstance(r.get("diff"), int)
             and 0 < r["diff"] <= args.max_diff and r.get("file") not in tried]
    cands.sort(key=lambda r: r["diff"])
    cands = cands[:args.limit]
    print(f"near-miss closer: {len(cands)} candidates (diff<= {args.max_diff}), "
          f"{len(tried)} already tried", flush=True)

    src_dir = args.verified_dir
    closed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(close_one, src_dir / r["file"], raw, mapper, str(args.compiler),
                          size_map, bin_dir, args.model): r for r in cands}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"file": r["file"], "closed": False, "reason": str(exc)[:60]}
            tried.add(r["file"])
            if res.get("closed"):
                closed += 1
                print(f"  ✓ closed {res.get('addr','')} (was diff {r['diff']})  [{closed}]", flush=True)
            if i % 20 == 0:
                state_path.write_text(json.dumps({"tried": sorted(tried)}))
    state_path.write_text(json.dumps({"tried": sorted(tried)}))
    print(f"near-miss closer done: {closed}/{len(cands)} newly byte-exact", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
