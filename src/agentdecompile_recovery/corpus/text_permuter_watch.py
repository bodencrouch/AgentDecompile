"""Autonomous text-mutation byte-accuracy pass for k1_win_gog_swkotor.exe.

CLI entrypoint for the `text-permuter` corpus subcommand (registered in
`kx_cli.py`), so it is driven the same way every other long-running corpus
action is: through the dashboard's action catalog / Jobs system
(`/dashboard/actions`), not by hand-invoking a script in a terminal.

Wraps `kx.text_permuter` (the mutation search, scored by
`verify_recovered_byteexact.masked_diff_count`) and the fixed
`kx.permuter_harness` (context/build_case) directly from their real,
populated data tree (`biodecompwarehouse/kotorxid`) -- this module does not
go through `agentdecompile_recovery.corpus.permuter_harness`'s
`EXTERNAL_ROOT`/env-var config, which currently has no
`AGENT_DECOMPILE_EXTERNAL_RECOVERY_ROOT` set and resolves to a directory that
does not exist. Rerouting that shared, multi-action config was out of scope
here; this module targets the real, known-good paths directly, the same way
the terminal session that developed and validated this search already did.

Maintains persistent state (`STATE_PATH`) across passes so `--watch` mode
only re-attempts addresses that have not already closed, and does not
reprocess a permanent failure every pass.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

KX_ROOT = "/home/brunner56/biodecompwarehouse/kotorxid"
sys.path.insert(0, KX_ROOT)

REPO_PATH = "/K1/k1_win_gog_swkotor.exe"
CAND_DIR = Path(
    f"{KX_ROOT}/output/binaries/K1__k1_win_gog_swkotor.exe/"
    "historical/ghidra_recovered_candidates/k1_win_gog_swkotor.exe")
DB_PATH = f"{KX_ROOT}/db/kotorxid.sqlite"
QUEUE_DIFFS = Path("/home/brunner56/agentdecompile-nvme/k1gog-queue-diffs.json")
STATE_PATH = Path("/home/brunner56/agentdecompile-nvme/k1gog-text-permuter-state.json")
BYTEEXACT_DIR = Path("/home/brunner56/agentdecompile-nvme/k1gog-text-permuter-byteexact")
STATUS_PATH = Path("/home/brunner56/agentdecompile-nvme/k1gog-text-permuter-status.json")

ADDR_RE = re.compile(r"address:\s*0x([0-9a-fA-F]+)")


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (OSError, ValueError):
            pass
    return {"closed": {}, "unclosed": {}}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=1))


def _write_status(**kv) -> None:
    payload = {"updatedAt": time.time(), **kv}
    STATUS_PATH.write_text(json.dumps(payload, indent=1))


def _addr_to_file(cand_dir: Path) -> dict[int, Path]:
    out = {}
    for f in cand_dir.glob("*.c"):
        txt = f.read_text(errors="replace")[:400]
        m = ADDR_RE.search(txt)
        if m:
            out[int(m.group(1), 16)] = f
    return out


def _queue_rows(min_size):
    diffs = json.loads(QUEUE_DIFFS.read_text())["results"]
    return [r for r in diffs if r.get("reason") == "mismatch" and r.get("diff") is not None
            and r.get("size", 0) >= min_size]


def _no_work_summary(rows, state):
    known_unclosed = sum(r['addr'] in state['unclosed'] for r in rows)
    reason = ('no_eligible_queue' if not rows else
              'known_unclosed_requires_dependency_repair' if known_unclosed else
              'selected_queue_exhausted')
    return {'passPending': 0, 'closedThisPass': 0,
            'closedTotal': len(state['closed']), 'unclosedTotal': len(state['unclosed']),
            'elapsedSeconds': 0, 'reason': reason, 'needsDependencyChange': True,
            'compilerInvocations': 0, 'contextRepairAttempted': False,
            'diagnosticOnly': True, 'goalComplete': False}


def _clean_queue(min_size: int) -> list[dict]:
    """Named mismatches, excluding tiny-thunk masking artifacts and Ghidra
    stub bodies (`ghidra_call()`/jumptable-recovery-failed placeholders) --
    neither is closable by mutation; see kx/text_permuter.py's module
    docstring and this session's diagnosis for why."""
    from kx import permuter_harness as ph
    from kx import text_permuter as tp

    rows = _queue_rows(min_size)
    clean = []
    for r in rows:
        f = CAND_DIR / r["file"]
        if not f.exists():
            continue
        txt = f.read_text(errors="replace")
        fname = ph.defined_name(txt, "")
        span = tp.find_body_span(txt, fname) if fname else None
        body = txt[span[0]:span[1]] if span else txt
        if "ghidra_call(" in body or "WARNING:" in body:
            continue
        clean.append(r)
    clean.sort(key=lambda r: r["diff"])
    return clean


