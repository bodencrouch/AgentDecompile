"""Self-healing verify driver: periodic full passes purge cache contamination.

The incremental cache in verify-byteexact keys results by (mtime, size), which
makes it fast (minutes instead of hours) but also means a transient failure
during one pass -- a compiler timeout under resource contention, a flaky Wine
call -- gets baked in permanently: the file's mtime/size don't change, so it's
never rechecked. That happened for real on 2026-09-15 (~350 files spuriously
marked non-byte-exact under load, silently capping the honest count until a
human noticed and force-ran --no-incremental).

This wraps verify-byteexact so the orchestrator no longer needs a human to
notice and intervene: every Nth pass runs --no-incremental to recompile
everything and self-correct any contamination, the rest run incremental for
speed. Both still only ever WRITE a .bin on success (verify_one never
deletes), so this can only ever recover lost byte-exact discoveries, never
regress the shipped build.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import verify_recovered_byteexact as vbx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full-every", type=int, default=6,
                    help="run a --no-incremental full pass every Nth invocation "
                         "(default 6; the orchestrator respawns this on exit, so "
                         "N passes ~= N verify cycles between self-corrections)")
    ap.add_argument("--counter-file", type=Path,
                    help="persists the pass count across respawns; defaults to "
                         "<out>.periodic-count next to --out")
    # Pass everything else straight through to verify_recovered_byteexact.
    args, rest = ap.parse_known_args(argv)

    out_idx = rest.index("--out") if "--out" in rest else -1
    out_path = Path(rest[out_idx + 1]) if out_idx >= 0 else None
    counter_path = args.counter_file or (
        out_path.with_suffix(out_path.suffix + ".periodic-count") if out_path else None)

    count = 0
    if counter_path and counter_path.is_file():
        try:
            count = int(counter_path.read_text().strip())
        except (OSError, ValueError):
            count = 0
    count += 1
    if counter_path:
        counter_path.write_text(str(count))

    full = args.full_every > 0 and count % args.full_every == 0
    if full:
        print(f"[verify-periodic] pass #{count}: FULL (--no-incremental) self-heal "
              f"pass -- purging any cache contamination from the last {args.full_every} "
              f"cycles", flush=True)
        rest = rest + ["--no-incremental"]
    else:
        print(f"[verify-periodic] pass #{count}: incremental "
              f"(next full pass at #{((count // args.full_every) + 1) * args.full_every})",
              flush=True)
    t0 = time.time()
    rc = vbx.main(rest)
    print(f"[verify-periodic] pass #{count} done in {time.time() - t0:.0f}s", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
