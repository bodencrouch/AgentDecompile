"""Autonomous recovery orchestrator: keep the whole matching-decomp loop running.

Supervises the recovery watchers for one binary and restarts any that exit --
so a one-shot pass (cascade, verify) re-runs after a cooldown and a crashed watch
loop comes back. This is the "everything auto-runs" driver: start it once and
the cascade grows compiling C, the permuter closes near-misses, verify measures
byte-exactness and emits substitution bytes, matching-watch rebuilds the
byte-identical image, and cross-place propagates to siblings -- all without any
manual job firing.

Passes are eventually-consistent: verify may read a .c the cascade is mid-
rewrite; the next verify pass corrects it. That is by design -- the loop
converges rather than requiring a global lock.

    python3 -m agentdecompile_recovery.corpus.cli recovery-orchestrator \\
        --program k1_win_gog_swkotor.exe --repo /K1/... --db <db> \\
        --out-dir <corpus_work> --kb <kb> --raw <raw_image> --binary-id 8 \\
        --compiler <compile-msvc71.sh> --extract-raw <dir>
"""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path


def _py(module: str, *args: str) -> list[str]:
    return ["python3", "-m", module, *args]


def build_specs(a) -> list[dict]:
    """One spec per watcher. `argv` is a full command; all are respawned on exit."""
    src_dir = str(Path(a.out_dir) / a.program)
    receipts = str(Path(a.out_dir) / f"{a.program}.byteexact.json")
    bin_dir = str(Path(a.out_dir) / f"{a.program}.bin")
    maxc_bin = str(Path(a.out_dir) / f"{a.program}.maxc-bin")
    matching_exe = str(Path(a.out_dir) / f"{a.program}.matching.exe")
    manifest = str(Path(a.out_dir) / f"{a.program}.matching.json")
    variants_report = str(Path(a.out_dir) / f"{a.program}.variants.json")
    floor = str(Path(a.out_dir) / f"{a.program}.byteexact-floor.json")
    nm_state = str(Path(a.out_dir) / f"{a.program}.nearmiss-state.json")
    cli = "agentdecompile_recovery.corpus.cli"
    specs = [
        # Cascade: grow compiling C (ghidra -> repair -> LLM -> asm floor).
        {"name": "cascade", "argv": _py(cli, "ghidra-bulk",
            "--program", a.program, "--repo", a.repo, "--db", a.db,
            "--out-dir", a.out_dir, "--kb", a.kb, "--workers", str(a.cascade_workers))
            + (["--compiler", a.compiler] if a.compiler else [])
            + (["--extract-raw", a.extract_raw] if a.extract_raw else []) if a.cascade else None},
        # Permuter: close near-miss mismatches to byte-exact (self-configuring
        # watch loop; reads its target from the program config, not argv).
        {"name": "permuter", "argv": _py("agentdecompile_recovery.corpus.text_permuter_watch",
            "--watch", "--interval", "30") if a.permuter else None},
        # Verify: measure byte-exactness + emit substitution bytes (re-runs on exit).
        # Self-healing verify: periodic --no-incremental passes purge any cache
        # contamination from a transient compile failure automatically (see
        # verify_periodic.py) -- no human has to notice a plateau and force a
        # clean pass. Every 6th respawn is a full purge; the rest stay fast.
        {"name": "verify", "argv": _py(cli, "verify-periodic",
            "--full-every", "6",
            "--verified-dir", src_dir, "--raw", a.raw, "--db", a.db,
            "--binary-id", str(a.binary_id), "--out", receipts, "--bin-dir", bin_dir, "--maxc-bin-dir", maxc_bin,
            "--workers", str(a.verify_workers))
            + (["--compiler", a.compiler] if a.compiler else []) if a.verify else None},
        # LLM near-miss closer: edit small-diff mismatches to byte-exact (the
        # lever past the permuter's text-search ceiling). Re-runs on exit.
        {"name": "nearmiss", "argv": _py(cli, "close-near-misses",
            "--verified-dir", src_dir, "--raw", a.raw, "--receipts", receipts,
            "--db", a.db, "--binary-id", str(a.binary_id), "--bin-dir", bin_dir,
            "--state", nm_state,
            "--max-diff", "8", "--limit", "120", "--workers", str(a.nearmiss_workers))
            + (["--compiler", a.compiler] if a.compiler else []) if a.nearmiss else None},
        # Matching build + honest ledger (fast, wine-free watch loop).
        {"name": "matching", "argv": _py(cli, "matching-watch",
            "--target", a.raw, "--db", a.db, "--binary-id", str(a.binary_id),
            "--src-dir", src_dir, "--receipts", receipts, "--func-bytes", bin_dir,
            "--out-exe", matching_exe, "--out-manifest", manifest,
            "--out-report", variants_report, "--byte-exact-floor", floor,
            "--watch", "--interval", "120")},
        # Cross-place recovered C onto bound sibling builds.
        {"name": "cross-place", "argv": _py(cli, "cross-place",
            "--from", a.program, "--db", a.db, "--out-dir", a.out_dir,
            "--repo", a.repo, "--watch", "--interval", "30") if a.cross_place else None},
    ]
    return [s for s in specs if s.get("argv")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--kb", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--binary-id", type=int, required=True)
    ap.add_argument("--compiler")
    ap.add_argument("--extract-raw")
    ap.add_argument("--cascade-workers", type=int, default=1)
    ap.add_argument("--verify-workers", type=int, default=1)
    ap.add_argument("--nearmiss-workers", type=int, default=1)
    ap.add_argument("--no-cascade", dest="cascade", action="store_false", default=True)
    ap.add_argument("--no-verify", dest="verify", action="store_false", default=True)
    ap.add_argument("--no-nearmiss", dest="nearmiss", action="store_false", default=True)
    ap.add_argument("--no-permuter", dest="permuter", action="store_false", default=True)
    ap.add_argument("--no-cross-place", dest="cross_place", action="store_false", default=True)
    ap.add_argument("--poll", type=float, default=20.0, help="seconds between liveness checks")
    ap.add_argument("--stagger", type=float, default=5.0, help="seconds between spawns")
    ap.add_argument("--backoff", type=float, default=30.0, help="seconds to wait before relaunching a crashed child")
    ap.add_argument("--success-backoff", type=float, default=300.0,
                    help="seconds to wait before rerunning a successful one-shot child")
    ap.add_argument("--log-dir", default="/tmp")
    a = ap.parse_args(argv)

    specs = build_specs(a)
    procs: dict[str, subprocess.Popen] = {}
    next_start: dict[str, float] = {}
    log_dir = Path(a.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"[orchestrator] supervising: {', '.join(s['name'] for s in specs)}", flush=True)
    try:
        while True:
            for s in specs:
                p = procs.get(s["name"])
                if p is None or p.poll() is not None:
                    if p is not None:
                        delay = a.success_backoff if p.returncode == 0 else a.backoff
                        next_start.setdefault(s["name"], time.monotonic() + delay)
                        if time.monotonic() < next_start[s["name"]]:
                            continue
                        print(f"[orchestrator] {s['name']} exited rc={p.returncode}; relaunching", flush=True)
                    with open(log_dir / f"orch_{a.program}_{s['name']}.log", "ab") as logf:
                        procs[s["name"]] = subprocess.Popen(
                            s["argv"], stdout=logf, stderr=subprocess.STDOUT)
                    next_start.pop(s["name"], None)
                    print(f"[orchestrator] started {s['name']} pid {procs[s['name']].pid}", flush=True)
                    time.sleep(a.stagger)  # avoid a thundering herd on the DB/wine
            time.sleep(a.poll)
    except KeyboardInterrupt:
        for p in procs.values():
            p.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
