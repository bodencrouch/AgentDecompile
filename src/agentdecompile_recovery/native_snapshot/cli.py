"""Command line for the native snapshot exporter.

``python -m agentdecompile_recovery.native_snapshot export <binary> --out DIR [--addr 0x... ...] [--all]
[--timeout-s N] [--project-location DIR] [--project-name NAME] [--allow-stale] [--limit N]``

Exit codes: 0 exported, 1 usage or unexpected failure, 2 stale (program changed during export),
3 precondition (open transaction, unsupported style, Ghidra or pyghidra unavailable).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import warnings

from agentdecompile_recovery.native_snapshot.manifest import MANIFEST_FILENAME, Manifest

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_STALE = 2
EXIT_PRECONDITION = 3

DEFAULT_HEAP = "2g"


def resolve_install_dir(explicit: str | None = None) -> Path | None:
    """``--ghidra-install-dir`` or ``GHIDRA_INSTALL_DIR``; must contain ``Ghidra/application.properties``."""
    raw = (explicit or os.environ.get("GHIDRA_INSTALL_DIR", "")).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not (path / "Ghidra" / "application.properties").is_file():
        return None
    return path


def start_jvm(install_dir: Path, heap: str = DEFAULT_HEAP) -> None:
    """Start one headless PyGhidra JVM with a bounded heap. Idempotent for an already-started JVM."""
    import jpype

    if jpype.isJVMStarted():
        return
    os.environ["GHIDRA_INSTALL_DIR"] = str(install_dir)
    from pyghidra.launcher import HeadlessPyGhidraLauncher

    launcher = HeadlessPyGhidraLauncher(verbose=False, install_dir=install_dir)
    launcher.add_vmargs(f"-Xmx{heap}")
    launcher.start()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m agentdecompile_recovery.native_snapshot", description="Export decompiler savefiles and oracle C for JVM-free replay.")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="Import and analyze a binary, then export a snapshot.")
    export.add_argument("binary", type=Path, help="Path to the binary to import.")
    export.add_argument("--out", type=Path, required=True, help="Snapshot directory to write.")
    export.add_argument("--addr", action="append", default=[], metavar="ADDR", help="Function entry address (hex like 0x401000 or a Ghidra address string). Repeatable.")
    export.add_argument("--all", action="store_true", help="Export every function (the default when no --addr is given).")
    export.add_argument("--timeout-s", type=int, default=60, help="Per-function decompile timeout in seconds (default 60).")
    export.add_argument("--project-location", type=Path, default=None, help="Ghidra project directory (default: <out>/.ghidra_project).")
    export.add_argument("--project-name", default=None, help="Ghidra project name (default: the binary file name).")
    export.add_argument("--allow-stale", action="store_true", help="Keep exporting when the program changes underneath; exit 0 with revision.stale set.")
    export.add_argument("--limit", type=int, default=None, help="Stop after the first N candidate functions in address order.")
    export.add_argument("--ghidra-install-dir", default=None, help="Override GHIDRA_INSTALL_DIR.")
    export.add_argument("--heap", default=DEFAULT_HEAP, help="JVM max heap passed as -Xmx (default 2g).")
    export.add_argument("--no-analyze", action="store_true", help="Skip auto-analysis after import.")
    export.add_argument("--quiet", action="store_true", help="Do not print per-function progress lines to stderr.")
    export.set_defaults(func=run_export)
    replay = sub.add_parser("replay", help="Replay a snapshot and write native replay JSONL.")
    replay.add_argument("snapshot", type=Path, help="Directory containing manifest.json.")
    replay.add_argument("--mode", choices=("console", "batch"), default="console", help="Replay backend (default: console).")
    replay.add_argument("--console", type=Path, default=None, help="Path to native decomp_console for --mode console.")
    replay.add_argument("--batch", type=Path, default=None, help="Path to gnsdk-batch for --mode batch.")
    replay.add_argument("--sleigh-home", type=Path, required=True, help="Compiled Ghidra-root/SLEIGH home.")
    replay.add_argument("--timeout-s", type=int, default=60, help="Per-function/backend timeout in seconds (default 60).")
    replay.add_argument("--workers", type=int, default=1, help="Batch replay worker count (default 1).")
    replay.add_argument("--tmpdir", type=Path, default=None, help="Tmpdir passed to gnsdk-batch in batch mode.")
    replay.add_argument("--output", type=Path, default=None, help="Replay JSONL output (default: <snapshot>/differential/replay.jsonl).")
    replay.set_defaults(func=run_replay)
    diff = sub.add_parser("diff", help="Replay a snapshot and write a strict differential report.")
    diff.add_argument("snapshot", type=Path, help="Directory containing manifest.json.")
    diff.add_argument("--mode", choices=("console", "batch"), default="console", help="Replay backend (default: console).")
    diff.add_argument("--console", type=Path, default=None, help="Path to native decomp_console for --mode console.")
    diff.add_argument("--batch", type=Path, default=None, help="Path to gnsdk-batch for --mode batch.")
    diff.add_argument("--sleigh-home", type=Path, required=True, help="Compiled Ghidra-root/SLEIGH home.")
    diff.add_argument("--timeout-s", type=int, default=60, help="Per-function/backend timeout in seconds (default 60).")
    diff.add_argument("--workers", type=int, default=1, help="Batch replay worker count (default 1).")
    diff.add_argument("--tmpdir", type=Path, default=None, help="Tmpdir passed to gnsdk-batch in batch mode.")
    diff.add_argument("--output", type=Path, default=None, help="Directory for report.json/report.md/diff (default: <snapshot>/differential).")
    diff.set_defaults(func=run_diff)
    return parser


def _fmt_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{count} B"


def summary_markdown(manifest: Manifest, out_dir: Path, wall_s: float) -> str:
    counts = manifest.counts
    decompiled = counts.ok + counts.timed_out + counts.error
    per_fn = manifest.total_bytes / counts.ok if counts.ok else 0
    lines = [
        f"# Snapshot export: {manifest.program.name}",
        "",
        f"- Output: `{out_dir}` (manifest `{out_dir / MANIFEST_FILENAME}`)",
        f"- Language: `{manifest.program.language_id}` / `{manifest.program.compiler_spec_id}` (supported: {str(manifest.capabilities.supported).lower()})",
        f"- Engine: Ghidra {manifest.producer.ghidra_version}, sig {manifest.engine.sig_major}.{manifest.engine.sig_minor}, sla format {manifest.engine.sla_format_version}, respawns {manifest.engine.respawns}",
        f"- Options sha256: `{manifest.options.sha256}` (style `{manifest.options.simplification_style}`)",
        f"- Revision: {manifest.revision.modification_number_before} -> {manifest.revision.modification_number_after} (stale: {str(manifest.revision.stale).lower()})",
        f"- Timeout: {manifest.timeout_s}s per function",
        "",
        "| Status | Count |",
        "|---|---|",
        f"| ok | {counts.ok} |",
        f"| timed_out | {counts.timed_out} |",
        f"| error | {counts.error} |",
        f"| skipped | {counts.skipped} |",
        f"| total | {counts.total} |",
    ]
    if counts.skipped_by_reason:
        lines.append("")
        lines.append("Skipped by reason: " + ", ".join(f"{reason}={n}" for reason, n in sorted(counts.skipped_by_reason.items())))
    lines.extend(
        [
            "",
            f"- Total bytes: {manifest.total_bytes} ({_fmt_bytes(manifest.total_bytes)})",
            f"- Bytes per ok function: {per_fn:.0f} ({_fmt_bytes(int(per_fn))})",
            f"- Decompiles attempted: {decompiled}",
            f"- Export wall time: {manifest.wall_s:.1f}s (decompile loop), {wall_s:.1f}s including JVM start, import and analysis",
        ]
    )
    if counts.ok:
        lines.append(f"- Decompile rate: {counts.ok / manifest.wall_s:.2f} ok functions/s" if manifest.wall_s > 0 else "- Decompile rate: n/a")
    lines.append("")
    return "\n".join(lines)


def _parse_addr(text: str) -> int | str:
    stripped = text.strip()
    try:
        return int(stripped, 0)
    except ValueError:
        return stripped


def run_export(args: argparse.Namespace) -> int:
    from agentdecompile_recovery.native_snapshot.exporter import SnapshotPreconditionError, SnapshotStaleError, export_snapshot, resolve_functions

    binary: Path = args.binary
    if not binary.is_file():
        print(f"error: binary not found: {binary}", file=sys.stderr)
        return EXIT_USAGE
    if args.timeout_s <= 0:
        print("error: --timeout-s must be positive", file=sys.stderr)
        return EXIT_USAGE
    if args.limit is not None and args.limit <= 0:
        print("error: --limit must be positive", file=sys.stderr)
        return EXIT_USAGE
    install_dir = resolve_install_dir(args.ghidra_install_dir)
    if install_dir is None:
        print("error: GHIDRA_INSTALL_DIR is not set to a Ghidra install (expected Ghidra/application.properties)", file=sys.stderr)
        return EXIT_PRECONDITION
    try:
        import pyghidra
    except ImportError:
        print("error: pyghidra is not installed in this environment", file=sys.stderr)
        return EXIT_PRECONDITION

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    project_location: Path = args.project_location or (out_dir / ".ghidra_project")
    project_location.mkdir(parents=True, exist_ok=True)
    project_name = args.project_name or binary.name

    started = time.perf_counter()
    start_jvm(install_dir, args.heap)

    def progress(event) -> None:
        if args.quiet:
            return
        detail = event.skip_reason or event.error or ""
        ms = f" {event.decompile_ms} ms" if event.decompile_ms is not None else ""
        print(f"[{event.index}/{event.total}] {event.addr} {event.name}: {event.status}{ms} {detail}".rstrip(), file=sys.stderr)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        context = pyghidra.open_program(str(binary), project_location=str(project_location), project_name=project_name, analyze=not args.no_analyze)
    exit_code = EXIT_OK
    manifest: Manifest | None = None
    with context as flat_api:
        program = flat_api.getCurrentProgram()
        try:
            selected = resolve_functions(program, [_parse_addr(a) for a in args.addr]) if args.addr else list(program.getFunctionManager().getFunctions(True))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        if args.limit is not None:
            selected = selected[: args.limit]
        try:
            manifest = export_snapshot(program, out_dir, functions=selected, timeout_s=args.timeout_s, on_progress=progress, allow_stale=args.allow_stale)
        except SnapshotStaleError as exc:
            manifest = exc.manifest
            exit_code = EXIT_STALE
            print(f"error: {exc}", file=sys.stderr)
        except SnapshotPreconditionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_PRECONDITION

    wall_s = time.perf_counter() - started
    if manifest is not None:
        print(summary_markdown(manifest, out_dir, wall_s))
        if manifest.revision.stale and exit_code == EXIT_OK:
            print("warning: program changed during export; revision.stale is set (--allow-stale)", file=sys.stderr)
    return exit_code


def _make_replayer(args: argparse.Namespace):
    from agentdecompile_recovery.native_snapshot.replay import BatchReplayer, ConsoleReplayer

    if args.timeout_s <= 0 or args.workers <= 0 or not args.sleigh_home.is_dir():
        return None
    if args.mode == "console":
        if args.console is None or not args.console.is_file():
            return None
        return ConsoleReplayer(args.console, sleigh_home=args.sleigh_home, timeout_s=args.timeout_s)
    if args.batch is None or not args.batch.is_file():
        return None
    return BatchReplayer(args.batch, sleigh_home=args.sleigh_home, timeout_s=args.timeout_s, workers=args.workers, tmpdir=args.tmpdir)


def _load_snapshot(snapshot: Path):
    from agentdecompile_recovery.native_snapshot.manifest import load_manifest

    try:
        return load_manifest(snapshot)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: invalid snapshot: {exc}", file=sys.stderr)
        return None


def run_replay(args: argparse.Namespace) -> int:
    manifest = _load_snapshot(args.snapshot)
    if manifest is None:
        return EXIT_USAGE
    replayer = _make_replayer(args)
    if replayer is None:
        return EXIT_USAGE
    replay = replayer.replay_manifest(args.snapshot, manifest)
    output = args.output or args.snapshot / "differential" / "replay.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for entry in manifest.ok_entries():
            result = replay.get(entry.addr)
            record = {
                "addr": entry.addr,
                "name": entry.name,
                "status": "missing" if result is None else ("ok" if result.c_text is not None else "error"),
                "c": None if result is None else result.c_text,
                "stderr": None if result is None else result.stderr,
                "returncode": None if result is None else result.returncode,
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            print(f"{record['addr']}\t{record['status']}\t{record['name']}")
    return EXIT_OK


def run_diff(args: argparse.Namespace) -> int:
    """Replay every successful savefile and return nonzero for any non-match."""
    from agentdecompile_recovery.native_snapshot.differential import MATCH, write_report

    manifest = _load_snapshot(args.snapshot)
    if manifest is None:
        return EXIT_USAGE
    replayer = _make_replayer(args)
    if replayer is None:
        return EXIT_USAGE
    replay = replayer.replay_manifest(args.snapshot, manifest)
    results = write_report(
        args.snapshot, manifest, {address: result.c_text for address, result in replay.items()},
        crashed={address for address, result in replay.items() if result.returncode < 0},
        timed_out={address for address, result in replay.items() if result.returncode == 124},
        errors={address: result.stderr for address, result in replay.items() if result.c_text is None and result.stderr},
        output=args.output,
    )
    for result in results:
        print(f"{result.addr}\t{result.classification}\t{result.name}")
    return EXIT_OK if all(result.classification == MATCH for result in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
