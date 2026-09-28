"""Batch runner for the upstream-style source recovery plugin pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .plugin_pipeline import PluginPipeline
from .compile_cache import target_slice_sha256
from .match_cache import is_proven_zero, source_sha256
from .source_export import export_recovered_source
from .source_parity_synthesize import (
    append_packaged_fallback,
    clean_jsonl,
    compiler_compatible_candidates,
    filter_candidates_by_explicit_rule_strategies,
    filter_candidates_by_source_quality,
    generate,
    is_boundary_suspect,
    iter_jsonl,
    iter_source_task_rows,
    packaged_source_candidate,
    parse_profile_flag_set,
    prioritize_candidates,
    strategy_allowed,
    synthesis_row_priority,
    write_json,
)
from .source_plugins import SourceCandidateGeneratorPlugin, SourceCandidateObjdiffPlugin
from .state import atomic_write_json


TERMINAL_ATTEMPT_CACHE_SCHEMA = "agentdecompile.source-plugin-terminal-attempt.v1"


@dataclass
class SourcePluginRunConfig:
    queue: Path | None = None
    source_tasks: list[Path] = field(default_factory=list)
    source_tasks_only: bool = False
    out_dir: Path = Path("target/source-plugin-pipeline/default")
    limit: int = 25
    offset: int = 0
    max_variants_per_function: int = 8
    max_retries: int = 8
    strategies: set[str] | None = None
    source_qualities: set[str] | None = None
    compiler: str = "msvc"
    clang: str = "clang"
    compiler_profiles: list[tuple[str, list[str]]] = field(default_factory=list)
    dry_run: bool = False
    semantic_only: bool = False
    skip_boundary_suspect: bool = False
    source_shape_search: bool = False
    work_dir: Path | None = None
    routed_playbook: str | None = None
    clean: bool = False
    inventory: Path = Path("target/binary-unpack/facts/function-inventory.jsonl")
    vc_root: Path | None = None
    wine: str = "wine"
    wineprefix: Path | None = None
    timeout: int = 120
    progress_every: int = 0
    target_sha: str | None = None
    resume: bool = False


def run_source_plugin_pipeline(config: SourcePluginRunConfig) -> dict[str, Any]:
    if config.clean and config.resume:
        raise ValueError("source plugin pipeline cannot combine clean and resume")
    if config.clean and config.out_dir.exists():
        shutil.rmtree(config.out_dir)
    config.out_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = config.out_dir / "plugin-attempts.jsonl"
    matches_path = config.out_dir / "plugin-code-slice-matches.jsonl"
    source_shape_matches_path = config.out_dir / "plugin-source-shape-matches.jsonl"
    events_path = config.out_dir / "plugin-events.jsonl"
    runs_path = config.out_dir / "plugin-runs.jsonl"
    terminal_cache_root = config.out_dir / "terminal-attempt-cache"
    if not config.resume and terminal_cache_root.exists():
        shutil.rmtree(terminal_cache_root)
    for path in (attempts_path, matches_path, source_shape_matches_path, events_path, runs_path):
        if config.resume:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        else:
            clean_jsonl(path)

    rows = collect_rows(config)
    inspected = 0
    skipped = 0
    skipped_boundary = 0
    skipped_no_candidate = 0
    succeeded = 0
    failed = 0
    resumed_terminal_attempts = 0
    resumed_successful_attempts = 0
    resumed_failed_attempts = 0
    pipeline = PluginPipeline(max_retries=max(1, config.max_retries), event_handler=jsonl_event_handler(events_path))
    pipeline.register(SourceCandidateGeneratorPlugin(), SourceCandidateObjdiffPlugin())

    for row in rows:
        if inspected >= config.limit:
            break
        if not strategy_allowed(row, config.strategies, {}):
            continue
        if compatible_candidate_count(row, config) == 0:
            skipped_no_candidate += 1
            continue
        if skipped < config.offset:
            skipped += 1
            continue
        if config.skip_boundary_suspect and is_boundary_suspect(row):
            skipped_boundary += 1
            continue
        inspected += 1
        terminal_key, terminal_key_payload = terminal_attempt_cache_key(row, config)
        cached_terminal = (
            load_terminal_attempt(terminal_cache_root, terminal_key, terminal_key_payload)
            if config.resume and terminal_key
            else None
        )
        if cached_terminal is not None:
            cached_result = cached_terminal.get("result") if isinstance(cached_terminal.get("result"), dict) else {}
            cached_success = cached_result.get("success") is True
            if not cached_success or restore_cached_proof_rows(
                cached_terminal,
                matches_path=matches_path,
                source_shape_matches_path=source_shape_matches_path,
            ):
                resumed_terminal_attempts += 1
                if cached_success:
                    succeeded += 1
                    resumed_successful_attempts += 1
                else:
                    failed += 1
                    resumed_failed_attempts += 1
                append_jsonl(
                    events_path,
                    {
                        "type": "terminal-attempt-cache-hit",
                        "cacheKey": terminal_key,
                        "functionName": row.get("name"),
                        "entry": row.get("entry"),
                        "success": cached_success,
                    },
                )
                continue

        attempt_offset = jsonl_size(attempts_path)
        match_offset = jsonl_size(matches_path)
        source_shape_match_offset = jsonl_size(source_shape_matches_path)
        result = pipeline.run_pipeline(
            prompt_path=str(row.get("source") or row.get("entry") or row.get("name") or ""),
            prompt_content="",
            function_name=str(row.get("name") or row.get("entry") or f"row_{inspected}"),
            target_object_path="",
            asm="",
            config={"schema": "agentdecompile.source-plugin-pipeline-config.v1"},
            initial_context={
                "sourceParityRow": row,
                "outDir": str(config.out_dir),
                "codeSliceMatchesPath": str(matches_path),
                "sourceShapeMatchesPath": str(source_shape_matches_path),
                "compiler": config.compiler,
                "clang": config.clang,
                "compilerProfiles": config.compiler_profiles,
                "inventory": str(config.inventory),
                "vcRoot": str(config.vc_root) if config.vc_root else None,
                "wine": config.wine,
                "wineprefix": str(config.wineprefix) if config.wineprefix else None,
                "timeout": config.timeout,
                "dryRun": config.dry_run,
                "semanticOnly": config.semantic_only,
                "sourceShapeSearch": config.source_shape_search,
                "routedPlaybook": config.routed_playbook,
                "workDir": str(config.work_dir) if config.work_dir else None,
                "maxVariantsPerFunction": config.max_variants_per_function,
                "targetSha256": config.target_sha,
                "strategies": sorted(config.strategies) if config.strategies else None,
                "sourceQualities": sorted(config.source_qualities) if config.source_qualities else None,
                "autonomyBudget": {
                    "maxFunctions": 1,
                    "maxAttemptsPerFunction": max(1, config.max_retries),
                },
            },
        )
        result_json = result.to_json()
        if terminal_key:
            result_json["terminalAttemptKey"] = terminal_key
        append_jsonl(runs_path, result_json)
        if result.success:
            succeeded += 1
        else:
            failed += 1
        if terminal_key:
            attempt_records = read_jsonl_tail(attempts_path, attempt_offset)
            proof_rows = [
                *tagged_proof_rows("code-slice", read_jsonl_tail(matches_path, match_offset)),
                *tagged_proof_rows("source-shape", read_jsonl_tail(source_shape_matches_path, source_shape_match_offset)),
            ]
            if terminal_result_is_cacheable(result_json, attempt_records, proof_rows):
                store_terminal_attempt(
                    terminal_cache_root,
                    terminal_key,
                    key_payload=terminal_key_payload,
                    result=result_json,
                    attempt_records=attempt_records,
                    proof_rows=proof_rows,
                )
        if config.progress_every and inspected % config.progress_every == 0:
            print(
                f"source-plugin-pipeline: inspected={inspected} succeeded={succeeded} failed={failed}",
                flush=True,
            )

    export = export_recovered_source([matches_path, source_shape_matches_path], out_dir=config.out_dir / "recovered-source", source_name="source_slices.c")
    raw_match_quality_counts = merge_counts(
        count_jsonl_values(matches_path, "sourceQuality"),
        count_jsonl_values(source_shape_matches_path, "sourceQuality", default="high-level-c"),
    )
    raw_match_scope_counts = merge_counts(
        count_jsonl_values(matches_path, "sourceRecoveryScope"),
        count_jsonl_values(source_shape_matches_path, "sourceRecoveryScope", default="whole-function"),
    )
    exported_quality_counts = count_manifest_function_values(Path(str(export.get("manifest") or "")), "sourceQuality", default="unknown")
    exported_scope_counts = count_manifest_function_values(Path(str(export.get("manifest") or "")), "sourceRecoveryScope", default="unknown")
    summary = {
        "schema": "agentdecompile.source-plugin-pipeline-summary.v1",
        "status": "generated-only" if config.dry_run else "complete",
        "outDir": str(config.out_dir),
        "queue": str(config.queue) if config.queue else None,
        "sourceTasks": [str(path) for path in config.source_tasks],
        "sourceTasksOnly": config.source_tasks_only,
        "attemptsPath": str(attempts_path),
        "codeSliceMatchesPath": str(matches_path),
        "sourceShapeMatchesPath": str(source_shape_matches_path),
        "eventsPath": str(events_path),
        "runsPath": str(runs_path),
        "totalInputRows": len(rows),
        "candidateEligibleFunctions": inspected + skipped,
        "candidateCoverageRatio": safe_ratio(inspected + skipped, len(rows)),
        "inspectedFunctions": inspected,
        "skippedEligibleFunctions": skipped,
        "skippedBoundarySuspectFunctions": skipped_boundary,
        "skippedNoCompatibleCandidateFunctions": skipped_no_candidate,
        "successfulFunctions": succeeded,
        "failedFunctions": failed,
        "resumedTerminalAttempts": resumed_terminal_attempts,
        "resumedSuccessfulAttempts": resumed_successful_attempts,
        "resumedFailedAttempts": resumed_failed_attempts,
        "terminalAttemptCacheDir": str(terminal_cache_root),
        "matchedBySourceQuality": exported_quality_counts,
        "matchedByRecoveryScope": exported_scope_counts,
        "rawMatchedBySourceQuality": raw_match_quality_counts,
        "rawMatchedByRecoveryScope": raw_match_scope_counts,
        "highLevelSourceMatches": exported_quality_counts.get("high-level-c", 0),
        "inlineAsmSourceMatches": exported_quality_counts.get("inline-asm-c", 0),
        "sourceShapeMatchedFunctions": sum(count_jsonl_values(source_shape_matches_path, "status").values()),
        "compiler": config.compiler,
        "compilerProfiles": [name for name, _flags in config.compiler_profiles],
        "compilerProfileSelection": "explicit" if config.compiler_profiles else "row-hints-then-defaults",
        "analysisBinarySha256": config.target_sha,
        "semanticOnly": config.semantic_only,
        "strategies": sorted(config.strategies) if config.strategies else None,
        "sourceQualityFilter": sorted(config.source_qualities) if config.source_qualities else None,
        "recoveredSourceExport": export,
        "claimBoundary": "Plugin pipeline emits source only for rows that compile and objdiff/byte-compare with zero differences; this is partial recovered source, not whole-program parity.",
    }
    write_json(config.out_dir / "summary.json", summary)
    return summary


def collect_rows(config: SourcePluginRunConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not config.source_tasks_only and config.queue is not None:
        rows.extend(iter_jsonl(config.queue))
    for source_tasks in config.source_tasks:
        rows.extend(iter_source_task_rows(source_tasks))
    if config.source_tasks:
        rows.sort(key=synthesis_row_priority)
    return rows


def compatible_candidate_count(row: dict[str, Any], config: SourcePluginRunConfig) -> int:
    return len(compatible_candidates(row, config))


def compatible_candidates(row: dict[str, Any], config: SourcePluginRunConfig) -> list[Any]:
    raw_candidates = append_packaged_fallback(
        generate(row, config.max_variants_per_function),
        packaged_source_candidate(row),
    )
    raw_candidates, _rule_filtered = filter_candidates_by_explicit_rule_strategies(raw_candidates, config.strategies)
    raw_candidates, _quality_filtered = filter_candidates_by_source_quality(raw_candidates, promotion_seed_qualities(config))
    candidates = compiler_compatible_candidates(row, raw_candidates, config.compiler, config.max_variants_per_function)
    if config.semantic_only:
        candidates = [candidate for candidate in candidates if candidate.semantic_source]
    return prioritize_candidates(candidates)


def terminal_attempt_cache_key(
    row: dict[str, Any],
    config: SourcePluginRunConfig,
) -> tuple[str | None, dict[str, Any]]:
    """Build a fail-closed resume key for one terminal plugin run."""

    # A live rewrite queue can change independently of the source-task row. Do
    # not cache those runs until the resolved rewrite itself is part of the key.
    if config.work_dir is not None:
        return None, {}
    target_slice_sha = target_slice_sha256(row)
    candidates = compatible_candidates(row, config)
    if not target_slice_sha or not candidates:
        return None, {}
    payload = {
        "schema": "agentdecompile.source-plugin-terminal-attempt-key.v1",
        "targetSliceSha256": target_slice_sha,
        "targetSha256": str(config.target_sha or row.get("targetSha256") or row.get("analysisBinarySha256") or ""),
        "entry": str(row.get("entry") or ""),
        "address": row.get("address"),
        "sources": [
            {
                "sha256": source_sha256(candidate.source),
                "rule": candidate.rule,
                "variant": candidate.variant,
                "suffix": candidate.source_suffix,
                "extraFlags": list(candidate.extra_flags),
                "semanticSource": bool(candidate.semantic_source),
            }
            for candidate in candidates
        ],
        "compiler": {
            "kind": config.compiler,
            "toolchain": compiler_toolchain_identity(config),
            "profiles": [
                {"name": name, "flags": list(flags)}
                for name, flags in config.compiler_profiles
            ],
            "rowProfileHints": row.get("compilerProfileHints"),
        },
        "inventorySha256": path_sha256(config.inventory),
        "configuration": {
            "dryRun": config.dry_run,
            "semanticOnly": config.semantic_only,
            "skipBoundarySuspect": config.skip_boundary_suspect,
            "sourceShapeSearch": config.source_shape_search,
            "routedPlaybook": config.routed_playbook,
            "maxVariantsPerFunction": config.max_variants_per_function,
            "maxRetries": config.max_retries,
            "timeout": config.timeout,
            "strategies": sorted(config.strategies) if config.strategies else None,
            "sourceQualities": sorted(config.source_qualities) if config.source_qualities else None,
        },
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest(), payload


def executable_identity(command: str) -> dict[str, Any]:
    resolved = shutil.which(command)
    return path_identity(Path(resolved) if resolved else Path(command))


def compiler_toolchain_identity(config: SourcePluginRunConfig) -> dict[str, Any]:
    if config.compiler != "msvc":
        return {"compiler": executable_identity(config.clang)}
    from .package_verify import resolve_msvc_root

    try:
        compiler = resolve_msvc_root(config.vc_root).expanduser().resolve() / "bin" / "cl.exe"
    except (OSError, RuntimeError, ValueError):
        compiler = (config.vc_root.expanduser().resolve() / "bin" / "cl.exe") if config.vc_root else Path("cl.exe")
    return {
        "compiler": path_identity(compiler),
        "wine": executable_identity(config.wine),
        "wineprefix": str(config.wineprefix.expanduser().resolve()) if config.wineprefix else None,
    }


def path_identity(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    try:
        stat = resolved.stat()
    except OSError:
        return {"path": str(resolved), "unavailable": True}
    return {"path": str(resolved), "size": stat.st_size, "mtimeNs": stat.st_mtime_ns}


def path_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def terminal_cache_path(cache_root: Path, key: str) -> Path:
    return cache_root / f"{key}.json"


def load_terminal_attempt(
    cache_root: Path,
    key: str,
    key_payload: dict[str, Any],
) -> dict[str, Any] | None:
    path = terminal_cache_path(cache_root, key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != TERMINAL_ATTEMPT_CACHE_SCHEMA:
        return None
    if payload.get("cacheKey") != key or payload.get("key") != key_payload:
        return None
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
        return None
    if result.get("success") is True:
        proof_rows = payload.get("proofRows")
        if not isinstance(proof_rows, list) or not proof_rows:
            return None
        source_shas = {str(row.get("sha256") or "") for row in key_payload.get("sources") or []}
        target_sha = str(key_payload.get("targetSha256") or "")
        if not all(valid_cached_proof(item, source_shas=source_shas, target_sha=target_sha) for item in proof_rows):
            return None
    return payload


def valid_cached_proof(item: Any, *, source_shas: set[str], target_sha: str) -> bool:
    if not isinstance(item, dict) or item.get("kind") not in {"code-slice", "source-shape"}:
        return False
    row = item.get("row")
    if not isinstance(row, dict) or not is_proven_zero(row):
        return False
    row_source_sha = str(row.get("sourceSha256") or "")
    if not row_source_sha or row_source_sha not in source_shas:
        return False
    row_target_sha = str(row.get("targetSha256") or row.get("analysisBinarySha256") or "")
    if target_sha and row_target_sha != target_sha:
        return False
    source_path = Path(str(row.get("source") or ""))
    return source_path.is_file() and path_sha256(source_path) == row_source_sha


def terminal_result_is_cacheable(
    result: dict[str, Any],
    attempt_records: list[dict[str, Any]],
    proof_rows: list[dict[str, Any]],
) -> bool:
    if result.get("success") is True:
        return bool(proof_rows) and all(
            isinstance(item.get("row"), dict) and is_proven_zero(item["row"])
            for item in proof_rows
        )
    if not attempt_records:
        return False
    deterministic_statuses = {"mismatched", "compile-failed", "slice-failed", "generated-only"}
    return all(str(row.get("status") or "") in deterministic_statuses for row in attempt_records)


def store_terminal_attempt(
    cache_root: Path,
    key: str,
    *,
    key_payload: dict[str, Any],
    result: dict[str, Any],
    attempt_records: list[dict[str, Any]],
    proof_rows: list[dict[str, Any]],
) -> None:
    atomic_write_json(
        terminal_cache_path(cache_root, key),
        {
            "schema": TERMINAL_ATTEMPT_CACHE_SCHEMA,
            "cacheKey": key,
            "key": key_payload,
            "result": result,
            "attemptRecords": attempt_records,
            "proofRows": proof_rows,
            "claimBoundary": "cached terminal attempts reuse only an exact target-slice/source/toolchain/configuration key; cached proof rows remain bounded objdiff-zero receipts",
        },
    )


def jsonl_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def read_jsonl_tail(path: Path, offset: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    return rows


def tagged_proof_rows(kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"kind": kind, "row": row} for row in rows if is_proven_zero(row)]


def restore_cached_proof_rows(
    payload: dict[str, Any],
    *,
    matches_path: Path,
    source_shape_matches_path: Path,
) -> bool:
    proof_rows = payload.get("proofRows")
    if not isinstance(proof_rows, list) or not proof_rows:
        return False
    existing = {
        "code-slice": canonical_jsonl_rows(matches_path),
        "source-shape": canonical_jsonl_rows(source_shape_matches_path),
    }
    destinations = {"code-slice": matches_path, "source-shape": source_shape_matches_path}
    for item in proof_rows:
        kind = str(item.get("kind") or "") if isinstance(item, dict) else ""
        row = item.get("row") if isinstance(item, dict) else None
        if kind not in destinations or not isinstance(row, dict) or not is_proven_zero(row):
            return False
        serialized = json.dumps(row, sort_keys=True)
        if serialized not in existing[kind]:
            append_jsonl(destinations[kind], row)
            existing[kind].add(serialized)
    return True


def canonical_jsonl_rows(path: Path) -> set[str]:
    return {json.dumps(row, sort_keys=True) for row in read_jsonl_tail(path, 0)}


def jsonl_event_handler(path: Path):
    def emit(event: dict[str, Any]) -> None:
        append_jsonl(path, event)

    return emit


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def count_jsonl_values(path: Path, key: str, *, default: str = "unknown") -> dict[str, int]:
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            value = str(row.get(key) or default)
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def count_manifest_function_values(path: Path, key: str, *, default: str = "unknown") -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    counts: dict[str, int] = {}
    for row in manifest.get("functions") or []:
        if not isinstance(row, dict):
            continue
        value = str(row.get(key) or default)
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def promotion_seed_qualities(config: SourcePluginRunConfig) -> set[str] | None:
    if not config.source_shape_search or not config.source_qualities or "high-level-c" not in config.source_qualities:
        return config.source_qualities
    return set(config.source_qualities) | {"inline-asm-c"}


def merge_counts(*items: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            merged[key] = merged.get(key, 0) + value
    return dict(sorted(merged.items()))


def parse_csv_set(value: str | None) -> set[str] | None:
    if not value:
        return None
    parsed = {item.strip() for item in value.split(",") if item.strip()}
    return parsed or None


def parse_profile_values(values: list[str]) -> list[tuple[str, list[str]]]:
    return [parse_profile_flag_set(value) for value in values if value.strip()]


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)
