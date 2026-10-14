"""Bounded verification audits; ordinary polling never advances a full-audit clock.

The default full audit is elapsed-time based. Explicit --no-incremental and
--force-full always request fresh compilation. Legacy --full-every is opt-in;
none of these local receipts replaces fresh whole-image final acceptance.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from . import verify_recovered_byteexact as vbx


def _arg(rest: list[str], name: str) -> str | None:
    return rest[rest.index(name) + 1] if name in rest and rest.index(name) + 1 < len(rest) else None


def audit_basis(rest: list[str]) -> str | None:
    """Digest of everything a full audit reads, or None when that cannot be proven (FP-26).

    Combines the verifier's own compiler-closure basis, which only counts with a declared
    complete input manifest, and the digests of every source under ``--verified-dir``.
    None never suppresses anything.
    """
    import hashlib
    manifest, compiler = _arg(rest, "--cache-input-manifest"), _arg(rest, "--compiler")
    raw, verified = _arg(rest, "--raw"), _arg(rest, "--verified-dir")
    if not (manifest and compiler and raw and verified):
        return None
    try:
        closure, complete = vbx._cache_basis(Path(raw).read_bytes(), compiler, {}, manifest)
        if not complete:
            return None
        root = Path(verified)
        sources = sorted((str(f.relative_to(root)), hashlib.sha256(f.read_bytes()).hexdigest())
                         for f in root.rglob("*") if f.is_file())
    except (OSError, ValueError):
        return None
    return hashlib.sha256(json.dumps([closure, sources]).encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full-every", type=int, default=0,
                    help="deprecated explicit opt-in invocation-count audit; default disabled")
    ap.add_argument("--full-interval-seconds", type=float, default=86400.0,
                    help="minimum elapsed seconds between automatic full attempts; 0 disables")
    ap.add_argument("--force-full", action="store_true", help="explicit fresh full audit")
    ap.add_argument("--counter-file", type=Path,
                    help="legacy count file; audit state and lock use companion suffixes")
    args, rest = ap.parse_known_args(argv)
    if args.full_every < 0 or not math.isfinite(args.full_interval_seconds) or args.full_interval_seconds < 0:
        ap.error("audit count and interval cannot be negative")
    out_idx = rest.index("--out") if "--out" in rest else -1
    if out_idx < 0 or out_idx + 1 >= len(rest):
        ap.error("--out is required for durable audit scheduling")
    out_path = Path(rest[out_idx + 1])
    counter = args.counter_file or out_path.with_suffix(out_path.suffix + ".periodic-count")
    state_path = counter.with_suffix(counter.suffix + ".json")
    lock_path = counter.with_suffix(counter.suffix + ".lock")
    try:
        import fcntl
    except ImportError:
        print("error: verification audits require POSIX flock support on this host", flush=True)
        return 2
    try:
        with lock_path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("error: verification-audit-owner-active", flush=True)
                return 2
            state = {"schema": "agentdecompile.periodic-audit/v1", "count": 0,
                     "last_full_attempt": None}
            if state_path.exists():
                loaded = json.loads(state_path.read_text())
                if (not isinstance(loaded, dict) or loaded.get("schema") != state["schema"]
                        or not isinstance(loaded.get("count"), int)
                        or loaded["count"] < 0
                        or (loaded.get("last_full_attempt") is not None
                            and (not isinstance(loaded["last_full_attempt"], (int, float))
                                 or not math.isfinite(loaded["last_full_attempt"])))):
                    raise ValueError("invalid audit scheduling state")
                state = loaded
            elif counter.exists():
                state["count"] = int(counter.read_text().strip())
                if state["count"] < 0:
                    raise ValueError("negative legacy audit count")
            now = time.time()
            last = state["last_full_attempt"]
            if last is not None and now < last:
                # Wall-clock rollback must not cause a full-audit storm or an
                # unbounded wait for a future timestamp from the previous boot.
                last = now
                state["last_full_attempt"] = now
            state["count"] += 1
            explicit = args.force_full or "--no-incremental" in rest
            legacy = args.full_every > 0 and state["count"] % args.full_every == 0
            elapsed = args.full_interval_seconds > 0 and (last is None or now - last >= args.full_interval_seconds)
            full = explicit or legacy or elapsed
            basis = audit_basis(rest)
            suppressed = (full and not explicit and basis is not None
                          and basis == state.get("last_full_basis"))
            if suppressed:
                # Unchanged inputs: a repeated automatic full audit adds no evidence (FP-26).
                # An explicit request, or any input change, still runs a fresh full audit.
                full = False
            if args.full_every:
                print("[verify-periodic] --full-every is deprecated and explicitly enabled", flush=True)
            if full:
                state["last_full_attempt"] = now  # Charge before invoking; failure does not reset cooldown.
                if "--no-incremental" not in rest:
                    rest.append("--no-incremental")
            vbx._write_json_atomic(state_path, state)
            reason = ("explicit" if explicit else "suppressed-unchanged-inputs" if suppressed
                      else "legacy-count" if legacy else "elapsed" if elapsed else "incremental")
            print(f"[verify-periodic] pass #{state['count']}: {'FULL' if full else 'incremental'} ({reason})", flush=True)
            start = time.monotonic()
            rc = vbx.main(rest)
            if full and rc == 0 and basis is not None:
                state["last_full_basis"] = basis  # only a completed full audit makes inputs "audited"
                vbx._write_json_atomic(state_path, state)
            print(f"[verify-periodic] pass #{state['count']} done in {time.monotonic() - start:.0f}s rc={rc}", flush=True)
            return rc
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: verification-audit-state-unavailable: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
