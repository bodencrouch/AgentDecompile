"""Enrich-before-decompile for the default reconstruct path.

Reuses ``pyghidra_enrich`` / ``module_resolver`` so one-shot and reconstruct
share behavior. Soft-degrades when PyGhidra is unavailable.
"""

from __future__ import annotations

import json
import re

from contextlib import suppress
from pathlib import Path
from typing import Any

from .curated_project import load_curated_names, load_curated_signatures
from .module_resolver import ModuleResolver, load_va_bands, normalize_code_path
from .pyghidra_enrich import (
    PyGhidraEnrichProgram,
    build_names_by_entry,
    is_default_ghidra_name,
    run_enrich_pipeline,
)
from .rtti_recover import (
    RttiClass,
    extract_assert_code_paths,
    extract_ghidra_rtti_classes,
    merge_rtti_classes,
    rtti_scan_receipt,
)
from .targets import sha256_file

SCHEMA = "agentdecompile.reconstruct-enrich.v1"


def resolve_existing_project_source(
    project: Path,
    project_program: str | None,
) -> dict[str, Any]:
    """Resolve one local Ghidra program and its current storage revision.

    ``ghidra_db`` performs this lookup without starting a JVM or modifying the
    project.  Keeping the database revision in the stage fingerprint makes a
    resumed run regenerate facts after the analyzed program changes.
    """

    from .ghidra_db import list_programs, resolve_project_root

    requested = project.expanduser().resolve()
    project_root = resolve_project_root(requested).resolve()
    if project_root.suffix.lower() != ".rep":
        raise ValueError(
            f"{requested}: existing-program decompilation requires a local .gpr/.rep project"
        )
    project_file = project_root.with_suffix(".gpr")
    if not project_file.is_file():
        raise ValueError(f"{project_root}: no sibling {project_file.name} project marker")

    programs = list_programs(project_root)
    if not programs:
        raise ValueError(f"{project_root}: project has no program items")
    if project_program:
        wanted = str(project_program).rstrip("/")
        matches = [
            entry
            for entry in programs
            if entry.project_path == wanted or entry.name == wanted
        ]
        if len(matches) != 1:
            available = ", ".join(entry.project_path for entry in programs)
            if not matches:
                raise ValueError(
                    f"{project_root}: no program {project_program!r} (have: {available})"
                )
            raise ValueError(
                f"{project_root}: program name {project_program!r} is ambiguous; "
                f"use its full project path (matches: {', '.join(entry.project_path for entry in matches)})"
            )
        selected = matches[0]
    elif len(programs) == 1:
        selected = programs[0]
    else:
        available = ", ".join(entry.project_path for entry in programs)
        raise ValueError(
            f"{project_root}: multiple programs in project, pass --project-program "
            f"to pick one (have: {available})"
        )

    stat = selected.database_path.stat()
    return {
        "mode": "existing-analyzed-project",
        "project": str(project_file.resolve()),
        "projectRoot": str(project_root),
        "projectDirectory": str(project_file.parent.resolve()),
        "projectName": project_file.stem,
        "program": selected.project_path,
        "revision": int(selected.version),
        "databaseFile": str(selected.database_path.resolve()),
        "databaseSize": int(stat.st_size),
        "databaseMtimeNs": int(stat.st_mtime_ns),
    }


def analysis_binary_from_work_dir(work_dir: Path) -> Path | None:
    analysis_path = work_dir / "analysis-target.json"
    if not analysis_path.exists():
        return None
    try:
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = payload.get("analysisBinaryPath")
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_file() else None


