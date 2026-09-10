#!/usr/bin/env python3
"""Measure JVM-free native replay lanes over one exported snapshot.

This intentionally measures only the supplied native lanes.  Java export and
parallel lanes must be added as separately observed lanes before ``k_star``
has any meaning; the report therefore records ``never`` for this invocation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time

from agentdecompile_recovery.native_snapshot.bench import Lane, report, write_report
from agentdecompile_recovery.native_snapshot.manifest import load_manifest
from agentdecompile_recovery.native_snapshot.replay import ConsoleReplayer


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--console", type=Path, required=True)
    p.add_argument("--batch", type=Path, required=True)
    p.add_argument("--sleigh-home", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=60)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = load_manifest(args.snapshot)
    entries = manifest.ok_entries()
    addresses = tuple(entry.addr for entry in entries)
    replayer = ConsoleReplayer(args.console, sleigh_home=args.sleigh_home, timeout_s=args.timeout)
    console_ms: list[float] = []
    console_completed: list[str] = []
    started = time.perf_counter()
    for entry in entries:
        at = time.perf_counter()
        result = replayer.replay(args.snapshot, entry)
        if result.returncode == 0 and result.c_text is not None:
            console_completed.append(entry.addr)
            console_ms.append((time.perf_counter() - at) * 1000)
    console_wall = time.perf_counter() - started
    result_file = args.output / "native-batch.jsonl"
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    completed = subprocess.run([str(args.batch), "--sleigh-home", str(args.sleigh_home), "--snapshot", str(args.snapshot), "--output", str(result_file), "--timeout", str(max(1, int(args.timeout)))], text=True, capture_output=True, timeout=args.timeout * max(1, len(entries)) + 10, check=False)
    batch_wall = time.perf_counter() - started
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"gnsdk-batch exited {completed.returncode}")
    records = [json.loads(line) for line in result_file.read_text(encoding="utf-8").splitlines() if line]
    batch_completed = tuple(str(record["id"]) for record in records if record.get("status") == "ok")
    batch_ms = tuple(float(record["elapsed_ms"]) for record in records if record.get("status") == "ok")
    payload = report(args.snapshot.name, [Lane("native-console", tuple(console_completed), console_wall, tuple(console_ms)), Lane("native-batch", batch_completed, batch_wall, batch_ms)], options_sha256=manifest.options.sha256, timeout_s=args.timeout)
    json_path, md_path = write_report(args.output, payload)
    print(json_path)
    print(md_path)
    return 0 if tuple(console_completed) == addresses == batch_completed else 3


if __name__ == "__main__":
    raise SystemExit(main())
