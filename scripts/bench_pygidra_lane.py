#!/usr/bin/env python3
"""Emit one fresh-JVM benchmark lane as JSONL for ``bench_native_sdk.py``.

Run this script once per Java-backed lane.  Each invocation starts at most one
Ghidra JVM, measures exactly one lane, prints a single JSON object to stdout,
and exits.  That keeps the "fresh JVM per lane" benchmark rule enforceable by
the shell/CI orchestration that calls it.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import warnings

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
if sys.path and Path(sys.path[0]).resolve() == _SCRIPT_DIR:
    sys.path.pop(0)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agentdecompile_recovery.native_snapshot.manifest import load_manifest
from agentdecompile_recovery.native_snapshot.procstat import TreeSampler


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--lane", required=True, choices=("serial", "parallel-4", "parallel-8", "parallel-11", "export", "ghidrecomp"))
    p.add_argument("--snapshot", type=Path, required=True, help="Snapshot whose manifest supplies function addresses and constant options hash")
    p.add_argument("--binary", type=Path, help="Binary to open; default is manifest program.executable_path")
    p.add_argument("--project-location", type=Path, required=True, help="Project directory outside .claude paths")
    p.add_argument("--project-name", default=None)
    p.add_argument("--timeout-s", type=int, default=60)
    p.add_argument("--heap", default="2g")
    p.add_argument("--java-user-home", type=Path, help="Pass -Duser.home here so Ghidra caches avoid a full /home")
    p.add_argument("--tmpdir", type=Path, help="Set TMPDIR/JAVA_IO_TMPDIR and pass -Djava.io.tmpdir here")
    p.add_argument("--export-out", type=Path, help="Required for --lane export")
    p.add_argument("--ghidra-install-dir", default=None)
    p.add_argument("--limit", type=int, help="Limit addresses from the snapshot manifest")
    return p


def _configure_process_environment(args: argparse.Namespace) -> None:
    if args.tmpdir is not None:
        args.tmpdir.mkdir(parents=True, exist_ok=True)
        os.environ["TMPDIR"] = str(args.tmpdir)
        os.environ["JAVA_IO_TMPDIR"] = str(args.tmpdir)
    if args.java_user_home is not None:
        args.java_user_home.mkdir(parents=True, exist_ok=True)


def _start_jvm(heap: str, install_dir: str | None, *, java_user_home: Path | None = None, tmpdir: Path | None = None) -> None:
    import jpype
    from pyghidra.launcher import HeadlessPyGhidraLauncher

    if install_dir:
        os.environ["GHIDRA_INSTALL_DIR"] = install_dir
    if jpype.isJVMStarted():
        return
    launcher = HeadlessPyGhidraLauncher(verbose=False, install_dir=Path(install_dir) if install_dir else None)
    vmargs = [f"-Xmx{heap}"]
    if java_user_home is not None:
        vmargs.append(f"-Duser.home={java_user_home}")
    if tmpdir is not None:
        vmargs.append(f"-Djava.io.tmpdir={tmpdir}")
    launcher.add_vmargs(*vmargs)
    launcher.start()


def _runtime_heap_mb() -> float | None:
    try:
        from java.lang import Runtime  # pyright: ignore[reportMissingImports]

        return float(Runtime.getRuntime().maxMemory()) / (1024 * 1024)
    except Exception:
        return None


def _lane_threads(name: str) -> int:
    if name == "serial":
        return 1
    if name.startswith("parallel-"):
        return int(name.rsplit("-", 1)[1])
    return 1


def _addresses(snapshot: Path, limit: int | None) -> tuple[str, ...]:
    entries = load_manifest(snapshot).ok_entries()
    if limit is not None:
        entries = entries[: max(0, int(limit))]
    return tuple(entry.addr for entry in entries)


def _java_decompile_lane(args: argparse.Namespace, binary: Path) -> dict[str, object]:
    import pyghidra

    from agentdecompile_cli.mcp_utils.parallel_decompile import batch_candidates, decompile_functions_iter, function_addr, serial_decompile_one

    wanted = _addresses(args.snapshot, args.limit)
    wanted_offsets = {int(addr, 16) for addr in wanted}
    started = time.perf_counter()
    sampler = TreeSampler(os.getpid(), interval_s=0.1).start()
    elapsed: list[float] = []
    completed: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        context = pyghidra.open_program(
            str(binary),
            project_location=str(args.project_location),
            project_name=args.project_name or f"bench-{args.lane}-{binary.name}",
            analyze=True,
        )
    with context as flat:
        program = flat.getCurrentProgram()
        functions = batch_candidates(program, addrs=wanted_offsets)
        by_addr = {function_addr(fn): fn for fn in functions}
        ordered = [by_addr[int(addr, 16)] for addr in wanted if int(addr, 16) in by_addr]
        if args.lane == "serial":
            for fn in ordered:
                at = time.perf_counter()
                result = serial_decompile_one(program, fn, timeout_s=args.timeout_s)
                if result.status == "ok":
                    completed.append(f"{result.addr:016x}")
                    elapsed.append((time.perf_counter() - at) * 1000.0)
        else:
            gen = decompile_functions_iter(program, ordered, threads=_lane_threads(args.lane), timeout_s=args.timeout_s)
            try:
                while True:
                    try:
                        result = next(gen)
                    except StopIteration:
                        break
                    if result.status == "ok":
                        completed.append(f"{result.addr:016x}")
                        elapsed.append(result.elapsed_ms)
            finally:
                gen.close()
    stats = sampler.stop()
    return {
        "name": args.lane,
        "completed": completed,
        "wall_s": time.perf_counter() - started,
        "elapsed_ms": elapsed,
        "cpu_s": stats.cpu_s_last_seen,
        "rss_hwm_mb": stats.pss_hwm_mb,
        "jvm_heap_max_mb": _runtime_heap_mb(),
        "child_hwm": stats.child_hwm,
        "named_child_hwm": stats.named_child_hwm,
        "includes_analysis": False,
    }


def _export_lane(args: argparse.Namespace, binary: Path) -> dict[str, object]:
    if args.export_out is None:
        raise SystemExit("--export-out is required for --lane export")
    started = time.perf_counter()
    cmd = [
        sys.executable,
        "-m",
        "agentdecompile_recovery.native_snapshot",
        "export",
        str(binary),
        "--out",
        str(args.export_out),
        "--project-location",
        str(args.project_location),
        "--project-name",
        args.project_name or f"bench-export-{binary.name}",
        "--timeout-s",
        str(args.timeout_s),
        "--heap",
        args.heap,
        "--quiet",
    ]
    if args.ghidra_install_dir:
        cmd.extend(["--ghidra-install-dir", args.ghidra_install_dir])
    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])
    env = os.environ.copy()
    java_tool_options: list[str] = []
    if args.tmpdir is not None:
        env["TMPDIR"] = str(args.tmpdir)
        env["JAVA_IO_TMPDIR"] = str(args.tmpdir)
        java_tool_options.append(f"-Djava.io.tmpdir={args.tmpdir}")
    if args.java_user_home is not None:
        java_tool_options.append(f"-Duser.home={args.java_user_home}")
    if java_tool_options:
        env["JAVA_TOOL_OPTIONS"] = " ".join(java_tool_options + ([env["JAVA_TOOL_OPTIONS"]] if env.get("JAVA_TOOL_OPTIONS") else []))
    proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    sampler = TreeSampler(proc.pid, interval_s=0.1).start()
    stdout, stderr = proc.communicate()
    stats = sampler.stop()
    (args.export_out / "lane-export.stdout").write_text(stdout, encoding="utf-8")
    (args.export_out / "lane-export.stderr").write_text(stderr, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(stderr.strip() or f"export lane exited {proc.returncode}")
    manifest = load_manifest(args.export_out)
    completed = tuple(entry.addr for entry in manifest.ok_entries())
    elapsed = tuple(float(entry.decompile_ms or 0.0) for entry in manifest.ok_entries())
    return {
        "name": "export",
        "completed": completed,
        "wall_s": time.perf_counter() - started,
        "elapsed_ms": elapsed,
        "cpu_s": stats.cpu_s_last_seen,
        "rss_hwm_mb": stats.pss_hwm_mb,
        "jvm_heap_max_mb": None,
        "child_hwm": stats.child_hwm,
        "named_child_hwm": stats.named_child_hwm,
        "includes_analysis": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    _configure_process_environment(args)
    manifest = load_manifest(args.snapshot)
    binary = args.binary or Path(manifest.program.executable_path)
    if not binary.is_file():
        print(f"error: binary not found: {binary}", file=sys.stderr)
        return 2
    args.project_location.mkdir(parents=True, exist_ok=True)
    try:
        if args.lane == "export":
            record = _export_lane(args, binary)
        elif args.lane == "ghidrecomp":
            print("error: ghidrecomp lane runner is not implemented yet", file=sys.stderr)
            return 2
        else:
            _start_jvm(args.heap, args.ghidra_install_dir, java_user_home=args.java_user_home, tmpdir=args.tmpdir)
            record = _java_decompile_lane(args, binary)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