def boundaries_from_candidates(candidates_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map reconstruct function-candidates into enrich boundary rows."""
    boundaries: list[dict[str, Any]] = []
    for row in candidates_payload.get("candidates") or []:
        raw = row.get("address")
        if raw is None:
            raw = row.get("rva")
        try:
            entry = int(raw)
        except (TypeError, ValueError):
            continue
        length = row.get("size") or row.get("length")
        try:
            length_i = int(length) if length not in (None, 0, "0") else None
        except (TypeError, ValueError):
            length_i = None
        boundaries.append(
            {
                "entry": entry,
                "length": length_i,
                "name": row.get("name"),
                "section": ((row.get("evidence") or {}).get("section")),
                "provenance": str(row.get("source") or "function-candidate"),
            }
        )
    return boundaries


def trusted_curated_signatures(
    work_dir: Path,
    boundaries: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Curated prototypes for the entries this run will decompile.

    Two filters, both load-bearing:

    * a record with no `signature` is dropped -- that is how
      `curated_enrichment.build_curated_signature` reports "the target's own
      `ret N` contradicts this parameter list", and applying such a prototype
      would produce a confidently wrong candidate;
    * a record for an address this run has no boundary for is dropped, so the
      count in the receipt is the number of prototypes actually applied rather
      than the size of the curated project.
    """

    curated = load_curated_signatures(work_dir)
    if not curated:
        return {}
    wanted = {int(row["entry"]) for row in boundaries if row.get("entry") is not None}
    return {
        entry: record
        for entry, record in curated.items()
        if entry in wanted and record.get("signature")
    }


def load_work_dir_va_bands(work_dir: Path) -> list[tuple[int, str]]:
    """Load optional PE VA band profile from work-dir metadata."""

    work_dir = work_dir.resolve()
    for path in (
        work_dir / "facts" / "pe-module-profile.json",
        work_dir / "target.json",
        work_dir / "analysis-target.json",
    ):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        raw = payload.get("vaBands") or payload.get("va_bands") or payload.get("moduleVaBands")
        bands = load_va_bands(raw)
        if bands:
            return bands
    return []


def _analysis_target_payload(work_dir: Path) -> dict[str, Any]:
    analysis_path = work_dir / "analysis-target.json"
    if not analysis_path.is_file():
        return {}
    try:
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _nds_container_primary(work_dir: Path) -> dict[str, Any] | None:
    payload = _analysis_target_payload(work_dir)
    container = payload.get("container") if isinstance(payload.get("container"), dict) else {}
    primary = container.get("primary") if isinstance(container.get("primary"), dict) else {}
    if container.get("format") != "nds" or not primary:
        return None
    return primary


def _expand_boundaries_from_discovered(
    boundaries: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer Ghidra-discovered functions over coarse static seeds."""
    if not discovered:
        return boundaries
    if len(discovered) <= len(boundaries):
        return boundaries
    expanded: list[dict[str, Any]] = []
    for row in discovered:
        entry = int(row["entry"])
        expanded.append(
            {
                "entry": entry,
                "length": row.get("length"),
                "name": row.get("name"),
                "section": None,
                "provenance": "ghidra-discovered",
            }
        )
    return expanded


def run_reconstruct_enrich(
    *,
    binary: Path,
    work_dir: Path,
    candidates_payload: dict[str, Any],
    skip: bool = False,
    project: Path | None = None,
    project_program: str | None = None,
) -> dict[str, Any]:
    """Run enrich+module-map into ``work_dir/facts/``."""
    facts_dir = work_dir / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    facts_path = facts_dir / "function-facts.jsonl"
    module_map_path = facts_dir / "module-map.json"
    # Also mirror at work-dir root for legacy default_function_facts_path lookup.
    root_facts = work_dir / "function-facts.jsonl"

    if skip:
        receipt = {
            "schema": SCHEMA,
            "status": "skipped",
            "reason": "skip-enrichment",
            "claimBoundary": "enrichment skipped; decompiler facts may be absent or acquisition-supplied only",
        }
        (facts_dir / "enrich-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt

    boundaries = boundaries_from_candidates(candidates_payload)
    if not boundaries and project is None:
        receipt = {
            "schema": SCHEMA,
            "status": "skipped",
            "reason": "no-function-candidates",
            "claimBoundary": "enrichment skipped; no boundaries to decompile",
        }
        (facts_dir / "enrich-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt

    assert_paths = extract_assert_code_paths(binary)
    rtti = rtti_scan_receipt(binary)
    string_classes = [RttiClass(mangled=c["mangled"], name=c["name"], provenance=c.get("provenance") or "rtti-typeinfo") for c in rtti.get("classes") or []]
    rtti_classes = list(string_classes)

    from .symbol_provenance import ingest_symbol_provenance

    provenance_path = facts_dir / "symbol-provenance.json"
    if not provenance_path.is_file():
        ingest_symbol_provenance(work_dir, binary_path=binary)

    va_bands = load_work_dir_va_bands(work_dir)

    try:
        import pyghidra

        from .ghidra_analysis import resolve_project_name
    except Exception as exc:  # noqa: BLE001 - soft degrade without Ghidra
        receipt = {
            "schema": SCHEMA,
            "status": "skipped",
            "reason": "pyghidra-unavailable",
            "error": str(exc)[:500],
            "claimBoundary": "enrichment skipped; install Ghidra/PyGhidra for typed decompiles",
        }
        (facts_dir / "enrich-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt

    source_project = (
        resolve_existing_project_source(project, project_program)
        if project is not None
        else None
    )
    project_root = (
        Path(str(source_project["projectDirectory"]))
        if source_project is not None
        else work_dir / "pyghidra-project"
    )
    if source_project is None:
        project_root.mkdir(parents=True, exist_ok=True)
    project_name = (
        str(source_project["projectName"])
        if source_project is not None
        else resolve_project_name(binary)
    )
    resolver = ModuleResolver(va_bands=va_bands)
    discovered: list[dict[str, Any]] = []
    module_entries: dict[str, dict[str, Any]] = {}
    names_by_entry: dict[int, tuple[str, str]] = {}
    module_by_entry: dict[int, str] = {}
    summary: dict[str, Any]
    open_ctx = None
    existing_project = None
    program_ctx = None
    gp = None
    program = None
    analysis_binary_sha256 = sha256_file(binary)

    try:
        nds_primary = _nds_container_primary(work_dir)
        flat_api = None
        if source_project is not None:
            pyghidra.start()
            from ghidra.program.flatapi import FlatProgramAPI  # pyright: ignore[reportMissingImports]

            existing_project = pyghidra.open_project(project_root, project_name)
            program_ctx = pyghidra.program_context(
                existing_project,
                str(source_project["program"]),
            )
            program = program_ctx.__enter__()
            flat_api = FlatProgramAPI(program)
            domain_file = program.getDomainFile()
            live_revision = None
            with suppress(Exception):
                live_revision = int(domain_file.getVersion())
            executable_sha256 = None
            with suppress(Exception):
                executable_sha256 = str(program.getExecutableSHA256() or "").strip().lower()
            if executable_sha256 and re.fullmatch(r"[0-9a-f]{64}", executable_sha256):
                source_project["executableSha256"] = executable_sha256
                if executable_sha256 != analysis_binary_sha256:
                    raise ValueError(
                        "selected Ghidra program does not match the analysis binary: "
                        f"program SHA-256 {executable_sha256}, binary SHA-256 {analysis_binary_sha256}"
                    )
            if live_revision is not None:
                source_project["ghidraVersion"] = live_revision
        elif nds_primary is not None:
            pyghidra.start()
            from agentdecompile_cli.mcp_utils.container_import import import_raw_binary_slice
            from agentdecompile_cli.mcp_utils.program_analysis import blocking_ensure_analyzed
            from ghidra.base.project import GhidraProject  # pyright: ignore[reportMissingImports]
            from ghidra.program.flatapi import FlatProgramAPI  # pyright: ignore[reportMissingImports]

            load_address = int(str(nds_primary.get("loadAddress") or "0"), 0)
            entry_point = int(str(nds_primary.get("entryPoint") or "0"), 0)
            language_id = str(nds_primary.get("languageId") or "ARM:LE:32:v5t")
            role = str(nds_primary.get("role") or "arm9")
            gp = GhidraProject.createProject(str(project_root.resolve()), project_name, False)
            program = import_raw_binary_slice(
                gp,
                binary,
                language_id=language_id,
                base_address=load_address,
                block_name=role,
                program_name=binary.name,
                dest_folder_path="/",
                entry_point=entry_point or None,
            )
            analyze_tx = program.startTransaction("nds-auto-analysis")
            try:
                blocking_ensure_analyzed(program, force=True)
            finally:
                program.endTransaction(analyze_tx, True)
            flat_api = FlatProgramAPI(program)
        else:
            open_ctx = pyghidra.open_program(
                binary,
                project_location=project_root,
                project_name=project_name,
                analyze=True,
            )
            flat_api = open_ctx.__enter__()
            program = flat_api.getCurrentProgram()

        function_manager = program.getFunctionManager()
        reference_manager = program.getReferenceManager()
        listing = program.getListing()
        for function in function_manager.getFunctions(True):
            body = function.getBody()
            discovered.append(
                {
                    "entry": int(function.getEntryPoint().getOffset()),
                    "name": str(function.getName()),
                    "length": int(body.getNumAddresses()) if body is not None else None,
                }
            )
        for data in listing.getDefinedData(True):
            try:
                value = str(data.getValue() or "")
            except Exception:  # noqa: BLE001
                continue
            lowered = value.lower()
            if not (
                "/code/" in lowered
                or "\\code\\" in lowered
                or lowered.endswith((".cpp", ".c", ".cc", ".cxx", ".h", ".hpp"))
            ):
                continue
            for reference in reference_manager.getReferencesTo(data.getAddress()):
                function = function_manager.getFunctionContaining(reference.getFromAddress())
                if function is None:
                    continue
                entry = int(function.getEntryPoint().getOffset())
                resolver.assert_paths_by_entry[entry] = value

        ghidra_classes = extract_ghidra_rtti_classes(program)
        rtti_classes = merge_rtti_classes(ghidra_classes, string_classes)
        boundaries = _expand_boundaries_from_discovered(boundaries, discovered)

        names_by_entry = build_names_by_entry(
            discovered=discovered,
            rtti_classes=rtti_classes,
            corpus=None,
            curated_names=load_curated_names(work_dir),
        )
        from .symbol_provenance import load_symbol_provenance_names

        for entry_hex, prov_name in load_symbol_provenance_names(work_dir).items():
            try:
                entry = int(entry_hex, 16)
            except (TypeError, ValueError):
                continue
            if entry not in names_by_entry:
                names_by_entry[entry] = (prov_name, "symbol-provenance")
        for row in boundaries:
            entry = int(row["entry"])
            name = str(row.get("name") or "")
            if (
                name
                and not is_default_ghidra_name(name)
                and entry not in names_by_entry
            ):
                names_by_entry[entry] = (name, "function-candidate")

        for row in boundaries:
            entry = int(row["entry"])
            evidence = resolver.resolve(entry)
            module_by_entry[entry] = evidence.module
            module_entries[f"{entry:08x}"] = {
                "module": evidence.module,
                "moduleProvenance": evidence.provenance,
                "score": evidence.score,
            }

        summary = run_enrich_pipeline(
            boundaries=boundaries,
            corpus=None,
            rtti_classes=rtti_classes,
            out_facts=facts_path,
            program_factory=lambda: PyGhidraEnrichProgram(
                flat_api,
                mutate=source_project is None,
            ),
            module_by_entry=module_by_entry,
            names_by_entry=names_by_entry,
            signatures_by_entry=trusted_curated_signatures(work_dir, boundaries),
        )
    except Exception as exc:  # noqa: BLE001 - soft degrade; reconstruct continues
        receipt = {
            "schema": SCHEMA,
            "status": "failed",
            "reason": "enrich-session-error",
            "error": str(exc)[:1000],
            "sourceProject": source_project,
            "claimBoundary": "enrichment failed; recovery continues without typed decompiles",
        }
        (facts_dir / "enrich-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt
    finally:
        if open_ctx is not None:
            with suppress(Exception):
                open_ctx.__exit__(None, None, None)
        if program_ctx is not None:
            with suppress(Exception):
                program_ctx.__exit__(None, None, None)
        if existing_project is not None:
            with suppress(Exception):
                existing_project.close()
        if gp is not None:
            if program is not None:
                with suppress(Exception):
                    gp.close(program)
            with suppress(Exception):
                gp.close()

    if facts_path.exists():
        root_facts.write_text(facts_path.read_text(encoding="utf-8"), encoding="utf-8")

    rtti = {
        **rtti,
        "classCount": len(rtti_classes),
        "classes": [
            {"name": c.name, "mangled": c.mangled, "provenance": c.provenance} for c in rtti_classes
        ],
        "stringClassCount": len(string_classes),
        "ghidraMerged": True,
    }
    module_payload = {
        "schema": "agentdecompile.module-map.v1",
        "assertCodePaths": assert_paths,
        "normalizedAssertPaths": [normalize_code_path(p) for p in assert_paths],
        "entries": module_entries,
        "xrefMapped": len(resolver.assert_paths_by_entry),
        "vaBandCount": len(va_bands),
    }
    module_map_path.write_text(
        json.dumps(module_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (facts_dir / "rtti-scan.json").write_text(
        json.dumps(rtti, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    receipt = {
        "schema": SCHEMA,
        "status": "complete",
        "factsJsonl": str(facts_path),
        "moduleMap": str(module_map_path),
        "functionCount": summary.get("functionCount"),
        "namedCount": summary.get("namedCount"),
        "namesApplied": len(names_by_entry),
        "boundaryCount": len(boundaries),
        "assertPathCount": len(assert_paths),
        "rttiClassCount": len(rtti_classes),
        "analysisBinarySha256": analysis_binary_sha256,
        "ghidraProjectPath": str(project_root),
        "ghidraProjectName": project_name,
        "sourceProject": source_project,
        "sourceProjectPath": source_project.get("project") if source_project else None,
        "sourceProgramPath": source_project.get("program") if source_project else None,
        "sourceProjectRevision": source_project.get("revision") if source_project else None,
        "singleSession": True,
        "claimBoundary": "enrichment facts are advisory decompilation; objdiff 0 still required for verified/",
    }
    (facts_dir / "enrich-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if facts_path.exists():
        from .readability_repair import write_readability_repair_queue

        write_readability_repair_queue(work_dir)
    return receipt
