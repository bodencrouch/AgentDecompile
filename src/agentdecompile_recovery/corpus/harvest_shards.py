"""Write byte-exact C from recovery run-results into a recovered-source tree.

Only results whose objdiff plugin reports ``differenceCount == 0`` are written.
A run marked ``success`` without a zero-difference receipt is not evidence of
byte-exactness.
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re

from .source_claims import is_real_c

NAME_RE = re.compile(r"F_([0-9a-fA-F]{8})")


def load_attempts(path: pathlib.Path) -> dict[str, list[str]]:
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return {}


def save_attempts(att: dict[str, list[str]], path: pathlib.Path) -> None:
    dest = pathlib.Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(att, sort_keys=True, indent=0))
    tmp.replace(dest)


def matching_code(result: dict) -> str | None:
    """Return code from the exact attempt carrying the zero-diff receipt."""
    for att in result.get("attempts") or []:
        code = None
        exact = False
        for pr in att.get("pluginResults") or []:
            if pr.get("pluginId") == "claude-runner":
                c = (pr.get("data") or {}).get("generatedCode")
                if c:
                    code = c
            elif pr.get("pluginId") == "objdiff":
                d = pr.get("data") or {}
                exact = (pr.get("status") == "success" and
                         d.get("differenceCount") == 0)
        if exact and code:
            return code
    return None


def matching_compiled_candidate(result: dict, max_diff: int) -> tuple[str, int] | None:
    """Return compiled C and its nonzero objdiff count for cautious staging.

    These outputs are candidates only. They must never enter the recovered
    source tree or byte-exact coverage ledger without a separate verifier.
    """
    for att in result.get("attempts") or []:
        code = None
        compiled = False
        diff = None
        for pr in att.get("pluginResults") or []:
            data = pr.get("data") or {}
            if pr.get("pluginId") == "claude-runner":
                code = data.get("generatedCode") or code
            elif pr.get("pluginId") == "compiler":
                compiled = pr.get("status") == "success"
            elif pr.get("pluginId") == "objdiff":
                count = data.get("differenceCount")
                diff = count if type(count) is int else None
        if code and compiled and diff is not None and 0 < diff <= max_diff:
            return code, diff
    return None


def merge_ledger(program: str, rows: list[dict], coverage_dir: pathlib.Path) -> None:
    """Append/replace ledger rows, keyed by ``function`` like the existing file."""
    path = pathlib.Path(coverage_dir) / f"{program}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    order: list[str] = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            fn = str(r.get("function") or "")
            if fn not in existing:
                order.append(fn)
            existing[fn] = r
    for r in rows:
        fn = r["function"]
        if fn not in existing:
            order.append(fn)
        existing[fn] = r
    path.write_text("".join(json.dumps(existing[f], sort_keys=True) + "\n"
                            for f in order))


def harvest(
    patterns: list[str],
    *,
    program: str,
    recovered_dir: pathlib.Path,
    coverage_dir: pathlib.Path,
    attempts_path: pathlib.Path,
    con=None,
    binary_id: int | None = None,
    near_miss_dir: pathlib.Path | None = None,
    near_miss_max_diff: int = 1,
    dry_run: bool = False,
) -> dict:
    meta = {}
    if con is not None and binary_id is not None:
        for r in con.execute(
            "SELECT addr, canon_key, size, calling_convention FROM func"
            " WHERE binary_id=?", (int(binary_id),)):
            meta[int(r["addr"])] = r

    dest_dir = pathlib.Path(recovered_dir) / program
    ledger_rows: list[dict] = []
    attempts = load_attempts(attempts_path)
    attempts_added = 0
    written = skipped_nodiff = skipped_nocode = skipped_shim = 0
    skipped_existing = identical_existing = 0
    near_misses_staged = near_misses_existing = near_misses_missing_meta = 0
    dirs = [d for p in patterns for d in sorted(glob.glob(p))]
    for d in dirs:
        files = sorted(glob.glob(str(pathlib.Path(d) / "*run-results*.json")),
                       key=lambda f: pathlib.Path(f).stat().st_mtime)
        if not files:
            continue
        try:
            results = json.loads(pathlib.Path(files[-1]).read_text())["results"]
        except Exception:
            continue
        run_tag = f"{pathlib.Path(d).name}:{pathlib.Path(files[-1]).name}"
        for res in results:
            am = NAME_RE.search(str(res.get("functionName")
                                    or res.get("promptPath") or ""))
            if am:
                ainfo = meta.get(int(am.group(1), 16))
                akey = (ainfo["canon_key"] if ainfo and ainfo["canon_key"]
                        else f"FUN_{int(am.group(1), 16):08x}")
                tags = attempts.setdefault(akey, [])
                if run_tag not in tags:
                    tags.append(run_tag)
                    attempts_added += 1

            if near_miss_dir is not None and not res.get("success"):
                near_miss = matching_compiled_candidate(res, near_miss_max_diff)
                nm = NAME_RE.search(str(res.get("functionName") or res.get("promptPath") or ""))
                if near_miss and nm:
                    addr = int(nm.group(1), 16)
                    info = meta.get(addr)
                    size = int(info["size"] or 0) if info else 0
                    if size <= 0:
                        near_misses_missing_meta += 1
                    else:
                        code, diff = near_miss
                        if is_real_c(code):
                            fname = (info["canon_key"] if info["canon_key"]
                                     else f"FUN_{addr:08x}")
                            candidate = (
                                "/*\n"
                                " * UNVERIFIED compiled shard candidate; not accepted recovery.\n"
                                f" * address: 0x{addr:08x}   size: {size} bytes\n"
                                f" * function: {fname}\n"
                                f" * source run: {run_tag}\n"
                                f" * objdiff differences: {diff}; relocation-aware verification pending\n"
                                " */\n" + code + "\n"
                            )
                            dest = pathlib.Path(near_miss_dir) / f"F_{addr:08x}.c"
                            if dest.exists():
                                near_misses_existing += 1
                            else:
                                if not dry_run:
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    dest.write_text(candidate)
                                near_misses_staged += 1
            if not res.get("success"):
                continue
            code = matching_code(res)
            if not code:
                skipped_nodiff += 1
                continue
            if not is_real_c(code):
                skipped_shim += 1
                continue
            m = NAME_RE.search(str(res.get("functionName") or res.get("promptPath") or ""))
            if not m:
                skipped_nocode += 1
                continue
            addr = int(m.group(1), 16)
            info = meta.get(addr)
            fname = (info["canon_key"] if info and info["canon_key"]
                     else f"FUN_{addr:08x}")
            sym = str(res.get("functionName") or "")
            head = (
                f"/*\n"
                f" * {fname}  --  recovered from {program}\n"
                f" * address: 0x{addr:08x}"
                + (f"   size: {info['size']} bytes" if info else "")
                + (f"   convention: {info['calling_convention']}"
                   if info and info["calling_convention"] else "")
                + "\n"
                " * VERIFIED BYTE-EXACT: objdiff reported 0 instruction differences\n"
                " */\n")
            output_path = dest_dir / f"{fname}.c"
            candidate_source = head + code + "\n"
            if output_path.exists():
                try:
                    existing_source = output_path.read_text(errors="replace")
                except OSError:
                    existing_source = None
                if existing_source == candidate_source:
                    identical_existing += 1
                else:
                    # A new exact result is evidence, not permission to
                    # replace an existing readable source (or its provenance).
                    # Preserve the candidate in its run-results receipt for
                    # explicit review instead of silently overwriting it.
                    skipped_existing += 1
                continue
            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
                output_path.write_text(candidate_source)
                ledger_rows.append({
                    "byteExact": True,
                    "byteExactVerified": True,
                    "convention": (info["calling_convention"] if info else None),
                    "error": "",
                    "function": fname,
                    "matched": True,
                    "originalBytes": None,
                    "size": (info["size"] if info else None),
                    "symbol": sym or None,
                })
            written += 1

    if ledger_rows and not dry_run:
        merge_ledger(program, ledger_rows, coverage_dir)
    if attempts_added and not dry_run:
        save_attempts(attempts, attempts_path)
    return {
        "written": written,
        "skipped_nodiff": skipped_nodiff,
        "skipped_nocode": skipped_nocode,
        "skipped_shim": skipped_shim,
        "skipped_existing": skipped_existing,
        "identical_existing": identical_existing,
        "near_misses_staged": near_misses_staged,
        "near_misses_existing": near_misses_existing,
        "near_misses_missing_meta": near_misses_missing_meta,
        "attempts_added": attempts_added,
        "dirs": len(dirs),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--program", required=True)
    ap.add_argument("--recovered-dir", type=pathlib.Path, required=True)
    ap.add_argument("--coverage-dir", type=pathlib.Path, required=True)
    ap.add_argument("--attempts", type=pathlib.Path, required=True)
    ap.add_argument("--db", type=pathlib.Path)
    ap.add_argument("--binary-id", type=int)
    ap.add_argument("--near-miss-dir", type=pathlib.Path,
                    help="separate unverified staging directory for compiled nonzero-diff C")
    ap.add_argument("--near-miss-max-diff", type=int, default=1,
                    help="maximum objdiff instruction differences to stage (default: 1)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    con = None
    if args.db is not None:
        from .store import connect
        con = connect(args.db)
    summary = harvest(
        args.patterns,
        program=args.program,
        recovered_dir=args.recovered_dir,
        coverage_dir=args.coverage_dir,
        attempts_path=args.attempts,
        con=con,
        binary_id=args.binary_id,
        near_miss_dir=args.near_miss_dir,
        near_miss_max_diff=args.near_miss_max_diff,
        dry_run=args.dry_run,
    )
    print(json.dumps({"ok": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