def run_pass(seconds_per_fn: float, min_size: int, limit: int | None) -> dict:
    state = _load_state()
    metadata_rows = _queue_rows(min_size)
    if not any(r['addr'] not in state['closed'] and r['addr'] not in state['unclosed']
               for r in metadata_rows):
        # No donor imports, source parsing or compiler context for exhausted state.
        return {**_no_work_summary(metadata_rows, state), 'eligibilityScope': 'queue-metadata'}
    rows = _clean_queue(min_size)
    pending = [r for r in rows if r["addr"] not in state["closed"] and r["addr"] not in state["unclosed"]]
    if limit:
        pending = pending[:limit]
    print(f"queue: {len(rows)} clean, {len(pending)} pending this pass "
          f"({len(state['closed'])} already closed, {len(state['unclosed'])} already known-unclosed)",
          flush=True)
    if not pending:
        sources = [str(CAND_DIR / row['file']) for row in metadata_rows
                   if row['addr'] not in state['closed'] and row['addr'] not in state['unclosed']]
        return {**_no_work_summary(rows, state), 'eligibilityScope': 'clean-source-queue',
                'idleSourceDependencies': sources[:4096],
                'idleDependencyCoverageComplete': len(sources) <= 4096}

    from kx import permuter_harness as ph
    from kx import text_permuter as tp
    # Compiler-backed context repair is justified only by an eligible pass.
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    size_map = {int(a): int(s or 0) for a, s in con.execute(
        "SELECT addr, size FROM func WHERE binary_id=8")}
    con.close()
    print("repairing context (compile-and-drop)...", flush=True)
    ph.CONTEXT_CACHE[REPO_PATH] = ph.repair_context(ph.context_for(REPO_PATH), "vc71")
    print(f"context ready: {len(ph.CONTEXT_CACHE[REPO_PATH].splitlines())} lines", flush=True)

    addr_to_file = _addr_to_file(CAND_DIR)
    work = Path("/home/brunner56/agentdecompile-nvme/text-permuter-work")
    work.mkdir(exist_ok=True)
    BYTEEXACT_DIR.mkdir(exist_ok=True)

    closed_this_pass = 0
    skipped = {}; attempted = 0; idle_sources = []
    t0 = time.time()
    for i, row in enumerate(pending, 1):
        addr = int(row["addr"], 16)
        f = addr_to_file.get(addr)
        if f is None:
            skipped['candidate_file_missing'] = skipped.get('candidate_file_missing', 0) + 1
            idle_sources.append(str(CAND_DIR / row['file']))
            continue
        src = f.read_text(errors="replace")
        size = size_map.get(addr, row.get("size", 0))
        fname = ph.defined_name(src, "")
        if not fname:
            skipped['defined_function_missing'] = skipped.get('defined_function_missing', 0) + 1
            idle_sources.append(str(f))
            continue
        d = ph.build_case(REPO_PATH, addr, size, fname, src, "vc71", work)
        if d is None:
            skipped['target_case_unavailable'] = skipped.get('target_case_unavailable', 0) + 1
            idle_sources.append(str(f))
            continue
        attempted += 1
        base_c = (d / "base.c").read_text()
        target = (d / "target_bytes.bin").read_bytes()
        ft = (d / "function.txt").read_text().strip()
        sym = ft if ft.startswith("_") else f"_{ft}"

        base_diff, _ = tp.compile_and_score(base_c, target, sym)
        if base_diff is None:
            state["unclosed"][row["addr"]] = {"reason": "base_c_does_not_compile"}
            continue
        if base_diff == 0:
            state["closed"][row["addr"]] = {"func": fname, "reason": "already_byte_exact"}
            closed_this_pass += 1
            continue

        r = tp.search(base_c, target, fname, base_diff, seconds_per_fn, sym)
        if r["byte_exact"] and r["source"]:
            (BYTEEXACT_DIR / f.name).write_text(r["source"])
            state["closed"][row["addr"]] = {"func": fname, "base_diff": base_diff}
            closed_this_pass += 1
        else:
            state["unclosed"][row["addr"]] = {"func": fname, "final_diff": r["diff"]}

        if i % 10 == 0:
            _save_state(state)
            _write_status(running=True, pass_progress=i, pass_total=len(pending),
                          closedTotal=len(state["closed"]), closedThisPass=closed_this_pass,
                          elapsedSeconds=round(time.time() - t0, 1))
            print(f"  {i}/{len(pending)}  closed this pass: {closed_this_pass}  "
                  f"(total closed: {len(state['closed'])})", flush=True)

    _save_state(state)
    elapsed = round(time.time() - t0, 1)
    summary = {"passPending": len(pending), "closedThisPass": closed_this_pass,
               "closedTotal": len(state["closed"]), "unclosedTotal": len(state["unclosed"]),
               "elapsedSeconds": elapsed, 'attemptedFunctions': attempted,
               'skippedCounts': skipped, 'contextRepairAttempted': True,
               'reason': 'pass_processed' if attempted else 'eligible_queue_blocked',
               'needsDependencyChange': attempted == 0,
               'idleSourceDependencies': idle_sources[:4096],
               'idleDependencyCoverageComplete': len(idle_sources) <= 4096,
               'diagnosticOnly': True, 'goalComplete': False}
    print(f"\nPASS DONE: {closed_this_pass}/{len(pending)} closed this pass "
          f"({len(state['closed'])} closed total, {elapsed}s)", flush=True)
    return summary


