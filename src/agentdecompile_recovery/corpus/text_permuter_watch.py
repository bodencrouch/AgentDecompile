"""Autonomous text-mutation byte-accuracy pass for one configured program.

CLI entrypoint for the `text-permuter` corpus subcommand (registered in
`kx_cli.py`), so it is driven the same way every other long-running corpus
action is: through the dashboard's action catalog / Jobs system
(`/dashboard/actions`), not by hand-invoking a script in a terminal.

Wraps `kx.text_permuter` (the mutation search, scored by
`verify_recovered_byteexact.masked_diff_count`) and `kx.permuter_harness`
(context/build_case) from an external toolkit checkout. The target program and
every path come from the program's config file
(``<AGENT_DECOMPILE_CORPUS_CONFIG_DIR>/programs/<program>.json``), under a
``permuter`` section::

    "permuter": {
      "toolkit_root": "...",   # directory holding the `kx` package
      "database": "...",       # corpus sqlite with the `binary`/`func` tables
      "candidate_dir": "...",  # Ghidra-recovered *.c candidates
      "queue_diffs": "...",    # mismatch queue (results[] with addr/file/diff)
      "compiler": "...",       # harness compiler id
      "state": "...", "status": "...", "byteexact_dir": "...", "work_dir": "..."
    }

With no ``--program`` and no ``CORPUS_PROGRAM``, the single program config that
has a ``permuter`` section is used.

Maintains persistent state across passes so `--watch` mode only re-attempts
addresses that have not already closed, and does not reprocess a permanent
failure every pass.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import corpus_config

ADDR_RE = re.compile(r"address:\s*0x([0-9a-fA-F]+)")

_REQUIRED = ("toolkit_root", "database", "candidate_dir", "queue_diffs", "compiler",
             "state", "status", "byteexact_dir", "work_dir")


@dataclass(frozen=True)
class Target:
    program: str
    repo_path: str
    toolkit_root: Path
    database: Path
    candidate_dir: Path
    queue_diffs: Path
    compiler: str
    state: Path
    status: Path
    byteexact_dir: Path
    work_dir: Path


def load_target(program: str | None = None) -> Target:
    name, raw = corpus_config.program_section("permuter", program)
    cfg = raw["permuter"]
    missing = [k for k in _REQUIRED if not str(cfg.get(k) or "").strip()]
    repo_path = str(raw.get("repo_path") or "").strip()
    if not repo_path:
        missing.append("repo_path")
    if missing:
        raise LookupError(f"program config {name!r} is missing: {', '.join(missing)}")
    return Target(
        program=name,
        repo_path=repo_path,
        toolkit_root=Path(cfg["toolkit_root"]),
        database=Path(cfg["database"]),
        candidate_dir=Path(cfg["candidate_dir"]),
        queue_diffs=Path(cfg["queue_diffs"]),
        compiler=str(cfg["compiler"]),
        state=Path(cfg["state"]),
        status=Path(cfg["status"]),
        byteexact_dir=Path(cfg["byteexact_dir"]),
        work_dir=Path(cfg["work_dir"]),
    )


def _use_toolkit(t: Target) -> None:
    root = str(t.toolkit_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def _load_state(t: Target) -> dict:
    if t.state.exists():
        try:
            return json.loads(t.state.read_text())
        except (OSError, ValueError):
            pass
    return {"closed": {}, "unclosed": {}}


def _save_state(t: Target, state: dict) -> None:
    t.state.write_text(json.dumps(state, indent=1))


def _write_status(t: Target, **kv) -> None:
    payload = {"updatedAt": time.time(), "program": t.program, **kv}
    t.status.write_text(json.dumps(payload, indent=1))


def _addr_to_file(cand_dir: Path) -> dict[int, Path]:
    out = {}
    for f in cand_dir.glob("*.c"):
        txt = f.read_text(errors="replace")[:400]
        m = ADDR_RE.search(txt)
        if m:
            out[int(m.group(1), 16)] = f
    return out


def _clean_queue(t: Target, min_size: int) -> list[dict]:
    """Named mismatches, excluding tiny-thunk masking artifacts and Ghidra
    stub bodies (`ghidra_call()`/jumptable-recovery-failed placeholders) --
    neither is closable by mutation; see kx/text_permuter.py's module
    docstring for why."""
    from kx import permuter_harness as ph
    from kx import text_permuter as tp

    diffs = json.loads(t.queue_diffs.read_text())["results"]
    rows = [r for r in diffs if r.get("reason") == "mismatch" and r.get("diff") is not None
            and r.get("size", 0) >= min_size]
    clean = []
    for r in rows:
        f = t.candidate_dir / r["file"]
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


def _binary_id(con: sqlite3.Connection, repo_path: str) -> int:
    row = con.execute("SELECT id FROM binary WHERE repo_path=?", (repo_path,)).fetchone()
    if row is None:
        raise LookupError(f"{repo_path} is not in the corpus database")
    return int(row[0])


def run_pass(t: Target, seconds_per_fn: float, min_size: int, limit: int | None) -> dict:
    _use_toolkit(t)
    from kx import permuter_harness as ph
    from kx import text_permuter as tp

    con = sqlite3.connect(f"file:{t.database}?mode=ro", uri=True)
    try:
        binary_id = _binary_id(con, t.repo_path)
        size_map = {int(a): int(s or 0) for a, s in con.execute(
            "SELECT addr, size FROM func WHERE binary_id=?", (binary_id,))}
    finally:
        con.close()

    print("repairing context (compile-and-drop)...", flush=True)
    ph.CONTEXT_CACHE[t.repo_path] = ph.repair_context(ph.context_for(t.repo_path), t.compiler)
    print(f"context ready: {len(ph.CONTEXT_CACHE[t.repo_path].splitlines())} lines", flush=True)

    rows = _clean_queue(t, min_size)
    state = _load_state(t)
    pending = [r for r in rows if r["addr"] not in state["closed"] and r["addr"] not in state["unclosed"]]
    if limit:
        pending = pending[:limit]
    print(f"queue: {len(rows)} clean, {len(pending)} pending this pass "
          f"({len(state['closed'])} already closed, {len(state['unclosed'])} already known-unclosed)",
          flush=True)

    addr_to_file = _addr_to_file(t.candidate_dir)
    t.work_dir.mkdir(exist_ok=True)
    t.byteexact_dir.mkdir(exist_ok=True)

    closed_this_pass = 0
    t0 = time.time()
    for i, row in enumerate(pending, 1):
        addr = int(row["addr"], 16)
        f = addr_to_file.get(addr)
        if f is None:
            continue
        src = f.read_text(errors="replace")
        size = size_map.get(addr, row.get("size", 0))
        fname = ph.defined_name(src, "")
        if not fname:
            continue
        d = ph.build_case(t.repo_path, addr, size, fname, src, t.compiler, t.work_dir)
        if d is None:
            continue
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
            (t.byteexact_dir / f.name).write_text(r["source"])
            state["closed"][row["addr"]] = {"func": fname, "base_diff": base_diff}
            closed_this_pass += 1
        else:
            state["unclosed"][row["addr"]] = {"func": fname, "final_diff": r["diff"]}

        if i % 10 == 0:
            _save_state(t, state)
            _write_status(t, running=True, pass_progress=i, pass_total=len(pending),
                          closedTotal=len(state["closed"]), closedThisPass=closed_this_pass,
                          elapsedSeconds=round(time.time() - t0, 1))
            print(f"  {i}/{len(pending)}  closed this pass: {closed_this_pass}  "
                  f"(total closed: {len(state['closed'])})", flush=True)

    _save_state(t, state)
    elapsed = round(time.time() - t0, 1)
    summary = {"passPending": len(pending), "closedThisPass": closed_this_pass,
               "closedTotal": len(state["closed"]), "unclosedTotal": len(state["unclosed"]),
               "elapsedSeconds": elapsed}
    print(f"\nPASS DONE: {closed_this_pass}/{len(pending)} closed this pass "
          f"({len(state['closed'])} closed total, {elapsed}s)", flush=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--program", default=None,
                    help="program config name (default: CORPUS_PROGRAM, else the one config with a permuter section)")
    ap.add_argument("--seconds-per-fn", type=float, default=15.0)
    ap.add_argument("--min-size", type=int, default=16,
                     help="exclude functions smaller than this (tiny-thunk reloc-mask artifact)")
    ap.add_argument("--limit", type=int, default=None, help="cap functions processed in one pass")
    ap.add_argument("--watch", action="store_true", help="loop passes forever")
    ap.add_argument("--interval", type=float, default=30.0, help="seconds between passes in --watch")
    args = ap.parse_args(argv)

    try:
        t = load_target(args.program)
    except LookupError as exc:
        print(f"text-permuter: {exc}", file=sys.stderr, flush=True)
        return 2

    _write_status(t, running=True, mode="watch" if args.watch else "single-pass")
    try:
        if not args.watch:
            run_pass(t, args.seconds_per_fn, args.min_size, args.limit)
            _write_status(t, running=False, mode="single-pass", finishedAt=time.time())
            return 0
        while True:
            summary = run_pass(t, args.seconds_per_fn, args.min_size, args.limit)
            _write_status(t, running=True, mode="watch", lastPass=summary)
            print(f"sleeping {args.interval}s before next pass...", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        _write_status(t, running=False, mode="watch", stoppedAt=time.time())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
