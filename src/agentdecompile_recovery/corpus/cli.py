"""CLI for the corpus-wide semantic decompilation pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from .archive import check_extraction, list_archive, summarize_entries
from .contract import STAGE_ALIASES, stages_catalog, resolve_stage
from .pipeline import run_corpus_pipeline, write_calibrate_global_receipt
from .registry import add_binary, load_corpus, new_corpus, save_corpus


def _hashed(slug: object) -> str:
    """A build name for a message: ``sha256(slug)[:12]``, never the slug."""
    return hashlib.sha256(str(slug).encode("utf-8")).hexdigest()[:12]


def _refusal_line(exc: BaseException) -> str | None:
    """One named line for a keyed verb's refusal, or None when *exc* is not one.

    The three refusal classes the keyed verbs (``export-hookpack``,
    ``verify-determinism``, ``logical-build``, ``backfill``) share:

    * ``BasisError`` -- the store cannot declare one basis.
    * ``ContentHashError`` -- a build the cascade keys on has no usable
      ``content_sha256``. Its message names slugs; only the count and the
      hashed names are printed.
    * ``sqlite3.OperationalError`` for a lock/busy/read-only condition --
      the write lock was held past ``busy_timeout``; reported as ``locked``
      rather than as a traceback. Any other operational error is a real
      failure and propagates.
    """
    from .determinism_basis import BasisError
    from .logical import BACKFILL_HINT, ContentHashError
    from .store import _is_lock_or_readonly

    if isinstance(exc, ContentHashError):
        names = ", ".join(_hashed(slug) for slug in exc.slugs)
        detail = "shared by" if exc.kind == "duplicate" else "missing for"
        return (
            f"error: ContentHashError: content_sha256 {detail} {len(exc.slugs)} build(s) [{names}]; "
            f"{BACKFILL_HINT}"
        )
    if isinstance(exc, BasisError):
        return f"error: {exc}"
    if isinstance(exc, sqlite3.OperationalError) and _is_lock_or_readonly(exc):
        return f"error: locked: {exc} (write lock held past busy_timeout)"
    return None


#: Returned by :func:`_run_keyed_verb` when the verb refused; the caller exits 2.
REFUSED = object()


def _run_keyed_verb(action):
    """Run *action*; on a refusal print one named line to stderr and return ``REFUSED``."""
    from .determinism_basis import BasisError
    from .logical import ContentHashError

    try:
        return action()
    except (BasisError, ContentHashError, sqlite3.OperationalError) as exc:
        line = _refusal_line(exc)
        if line is None:
            raise
        print(line, file=sys.stderr)
        return REFUSED


def run_list_archive_command(args: argparse.Namespace) -> int:
    archive: Path = args.archive
    if not archive.is_file():
        print(f"error: {archive} is not a file", file=sys.stderr)
        return 1

    entries = list(list_archive(archive))
    if getattr(args, "output_json", False):
        summary = summarize_entries(archive, entries)
        shown = [e.to_json() for e in entries if not (args.files_only and e.is_dir)]
        print(json.dumps({"summary": summary.to_json(), "entries": shown}, indent=2))
        return 0
    total_files = 0
    total_uncompressed = 0
    for entry in entries:
        if entry.is_dir and args.files_only:
            continue
        kind_tag = f"  [{entry.ghidra_kind}]" if entry.ghidra_kind else ""
        if entry.is_dir:
            print(f"         -  {entry.name.rstrip('/')}/{kind_tag}")
        else:
            print(f"  {entry.file_size:>12,}  {entry.name}{kind_tag}")
            total_files += 1
            total_uncompressed += entry.file_size
    print(f"\n  {total_uncompressed:>12,}  {total_files} files")
    return 0


def run_check_extraction_command(args: argparse.Namespace) -> int:
    archive: Path = args.archive
    directory: Path = args.directory
    if not archive.is_file():
        print(f"error: {archive} is not a file", file=sys.stderr)
        return 1
    if not directory.is_dir():
        print(f"error: {directory} is not a directory", file=sys.stderr)
        return 1

    report = check_extraction(archive, directory, check_extra=not args.no_extra)
    if getattr(args, "output_json", False):
        print(json.dumps(report.to_json(), indent=2))
    else:
        print(f"archive:   {archive}")
        print(f"directory: {directory}")
        print(f"status:    {report.status}")
        if report.missing:
            print(f"\nmissing ({len(report.missing)}):")
            for name in report.missing:
                print(f"  {name}")
        if report.size_mismatch:
            print(f"\nsize mismatch ({len(report.size_mismatch)}):")
            for item in report.size_mismatch:
                print(f"  {item['path']}  expected={item['expectedBytes']}  actual={item['actualBytes']}")
        if report.extra:
            print(f"\nextra ({len(report.extra)}):")
            for name in report.extra:
                print(f"  {name}")
        if report.is_complete:
            print("\nExtraction is complete.")
    return 0 if report.is_complete else 1


def default_batch_threads() -> int:
    import os

    return max(1, min(os.cpu_count() or 1, 8))


def render_batch_markdown(summary: dict) -> str:
    """Markdown table for a decompile-batch run (plain rows, no prose)."""
    rows = [
        ("repo_path", summary.get("repo_path")),
        ("want", summary.get("want")),
        ("already stored", summary.get("already_done")),
        ("pending", summary.get("pending")),
        ("attempted", summary.get("attempted")),
        ("completed", summary.get("completed")),
        ("timed out", summary.get("timed_out")),
        ("errored", summary.get("errored")),
        ("cancelled", summary.get("cancelled")),
        ("threads", summary.get("threads")),
        ("timeout_s", summary.get("timeout_s")),
        ("wall_s", f"{summary.get('wall_s', 0.0):.2f}"),
        ("fn_per_s", f"{summary.get('fn_per_s', 0.0):.2f}"),
        ("stale", summary.get("stale")),
        ("options_sha256", summary.get("options_sha256")),
        ("persisted", summary.get("persisted")),
        ("pending after", summary.get("pending_after")),
    ]
    lines = ["| field | value |", "|---|---|"]
    lines.extend(f"| {k} | {v} |" for k, v in rows)
    return "\n".join(lines) + "\n"


def run_decompile_batch_command(args: argparse.Namespace) -> int:
    """Open the program read-only, decompile pending addresses with the private parallel pool, persist to ctext."""
    from agentdecompile_recovery.corpus.decompile_text import connect_ctext, done_addrs, pending_addrs, pending_from, persist_batch_results

    if args.binary is None and not (args.project_location and args.project_name and args.program_name):
        print("error: --binary or (--project-location, --project-name, --program) is required", file=sys.stderr)
        return 2
    binary = args.binary.resolve() if args.binary is not None else None
    project_location = args.project_location or (args.ctext_db.resolve().parent / "pyghidra-project")
    project_name = args.project_name or (binary.name if binary is not None else "corpus")
    repo_path = args.repo_path or (str(binary) if binary is not None else f"{project_name}/{args.program_name}")
    threads = max(1, int(args.threads))

    import pyghidra
    from pyghidra.launcher import HeadlessPyGhidraLauncher

    if not pyghidra.started():
        launcher = HeadlessPyGhidraLauncher(verbose=False)
        launcher.add_vmargs(f"-Xmx{args.jvm_xmx}", f"-Dcpu.core.limit={threads}")
        launcher.start()

    from agentdecompile_cli.mcp_utils.parallel_decompile import batch_candidates, decompile_functions_iter, function_addr

    ctext_con = connect_ctext(args.ctext_db)
    project_location.mkdir(parents=True, exist_ok=True)
    summary: dict = {"repo_path": repo_path, "threads": threads, "timeout_s": int(args.timeout_s)}
    with pyghidra.open_program(
        binary,
        project_location=project_location,
        project_name=project_name,
        analyze=bool(args.analyze),
        program_name=args.program_name,
    ) as flat_api:
        program = flat_api.getCurrentProgram()
        candidates = batch_candidates(program)
        by_addr = {function_addr(f): f for f in candidates}
        if args.db is not None and args.binary_id is not None:
            from agentdecompile_recovery.corpus.store import connect as store_connect

            want = [a for a in pending_addrs(store_connect(args.db), ctext_con, repo_path, args.binary_id, min_instr=args.min_instr) if a in by_addr]
            want_total = len(want)
        else:
            want = list(by_addr)
            want_total = len(want)
        done = done_addrs(ctext_con, repo_path, include_failed=not args.retry_failed)
        pending = pending_from(want, done)
        if args.limit is not None:
            pending = pending[: max(0, int(args.limit))]
        summary.update({"want": want_total, "already_done": len([a for a in want if a in done]), "pending": len(pending)})
        persisted = 0
        batch = None
        gen = decompile_functions_iter(program, [by_addr[a] for a in pending], threads=threads, timeout_s=int(args.timeout_s))
        try:
            pending_results = []
            while True:
                try:
                    result = next(gen)
                except StopIteration as stop:
                    batch = stop.value
                    break
                pending_results.append(result)
                if len(pending_results) >= 64:
                    persisted += persist_batch_results(ctext_con, repo_path, pending_results)
                    pending_results = []
            persisted += persist_batch_results(ctext_con, repo_path, pending_results)
        finally:
            gen.close()
        summary["persisted"] = persisted
        if batch is not None:
            summary.update(batch.to_dict())
            summary["fn_per_s"] = (batch.completed / batch.wall_s) if batch.wall_s > 0 else 0.0
        summary["pending_after"] = len(pending_from(want, done_addrs(ctext_con, repo_path, include_failed=not args.retry_failed)))
    ctext_con.close()
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render_batch_markdown(summary))
    if summary.get("stale"):
        print("warning: program modification number changed during the batch (stale)", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentdecompile-corpus",
        description=(
            "Corpus-wide semantic decompilation. First priority is linking one "
            "STABS/DWARF donor project to a complete executable. Adding a binary "
            "is a registry action, not a rewrite."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create an empty corpus file")
    init.danger = init.mutating = True
    init.add_argument("--id", required=True, dest="corpus_id")
    init.add_argument("--out", type=Path, required=True)

    add = sub.add_parser("add-binary", help="Register another binary in the corpus")
    add.add_argument("--corpus", type=Path, required=True)
    add.add_argument("--id", required=True, dest="binary_id")
    add.add_argument("--path", required=True)
    add.add_argument("--debug", choices=("stabs", "dwarf", "none"), default="none")
    add.add_argument("--donor", action="store_true", help="Use this binary for STABS/DWARF layout")
    add.add_argument("--label", default="")
    add.add_argument("--threshold-with", dest="threshold_with", help="Other binary id for a pair threshold")
    add.add_argument("--min-confidence", type=float, default=0.55)
    add.add_argument("--arch", default="")
    add.add_argument("--bits", type=int, default=0)
    add.add_argument("--format", dest="file_format", default="")
    add.add_argument("--game", default="")

    rmbin = sub.add_parser(
        "remove-binary",
        help="Delete one binary and its per-binary rows from a store",
    )
    rmbin.danger = rmbin.mutating = True
    rmbin.identity_scope = "database"
    rmbin.add_argument("--db", type=Path, required=True)
    rmbin.add_argument("--repo", dest="repo_path")
    rmbin.add_argument("--slug")

    stabs = sub.add_parser("extract-stabs", help="Read Mach-O STABS into a functions snapshot")
    stabs.long_running = True
    stabs.add_argument("--binary", type=Path, required=True)
    stabs.add_argument("--id", required=True, dest="binary_id")
    stabs.add_argument("--out-dir", type=Path, required=True)

    run = sub.add_parser("run", help="Run pipeline stages in contract order")
    run.long_running = True
    run.add_argument("--corpus", type=Path, required=True)
    run.add_argument("--work-dir", type=Path, required=True)
    run.add_argument("--snapshot-dir", type=Path, required=True, help="Directory of {id}.functions.json extracts")
    run.add_argument(
        "--stop-after",
        default="compile",
        help=(
            "Last stage to run. Live names or aliases "
            f"({', '.join(f'{k}->{v}' for k, v in STAGE_ALIASES.items())}). "
            "Default compile aliases to recover-source."
        ),
    )
    run.add_argument("--compiler", default=None)
    run.add_argument(
        "--llm",
        action="store_true",
        help=(
            "After preparse+compile still fail, edit that Ghidra C with the local "
            "claude CLI and retry once. The model is given `agentdecompile-cli get-function` output."
        ),
    )
    run.add_argument("--llm-model", default=None, help="Optional claude --model for cleanup")

    sub.add_parser("stages", help="Print the contract stages and priorities")

    list_archive = sub.add_parser("list-archive", help="List a corpus ZIP without extracting it")
    list_archive.add_argument("archive", type=Path)
    list_archive.add_argument("--json", action="store_true", dest="output_json")
    list_archive.add_argument("--files-only", action="store_true")

    check_extraction = sub.add_parser(
        "check-extraction",
        help="Compare an extracted directory against its source archive",
    )
    check_extraction.add_argument("archive", type=Path)
    check_extraction.add_argument("directory", type=Path)
    check_extraction.add_argument("--no-extra", action="store_true")
    check_extraction.add_argument("--json", action="store_true", dest="output_json")

    init_store = sub.add_parser("init-store", help="Create an empty identity SQLite store")
    init_store.add_argument("--db", type=Path, required=True)

    write_snap = sub.add_parser("write-snapshot", help="Write {id}.functions.json from a JSON array")
    write_snap.add_argument("--id", required=True, dest="binary_id")
    write_snap.add_argument("--from-json", type=Path, required=True)
    write_snap.add_argument("--out-dir", type=Path, required=True)

    apply_stabs = sub.add_parser("apply-stabs", help="Apply a reviewed STABS manifest to a store")
    apply_stabs.long_running = True
    apply_stabs.identity_scope = "database"
    apply_stabs.add_argument("--db", type=Path, required=True)
    apply_stabs.add_argument("--binary-id", type=int, required=True)
    apply_stabs.add_argument("--manifest", type=Path, required=True)

    prop = sub.add_parser("propagate-source", help="Carry source_file across logical identities")
    prop.identity_scope = "database"
    prop.add_argument("--db", type=Path, required=True)

    ev = sub.add_parser("evaluate-pair", help="Measure matcher vs unique-name ground truth")
    ev.add_argument("--db", type=Path, required=True)
    ev.add_argument("--src", required=True)
    ev.add_argument("--dst", required=True)
    ev.add_argument("--mode", choices=("engine", "fid"), default="engine")

    sib = sub.add_parser("export-siblings", help="Export same-class method-name conflicts")
    sib.add_argument("--db", type=Path, required=True)
    sib.add_argument("--out", type=Path, required=True)

    hookpack = sub.add_parser(
        "export-hookpack",
        aliases=["export-hook-pack"],
        help="Write a Phasor-shaped hook pack from logical identities (VA is a cache)",
    )
    hookpack.add_argument("--db", type=Path, required=True)
    hookpack.add_argument("--out", type=Path, required=True)
    hookpack.add_argument(
        "--site-policy", type=Path, default=None,
        help="Optional validated site-kind/field policy for emitted hook sites.",
    )
    hookpack.add_argument(
        "--adapter-map", type=Path, default=None,
        help="Optional validated mapping from exported site names to runtime adapter roles.",
    )
    hookpack.add_argument(
        "--operation-contract", type=Path, default=None,
        help="Validated target-bound native operation declarations to include in the hook pack.",
    )

    verify_det = sub.add_parser(
        "verify-determinism",
        help="Export the hook pack from two temp copies of a store and byte-diff the results",
    )
    verify_det.add_argument("--db", type=Path, required=True)

    rebaseline = sub.add_parser(
        "rebaseline",
        help="Record a package-basis change as a supersession and re-stamp every binary row",
    )
    rebaseline.add_argument("--db", type=Path, required=True)
    rebaseline.add_argument(
        "--receipts", type=Path, required=True,
        help="Receipts directory. The receipt lands under rebaseline/ inside it.",
    )
    rebaseline.add_argument("--reason", default=None, help="Why the basis changed. Stored with the supersession.")
    rebaseline.add_argument(
        "--export-out", type=Path, default=None,
        help="Write a hook pack under the new basis into this directory.",
    )
    rebaseline.add_argument(
        "--prior-pack", type=Path, default=None,
        help="Diff the new pack against this pack. The prior pack is not changed.",
    )
    rebaseline.add_argument("--dry-run", action="store_true", help="Show the supersession. Write nothing.")
    rebaseline.add_argument(
        "--deadline-s", type=float, default=None,
        help="Stop between phases after this many seconds. Exit 4.",
    )

    backfill = sub.add_parser(
        "backfill",
        help="Re-derive binary columns from raw images; one receipt per (pass, binary) makes it resumable",
    )
    backfill.add_argument("--db", type=Path, required=True)
    backfill.add_argument("--pass", dest="passes", action="append", required=True, metavar="NAME")
    backfill.add_argument("--receipts", type=Path, required=True)
    backfill.add_argument("--no-resume", dest="resume", action="store_false")

    match_pair = sub.add_parser("match-pair", help="Run the store matcher on one directed pair")
    match_pair.identity_scope = "pair"
    match_pair.add_argument("--db", type=Path, required=True)
    match_pair.add_argument("--src", required=True)
    match_pair.add_argument("--dst", required=True)
    match_pair.add_argument("--run", default="v1")
    match_pair.add_argument("--note", default="")
    match_pair.add_argument("--progress-json", action="store_true", help="Emit matcher progress JSONL while scoring")

    logical_build = sub.add_parser("logical-build", help="Rebuild name-first logical identities")
    logical_build.identity_scope = "database"
    logical_build.add_argument("--db", type=Path, required=True)

    pkg = sub.add_parser("package", help="Copy a workspace tree to an output directory")
    pkg.add_argument("--workspace", type=Path, required=True)
    pkg.add_argument("--out", type=Path, required=True)

    cal = sub.add_parser("calibrate", help="Sweep score/margin from an evaluation JSON list")
    cal.add_argument("--from-json", type=Path, required=True)
    cal.add_argument("--out", type=Path, required=True)

    calg = sub.add_parser(
        "calibrate-global",
        help="Write compiler/ABI/types calibration receipt (not matcher score sweep)",
    )
    calg.long_running = True
    calg.add_argument("--work-dir", type=Path, required=True)
    calg.add_argument("--db", type=Path)
    calg.add_argument("--types-header", type=Path)
    calg.add_argument("--compiler-profile", type=Path)

    merge_parts = sub.add_parser("merge-parts", help="Merge per-program part databases into one store")
    merge_parts.danger = merge_parts.mutating = True
    merge_parts.identity_scope = "database"
    merge_parts.add_argument("--parts-dir", type=Path, required=True)
    merge_parts.add_argument("--db", type=Path, required=True)

    stabs_rep = sub.add_parser("stabs-report", help="Write STABS JSON + markdown for one Mach-O")
    stabs_rep.add_argument("--binary", type=Path, required=True)
    stabs_rep.add_argument("--out", type=Path, required=True)

    genp = sub.add_parser("genproject", help="Write a prompt project from the logical-function queue")
    genp.long_running = True
    genp.add_argument("--queue", type=Path, required=True)
    genp.add_argument("--out", type=Path, required=True)
    genp.add_argument("--db", type=Path, required=True)
    genp.add_argument("--raw", type=Path, required=True)
    genp.add_argument("--repo-path", required=True)
    genp.add_argument("--limit", type=int, default=25)
    genp.add_argument("--max-size", type=int, default=256)
    genp.add_argument("--min-size", type=int, default=4)
    genp.add_argument("--base-project", type=Path)
    genp.add_argument("--mkobj", type=Path)
    genp.add_argument("--coverage-ledger", type=Path)
    genp.add_argument("--skip-manifests", nargs="*", action="extend", default=[], type=Path)
    genp.add_argument("--skip-recovered", action="store_true")
    genp.add_argument("--leftover-only", action="store_true", default=True)
    genp.add_argument("--all-queue", dest="leftover_only", action="store_false")

    image_roundtrip = sub.add_parser(
        "roundtrip",
        help="Reassemble one binary as a byte-identical assembly file image",
    )
    image_roundtrip.add_argument("--repo-path", required=True)
    image_roundtrip.add_argument("--db", type=Path, required=True)
    image_roundtrip.add_argument("--raw", type=Path, required=True)
    image_roundtrip.add_argument("--out-dir", type=Path, required=True)
    image_roundtrip.add_argument(
        "--no-assemble",
        dest="assemble",
        action="store_false",
        default=True,
    )

    ingest_rec = sub.add_parser("ingest-recovered", help="Bind recovered C to existing identities")
    ingest_rec.long_running = True
    ingest_rec.add_argument("--db", type=Path, required=True)
    ingest_rec.add_argument("--recovered-dir", type=Path, required=True)
    ingest_rec.add_argument("--coverage-dir", type=Path, required=True)
    ingest_rec.add_argument("--out-dir", type=Path, required=True)
    ingest_rec.add_argument("--seed-results", type=Path)
    ingest_rec.add_argument("--reuse-candidates", type=Path)
    ingest_rec.add_argument("--force", action="store_true")
    ingest_rec.add_argument("--report", action="store_true")

    export_rr = sub.add_parser("export-run-report", help="Write aggregated recovered_function run results")
    export_rr.add_argument("--db", type=Path, required=True)
    export_rr.add_argument("--out", type=Path, required=True)

    gurl = sub.add_parser("ghidra-url", help="Print the Ghidra URL for a repo path")
    gurl.add_argument("path")

    apply_ann = sub.add_parser("apply-annotations", help="Apply jsonl names to a Ghidra program (dry-run default)")
    apply_ann.danger = apply_ann.mutating = True
    apply_ann.ghidra_exclusive = True
    apply_ann.add_argument("jsonl", type=Path)
    apply_ann.add_argument("--program", required=True)
    apply_ann.add_argument("--min-confidence", type=float, default=0.95)
    apply_ann.add_argument("--status", default="auto")
    apply_ann.add_argument("--apply", action="store_true")
    apply_ann.add_argument("--no-comments", action="store_true")

    bulk = sub.add_parser("ghidra-bulk", help="Normalize + compile Ghidra decompiled C")
    bulk.long_running = True
    bulk.add_argument("--program", required=True)
    bulk.add_argument("--repo", required=True)
    bulk.add_argument("--db", type=Path, required=True)
    bulk.add_argument("--out-dir", type=Path, required=True)
    bulk.add_argument("--kb", type=Path, required=True)
    bulk.add_argument("--mode", choices=("compile-only", "semantic"), default="compile-only")
    bulk.add_argument("--compiler", type=Path)
    bulk.add_argument("--sample", type=int)
    bulk.add_argument("--resume-failures-sha256", help="Continue identical inputs using the exact current failure receipt")
    bulk.add_argument("--workers", type=int, default=2)
    bulk.add_argument("--write", action="store_true", default=True)
    bulk.add_argument("--no-write", dest="write", action="store_false")
    bulk.add_argument("--skip-existing", action="store_true", default=True)
    bulk.add_argument("--force", dest="skip_existing", action="store_false")
    bulk.add_argument("--force-c-replace", action="store_true")
    bulk.add_argument("--llm-cleanup", action="store_true")
    bulk.add_argument("--llm-model")
    bulk.add_argument("--compile-complete", type=float, default=0.95)
    bulk.add_argument("--asm-fallback", action="store_true", default=True)
    bulk.add_argument("--no-asm-fallback", dest="asm_fallback", action="store_false")
    bulk.add_argument("--extract-raw", type=Path)

    workspace = sub.add_parser(
        "workspace",
        help="Write STABS folders and fill each compiling function as its own TU",
    )
    workspace.long_running = True
    workspace.add_argument("--db", type=Path, required=True)
    workspace.add_argument("--donor-slug", required=True)
    workspace.add_argument("--out", type=Path, required=True)
    workspace.add_argument("--fill-from", help="program id or repo_path to read addresses from")
    workspace.add_argument("--src-dir", type=Path, help="ghidra-bulk recovered-source tree")

    clink = sub.add_parser(
        "compile-link",
        help="Compile workspace units and link one executable (not byte-accuracy)",
    )
    clink.long_running = True
    clink.add_argument("--src-dir", type=Path, required=True)
    clink.add_argument("--out", type=Path, required=True)
    clink.add_argument("--compiler", type=Path)
    clink.add_argument("--sample", type=int)
    clink.add_argument("--obj-dir", type=Path)
    clink.add_argument("--workers", type=int, default=2)
    clink.add_argument("--vcroot", type=Path,
                       help="VC7 toolchain root for a direct MSVC/Wine link")
    clink.add_argument("--wineprefix", type=Path,
                       help="Wine prefix for a direct MSVC/Wine link")
    clink.add_argument("--no-entrypoint", dest="entrypoint", action="store_false")

    xplace = sub.add_parser("cross-place", help="Publish separately admitted recipient candidates; never replace accepted source")
    xplace.long_running = True
    xplace.mutating = True
    xplace.add_argument("--from", dest="program", required=True)
    xplace.add_argument("--db", type=Path, required=True)
    xplace.add_argument("--out-dir", type=Path, required=True)
    xplace.add_argument("--repo", required=True)
    xplace.add_argument("--raw-dir", type=Path, required=True, help="Current original images by binary slug")
    xplace.add_argument("--watch", action="store_true")
    xplace.add_argument("--interval", type=float, default=8.0)
    xplace.add_argument("--no-compile-gate", action="store_true")
    xplace.add_argument("--byteexact-receipt", type=Path,
                        help="completed verify-byteexact receipt; copy only individually exact C")

    vbx = sub.add_parser(
        "verify-byteexact",
        help="Relocation-aware objdiff-0 check: which recovered C compiles to "
             "the shipped bytes (asm-floor shims excluded from the count)",
    )
    vbx.add_argument("--verified-dir", type=Path, required=True)
    vbx.add_argument("--raw", type=Path, required=True)
    vbx.add_argument("--db", type=Path, required=True)
    vbx.add_argument("--binary-id", type=int, required=True)
    vbx.add_argument("--out", type=Path, required=True)
    vbx.add_argument("--maxc-bin-dir", type=Path, help="emit slot-fitting compiled "
                     "bytes for ANY compiling function (byte-exact or not) for the max-C image")
    vbx.add_argument("--bin-dir", type=Path, help="emit <addr>.bin substitution "
                     "inputs for reloc-free byte-exact real-C functions")
    vbx.add_argument("--compiler", type=Path)
    vbx.add_argument("--workers", type=int, default=3)
    vbx.add_argument("--limit", type=int, default=None)
    vbx.add_argument("--no-incremental", action="store_true",
                     help="ignore cached results and freshly recompile every selected file")

    vbx.add_argument("--cache-input-manifest", type=Path, help="Declared compiler/header/library input closure for verified cache reuse")
    vbx.add_argument("--transient-retry-seconds", type=float, default=300.0)

    vpd = sub.add_parser(
        "verify-periodic",
        help="Content-aware incremental verification with bounded time-based full audits",
    )
    vpd.add_argument("--verified-dir", type=Path, required=True)
    vpd.add_argument("--raw", type=Path, required=True)
    vpd.add_argument("--db", type=Path, required=True)
    vpd.add_argument("--binary-id", type=int, required=True)
    vpd.add_argument("--out", type=Path, required=True)
    vpd.add_argument("--maxc-bin-dir", type=Path)
    vpd.add_argument("--bin-dir", type=Path)
    vpd.add_argument("--compiler", type=Path)
    vpd.add_argument("--workers", type=int, default=3)
    vpd.add_argument("--limit", type=int, default=None)
    vpd.add_argument("--full-every", type=int, default=0, help="Legacy explicit pass-count audit; zero disables")
    vpd.add_argument("--full-interval-seconds", type=float, default=86400.0)
    vpd.add_argument("--force-full", action="store_true")
    vpd.add_argument("--counter-file", type=Path)
    vpd.add_argument("--cache-input-manifest", type=Path)
    vpd.add_argument("--transient-retry-seconds", type=float, default=300.0)

    vfi = sub.add_parser(
        "verify-full-image-receipt",
        help="Run one full build and require fresh objdiff evidence plus whole-file equality",
    )
    vfi.add_argument("--target", type=Path, required=True)
    vfi.add_argument("--candidate", type=Path, required=True)
    vfi.add_argument("--objdiff-receipt", type=Path, required=True)
    vfi.add_argument("--out", type=Path, required=True)
    vfi.add_argument("--cwd", type=Path, default=Path.cwd())
    vfi.add_argument("--timeout", type=int, default=7200)
    vfi.add_argument("--build-command", nargs=argparse.REMAINDER, required=True)

    vdfi = sub.add_parser(
        "verify-direct-full-image",
        help="Fresh direct VC7 compile/link, function objdiff receipt, and whole-file comparison",
    )
    vdfi.add_argument("--target", type=Path, required=True)
    vdfi.add_argument("--src-dir", type=Path, required=True)
    vdfi.add_argument("--raw", type=Path, required=True)
    vdfi.add_argument("--db", type=Path, required=True)
    vdfi.add_argument("--binary-id", type=int, required=True)
    vdfi.add_argument("--compiler", type=Path, required=True)
    vdfi.add_argument("--vcroot", type=Path, required=True)
    vdfi.add_argument("--wineprefix", type=Path, required=True)
    vdfi.add_argument("--work-dir", type=Path, required=True)
    vdfi.add_argument("--workers", type=int, default=1)

    wir = sub.add_parser(
        "whole-image-relink",
        help="Emit an exact-placement diagnostic using asm-floor original bytes "
             "where no verified C exists and verified-C bytes where it does; "
             "not a compiler-produced whole-image gate.",
    )
    wir.add_argument("--target", type=Path, required=True)
    wir.add_argument("--db", type=Path, required=True)
    wir.add_argument("--binary-id", type=int, required=True)
    wir.add_argument("--out", type=Path, required=True)
    wir.add_argument("--func-bytes", type=Path, help="dir of <addr>.bin verified-C "
                     "bytes to substitute; absent -> pure asm floor")

    mst = sub.add_parser(
        "matching-status",
        help="Honest matching-decomp ledger: recovered (real-C byte-exact) vs "
             "asm floor vs not-yet, plus an exact-placement diagnostic image",
    )
    mst.add_argument("--target", type=Path, required=True)
    mst.add_argument("--db", type=Path, required=True)
    mst.add_argument("--binary-id", type=int, required=True)
    mst.add_argument("--src-dir", type=Path, required=True)
    mst.add_argument("--receipts", type=Path, help="verify-byteexact --out JSON")
    mst.add_argument("--out-exe", type=Path)
    mst.add_argument("--out-manifest", type=Path)
    mst.add_argument("--out-report", type=Path)
    mst.add_argument("--byte-exact-floor", type=Path)

    mwatch = sub.add_parser(
        "matching-watch",
        help="Autonomous loop: emit the exact-placement diagnostic + refresh the "
             "honest ledger from the current verified-C set (asm floor elsewhere)",
    )
    mwatch.add_argument("--target", type=Path, required=True)
    mwatch.add_argument("--db", type=Path, required=True)
    mwatch.add_argument("--binary-id", type=int, required=True)
    mwatch.add_argument("--src-dir", type=Path, required=True)
    mwatch.add_argument("--receipts", type=Path)
    mwatch.add_argument("--func-bytes", type=Path)
    mwatch.add_argument("--out-exe", type=Path)
    mwatch.add_argument("--out-manifest", type=Path)
    mwatch.add_argument("--out-report", type=Path)
    mwatch.add_argument("--byte-exact-floor", type=Path)
    mwatch.add_argument("--watch", action="store_true")
    mwatch.add_argument("--interval", type=float, default=60.0)

    cnm = sub.add_parser("close-near-misses",
        help="LLM-edit small-diff mismatches to byte-exact (grows the byte-accurate build)")
    cnm.add_argument("--verified-dir", type=Path, required=True)
    cnm.add_argument("--raw", type=Path, required=True)
    cnm.add_argument("--receipts", type=Path, required=True)
    cnm.add_argument("--compiler", type=Path)
    cnm.add_argument("--db", type=Path)
    cnm.add_argument("--binary-id", type=int)
    cnm.add_argument("--bin-dir", type=Path)
    cnm.add_argument("--max-diff", type=int, default=8)
    cnm.add_argument("--limit", type=int, default=200)
    cnm.add_argument("--workers", type=int, default=2)
    cnm.add_argument("--model")
    cnm.add_argument("--state", type=Path)

    unp = sub.add_parser(
        "unpack",
        help="Detect packing/DRM (entropy + signatures) and unpack when possible "
             "(UPX / emulation); gate ciphertext so recovery never emits garbage",
    )
    unp.add_argument("--binary", type=Path, required=True)
    unp.add_argument("--out", type=Path)
    unp.add_argument("--detect-only", action="store_true")
    unp.add_argument("--allow-run", action="store_true")
    unp.add_argument("--wineprefix")
    unp.add_argument("--run-timeout", type=int, default=120)

    cons = sub.add_parser(
        "consolidate-corpus",
        help="Pick best-C-per-function across all corpora (MizuchiRE semantic, "
             "verified_c, historical, live) and upgrade the live tree in place",
    )
    cons.add_argument("--program", required=True)
    cons.add_argument("--live-dir", type=Path, required=True)
    cons.add_argument("--source", action="append", default=[],
                      help="repeatable 'rank:semantic:PATH'; lower rank wins")
    cons.add_argument("--dry-run", action="store_true")

    orch = sub.add_parser(
        "recovery-orchestrator",
        help="Durable bounded recovery supervision; failed-stage budgets survive restart",
    )
    # The aggregate command launches mutable providers; CLI exposure alone does
    # not reserve corpus/Ghidra state. Status inspection is read-only at admission.
    orch.mutating = orch.long_running = True
    orch.identity_scope = "database"
    orch.ghidra_exclusive = True
    orch.add_argument("--program", required=True)
    orch.add_argument("--repo", required=True)
    orch.add_argument("--db", required=True)
    orch.add_argument("--out-dir", required=True)
    orch.add_argument("--kb", required=True)
    orch.add_argument("--raw", required=True)
    orch.add_argument("--binary-id", type=int, required=True)
    orch.add_argument("--compiler")
    orch.add_argument("--extract-raw")
    orch.add_argument("--cascade-workers", type=int, default=1)
    orch.add_argument("--verify-workers", type=int, default=1)
    orch.add_argument("--no-cascade", dest="cascade", action="store_false", default=True)
    orch.add_argument("--no-verify", dest="verify", action="store_false", default=True)
    orch.add_argument("--no-nearmiss", dest="nearmiss", action="store_false", default=True)
    orch.add_argument("--no-permuter", dest="permuter", action="store_false", default=True)
    orch.add_argument("--no-cross-place", dest="cross_place", action="store_false", default=True)
    orch.add_argument("--poll", type=float, default=20.0)
    orch.add_argument("--log-dir", default="/tmp")
    orch.add_argument("--nearmiss-workers", type=int, default=1)
    orch.add_argument("--cache-input-manifest", type=Path)
    orch.add_argument("--transient-retry-seconds", type=float, default=300.0)
    orch.add_argument("--full-interval-seconds", type=float, default=86400.0)
    orch.add_argument("--input-basis", help="Verified semantic input manifest identity; required to launch")
    orch.add_argument("--max-failed-exits", type=int, default=3)
    orch.add_argument("--backoff", type=float, default=30.0)
    orch.add_argument("--success-backoff", type=float, default=300.0)
    orch.add_argument("--stagger", type=float, default=5.0)
    orch.add_argument("--status", action="store_true", help="Read persisted supervision status without launching")
    orch.add_argument("--once", action="store_true", help="One reconciliation/admission cycle; not goal completion")

    external = sub.add_parser("normalize-validation-report", help="Read external diagnostics as unaccepted proposals; no provider execution")
    external.add_argument("--provider", choices=("reagent-benchmark", "reccmp-compare"), required=True)
    external.add_argument("--report", type=Path, required=True)

    snapshot = sub.add_parser("export-reagent-snapshot", help="Export selected cached Ghidra evidence for ReAgent without new analysis")
    snapshot.mutating = True  # creates a new private destination, never edits the cache
    snapshot.add_argument("--kb", type=Path, required=True)
    snapshot.add_argument("--program", required=True)
    snapshot.add_argument("--address", action="append", required=True)
    snapshot.add_argument("--destination", type=Path, required=True)
    snapshot.add_argument("--max-functions", type=int, default=100)

    dbatch = sub.add_parser(
        "decompile-batch",
        help="Decompile pending functions in parallel into the ctext sqlite (never decompiles an address twice)",
    )
    dbatch.add_argument("--binary", type=Path, help="Binary to import (omit to open an existing program from the project)")
    dbatch.add_argument("--project-location", type=Path, help="Ghidra project directory (default: <ctext-db dir>/pyghidra-project)")
    dbatch.add_argument("--project-name", help="Ghidra project name (default: derived from the binary name)")
    dbatch.add_argument("--program", dest="program_name", help="Program name inside the project when --binary is omitted")
    dbatch.add_argument("--ctext-db", type=Path, required=True, help="ctext sqlite (schema from decompile_text.connect_ctext; rows via INSERT OR REPLACE like persist_text)")
    dbatch.add_argument("--repo-path", help="ctext key (default: resolved binary path, or <project>/<program>)")
    dbatch.add_argument("--threads", type=int, default=default_batch_threads(), help="Private decompiler pool size (default: min(cpu, 8))")
    dbatch.add_argument("--timeout-s", type=int, default=60, help="Per-function decompile timeout in seconds")
    dbatch.add_argument("--limit", type=int, help="Decompile at most this many pending functions")
    dbatch.add_argument("--db", type=Path, help="Identity store; with --binary-id the want-list comes from its func table")
    dbatch.add_argument("--binary-id", type=int, help="binary.id in --db")
    dbatch.add_argument("--min-instr", type=int, default=1, help="Store want-list filter (n_instr >= N)")
    dbatch.add_argument("--retry-failed", action="store_true", help="Treat ok=0 rows as pending again")
    dbatch.add_argument("--no-analyze", dest="analyze", action="store_false", help="Do not run auto-analysis on import")
    dbatch.add_argument("--jvm-xmx", default="2g", help="JVM max heap passed as -Xmx (default 2g)")
    dbatch.add_argument("--json", dest="json_out", type=Path, help="Also write the summary as JSON to this path")

    from . import kx_cli

    kx_cli.register(sub)
    from . import mizuchi_tools_cli

    mizuchi_tools_cli.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "export-reagent-snapshot":
        from .export_reagent_snapshot import export_reagent_snapshot
        try:
            result = export_reagent_snapshot(knowledge_db=args.kb, program=args.program,
                addresses=args.address, output_dir=args.destination, max_functions=args.max_functions)
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(json.dumps({"ok": False, "recovery_accepted": False, "error": str(exc)}))
            return 2
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    if args.cmd == "normalize-validation-report":
        from .external_validation import InvalidReport, read_report
        try:
            result = read_report(args.report, args.provider)
        except (InvalidReport, OSError) as exc:
            print(json.dumps({"report_state": "invalid_output", "recovery_accepted": False, "error": str(exc)}))
            return 2
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    if args.cmd == "init":
        save_corpus(args.out, new_corpus(args.corpus_id))
        print(args.out)
        return 0
    if args.cmd == "remove-binary":
        from .store import connect, remove_binary

        if not args.repo_path and not args.slug:
            print("error: --repo or --slug is required", file=sys.stderr)
            return 2
        print(json.dumps(remove_binary(connect(args.db), repo_path=args.repo_path, slug=args.slug), indent=2))
        return 0
    if args.cmd == "add-binary":
        corpus = load_corpus(args.corpus)
        add_binary(
            corpus,
            binary_id=args.binary_id,
            path=args.path,
            debug=args.debug,
            donor=args.donor,
            label=args.label,
            arch=args.arch,
            bits=args.bits,
            format=args.file_format,
            game=args.game,
        )
        if args.threshold_with:
            from .registry import PairThreshold

            corpus.pair_thresholds.append(
                PairThreshold(left=args.binary_id, right=args.threshold_with, min_confidence=args.min_confidence)
            )
        save_corpus(args.corpus, corpus)
        print(json.dumps({"binaries": [b.id for b in corpus.binaries], "donorId": corpus.donor_id}))
        return 0
    if args.cmd == "extract-stabs":
        from .machostabs import analyze

        report = analyze(args.binary)
        functions = []
        for sl in report.get("slices") or []:
            stabs = sl.get("stabs") or {}
            for fn in stabs.get("functions") or []:
                functions.append(
                    {
                        "id": f"0x{fn.get('addr') or 0:x}",
                        "addr": fn.get("addr"),
                        "name": fn.get("name"),
                        "stabs_name": fn.get("name"),
                        "source_file": fn.get("source_file"),
                        "object_file": fn.get("object_file"),
                        "size": fn.get("size"),
                        "name_origin": "stabs",
                        "strings": [],
                        "consts": [],
                        "ext_calls": [],
                        "mnem": {},
                        "callees": [],
                    }
                )
        args.out_dir.mkdir(parents=True, exist_ok=True)
        dest = args.out_dir / f"{args.binary_id}.functions.json"
        dest.write_text(json.dumps(functions, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"wrote": str(dest), "functions": len(functions), "slices": len(report.get("slices") or [])}))
        return 0
    if args.cmd == "run":
        try:
            stop_after = resolve_stage(args.stop_after)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        corpus = load_corpus(args.corpus)
        summary = run_corpus_pipeline(
            corpus,
            work_dir=args.work_dir,
            snapshot_dir=args.snapshot_dir,
            stop_after=stop_after,
            compiler=args.compiler,
            llm=bool(args.llm),
            llm_model=args.llm_model,
        )
        print(json.dumps(summary, indent=2))
        if stop_after == "recover-source" and not summary.get("completeExecutable"):
            return 2
        return 0
    if args.cmd == "stages":
        print(json.dumps(stages_catalog(), indent=2))
        return 0
    if args.cmd == "calibrate-global":
        if args.db is None and args.work_dir is None:
            print("error: --work-dir is required", file=sys.stderr)
            return 2
        receipt = write_calibrate_global_receipt(
            args.work_dir,
            db=args.db,
            types_header=args.types_header,
            compiler_profile=args.compiler_profile,
        )
        print(json.dumps(receipt, indent=2))
        return 0 if receipt.get("state") != "error" else 1
    if args.cmd == "list-archive":
        return run_list_archive_command(args)
    if args.cmd == "check-extraction":
        return run_check_extraction_command(args)
    if args.cmd == "init-store":
        from .store import connect

        connect(args.db).close()
        print(args.db)
        return 0
    if args.cmd == "write-snapshot":
        from .extract import write_snapshot
        from .io import read_json

        rows = read_json(args.from_json)
        functions = list(rows) if isinstance(rows, list) else list(rows.get("functions") or [])
        dest = write_snapshot(args.out_dir, args.binary_id, functions)
        print(json.dumps({"wrote": str(dest), "functions": len(functions)}))
        return 0
    if args.cmd == "apply-stabs":
        from .stabs_link import apply_manifest_records, ensure_columns
        from .store import connect

        records = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line]
        con = connect(args.db)
        ensure_columns(con)
        n = apply_manifest_records(con, args.binary_id, records)
        print(json.dumps({"applied": n}))
        return 0
    if args.cmd == "propagate-source":
        from .stabs_link import ensure_columns, propagate_source_files
        from .store import connect

        con = connect(args.db)
        ensure_columns(con)
        print(json.dumps({"pushed": propagate_source_files(con)}))
        return 0
    if args.cmd == "evaluate-pair":
        from .evaluate import evaluate
        from .store import connect

        print(json.dumps(evaluate(connect(args.db), args.src, args.dst, mode=args.mode), indent=2))
        return 0
    if args.cmd == "export-siblings":
        from .sibling_conflicts import export_sibling_conflicts
        from .store import connect

        print(json.dumps(export_sibling_conflicts(connect(args.db), args.out)))
        return 0
    if args.cmd in {"export-hookpack", "export-hook-pack"}:
        from .export_hookpack import export_hookpack
        from .store import connect

        # A refusal (basis, content hash, lock) is exit 2 with one named
        # line; the basis check runs before the site loop so it costs
        # milliseconds, not the loop's minutes. Nothing was written.
        summary = _run_keyed_verb(
            lambda: export_hookpack(
                connect(args.db), args.out,
                site_policy=args.site_policy,
                adapter_map=args.adapter_map,
                operation_contract=args.operation_contract,
            )
        )
        if summary is REFUSED:
            return 2
        print(json.dumps(summary))
        return 0
    if args.cmd == "verify-determinism":
        from .determinism_basis import verify_export
        from .export_hookpack import export_hookpack

        result = _run_keyed_verb(lambda: verify_export(args.db, export_hookpack))
        if result is REFUSED:
            return 2
        print(json.dumps(result))
        return 0 if result["identical"] else 1
    if args.cmd == "rebaseline":
        from .determinism_basis import BasisError
        from .logical import ContentHashError
        from .rebaseline import rebaseline as run_rebaseline
        from .store import connect

        def run_it():
            try:
                return run_rebaseline(
                    connect(args.db),
                    receipts_dir=args.receipts,
                    reason=args.reason,
                    export_out=args.export_out,
                    prior_pack=args.prior_pack,
                    dry_run=args.dry_run,
                    deadline_s=args.deadline_s,
                )
            except (BasisError, ContentHashError):
                raise
            except ValueError as exc:
                raise SystemExit(f"error: {exc}") from exc

        # Refusals (basis, content hash, lock) are exit 2 with one named
        # line and nothing written. A deadline is exit 4: the re-stamp is
        # one transaction, so it either landed whole or not at all; the
        # summary says which. An export that refused after the re-stamp
        # landed keeps exit 0: the supersession stands, and the refusal is
        # recorded under run.export and named once on stderr.
        result = _run_keyed_verb(run_it)
        if result is REFUSED:
            return 2
        print(json.dumps(result, sort_keys=True, indent=2))
        if result["status"] == "deadline":
            return 4
        export = (result.get("run") or {}).get("export") or {}
        if export.get("status") == "refused":
            print(f"error: export refused after re-stamp: {export.get('error')}", file=sys.stderr)
        return 0
    if args.cmd == "backfill":
        from .backfill import run as run_backfill
        from .logical import ContentHashError
        from .store import connect

        def run_it():
            try:
                return run_backfill(connect(args.db), args.passes, receipts_dir=args.receipts, resume=args.resume)
            except ContentHashError:
                raise
            except ValueError as exc:
                raise SystemExit(f"error: {exc}") from exc

        result = _run_keyed_verb(run_it)
        if result is REFUSED:
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.cmd == "match-pair":
        from .propagate import run_pair
        from .store import connect

        def emit_progress(event: dict) -> None:
            print(json.dumps({"event": "match-pair-progress", **event}), flush=True)

        print(json.dumps(run_pair(
            connect(args.db), args.src, args.dst, args.note, args.run,
            progress=emit_progress if args.progress_json else None,
        ), indent=2))
        return 0
    if args.cmd == "logical-build":
        from .logical import build
        from .store import connect

        result = _run_keyed_verb(lambda: build(connect(args.db)))
        if result is REFUSED:
            return 2
        print(json.dumps(result))
        return 0
    if args.cmd == "package":
        from .package_project import package_project

        print(json.dumps(package_project(args.workspace, args.out)))
        return 0
    if args.cmd == "calibrate":
        from .calibrate import calibrate_evaluations
        from .io import read_json, write_json

        payload = read_json(args.from_json)
        write_json(args.out, calibrate_evaluations(list(payload)))
        print(args.out)
        return 0
    if args.cmd == "merge-parts":
        from .merge import merge_parts

        parts = sorted(
            p
            for p in args.parts_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".sqlite", ".db", ".sqlite3"}
        )
        print(json.dumps(merge_parts(parts, args.db), indent=2))
        return 0
    if args.cmd == "stabs-report":
        from .stabs_report import write_report

        print(json.dumps(write_report(args.binary, args.out), indent=2))
        return 0
    if args.cmd == "genproject":
        from .genproject import generate_project
        from .store import connect

        print(
            json.dumps(
                generate_project(
                    con=connect(args.db),
                    repo_path=args.repo_path,
                    out_dir=args.out,
                    queue_path=args.queue,
                    raw_path=args.raw,
                    limit=args.limit,
                    max_size=args.max_size,
                    min_size=args.min_size,
                    base_project=args.base_project,
                    mkobj=args.mkobj,
                    coverage_ledger=args.coverage_ledger,
                    skip_manifests=args.skip_manifests,
                    skip_recovered=args.skip_recovered,
                    leftover_only=args.leftover_only,
                ),
                indent=2,
            )
        )
        return 0
    if args.cmd == "roundtrip":
        from .roundtrip import roundtrip, write_results
        from .store import connect

        result = roundtrip(
            args.repo_path,
            connect(args.db),
            raw_path=args.raw,
            out_dir=args.out_dir,
            assemble=args.assemble,
        )
        receipt = write_results(args.out_dir, [result])
        result["receipt"] = str(receipt)
        print(json.dumps(result, indent=2))
        return 0 if result.get("identical") is True else 1
    if args.cmd == "ingest-recovered":
        from .ingest_recovered import ensure_recovered_schema, ingest, print_summary
        from .store import connect

        con = connect(args.db)
        ensure_recovered_schema(con)
        if args.report:
            print(json.dumps(print_summary(con, args.out_dir), indent=2))
            return 0
        print(
            json.dumps(
                ingest(
                    con,
                    recovered_dir=args.recovered_dir,
                    coverage_dir=args.coverage_dir,
                    out_dir=args.out_dir,
                    seed_results=args.seed_results,
                    reuse_candidates=args.reuse_candidates,
                    force=args.force,
                ),
                indent=2,
            )
        )
        return 0
    if args.cmd == "export-run-report":
        from .export_run_report import write_report

        report = write_report(args.db, args.out)
        print(json.dumps({"out": report["out"], "summary": report["summary"]}, indent=2))
        return 0
    if args.cmd == "ghidra-url":
        from .ghidra_url import ghidra_url

        print(ghidra_url(args.path))
        return 0
    if args.cmd == "apply-annotations":
        from .apply_annotations import apply_annotations

        print(
            json.dumps(
                apply_annotations(
                    args.jsonl,
                    args.program,
                    apply=args.apply,
                    min_confidence=args.min_confidence,
                    status=args.status,
                    comments=not args.no_comments,
                ),
                indent=2,
            )
        )
        return 0
    if args.cmd == "ghidra-bulk":
        from . import ghidra_bulk as gb

        bulk_argv = [
            "--program", args.program,
            "--repo", args.repo,
            "--db", str(args.db),
            "--out-dir", str(args.out_dir),
            "--kb", str(args.kb),
            "--mode", args.mode,
            "--compile-complete", str(args.compile_complete),
            "--workers", str(args.workers),
        ]
        if args.compiler:
            bulk_argv += ["--compiler", str(args.compiler)]
        if args.sample is not None:
            bulk_argv += ["--sample", str(args.sample)]
        if args.resume_failures_sha256:
            bulk_argv += ["--resume-failures-sha256", args.resume_failures_sha256]
        if not args.write:
            bulk_argv.append("--no-write")
        if not args.skip_existing:
            bulk_argv.append("--force")
        if getattr(args, "force_c_replace", False):
            bulk_argv.append("--force-c-replace")
        if args.llm_cleanup:
            bulk_argv.append("--llm-cleanup")
        if args.llm_model:
            bulk_argv += ["--llm-model", args.llm_model]
        if not args.asm_fallback:
            bulk_argv.append("--no-asm-fallback")
        if args.extract_raw:
            bulk_argv += ["--extract-raw", str(args.extract_raw)]
        return gb.main(bulk_argv)
    if args.cmd == "workspace":
        from .store import connect
        from .workspace_skeleton import build_workspace

        if args.fill_from and args.src_dir is None:
            print("error: --src-dir is required with --fill-from", file=sys.stderr)
            return 2
        con = connect(args.db)
        stats = build_workspace(
            con,
            args.donor_slug,
            args.out,
            fill_from=args.fill_from,
            src_dir=args.src_dir,
        )
        print(json.dumps(stats, indent=2))
        return 0
    if args.cmd == "compile-link":
        from .compile_link import compile_and_link_tree

        result = compile_and_link_tree(
            args.src_dir,
            args.out,
            compiler=str(args.compiler) if args.compiler else None,
            sample=args.sample,
            obj_dir=args.obj_dir,
            workers=args.workers,
            entrypoint=getattr(args, "entrypoint", True),
            vcroot=args.vcroot,
            wineprefix=str(args.wineprefix) if args.wineprefix else None,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "cross-place":
        from .cross_place import main as cross_main

        argv = [
            "--from", args.program,
            "--db", str(args.db),
            "--out-dir", str(args.out_dir),
            "--repo", args.repo,
            "--raw-dir", str(args.raw_dir),
        ]
        if args.watch:
            argv.append("--watch")
            argv += ["--interval", str(args.interval)]
        if getattr(args, 'no_compile_gate', False):
            argv.append("--no-compile-gate")
        if args.byteexact_receipt:
            argv += ["--byteexact-receipt", str(args.byteexact_receipt)]
        return cross_main(argv)
    if args.cmd == "verify-byteexact":
        from .verify_recovered_byteexact import main as vbx_main
        argv = ["--verified-dir", str(args.verified_dir), "--raw", str(args.raw),
                "--db", str(args.db), "--binary-id", str(args.binary_id),
                "--out", str(args.out), "--workers", str(args.workers)]
        if args.compiler:
            argv += ["--compiler", str(args.compiler)]
        else:
            from .ghidra_bulk import _find_compiler
            argv += ["--compiler", str(_find_compiler(args.out.parent, args.db))]
        if args.bin_dir:
            argv += ["--bin-dir", str(args.bin_dir)]
        if getattr(args, "maxc_bin_dir", None):
            argv += ["--maxc-bin-dir", str(args.maxc_bin_dir)]
        if args.limit is not None:
            argv += ["--limit", str(args.limit)]
        if getattr(args, "no_incremental", False):
            argv += ["--no-incremental"]
        if args.cache_input_manifest:
            argv += ["--cache-input-manifest", str(args.cache_input_manifest)]
        argv += ["--transient-retry-seconds", str(args.transient_retry_seconds)]
        return vbx_main(argv)
    if args.cmd == "verify-periodic":
        from .verify_periodic import main as vpd_main
        argv = ["--verified-dir", str(args.verified_dir), "--raw", str(args.raw),
                "--db", str(args.db), "--binary-id", str(args.binary_id),
                "--out", str(args.out), "--workers", str(args.workers),
                "--full-every", str(args.full_every)]
        if args.compiler:
            argv += ["--compiler", str(args.compiler)]
        else:
            from .ghidra_bulk import _find_compiler
            argv += ["--compiler", str(_find_compiler(args.out.parent, args.db))]
        if args.bin_dir:
            argv += ["--bin-dir", str(args.bin_dir)]
        if getattr(args, "maxc_bin_dir", None):
            argv += ["--maxc-bin-dir", str(args.maxc_bin_dir)]
        if args.limit is not None:
            argv += ["--limit", str(args.limit)]
        argv += ["--full-interval-seconds", str(args.full_interval_seconds),
                 "--transient-retry-seconds", str(args.transient_retry_seconds)]
        if args.force_full:
            argv.append("--force-full")
        if args.counter_file:
            argv += ["--counter-file", str(args.counter_file)]
        if args.cache_input_manifest:
            argv += ["--cache-input-manifest", str(args.cache_input_manifest)]
        return vpd_main(argv)
    if args.cmd == "verify-full-image-receipt":
        from .verify_full_image_receipt import main as vfi_main
        argv = ["--target", str(args.target), "--candidate", str(args.candidate),
                "--objdiff-receipt", str(args.objdiff_receipt), "--out", str(args.out),
                "--cwd", str(args.cwd), "--timeout", str(args.timeout),
                "--build-command", *args.build_command]
        return vfi_main(argv)
    if args.cmd == "verify-direct-full-image":
        from .verify_direct_full_image import main as vdfi_main

        return vdfi_main([
            "--target", str(args.target), "--src-dir", str(args.src_dir),
            "--raw", str(args.raw), "--db", str(args.db), "--binary-id", str(args.binary_id),
            "--compiler", str(args.compiler), "--vcroot", str(args.vcroot),
            "--wineprefix", str(args.wineprefix), "--work-dir", str(args.work_dir),
            "--workers", str(args.workers),
        ])
    if args.cmd == "whole-image-relink":
        from .whole_image_relink import main as wir_main
        argv = ["--target", str(args.target), "--db", str(args.db),
                "--binary-id", str(args.binary_id), "--out", str(args.out)]
        if args.func_bytes:
            argv += ["--func-bytes", str(args.func_bytes)]
        return wir_main(argv)
    if args.cmd == "matching-status":
        from .matching_status import main as mst_main
        argv = ["--target", str(args.target), "--db", str(args.db),
                "--binary-id", str(args.binary_id), "--src-dir", str(args.src_dir)]
        if args.receipts:
            argv += ["--receipts", str(args.receipts)]
        if args.out_exe:
            argv += ["--out-exe", str(args.out_exe)]
        if args.out_manifest:
            argv += ["--out-manifest", str(args.out_manifest)]
        if args.out_report:
            argv += ["--out-report", str(args.out_report)]
        if args.byte_exact_floor:
            argv += ["--byte-exact-floor", str(args.byte_exact_floor)]
        return mst_main(argv)
    if args.cmd == "matching-watch":
        from .matching_watch import main as mw_main
        argv = ["--target", str(args.target), "--db", str(args.db),
                "--binary-id", str(args.binary_id), "--src-dir", str(args.src_dir)]
        for opt, val in (("--receipts", args.receipts), ("--func-bytes", args.func_bytes),
                         ("--out-exe", args.out_exe), ("--out-manifest", args.out_manifest),
                         ("--out-report", args.out_report), ("--byte-exact-floor", args.byte_exact_floor)):
            if val:
                argv += [opt, str(val)]
        if args.watch:
            argv += ["--watch", "--interval", str(args.interval)]
        return mw_main(argv)
    if args.cmd == "close-near-misses":
        from .close_near_misses import main as cnm_main
        argv=["--verified-dir",str(args.verified_dir),"--raw",str(args.raw),
              "--receipts",str(args.receipts),"--max-diff",str(args.max_diff),
              "--limit",str(args.limit),"--workers",str(args.workers)]
        if args.compiler: argv+=["--compiler",str(args.compiler)]
        else:
            from .ghidra_bulk import _find_compiler
            argv+=["--compiler",str(_find_compiler(args.raw.parent,args.db) if args.db else _find_compiler(args.raw.parent))]
        if args.db: argv+=["--db",str(args.db)]
        if args.binary_id is not None: argv+=["--binary-id",str(args.binary_id)]
        if args.bin_dir: argv+=["--bin-dir",str(args.bin_dir)]
        if args.model: argv+=["--model",str(args.model)]
        if args.state: argv+=["--state",str(args.state)]
        return cnm_main(argv)
    if args.cmd == "unpack":
        from .unpack import main as unpack_main
        argv = ["--binary", str(args.binary)]
        if args.out:
            argv += ["--out", str(args.out)]
        if args.detect_only:
            argv.append("--detect-only")
        if getattr(args, "allow_run", False):
            argv.append("--allow-run")
        if getattr(args, "wineprefix", None):
            argv += ["--wineprefix", str(args.wineprefix)]
        if getattr(args, "run_timeout", None):
            argv += ["--run-timeout", str(args.run_timeout)]
        return unpack_main(argv)
    if args.cmd == "consolidate-corpus":
        from .consolidate_corpus import main as cons_main
        argv = ["--program", args.program, "--live-dir", str(args.live_dir)]
        for s in args.source:
            argv += ["--source", s]
        if args.dry_run:
            argv.append("--dry-run")
        return cons_main(argv)
    if args.cmd == "recovery-orchestrator":
        from .recovery_orchestrator import main as orch_main
        argv = ["--program", args.program, "--repo", args.repo, "--db", str(args.db),
                "--out-dir", str(args.out_dir), "--kb", str(args.kb),
                "--raw", str(args.raw), "--binary-id", str(args.binary_id),
                "--cascade-workers", str(args.cascade_workers),
                "--verify-workers", str(args.verify_workers),
                "--poll", str(args.poll), "--log-dir", str(args.log_dir)]
        if args.compiler:
            argv += ["--compiler", str(args.compiler)]
        if args.extract_raw:
            argv += ["--extract-raw", str(args.extract_raw)]
        if not args.permuter:
            argv.append("--no-permuter")
        if not args.cross_place:
            argv.append("--no-cross-place")
        if not args.cascade:
            argv.append("--no-cascade")
        if not args.verify:
            argv.append("--no-verify")
        if not args.nearmiss:
            argv.append("--no-nearmiss")
        argv += ["--nearmiss-workers", str(args.nearmiss_workers),
                 "--max-failed-exits", str(args.max_failed_exits),
                 "--backoff", str(args.backoff), "--success-backoff", str(args.success_backoff),
                 "--stagger", str(args.stagger)]
        argv += ["--transient-retry-seconds", str(args.transient_retry_seconds),
                 "--full-interval-seconds", str(args.full_interval_seconds)]
        if args.cache_input_manifest:
            argv += ["--cache-input-manifest", str(args.cache_input_manifest)]
        if args.input_basis:
            argv += ["--input-basis", args.input_basis]
        if args.status:
            argv.append("--status")
        if args.once:
            argv.append("--once")
        return orch_main(argv)
    if args.cmd == "decompile-batch":
        return run_decompile_batch_command(args)
    from . import kx_cli

    code = kx_cli.dispatch(args)
    if code is not None:
        return code
    from . import mizuchi_tools_cli

    code = mizuchi_tools_cli.dispatch(args)
    if code is not None:
        return code
    return 2


if __name__ == "__main__":
    sys.exit(main())