def _queue_revision(source_dependencies=()):
    """Cheap idle trigger only, never source/toolchain equivalence proof.

    Existing failed entries are not cleared when a file changes. An operator
    must repair their dependencies/selection; this snapshot only avoids
    repeatedly invoking the compiler on an unchanged, nonactionable queue.
    """
    revision = []
    from itertools import islice

    sources = tuple(islice(iter(source_dependencies), 4097))
    if len(sources) > 4096:
        raise ValueError('idle_source_dependency_capacity')
    for path in (QUEUE_DIFFS, STATE_PATH, CAND_DIR, *(Path(p) for p in sources)):
        try:
            st = path.stat()
            revision.append((st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
        except OSError:
            revision.append(None)
    return tuple(revision)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds-per-fn", type=float, default=15.0)
    ap.add_argument("--min-size", type=int, default=16,
                     help="exclude functions smaller than this (tiny-thunk reloc-mask artifact)")
    ap.add_argument("--limit", type=int, default=None, help="cap functions processed in one pass")
    ap.add_argument("--watch", action="store_true", help="loop passes forever")
    ap.add_argument("--interval", type=float, default=30.0, help="seconds between passes in --watch")
    args = ap.parse_args(argv)

    _write_status(running=True, mode="watch" if args.watch else "single-pass")
    try:
        if not args.watch:
            summary = run_pass(args.seconds_per_fn, args.min_size, args.limit)
            _write_status(running=False, mode="single-pass", finishedAt=time.time(), lastPass=summary)
            return 0
        while True:
            before = _queue_revision()
            summary = run_pass(args.seconds_per_fn, args.min_size, args.limit)
            if summary.get('needsDependencyChange'):
                if summary.get('idleDependencyCoverageComplete') is False:
                    _write_status(running=False, mode='watch', lastPass=summary,
                                  reason='idle_source_dependency_capacity', goalComplete=False)
                    return 1
                # The pass may write its state; don't mistake our own write for
                # new work. Changes that occurred during the pass get one cheap
                # eligibility recheck before entering the idle wait.
                source_dependencies = summary.get('idleSourceDependencies', ())
                revision = _queue_revision(source_dependencies)
                after = _queue_revision()
                external_changed = after[0] != before[0] or after[2] != before[2]
                state_changed_without_write = (summary.get('contextRepairAttempted') is False
                                               and after[1] != before[1])
                if external_changed or state_changed_without_write:
                    continue
                _write_status(running=True, mode='watch-idle', lastPass=summary,
                              waitingFor='queue_or_state_revision', goalComplete=False)
                print('No actionable pass; waiting for queue/state changes without context compilation.', flush=True)
                while _queue_revision(source_dependencies) == revision:
                    time.sleep(max(1.0, args.interval))
                continue
            _write_status(running=True, mode="watch", lastPass=summary)
            print(f"sleeping {args.interval}s before next pass...", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        _write_status(running=False, mode="watch", stoppedAt=time.time())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
