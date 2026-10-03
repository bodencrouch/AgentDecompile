"""Supervise existing recovery stages with durable bounded retry admission.

A successful child exit means one pass completed, never whole-image recovery.
This preserves the existing stage topology; it does not make concurrent mutable
providers safe or replace catalog ownership checks. Interrupted/unknown children
retain reservations until external reconciliation; they are never blindly replayed.
"""
from __future__ import annotations

import argparse
import json
import math
import uuid
import subprocess
import sys
import time
from pathlib import Path

from .supervision import (RESERVED, SupervisionError, decide, execution_basis,
                          load_state, owner_lock, process_identity,
                          provider_revision, save_state, session_clearance)


def _py(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def build_specs(a) -> list[dict]:
    """Existing stage topology; durable policy gates subsequent dispatches."""
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
        # Periodic verifier owns its time-based full-audit policy.
        {"name": "verify", "argv": _py(cli, "verify-periodic",
            "--verified-dir", src_dir, "--raw", a.raw, "--db", a.db,
            "--binary-id", str(a.binary_id), "--out", receipts, "--bin-dir", bin_dir, "--maxc-bin-dir", maxc_bin,
            "--workers", str(a.verify_workers),
            "--full-interval-seconds", str(a.full_interval_seconds),
            "--transient-retry-seconds", str(a.transient_retry_seconds))
            + (["--cache-input-manifest", a.cache_input_manifest] if a.cache_input_manifest else [])
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
            "--repo", a.repo, "--raw-dir", str(Path(a.extract_raw) if a.extract_raw and Path(a.extract_raw).is_dir() else Path(a.raw).parent),
            "--byteexact-receipt", receipts, "--watch", "--interval", "30") if a.cross_place else None},
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
    ap.add_argument("--cache-input-manifest")
    ap.add_argument("--transient-retry-seconds", type=float, default=300.0)
    ap.add_argument("--full-interval-seconds", type=float, default=86400.0)
    ap.add_argument("--input-basis", help="explicit immutable input manifest digest/revision; required to launch")
    ap.add_argument("--max-failed-exits", type=int, default=3)
    ap.add_argument("--status", action="store_true", help="read durable state without writes or launches")
    ap.add_argument("--once", action="store_true", help="one admission cycle; dispatched children remain reserved")
    a = ap.parse_args(argv)
    for name in ("poll", "stagger", "backoff", "success_backoff", "transient_retry_seconds", "full_interval_seconds"):
        value = getattr(a, name)
        if not math.isfinite(value) or value < 0:
            ap.error(f"--{name.replace('_', '-')} must be finite and nonnegative")
    if a.max_failed_exits < 1:
        ap.error("--max-failed-exits must be positive")
    if not a.status and not (a.input_basis and a.input_basis.strip()):
        ap.error("--input-basis is required for dispatch")
    # Canonicalize path arguments once, before constructing commands and hashes.
    for name in ("db", "out_dir", "kb", "raw", "compiler", "extract_raw", "log_dir", "cache_input_manifest"):
        if getattr(a, name, None):
            setattr(a, name, str(Path(getattr(a, name)).resolve()))
    scope = {"output_root": a.out_dir, "target": a.raw, "program": a.program,
             "binary_id": a.binary_id}
    directory = Path(a.out_dir) / ".supervision"
    path = directory / "state.json"
    try:
        if a.status:
            state = load_state(path, scope)
            # A snapshot cannot establish whether a recorded child is still live.
            print(json.dumps({"snapshot_only": True, "recovery_accepted": False,
                              "state": state}, sort_keys=True))
            return 0
        with owner_lock(directory):
            return supervise(a, scope, path)
    except (SupervisionError, OSError) as exc:
        print(f"[orchestrator] admission refused: {exc}", flush=True)
        return 2


