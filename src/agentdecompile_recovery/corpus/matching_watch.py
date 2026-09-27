"""Refresh an exact-placement diagnostic or an explicitly supplied observation.

Legacy bin directories remain diagnostic with zero contribution. A typed
reconstruction is independently reevaluated against the selected corpus rows;
watch never recompiles or imports stored JSON as trusted provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

from . import matching_status, whole_image_relink
from .finish_binary import total_functions


def one_pass(args) -> dict:
    observation = getattr(args, "reconstruction_observation", None)
    target = Path(args.target).read_bytes()
    if observation is not None:
        contribution = whole_image_relink.evaluate_reconstruction(
            observation, target_path=args.target, output_path=args.out_exe,
            db=args.db, binary_id=args.binary_id)
        stats = {**contribution, "substituted_byte_equal": contribution["placedCompiledRegions"],
                 "substituted_mismatch": 0, "functions": total_functions(str(args.db), args.binary_id)}
        identical = contribution["wholeFileByteIdentical"]
    else:
        rebuilt, stats = whole_image_relink.rebuild(
            target, str(args.db), args.binary_id,
            str(args.func_bytes) if args.func_bytes else None)
        if args.out_exe:
            Path(args.out_exe).write_bytes(rebuilt)
        identical = hashlib.sha256(rebuilt).hexdigest() == hashlib.sha256(target).hexdigest()
    # Refresh the honest ledger (recovered = real-C byte-exact only).
    mst_argv = ["--target", str(args.target), "--db", str(args.db),
                "--binary-id", str(args.binary_id), "--src-dir", str(args.src_dir)]
    if args.receipts:
        mst_argv += ["--receipts", str(args.receipts)]
    if args.out_manifest:
        mst_argv += ["--out-manifest", str(args.out_manifest)]
    if args.out_report:
        mst_argv += ["--out-report", str(args.out_report)]
    if args.byte_exact_floor:
        mst_argv += ["--byte-exact-floor", str(args.byte_exact_floor)]
    matching_status.main(mst_argv, reconstruction_observation=observation)
    print(f"[matching-watch] placed_compiled_regions={stats['substituted_byte_equal']} "
          f"mismatch={stats['substituted_mismatch']} exact_placement_hash_equal={identical} "
          "compiler_produced=False",
          flush=True)
    # Discord: keep a fast live k1-style progress line always current, and refresh
    # the full all-binary corpus report (with PNG) at most every 10 min (its scan
    # of every binary's tree is heavy). Both edit one message in place, no spam.
    try:
        from . import discord_notify, corpus_report
        discord_notify.announce_progress(
            program=Path(args.src_dir).name,
            byte_exact=int(stats["substituted_byte_equal"]),
            total=int(stats["functions"]),
            byte_identical=False, min_delta=1)
        s = discord_notify.load_settings()
        if time.time() - float(s.get("last_corpus_report") or 0) > 600:
            discord_notify.save_settings({"last_corpus_report": time.time()})
            corpus_report.post_report(Path(args.out_exe).parent if args.out_exe
                                      else Path(args.src_dir).parent)
    except Exception:  # noqa: BLE001 - notification must never break the build loop
        pass
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--binary-id", type=int, required=True)
    ap.add_argument("--src-dir", type=Path, required=True)
    ap.add_argument("--receipts", type=Path)
    ap.add_argument("--func-bytes", type=Path)
    ap.add_argument("--out-exe", type=Path)
    ap.add_argument("--out-manifest", type=Path)
    ap.add_argument("--out-report", type=Path)
    ap.add_argument("--byte-exact-floor", type=Path)
    ap.add_argument("--watch", action="store_true", help="loop passes forever")
    ap.add_argument("--interval", type=float, default=60.0)
    args = ap.parse_args(argv)

    if not args.watch:
        stats = one_pass(args)
        # A mismatch means a substituted function's compiled bytes did not equal
        # the shipped bytes -- that breaks byte-identity and must never ship.
        return 1 if stats.get("substituted_mismatch") else 0
    while True:
        try:
            one_pass(args)
        except (OSError, ValueError) as exc:
            print(f"[matching-watch] pass error: {exc}", flush=True)
        print(f"[matching-watch] sleeping {args.interval}s...", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
