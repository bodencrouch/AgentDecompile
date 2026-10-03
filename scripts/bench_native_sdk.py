#!/usr/bin/env python3
"""Collect and report native SDK benchmark lanes over one exported snapshot.

The harness has two jobs:

1. measure native replay lanes (`native-console`, `native-batch`) in fresh
   subprocesses while sampling their process trees; and
2. merge externally observed Java/export lanes from JSONL files.

Java lanes are intentionally loaded from files instead of run in this process:
JPype cannot safely stop and restart a Ghidra JVM, while the RFC requires one
fresh JVM per lane (`serial`, `parallel-4`, `parallel-8`, `parallel-11`,
`export`, and optional `ghidrecomp`).  The companion lane shape is deliberately
small and stable so a lane runner can be a shell script, CI step, or a later
Python subprocess wrapper without changing the report gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass

from agentdecompile_recovery.native_snapshot.bench import (
    CompletionIdentityError,
    CompletionMismatch,
    Lane,
    normalize_lanes,
    report,
    write_report,
)
from agentdecompile_recovery.native_snapshot.manifest import Manifest, load_manifest
from agentdecompile_recovery.native_snapshot.procstat import TreeSampler
from agentdecompile_recovery.native_snapshot.replay import ConsoleReplayer


@dataclass(slots=True)
class ProcessResult:
    returncode: int
    wall_s: float
    cpu_s: float | None
    rss_hwm_mb: float | None
    child_hwm: int | None
    named_child_hwm: int | None
    stdout: str
    stderr: str


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--corpus", help="Report corpus name (default: snapshot directory name)")
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--console", type=Path, help="decomp_console path; enables native-console unless --no-native-console")
    p.add_argument("--batch", type=Path, help="gnsdk-batch path; enables native-batch unless --no-native-batch")
    p.add_argument("--sleigh-home", type=Path, help="native sleigh-home path")
    p.add_argument("--tmpdir", type=Path, help="temporary directory passed through to native batch")
    p.add_argument("--workers", type=int, default=1, help="native-batch workers")
    p.add_argument("--per-process", type=int, default=200, help="native-console functions per decomp_console process")
    p.add_argument("--no-native-console", action="store_true")
    p.add_argument("--no-native-batch", action="store_true")
    p.add_argument("--lane-jsonl", action="append", type=Path, default=[], help="Additional pre-collected lane JSONL; one object per lane")
    p.add_argument("--max-completion-drift", type=int, default=0, help="Allowed symmetric-difference size between lane completions; default refuses any drift")
    return p


def _completed_entries(snapshot: Path) -> tuple[Manifest, tuple[str, ...]]:
    manifest = load_manifest(snapshot)
    return manifest, tuple(entry.stable_id for entry in manifest.ok_entries())


def _run_sampled(command: list[str], *, timeout_s: float, cwd: Path | None = None) -> ProcessResult:
    started = time.perf_counter()
    proc = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sampler = TreeSampler(proc.pid, interval_s=0.1).start()
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        stats = sampler.stop()
        return ProcessResult(124, time.perf_counter() - started, stats.cpu_s_last_seen, stats.pss_hwm_mb, stats.child_hwm, stats.named_child_hwm, stdout, stderr)
    stats = sampler.stop()
    return ProcessResult(proc.returncode, time.perf_counter() - started, stats.cpu_s_last_seen, stats.pss_hwm_mb, stats.child_hwm, stats.named_child_hwm, stdout, stderr)


def _parse_batch_jsonl(path: Path) -> tuple[tuple[str, ...], tuple[float, ...]]:
    completed: list[str] = []
    elapsed: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("status") == "ok":
            completed.append(str(record["id"]))
            elapsed.append(float(record.get("elapsed_ms", 0.0)))
    return tuple(completed), tuple(elapsed)


def _native_batch_lane(args: argparse.Namespace) -> Lane:
    if args.batch is None or args.sleigh_home is None:
        raise SystemExit("--batch and --sleigh-home are required for native-batch")
    result_file = args.output / "native-batch.jsonl"
    cmd = [
        str(args.batch),
        "--sleigh-home",
        str(args.sleigh_home),
        "--snapshot",
        str(args.snapshot),
        "--output",
        str(result_file),
        "--timeout",
        str(max(1, int(args.timeout))),
        "--workers",
        str(max(1, int(args.workers))),
    ]
    if args.tmpdir is not None:
        cmd.extend(["--tmpdir", str(args.tmpdir)])
    run = _run_sampled(cmd, timeout_s=args.timeout * max(1, len(load_manifest(args.snapshot).ok_entries())) + 30)
    (args.output / "native-batch.stdout").write_text(run.stdout, encoding="utf-8")
    (args.output / "native-batch.stderr").write_text(run.stderr, encoding="utf-8")
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"native-batch exited {run.returncode}")
    completed, elapsed = _parse_batch_jsonl(result_file)
    return Lane("native-batch", completed, run.wall_s, elapsed, cpu_s=run.cpu_s, rss_hwm_mb=run.rss_hwm_mb, child_hwm=run.child_hwm, named_child_hwm=run.named_child_hwm)


def _native_console_lane(args: argparse.Namespace) -> Lane:
    if args.console is None or args.sleigh_home is None:
        raise SystemExit("--console and --sleigh-home are required for native-console")
    replayer = ConsoleReplayer(args.console, sleigh_home=args.sleigh_home, timeout_s=args.timeout, per_process=max(1, int(args.per_process)))
    manifest = load_manifest(args.snapshot)
    started = time.perf_counter()
    results = replayer.replay_manifest(args.snapshot, manifest)
    wall = time.perf_counter() - started
    completed = [addr for addr, result in results.items() if result.returncode == 0 and result.c_text is not None]
    per_function_ms = (wall * 1000.0) / max(1, len(results))
    elapsed = [per_function_ms for _addr in completed]
    # ConsoleReplayer owns the subprocess internally, so the sampled metrics
    # are unavailable in this collection mode.  Wall and per-function timings
    # are still real observations and the report marks resource fields as n/a.
    return Lane("native-console", tuple(completed), wall, tuple(elapsed))


def _load_lane_jsonl(paths: Iterable[Path]) -> list[Lane]:
    lanes: list[Lane] = []
    for path in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            try:
                lanes.append(
                    Lane(
                        str(record["name"]),
                        tuple(str(a) for a in record["completed"]),
                        float(record["wall_s"]),
                        tuple(float(v) for v in record["elapsed_ms"]),
                        cpu_s=record.get("cpu_s"),
                        rss_hwm_mb=record.get("rss_hwm_mb"),
                        jvm_heap_max_mb=record.get("jvm_heap_max_mb"),
                        child_hwm=record.get("child_hwm"),
                        named_child_hwm=record.get("named_child_hwm"),
                        includes_analysis=bool(record.get("includes_analysis", False)),
                    )
                )
            except KeyError as exc:
                raise ValueError(f"{path}:{line_no}: missing required lane field {exc.args[0]!r}") from exc
    return lanes


def _completion_drift(lanes: list[Lane]) -> int:
    if not lanes:
        return 0
    expected = set(lanes[0].completed)
    return max(len(set(lane.completed) ^ expected) for lane in lanes)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest, _addresses = _completed_entries(args.snapshot)
    lanes = _load_lane_jsonl(args.lane_jsonl)
    if not args.no_native_console and args.console is not None:
        lanes.append(_native_console_lane(args))
    if not args.no_native_batch and args.batch is not None:
        lanes.append(_native_batch_lane(args))
    if not lanes:
        print("error: no lanes selected", file=sys.stderr)
        return 2
    try:
        lanes = normalize_lanes(lanes, manifest)
    except CompletionIdentityError as exc:
        print(f"REFUSED (completion identity): {exc}", file=sys.stderr)
        return 3
    drift = _completion_drift(lanes)
    if drift > int(args.max_completion_drift):
        print(f"REFUSED (completion mismatch): drift={drift} max={args.max_completion_drift}", file=sys.stderr)
        return 3
    try:
        payload = report(args.corpus or args.snapshot.name, lanes, options_sha256=manifest.options.sha256, timeout_s=args.timeout)
    except CompletionMismatch as exc:
        print(str(exc), file=sys.stderr)
        return 3
    json_path, md_path = write_report(args.output, payload)
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
