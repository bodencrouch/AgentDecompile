"""Consolidate every recovered-C corpus into one best-C-per-function tree.

For a binary, multiple corpora may each hold recovered C for a given function:
MizuchiRE (readable semantic C++ names), byte-verified C, historical Ghidra
candidates, and the live working tree. This picks the highest-quality real C
per function address and writes it into the live tree, so downstream verify /
matching / cross-place all operate on the best available source.

Quality order (best first) is the --source order: earlier sources win. A source
is `rank:semantic:PATH` where semantic=1 marks readable-name corpora. Assembly-
floor shims (`compile-only-asm`) and byte-emitters are never chosen as "real C".
Only functions where the live tree currently has a shim (or nothing) are
upgraded, so a genuine live recovery is never overwritten by a worse source.

No hardcoded paths -- every corpus root is a --source argument.

    python3 -m agentdecompile_recovery.corpus.cli consolidate-corpus \\
        --program k1_win_gog_swkotor.exe --live-dir <corpus_work/prog> \\
        --source 0:1:<MizuchiRE/recovered-source/prog> \\
        --source 1:0:<.../source/verified_c> \\
        --source 2:0:<.../historical/ghidra_recovered_candidates/prog>
"""
from __future__ import annotations

import argparse
import re
import time
import shutil
from pathlib import Path

_HEX = re.compile(r"([0-9a-fA-F]{6,8})")
_ADDR = re.compile(r"address:\s*0x([0-9a-fA-F]+)", re.I)
_SHIM = "compile-only-asm"
_BOGUS = ("recovery_function_slice", "Generated function byte-slice source")


def _addr_of(path: Path, head: str) -> int | None:
    m = _ADDR.search(head)
    if m:
        try:
            return int(m.group(1), 16)
        except ValueError:
            pass
    m = _HEX.findall(path.stem)
    if m:
        try:
            return int(m[-1], 16)
        except ValueError:
            pass
    return None


def _is_real_c(head: str) -> bool:
    return _SHIM not in head and not any(b in head for b in _BOGUS)


def index_source(root: Path) -> dict[int, tuple[Path, str]]:
    """addr -> (file, text) for real-C files under root."""
    out: dict[int, tuple[Path, str]] = {}
    if not root.is_dir():
        return out
    for f in root.rglob("*.c"):
        try:
            t = f.read_text(errors="replace")
        except OSError:
            continue
        if not _is_real_c(t[:2000]):
            continue
        a = _addr_of(f, t[:400])
        if a is not None and a not in out:
            out[a] = (f, t)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--live-dir", type=Path, required=True,
                    help="the working recovered-source dir to upgrade in place")
    ap.add_argument("--source", action="append", default=[],
                    help="repeatable 'rank:semantic:PATH'; lower rank wins")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    live = args.live_dir
    if not live.is_dir():
        print(f"live dir missing: {live}")
        return 1

    # Parse + rank sources.
    specs = []
    for s in args.source:
        rank, semantic, path = s.split(":", 2)
        specs.append((int(rank), int(semantic), Path(path)))
    specs.sort(key=lambda x: x[0])

    # Best real-C per addr across sources.
    best: dict[int, tuple[int, bool, Path, str]] = {}
    for rank, semantic, root in specs:
        for a, (f, t) in index_source(root).items():
            cur = best.get(a)
            if cur is None or rank < cur[0]:
                best[a] = (rank, bool(semantic), f, t)

    # Live tree state: addr -> (file, is_shim).
    live_idx: dict[int, tuple[Path, bool]] = {}
    for f in live.glob("*.c"):
        try:
            head = f.read_text(errors="replace")[:2000]
        except OSError:
            continue
        a = _addr_of(f, head[:400])
        if a is None:
            continue
        if a not in live_idx or live_idx[a][1]:  # prefer recording real-c
            live_idx[a] = (f, _SHIM in head)

    bk = live.parent / f"_consolidate_backup_{args.program}_{time.strftime('%Y%m%d-%H%M%S')}"
    upgraded = added = kept = 0
    semantic_c = 0
    for a, (rank, semantic, src, text) in best.items():
        cur = live_idx.get(a)
        if cur is not None and not cur[1]:
            kept += 1  # live already has genuine real C; don't downgrade
            continue
        if "address:" not in text[:400]:
            text = f"/* address: 0x{a:08x}  consolidated */\n" + text
        if args.dry_run:
            (upgraded := upgraded + 1) if cur is not None else (added := added + 1)
            if semantic:
                semantic_c += 1
            continue
        if not bk.exists():
            bk.mkdir(parents=True, exist_ok=True)
        if cur is not None:
            shutil.copy2(cur[0], bk / cur[0].name)
            cur[0].write_text(text)
            upgraded += 1
        else:
            (live / f"consolidated_{a:08x}.c").write_text(text)
            added += 1
        if semantic:
            semantic_c += 1

    print(f"[consolidate {args.program}] sources={len(specs)} best-real-C={len(best)} "
          f"upgraded_shims={upgraded} added_new={added} kept_live_realC={kept} "
          f"semantic_chosen={semantic_c}{' (dry-run)' if args.dry_run else ''}")
    if not args.dry_run and bk.exists():
        print(f"  backup -> {bk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
