"""Concrete source-recovery plugins for the Python plugin pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import shutil

from dataclasses import replace
from pathlib import Path
from typing import Any

from . import rewrite_queue
from .mismatch_classify import enrich_attempt_records, routed_playbook_for_class, write_mismatch_class_last
from .objdiff_verification import is_objdiff_match
from .plugin_pipeline import PluginResult, now_ms
from .source_export import export_recovered_source
from .source_parity_synthesize import (
    GeneratedCandidate,
    append_packaged_fallback,
    attempt_candidate,
    compiler_compatible_candidates,
    filter_candidates_by_explicit_rule_strategies,
    filter_candidates_by_source_quality,
    generate,
    generated_candidate_source_quality,
    matched_source_shape_record,
    packaged_source_candidate,
    pending_rewrite_variant,
    prioritize_candidates,
    resolve_profiles,
)


class SourceCandidateGeneratorPlugin:
    id = "source-candidate-generator"
    name = "Source Candidate Generator"
    description = "Generate and select semantic source candidates for a bounded target slice."

    def execute(self, context: dict[str, Any]) -> tuple[PluginResult, dict[str, Any]]:
        start = now_ms()
        row = context.get("sourceParityRow")
        if not isinstance(row, dict):
            return failure(self, start, "sourceParityRow missing from context"), context
        compiler = str(context.get("compiler") or "msvc")
        max_variants = int(context.get("maxVariantsPerFunction") or 8)
        prepared_candidates = context.get("preparedSourceParityCandidates")
        prepared_filter_counts = context.get("preparedCandidateFilterCounts")
        prepared_filter_counts = prepared_filter_counts if isinstance(prepared_filter_counts, dict) else {}
        rule_count = prepared_filter_counts.get("filteredByExplicitRuleStrategies")
        quality_count = prepared_filter_counts.get("filteredBySourceQuality")
        counts_valid = all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (rule_count, quality_count)
        )
        can_reuse_prepared = (
            isinstance(prepared_candidates, list)
            and bool(prepared_candidates)
            and counts_valid
            and context.get("preparedCandidateSourceShapeSearch") is bool(context.get("sourceShapeSearch"))
            and all(isinstance(candidate, GeneratedCandidate) for candidate in prepared_candidates)
        )
        if can_reuse_prepared:
            candidates = prepared_candidates
            rule_filtered = rule_count
            quality_filtered = quality_count
            candidate_set_reused = True
        else:
            raw_candidates = append_packaged_fallback(
                generate(row, max_variants),
                packaged_source_candidate(row),
            )
            strategies = normalize_filter_set(context.get("strategies"))
            raw_candidates, rule_filtered = filter_candidates_by_explicit_rule_strategies(raw_candidates, strategies)
            source_qualities = normalize_filter_set(context.get("sourceQualities"))
            effective_source_qualities = promotion_seed_qualities(source_qualities, bool(context.get("sourceShapeSearch")))
            raw_candidates, quality_filtered = filter_candidates_by_source_quality(raw_candidates, effective_source_qualities)
            candidates = compiler_compatible_candidates(row, raw_candidates, compiler, max_variants)
            if context.get("semanticOnly"):
                candidates = [candidate for candidate in candidates if candidate.semantic_source]
            candidates = prioritize_candidates(candidates)
            candidate_set_reused = False
        updated = dict(context)
        updated["preparedSourceParityCandidates"] = candidates
        updated["preparedCandidateFilterCounts"] = {
            "filteredByExplicitRuleStrategies": rule_filtered,
            "filteredBySourceQuality": quality_filtered,
        }
        updated["preparedCandidateSourceShapeSearch"] = bool(context.get("sourceShapeSearch"))
        index = int(context.get("sourceCandidateIndex") or 0)
        if index >= len(candidates):
            return failure(
                self,
                start,
                f"no source candidate at index {index}; generated {len(candidates)} compatible candidate(s)",
                {"generatedCandidates": len(candidates), "candidateIndex": index},
            ), updated
        selected = candidates[index]
        updated["sourceParityCandidates"] = candidates
        updated["selectedSourceCandidate"] = selected
        return (
            PluginResult(
                self.id,
                self.name,
                "success",
                now_ms() - start,
                data={
                    "generatedCandidates": len(candidates),
                    "candidateIndex": index,
                    "rule": selected.rule,
                    "variant": selected.variant,
                    "sourceQuality": generated_candidate_source_quality(selected),
                    "semanticSource": selected.semantic_source,
                    "filteredByExplicitRuleStrategies": rule_filtered,
                    "filteredBySourceQuality": quality_filtered,
                    "candidateSetReused": candidate_set_reused,
                },
            ),
            updated,
        )

    def prepare_retry(
        self,
        context: dict[str, Any],
        _previous_attempts: list[dict[str, PluginResult]],
    ) -> dict[str, Any]:
        updated = dict(context)
        if updated.get("autonomyStop"):
            return updated
        policy = updated.get("autonomousPolicy") if isinstance(updated.get("autonomousPolicy"), dict) else {}
        action = str(policy.get("action") or "")
        # Only advance the candidate index when policy asks for another generated shape.
        bump_actions = {
            "try-next-generated-candidate",
            "try-nearby-source-shape-or-permuter",
            "regenerate-source-shape",
            "",
        }
        if action == "try-nearby-source-shape-or-permuter":
            updated["sourceShapeSearch"] = True
            routed = policy.get("routedPlaybook") or routed_playbook_for_class(policy.get("mismatchClass"))
            if routed:
                updated["routedPlaybook"] = routed
        if action in bump_actions:
            updated["sourceCandidateIndex"] = int(updated.get("sourceCandidateIndex") or 0) + 1
        return updated


class SourceCandidateObjdiffPlugin:
    id = "source-candidate-objdiff"
    name = "Source Candidate Objdiff"
    description = "Compile selected generated source and objdiff it against the bounded target slice."

    def execute(self, context: dict[str, Any]) -> tuple[PluginResult, dict[str, Any]]:
        start = now_ms()
        row = context.get("sourceParityRow")
        candidate = context.get("selectedSourceCandidate")
        if not isinstance(row, dict):
            return failure(self, start, "sourceParityRow missing from context"), context
        if candidate is None:
            return failure(self, start, "selectedSourceCandidate missing from context"), context
        out_dir = Path(str(context.get("outDir") or "target/plugin-source-pipeline"))
        work_dir_value = context.get("workDir")
        pending_rewrite_result: dict[str, Any] | None = None
        rewrite_request_id: str | None = None
        if work_dir_value:
            rewrite_request_id = rewrite_queue.derive_request_id(
                str(row.get("name") or ""), str(getattr(candidate, "source", "") or "")
            )
            pending_rewrite_result = rewrite_queue.find_entry(Path(str(work_dir_value)), rewrite_request_id)
        rewrite_variant = pending_rewrite_variant(row, candidate, pending_rewrite_result)
        if rewrite_variant is not None:
            # Queue metadata is advisory. Keep the locally selected symbol,
            # calling convention, compiler flags, and proof scope.
            candidate = replace(
                candidate,
                source=rewrite_variant["source"],
                source_suffix=".c",
                variant=f"{candidate.variant}-rewrite-request",
                evidence={**candidate.evidence, "rewriteRequestId": rewrite_request_id},
            )
        cache_toolchain_identity = diagnostic_cache_toolchain_identity(
            row,
            candidate,
            compiler=str(context.get("compiler") or "msvc"),
            compiler_profiles=list(context.get("compilerProfiles") or []),
            vc_root=Path(str(context["vcRoot"])) if context.get("vcRoot") else None,
            wine=str(context.get("wine") or "wine"),
            wineprefix=Path(str(context["wineprefix"])) if context.get("wineprefix") else None,
            source_shape_search=bool(context.get("sourceShapeSearch")) and rewrite_variant is None,
        )
        records = attempt_candidate(
            row,
            candidate,
            out_dir,
            compiler=str(context.get("compiler") or "msvc"),
            clang=str(context.get("clang") or "clang"),
            compiler_profiles=list(context.get("compilerProfiles") or []),
            inventory=Path(str(context.get("inventory") or "target/binary-unpack/facts/function-inventory.jsonl")),
            vc_root=Path(str(context["vcRoot"])) if context.get("vcRoot") else None,
            wine=str(context.get("wine") or "wine"),
            wineprefix=Path(str(context["wineprefix"])) if context.get("wineprefix") else None,
            timeout=int(context.get("timeout") or 120),
            dry_run=bool(context.get("dryRun")),
            source_shape_search=bool(context.get("sourceShapeSearch")) and rewrite_variant is None,
            cache_toolchain_identity=cache_toolchain_identity,
            diagnostic_cache_root=Path(str(context["diagnosticCacheRoot"]))
            if context.get("diagnosticCacheRoot")
            else None,
        )
        target_sha = str(
            context.get("targetSha256")
            or row.get("targetSha256")
            or row.get("analysisBinarySha256")
            or ""
        ).strip()
        if target_sha:
            for record in records:
                if isinstance(record, dict) and not record.get("targetSha256"):
                    record["targetSha256"] = target_sha
        enrich_attempt_records(records, row if isinstance(row, dict) else None)
        toolchain_not_invoked = bool(records) and all(
            (
                record.get("status") == "compile-failed"
                and record.get("candidateCompileInvoked") is False
                and isinstance(record.get("candidateCompile"), dict)
                and record["candidateCompile"].get("compilerInvoked") is False
            )
            or (
                record.get("status") == "slice-failed"
                and record.get("toolchainLaunchFailure") is True
            )
            for record in records
        )
        profile_sweep_stopped_before_invocation = any(
            isinstance(record, dict)
            and record.get("candidateCompileInvoked") is False
            and isinstance(record.get("profileSweepStopped"), dict)
            and record["profileSweepStopped"].get("reason") == "compiler-not-invoked"
            for record in records
        )
        if toolchain_not_invoked or profile_sweep_stopped_before_invocation:
            # This is a toolchain/launcher readiness failure, not a source
            # mismatch. Trying another generated source candidate or MSVC flag
            # profile cannot repair Wine/prefix/compiler startup.
            updated["autonomyStop"] = True
            updated["autonomyStopCode"] = "toolchain-launch-failed"
            updated["autonomyStopReason"] = (
                "compiler or target-assembler launcher failed before invocation; resolve the toolchain environment before retrying"
            )
        matches = [
            record
            for record in records
            if is_objdiff_match(record)
        ]
        output_source_qualities = normalize_filter_set(context.get("sourceQualities"))
        exportable_matches = [
            record
            for record in matches
            if output_source_qualities is None or str(record.get("sourceQuality") or "") in output_source_qualities
        ]
        source_shape_matches = []
        for record in records:
            search_path = record.get("sourceShapeSearch")
            if search_path:
                source_shape_record = matched_source_shape_record(record, str(search_path))
                if source_shape_record is not None:
                    source_shape_matches.append(source_shape_record)
        best_difference = min((int(record.get("differences", 999999)) for record in records), default=999999)
        latest_record = records[-1] if records else {}
        diagnostic_cache_hits = sum(
            1
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("candidateCompile"), dict)
            and record["candidateCompile"].get("diagnosticCacheHit") is True
        )
        attempts_path = out_dir / "plugin-attempts.jsonl"
        out_dir.mkdir(parents=True, exist_ok=True)
        with attempts_path.open("a", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        if latest_record.get("mismatchClass"):
            if work_dir_value:
                write_mismatch_class_last(
                    Path(str(work_dir_value)),
                    function_name=str(row.get("name") or ""),
                    classification=latest_record,
                    routed_playbook=str(latest_record.get("routedPlaybook") or routed_playbook_for_class(latest_record.get("mismatchClass"))),
                )
        match_rows_path = Path(str(context.get("codeSliceMatchesPath"))) if context.get("codeSliceMatchesPath") else None
        if match_rows_path is not None and exportable_matches:
            match_rows_path.parent.mkdir(parents=True, exist_ok=True)
            with match_rows_path.open("a", encoding="utf-8") as fh:
                for record in exportable_matches:
                    fh.write(json.dumps(record, sort_keys=True) + "\n")
        source_shape_rows_path = Path(str(context.get("sourceShapeMatchesPath"))) if context.get("sourceShapeMatchesPath") else None
        if source_shape_rows_path is not None and source_shape_matches:
            source_shape_rows_path.parent.mkdir(parents=True, exist_ok=True)
            with source_shape_rows_path.open("a", encoding="utf-8") as fh:
                for record in source_shape_matches:
                    fh.write(json.dumps(record, sort_keys=True) + "\n")
        updated = dict(context)
        updated["sourceParityAttemptRecords"] = records
        updated["sourceParityMatchRecords"] = exportable_matches
        updated["sourceShapeMatchRecords"] = source_shape_matches
        updated["sourceParityAttemptsPath"] = str(attempts_path)
        status = "success" if exportable_matches or source_shape_matches else "failure"
        if (
            work_dir_value
            and rewrite_request_id
            and pending_rewrite_result is not None
            and pending_rewrite_result.get("status") in {"completed", "failed"}
            and not context.get("dryRun")
            and (
                rewrite_variant is None
                or bool(matches)
                or (
                    bool(records)
                    and all(
                        record.get("candidateCompileInvoked") is True
                        and (
                            record.get("status") == "compile-failed"
                            or (record.get("status") == "mismatched" and record.get("objdiffExit") == 0 and not record.get("fallback"))
                        )
                        for record in records
                    )
                )
            )
        ):
            # Target preparation and verifier errors leave the proposal retryable.
            # Status alone is insufficient: missing toolchains can be compile-failed.
            # A match settles the candidate; rejection requires every profile to
            # finish conclusively so one failure cannot hide another profile's retry.
            rewrite_queue.prune_consumed_entries(Path(str(work_dir_value)), [rewrite_request_id])
        return (
            PluginResult(
                self.id,
                self.name,
                status,
                now_ms() - start,
                error=None if matches else f"no byte-identical source candidate; best differences={best_difference}",
                data={
                    "attemptCount": len(records),
                    "compileDiagnosticCacheHits": diagnostic_cache_hits,
                    "matchCount": len(matches),
                    "exportableMatchCount": len(exportable_matches),
                    "sourceShapeMatchCount": len(source_shape_matches),
                    "differenceCount": 0 if matches else best_difference,
                    "compilerNotInvoked": toolchain_not_invoked,
                    "attemptsPath": str(attempts_path),
                    "bestStatus": matches[0].get("status") if matches else (records[0].get("status") if records else None),
                    "mismatchClass": latest_record.get("mismatchClass"),
                    "mismatchHistogram": latest_record.get("mismatchHistogram"),
                    "primaryMismatchKind": latest_record.get("primaryMismatchKind"),
                    "detailLevel": latest_record.get("detailLevel"),
                    "routedPlaybook": routed_playbook_for_class(latest_record.get("mismatchClass")),
                },
            ),
            updated,
        )


class RecoveredSourceExportPlugin:
    id = "recovered-source-export"
    name = "Recovered Source Export"
    description = "Export verified source matches from plugin-pipeline attempts into a bounded source shard."

    def execute(self, context: dict[str, Any]) -> tuple[PluginResult, dict[str, Any]]:
        start = now_ms()
        out_dir = Path(str(context.get("outDir") or "target/plugin-source-pipeline"))
        matches_path = out_dir / "plugin-code-slice-matches.jsonl"
        matches = list(context.get("sourceParityMatchRecords") or [])
        out_dir.mkdir(parents=True, exist_ok=True)
        with matches_path.open("w", encoding="utf-8") as fh:
            for record in matches:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        export = export_recovered_source(
            [matches_path],
            out_dir=out_dir / "recovered-source",
            source_name="source_slices.c",
        )
        updated = dict(context)
        updated["recoveredSourceExport"] = export
        return (
            PluginResult(
                self.id,
                self.name,
                "success" if export.get("status") == "complete" else "failure",
                now_ms() - start,
                error=None if export.get("status") == "complete" else "no verified source matches to export",
                data=export,
            ),
            updated,
        )


def failure(plugin: Any, start: int, message: str, data: dict[str, Any] | None = None) -> PluginResult:
    return PluginResult(
        plugin.id,
        plugin.name,
        "failure",
        now_ms() - start,
        error=message,
        data=data or {},
    )


def diagnostic_cache_toolchain_identity(
    row: dict[str, Any],
    candidate: Any,
    *,
    compiler: str,
    compiler_profiles: list[tuple[str, list[str]]],
    vc_root: Path | None,
    wine: str,
    wineprefix: Path | None,
    source_shape_search: bool,
) -> str | None:
    """Return the legacy lane's bounded, content-hashed MSVC identity.

    This identity is advisory cache partitioning, not compiler provenance. In
    particular, do not infer a Wine prefix from a default path: without an
    explicit prefix in configuration or the environment, reuse is disabled.
    The helper only hashes existing inputs and constructs an environment; it
    never launches MSVC/Wine or creates/initializes a prefix.
    """
    if compiler != "msvc" or source_shape_search:
        return None
    from .compile_cache import advisory_toolchain_identity, source_has_bounded_compile_inputs
    from .package_verify import build_recovered_c_shim, msvc_environment, resolve_msvc_root

    effective_prefix = wineprefix
    if effective_prefix is None and os.environ.get("WINEPREFIX"):
        effective_prefix = Path(os.environ["WINEPREFIX"])
    if effective_prefix is None:
        return None
    try:
        compiler_root = resolve_msvc_root(vc_root).expanduser().resolve()
        compiler_path = compiler_root / "bin" / "cl.exe"
        target_slice_clang_path = Path(shutil.which("clang") or "clang").expanduser().resolve()
        effective_env = msvc_environment(compiler_root, effective_prefix)
        resolved_prefix = Path(effective_env["WINEPREFIX"]).expanduser().resolve()
        if resolved_prefix != effective_prefix.expanduser().resolve():
            return None
    except (KeyError, OSError, RuntimeError, ValueError):
        return None

    effective_profiles = resolve_profiles(row, compiler_profiles, compiler, source_shape_search=False)
    if not effective_profiles:
        return None
    if str(candidate.source_suffix).lower() not in {".c", ".cc", ".cpp", ".cxx"}:
        return None
    compile_flags = [flag for _name, flags in effective_profiles for flag in flags] + list(candidate.extra_flags)
    compiler_source = str(candidate.source)
    if str(candidate.source_suffix).lower() == ".c":
        compiler_source = build_recovered_c_shim(compiler_source) + "\n\n" + compiler_source
    if not source_has_bounded_compile_inputs(compiler_source, compile_flags):
        return None

    objdiff_path = shutil.which("objdiff")
    wine_path = shutil.which(wine) or wine
    files: dict[str, Path | None] = {
        "candidate-compiler": compiler_path,
        "target-slice-clang": target_slice_clang_path,
        "objdiff": Path(objdiff_path) if objdiff_path else None,
        "source-synthesizer": Path(__file__).with_name("source_parity_synthesize.py"),
        "source-plugin-runner": Path(__file__).with_name("source_plugin_runner.py"),
        "compile-cache-identity": Path(__file__).with_name("compile_cache.py"),
        "objdiff-verifier": Path(__file__).with_name("objdiff_verification.py"),
        "package-compiler-adapter": Path(__file__).with_name("package_verify.py"),
        "recovered-c-preamble": Path(__file__).with_name("corpus") / "recovered_c_preamble.py",
        "wine": Path(wine_path),
    }
    for tool in ("c1.dll", "c1xx.dll", "c2.dll"):
        path = compiler_root / "bin" / tool
        if not path.is_file():
            return None
        files[f"msvc-{tool}"] = path
    for registry_name in ("system.reg", "user.reg", "userdef.reg"):
        files[f"wine-prefix-{registry_name}"] = resolved_prefix / registry_name

    profile_flags = json.dumps(
        {"profiles": effective_profiles, "candidateFlags": list(candidate.extra_flags)},
        sort_keys=True,
        separators=(",", ":"),
    )
    default_profile_name = effective_profiles[0][0]
    environment_names = (
        "PATH", "INCLUDE", "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "SDKROOT",
        "CCC_OVERRIDE_OPTIONS", "CLANG_CONFIG_FILE_USER_DIR", "CLANG_CONFIG_FILE_SYSTEM_DIR",
        "SOURCE_DATE_EPOCH", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL", "WINEPREFIX",
        "WINEDEBUG", "WINEARCH", "WINEDLLOVERRIDES", "WINEPATH",
    )
    settings = {
        "compiler": compiler,
        "compilerPath": str(compiler_path),
        "targetSliceClangPath": str(target_slice_clang_path),
        "configuredClangPath": None,
        "compilerProfile": default_profile_name,
        "compilerFlags": profile_flags,
        "sourceSuffix": candidate.source_suffix,
        "sourceShapeSearch": False,
        "candidateRule": candidate.rule,
        "candidateVariant": candidate.variant,
        "candidateSymbol": candidate.symbol,
        "candidateCName": candidate.c_name,
        "candidateCallConvention": candidate.callconv,
        "candidateSemanticSource": candidate.semantic_source,
        "candidateEvidenceSha256": hashlib.sha256(
            json.dumps(candidate.evidence, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest(),
    }
    return advisory_toolchain_identity(
        files=files,
        settings=settings,
        environment={name: effective_env[name] for name in environment_names if name in effective_env},
    )


def optional_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_filter_set(value: Any) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        try:
            items = [str(part).strip() for part in value]
        except TypeError:
            items = [str(value).strip()]
    normalized = {item for item in items if item}
    return normalized or None


def promotion_seed_qualities(source_qualities: set[str] | None, source_shape_search: bool) -> set[str] | None:
    if not source_shape_search or not source_qualities or "high-level-c" not in source_qualities:
        return source_qualities
    return set(source_qualities) | {"inline-asm-c"}