def supervise(a, scope: dict, path: Path) -> int:
    specs = build_specs(a)
    state = load_state(path, scope)
    # Any prior uncertain child may still mutate shared stage inputs/outputs.
    # Refuse the scope rather than inferring death from a PID or a timeout.
    uncertain = [name for name, rec in state["stages"].items() if rec["state"] in RESERVED]
    if uncertain:
        for name in uncertain:
            state["stages"][name]["state"] = "needs_reconciliation"
        save_state(path, state)
        print(json.dumps({"status": "needs_reconciliation", "stages": uncertain}))
        return 3
    revision = provider_revision(Path(__file__).resolve().parent)
    bases = {s["name"]: execution_basis(s["argv"], revision, a.input_basis) for s in specs}
    procs: dict[str, subprocess.Popen] = {}
    log_scope = execution_basis([str(path.parent.parent.resolve())], "log-scope-v1", "")[:16]
    log_dir = Path(a.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"[orchestrator] supervising: {', '.join(s['name'] for s in specs)}", flush=True)
    try:
        while True:
            now = time.time()
            for spec in specs:
                name = spec["name"]
                record = state["stages"].get(name, {})
                child = procs.get(name)
                if child is not None:
                    result = child.poll()
                    if result is None:
                        continue
                    clearance = session_clearance(record.get("process", {}))
                    if clearance != "clear":
                        record.update(state="needs_reconciliation", exit_code=result,
                                      leader_finished_at=now, session_clearance=clearance)
                        save_state(path, state)
                        print(json.dumps({"status": "needs_reconciliation", "stage": name,
                                          "reason": "leader exited but managed session is occupied or unknown"}))
                        return 3
                    record.update(state="pass_done" if result == 0 else "failed_exit",
                                  exit_code=result, finished_at=now,
                                  next_eligible_at=now + (a.success_backoff if result == 0 else a.backoff))
                    if result != 0:
                        record["failed_exits"] += 1
                    save_state(path, state)
                    del procs[name]
                    # A completed pass is not a claim of recovered image acceptance.
                    print(f"[orchestrator] {name}: {record['state']} rc={result}", flush=True)
                    continue
                decision = decide(record, bases[name], now, a.max_failed_exits)
                if decision != "launch":
                    continue
                if record.get("basis") != bases[name]:
                    history = record.get("history", [])
                    if record:
                        history = history + [{k: v for k, v in record.items() if k != "history"}]
                    record = {"basis": bases[name], "failed_exits": 0, "next_eligible_at": 0,
                              "history": history}
                    state["stages"][name] = record
                record.update(state="launch_intent", attempt_id=uuid.uuid4().hex,
                              intended_at=now, argv=spec["argv"], input_basis=a.input_basis,
                              provider_revision=revision)
                # Persistence failure here prevents Popen. A crash after this write
                # is deliberately ambiguous, even if no child was actually started.
                save_state(path, state)
                try:
                    with (log_dir / f"orch_{log_scope}_{name}.log").open("ab") as logf:
                        child = subprocess.Popen(spec["argv"], stdout=logf, stderr=subprocess.STDOUT,
                                                 close_fds=True, start_new_session=True)
                except OSError as exc:
                    record.update(state="failed_exit", failed_exits=record["failed_exits"] + 1,
                                  next_eligible_at=now + a.backoff, launch_error=str(exc))
                    save_state(path, state)
                    continue
                procs[name] = child
                record.update(state="running", process=process_identity(child.pid))
                save_state(path, state)
                print(f"[orchestrator] started {name} pid {child.pid}", flush=True)
                if not a.once:
                    time.sleep(a.stagger)
            if a.once:
                return 0
            if not procs and all(decide(state["stages"].get(s["name"], {}), bases[s["name"]],
                                        time.time(), a.max_failed_exits) == "budget_exhausted" for s in specs):
                print("[orchestrator] bounded failure budgets exhausted", flush=True)
                return 4
            time.sleep(a.poll)
    except KeyboardInterrupt:
        # Do not confuse supervisor shutdown with child termination. Durable
        # reservations remain; we never kill a process inferred from old metadata.
        print("[orchestrator] stopped; child reservations require reconciliation", flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
