"""Batch runner for the upstream-style source recovery plugin pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from .plugin_pipeline import PluginPipeline
from .compile_cache import target_slice_sha256
from .match_cache import source_sha256
from .source_export import export_recovered_source
from .source_parity_synthesize import (
    apply_diagnostic_priorities,
    append_packaged_fallback,
    clean_jsonl,
    compiler_compatible_candidates,
    filter_candidates_by_explicit_rule_strategies,
    filter_candidates_by_source_quality,
    generate,
    is_boundary_suspect,
    load_diagnostic_priority_states,
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
from . import rewrite_queue
from .state import atomic_write_json


TERMINAL_ATTEMPT_CACHE_SCHEMA = "agentdecompile.source-plugin-terminal-attempt.v2"


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
    bind_unlabeled_source_tasks_to_target: bool = False
    diagnostic_priority_states: list[Path] = field(default_factory=list)
    diagnostic_cache_root: Path | None = None
    resume: bool = False
    force_fresh: bool = False


def run_source_plugin_pipeline(config: SourcePluginRunConfig) -> dict[str, Any]:
    if config.clean and config.resume:
        raise ValueError("source plugin pipeline cannot combine clean and resume")
    if config.bind_unlabeled_source_tasks_to_target and not (
        config.source_tasks_only and config.source_tasks and config.target_sha
    ):
        raise ValueError(
            "source-task-target-binding-requires-source-tasks-only-and-verified-target-sha256"
        )
    resolved_out_dir = config.out_dir.expanduser().resolve()
    diagnostic_cache_root = config.diagnostic_cache_root or (config.out_dir.parent / "compile-diagnostic-cache")
    resolved_diagnostic_cache_root = diagnostic_cache_root.expanduser().resolve()
    if resolved_diagnostic_cache_root == resolved_out_dir or resolved_out_dir in resolved_diagnostic_cache_root.parents:
        if config.diagnostic_cache_root is not None:
            raise ValueError("diagnostic-cache-root-must-be-outside-cleanable-output-directory")
        diagnostic_cache_root = resolved_out_dir.parent / "compile-diagnostic-cache"
        resolved_diagnostic_cache_root = diagnostic_cache_root.resolve()
        if resolved_diagnostic_cache_root == resolved_out_dir or resolved_out_dir in resolved_diagnostic_cache_root.parents:
            raise ValueError("diagnostic-cache-root-must-be-outside-cleanable-output-directory")
    diagnostic_cache_root = resolved_diagnostic_cache_root
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
    diagnostic_priority_metadata: list[dict[str, Any]] = []
    diagnostic_priority_hint_count = 0
    diagnostic_priority_matches = 0
    if config.diagnostic_priority_states:
        if not config.target_sha:
            raise ValueError("diagnostic-priority-state-requires-verified-target-sha256")
        diagnostic_hints, diagnostic_priority_metadata = load_diagnostic_priority_states(
            config.diagnostic_priority_states,
            config.target_sha,
        )
        diagnostic_priority_hint_count = len(diagnostic_hints)
        # The recovery pipeline may opt in for its own source-task-only input:
        # those tasks were emitted from this run's verified target image.
        # General plugin invocations must never infer that association.
        if config.bind_unlabeled_source_tasks_to_target:
            for row in rows:
                if row.get("sourceTask") is True and not (
                    row.get("targetSha256") or row.get("analysisBinarySha256")
                ):
                    row["targetSha256"] = config.target_sha
        diagnostic_priority_matches = apply_diagnostic_priorities(
            rows,
            diagnostic_hints,
            config.target_sha,
        )
        rows.sort(key=synthesis_row_priority)
    inspected = 0
    skipped = 0
    skipped_boundary = 0
    skipped_no_candidate = 0
    succeeded = 0
    failed = 0
    resumed_terminal_attempts = 0
    resumed_successful_attempts = 0
    resumed_failed_attempts = 0
    compile_diagnostic_cache_hits = 0
    pipeline_stop: dict[str, Any] = {}

    def handle_pipeline_event(event: dict[str, Any]) -> None:
        append_jsonl(events_path, event)
        if event.get("type") == "autonomy-stop" and event.get("code") == "toolchain-launch-failed":
            pipeline_stop.update({
                "code": event["code"],
                "reason": event.get("reason"),
                "attemptNumber": event.get("attemptNumber"),
            })

    pipeline = PluginPipeline(max_retries=max(1, config.max_retries), event_handler=handle_pipeline_event)
    pipeline.register(SourceCandidateGeneratorPlugin(), SourceCandidateObjdiffPlugin())
    stopped_after_row: int | None = None

    for row_index, row in enumerate(rows):
        if inspected >= config.limit:
            break
        if not strategy_allowed(row, config.strategies, {}):
            continue
        candidates, rule_filtered, quality_filtered = prepare_compatible_candidates(row, config)
        if not candidates:
            skipped_no_candidate += 1
            continue
        if skipped < config.offset:
            skipped += 1
            continue
        if config.skip_boundary_suspect and is_boundary_suspect(row):
            skipped_boundary += 1
            continue
        inspected += 1
        terminal_key, terminal_key_payload = terminal_attempt_cache_key(row, config, candidates=candidates)
        if config.resume and not config.force_fresh and terminal_key:
            queue_guard = (
                rewrite_queue.locked_rewrite_queue_snapshot(config.work_dir.expanduser().resolve())
                if config.work_dir is not None
                else nullcontext(None)
            )
            with queue_guard as queue:
                if queue is None or rewrite_queue_snapshot_matches(queue, terminal_key_payload):
                    cached_terminal = load_terminal_attempt(
                        terminal_cache_root, terminal_key, terminal_key_payload
                    )
                    if cached_terminal is not None:
                        cached_result = cached_terminal.get("result") if isinstance(cached_terminal.get("result"), dict) else {}
                        # The v2 terminal cache stores mismatches only. Positive
                        # proof rows are never replayed as fresh compiler work.
                        resumed_terminal_attempts += 1
                        failed += 1
                        resumed_failed_attempts += 1
                        append_jsonl(
                            events_path,
                            {
                                "type": "terminal-attempt-cache-hit",
                                "cacheKey": terminal_key,
                                "functionName": row.get("name"),
                                "entry": row.get("entry"),
                                "success": False,
                                "reusedStatus": cached_result.get("status"),
                                "reuseOnly": True,
                                "compilerInvoked": False,
                                "freshProofProduced": False,
                            },
                        )
                        continue

        attempt_offset = jsonl_size(attempts_path)
        pipeline_stop.clear()
        result = pipeline.run_pipeline(
            prompt_path=str(row.get("source") or row.get("entry") or row.get("name") or ""),
            prompt_content="",
            function_name=str(row.get("name") or row.get("entry") or f"row_{inspected}"),
            target_object_path="",
            asm="",
            config={"schema": "agentdecompile.source-plugin-pipeline-config.v1"},
            initial_context={
                "sourceParityRow": row,
                "preparedSourceParityCandidates": candidates,
                "preparedCandidateFilterCounts": {
                    "filteredByExplicitRuleStrategies": rule_filtered,
                    "filteredBySourceQuality": quality_filtered,
                },
                "preparedCandidateSourceShapeSearch": config.source_shape_search,
                "outDir": str(config.out_dir),
                "diagnosticCacheRoot": str(diagnostic_cache_root),
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
        compile_diagnostic_cache_hits += sum_json_values(result_json, "compileDiagnosticCacheHits")
        if terminal_key:
            result_json["terminalAttemptKey"] = terminal_key
        append_jsonl(runs_path, result_json)
        if result.success:
            succeeded += 1
        else:
            failed += 1
        if terminal_key:
            attempt_records = read_jsonl_tail(attempts_path, attempt_offset)
            if terminal_result_is_cacheable(result_json, attempt_records):
                store_terminal_attempt(
                    terminal_cache_root,
                    terminal_key,
                    key_payload=terminal_key_payload,
                    result=result_json,
                    attempt_records=attempt_records,
                )
        if config.progress_every and inspected % config.progress_every == 0:
            print(
                f"source-plugin-pipeline: inspected={inspected} succeeded={succeeded} failed={failed}",
                flush=True,
            )
        if pipeline_stop:
            stopped_after_row = row_index
            pipeline_stop["stoppedAfterInputRow"] = {
                "index": row_index,
                "functionName": row.get("name"),
                "entry": row.get("entry"),
                "source": row.get("source"),
                "targetSha256": row.get("targetSha256") or row.get("analysisBinarySha256"),
            }
            break

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
        "status": (
            "generated-only" if config.dry_run else
            "paused-toolchain-launch-failure" if pipeline_stop else
            "complete"
        ),
        "pipelineStop": dict(pipeline_stop) if pipeline_stop else None,
        "unvisitedInputRows": (
            len(rows) - stopped_after_row - 1
            if stopped_after_row is not None
            else 0
        ),
        "unvisitedInputRowsMeaning": (
            "Raw rows after the early stop; includes rows that later filters could have skipped."
            if stopped_after_row is not None
            else None
        ),
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
        "compileDiagnosticCacheHits": compile_diagnostic_cache_hits,
        "terminalAttemptCacheDir": str(terminal_cache_root),
        "compileDiagnosticCacheDir": str(diagnostic_cache_root),
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
        **(
            {
                "diagnosticPriorityStates": diagnostic_priority_metadata,
                "diagnosticPriorityHintCount": diagnostic_priority_hint_count,
                "diagnosticPriorityMatchedRows": diagnostic_priority_matches,
                "diagnosticPriorityClaim": (
                    "Scheduling hints only; historical rows are never accepted, cached, or substituted "
                    "for fresh compiler and objdiff evidence."
                ),
            }
            if config.diagnostic_priority_states
            else {}
        ),
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


def compatible_candidates(row: dict[str, Any], config: SourcePluginRunConfig) -> list[Any]:
    return prepare_compatible_candidates(row, config)[0]


def prepare_compatible_candidates(
    row: dict[str, Any], config: SourcePluginRunConfig
) -> tuple[list[Any], int, int]:
    raw_candidates = append_packaged_fallback(
        generate(row, config.max_variants_per_function),
        packaged_source_candidate(row),
    )
    raw_candidates, rule_filtered = filter_candidates_by_explicit_rule_strategies(raw_candidates, config.strategies)
    raw_candidates, quality_filtered = filter_candidates_by_source_quality(
        raw_candidates, promotion_seed_qualities(config)
    )
    candidates = compiler_compatible_candidates(row, raw_candidates, config.compiler, config.max_variants_per_function)
    if config.semantic_only:
        candidates = [candidate for candidate in candidates if candidate.semantic_source]
    return prioritize_candidates(candidates), rule_filtered, quality_filtered


def terminal_attempt_cache_key(
    row: dict[str, Any],
    config: SourcePluginRunConfig,
    *,
    candidates: list[Any] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Build a fail-closed resume key for one terminal plugin run."""
    target_slice_sha = target_slice_sha256(row)
    candidates = candidates if candidates is not None else compatible_candidates(row, config)
    if not target_slice_sha or not candidates:
        return None, {}

    # Rewrite requests are keyed by the exact candidate source and can be
    # fulfilled independently of the source-task row. Include the current
    # candidate-specific queue entry in the resume identity, and fail closed
    # while a candidate has work in flight. A later queue mutation therefore
    # cannot silently reuse the result from an earlier state.
    rewrite_entries: list[dict[str, Any]] = []
    if config.work_dir is not None:
        work_dir = config.work_dir.expanduser().resolve()
        try:
            queue = rewrite_queue.read_rewrite_queue_for_cache(work_dir)
        except (OSError, ValueError, TypeError):
            return None, {}
        for candidate in candidates:
            request_id = rewrite_queue.derive_request_id(
                str(row.get("name") or ""), str(candidate.source)
            )
            raw_entry = queue["entries"].get(request_id)
            if request_id in queue["entries"] and not isinstance(raw_entry, dict):
                return None, {}
            entry = dict(raw_entry) if isinstance(raw_entry, dict) else None
            if entry is not None:
                if entry.get("status") in {rewrite_queue.STATUS_PENDING, rewrite_queue.STATUS_CLAIMED}:
                    return None, {}
                if entry.get("status") not in {rewrite_queue.STATUS_COMPLETED, rewrite_queue.STATUS_FAILED}:
                    return None, {}
            rewrite_entries.append(
                {
                    "requestId": request_id,
                    "entrySha256": canonical_value_sha256(entry) if entry is not None else None,
                }
            )

    # The diagnostic cache has a bounded content-hashed toolchain identity,
    # including compiler components, objdiff, package adapter, and the shared
    # recovered-C preamble implementation. Reuse it rather than relying on
    # file mtimes for terminal compiler/objdiff results. If it cannot establish
    # that identity, terminal reuse is disabled.
    from .source_plugins import diagnostic_cache_toolchain_identity

    toolchain_identities: list[dict[str, str]] = []
    for candidate in candidates:
        identity = diagnostic_cache_toolchain_identity(
            row,
            candidate,
            compiler=config.compiler,
            compiler_profiles=config.compiler_profiles,
            vc_root=config.vc_root,
            wine=config.wine,
            wineprefix=config.wineprefix,
            source_shape_search=config.source_shape_search,
        )
        if identity is None:
            return None, {}
        toolchain_identities.append(
            {
                "candidateSourceSha256": source_sha256(candidate.source),
                "identitySha256": identity,
            }
        )

    row_material = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    payload = {
        "schema": "agentdecompile.source-plugin-terminal-attempt-key.v2",
        "targetSliceSha256": target_slice_sha,
        "targetSha256": str(config.target_sha or row.get("targetSha256") or row.get("analysisBinarySha256") or ""),
        "rowIdentitySha256": hashlib.sha256(row_material.encode("utf-8")).hexdigest(),
        "entry": str(row.get("entry") or ""),
        "address": row.get("address"),
        "workDir": str(config.work_dir.expanduser().resolve()) if config.work_dir else None,
        "rewriteEntries": rewrite_entries,
        "contentHashedToolchainIdentities": toolchain_identities,
        "sources": [
            {
                "sha256": source_sha256(candidate.source),
                "rule": candidate.rule,
                "variant": candidate.variant,
                "suffix": candidate.source_suffix,
                "symbol": candidate.symbol,
                "cName": candidate.c_name,
                "callingConvention": candidate.callconv,
                "returnType": candidate.return_type,
                "evidenceSha256": canonical_value_sha256(candidate.evidence),
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


def canonical_value_sha256(value: Any) -> str:
    """Hash a JSON-compatible identity value with stable fallback encoding."""
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def rewrite_queue_snapshot_matches(queue: dict[str, Any], key_payload: dict[str, Any]) -> bool:
    """Revalidate every candidate-specific queue entry while its lock is held."""

    entries = queue.get("entries")
    expected = key_payload.get("rewriteEntries")
    if not isinstance(entries, dict) or not isinstance(expected, list):
        return False
    for item in expected:
        if not isinstance(item, dict) or not isinstance(item.get("requestId"), str):
            return False
        request_id = item["requestId"]
        raw_entry = entries.get(request_id)
        if request_id in entries and not isinstance(raw_entry, dict):
            return False
        current_sha = canonical_value_sha256(raw_entry) if isinstance(raw_entry, dict) else None
        if current_sha != item.get("entrySha256"):
            return False
        if isinstance(raw_entry, dict) and raw_entry.get("status") not in {
            rewrite_queue.STATUS_COMPLETED,
            rewrite_queue.STATUS_FAILED,
        }:
            return False
    return True


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
    # Positive cache reuse is intentionally disabled. Match JSONL is consumed
    # independently of the event stream, so replaying its old rows can imply a
    # fresh compiler receipt.
    if result.get("success") is True:
        return None
    attempt_records = payload.get("attemptRecords")
    if not isinstance(attempt_records, list) or not terminal_result_is_cacheable(result, attempt_records):
        return None
    return payload


def terminal_result_is_cacheable(
    result: dict[str, Any],
    attempt_records: list[dict[str, Any]],
) -> bool:
    if result.get("success") is not False or not attempt_records:
        return False
    # Cache only a conclusive candidate/object mismatch. Broad statuses like
    # compile-failed, slice-failed, and generated-only include launch failures,
    # timeouts, preparation errors, and dry runs that must remain retryable.
    return all(
        isinstance(row, dict)
        and row.get("status") == "mismatched"
        and row.get("candidateCompileInvoked") is True
        and isinstance(row.get("candidateCompile"), dict)
        and row["candidateCompile"].get("status") == "ok"
        and row["candidateCompile"].get("compilerInvoked") is True
        and isinstance(row.get("targetCompile"), dict)
        and row["targetCompile"].get("status") == "ok"
        and type(row.get("objdiffExit")) is int
        and row.get("objdiffExit") == 0
        and type(row.get("differences")) is int
        and row.get("differences") > 0
        and not row.get("fallback")
        and not row.get("diagnosticFallback")
        for row in attempt_records
    )


def store_terminal_attempt(
    cache_root: Path,
    key: str,
    *,
    key_payload: dict[str, Any],
    result: dict[str, Any],
    attempt_records: list[dict[str, Any]],
) -> None:
    atomic_write_json(
        terminal_cache_path(cache_root, key),
        {
            "schema": TERMINAL_ATTEMPT_CACHE_SCHEMA,
            "cacheKey": key,
            "key": key_payload,
            "result": result,
            "attemptRecords": attempt_records,
            "claimBoundary": "reused terminal entries record only completed candidate compiler and objdiff mismatches; they are not match receipts or fresh proof",
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


def jsonl_event_handler(path: Path):
    def emit(event: dict[str, Any]) -> None:
        append_jsonl(path, event)

    return emit


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def sum_json_values(value: Any, key: str) -> int:
    if isinstance(value, dict):
        own = value.get(key)
        return (own if isinstance(own, int) and not isinstance(own, bool) else 0) + sum(
            sum_json_values(child, key) for name, child in value.items() if name != key
        )
    if isinstance(value, list):
        return sum(sum_json_values(child, key) for child in value)
    return 0


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
