"""Read-only recovery run status for CLI and curated MCP tools."""

from __future__ import annotations

import json
import os

from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _queue_counts(queue: dict[str, Any] | None) -> dict[str, int] | None:
    if queue is None:
        return None
    counts: dict[str, int] = {}
    for key in ("pending", "matched", "integrated", "failed", "difficult"):
        value = queue.get(key)
        counts[key] = len(value) if isinstance(value, list) else 0
    return counts


_UNITY_RECEIPTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "probe": (
        "unity-probe",
        "probe.json",
        ("detected", "unityVersion", "scriptingBackend", "sceneCount", "managedAssemblyCount", "dataDir", "claimBoundary"),
    ),
    "plan": ("unity-plan", "plan.json", ("blockedReason", "claimBoundary")),
    "export": (
        "unity-export-assets",
        "assetripper.json",
        ("mode", "exportedProject", "hasProjectVersion", "memoryFailureSuspected", "stagedContainerCount", "reason", "claimBoundary"),
    ),
    "managed": (
        "unity-decompile-managed",
        "managed.json",
        ("requested", "decompiled", "failed", "totalFileCount", "strippedCount", "outDir", "claimBoundary"),
    ),
    "compose": (
        "unity-compose-project",
        "compose.json",
        ("exportedProject", "targetProject", "totalFilesCopied", "openable", "warnings", "claimBoundary"),
    ),
    "editorValidation": (
        "unity-editor-validate",
        "validate.json",
        ("projectPath", "clean", "validatorRan", "returnCode", "timedOut", "scenes", "claimBoundary"),
    ),
    "repair": (
        "unity-repair",
        "repair.json",
        ("projectPath", "disposition", "attemptCount", "finalErrorCount", "unfixedErrorCount", "unimplementedRecipeCounts", "unverifiedRepairs", "claimBoundary"),
    ),
}
_UNITY_REQUIRED_STAGES = tuple(_UNITY_RECEIPTS)
_UNITY_FAILURE_STATUSES = frozenset({"error", "failed", "timeout", "refused"})


def _path_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return os.path.abspath(os.path.expanduser(str(value)))
    except (OSError, TypeError, ValueError):
        return str(value)


def build_unity_recovery_summary(
    work_dir: Path,
    *,
    project_path: Path | str | None = None,
    requested: bool | None = None,
) -> dict[str, Any]:
    """Build a read-only Unity receipt summary and configured-run outcome.

    A Unity project is an explicit deliverable only when ``project_path`` was
    configured. In that case skipped/missing stages on a detected Unity target
    are incomplete, while a confirmed non-Unity target remains benign.
    """

    work_dir = work_dir.resolve()
    unity_dir = work_dir / "unity"
    state = _load_json(work_dir / "state.json") or {}
    report = _load_json(work_dir / "report.json") or {}
    state_stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}

    settings: dict[str, Any] = {}
    has_current_settings = False
    for stage_name, _receipt_name, _fields in _UNITY_RECEIPTS.values():
        stage_state = state_stages.get(stage_name) if isinstance(state_stages, dict) else None
        config = stage_state.get("config") if isinstance(stage_state, dict) else None
        candidate = config.get("unitySettings") if isinstance(config, dict) else None
        if isinstance(candidate, dict):
            settings = candidate
            has_current_settings = True
            break

    if project_path is None:
        project_path = settings.get("projectOut")
    old_summary = report.get("unity") if isinstance(report.get("unity"), dict) else {}
    if project_path is None and not has_current_settings:
        project_path = old_summary.get("projectPath")
    resolved_project = _path_string(project_path)
    if requested is None:
        if has_current_settings:
            requested = bool(settings.get("projectOut"))
        else:
            requested = bool(resolved_project or old_summary.get("requested"))

    receipts: dict[str, dict[str, Any]] = {}
    for key, (stage_name, filename, fields) in _UNITY_RECEIPTS.items():
        path = unity_dir / filename
        receipt = _load_json(path) or {}
        stage_state = state_stages.get(stage_name) if isinstance(state_stages, dict) else None
        state_status = stage_state.get("status") if isinstance(stage_state, dict) else None
        summary = stage_state.get("summary") if isinstance(stage_state, dict) else None
        status = receipt.get("status")
        if status is None and isinstance(summary, dict):
            status = summary.get("status")
        if status is None:
            status = state_status
        item: dict[str, Any] = {
            "status": status,
            "present": path.is_file(),
            "receiptPath": str(path),
        }
        reason = receipt.get("reason") or receipt.get("blockedReason")
        if reason is None and isinstance(stage_state, dict):
            reason = stage_state.get("reason") or (summary.get("reason") if isinstance(summary, dict) else None)
        if reason is not None:
            item["reason"] = reason
        for field in fields:
            if field in receipt:
                item[field] = receipt[field]
        if key == "plan":
            export = receipt.get("export")
            if isinstance(export, dict):
                item["export"] = {
                    "mode": export.get("mode"),
                    "reason": export.get("reason"),
                    "includedContainerCount": len(export.get("includedContainers") or []),
                    "excludedContainers": export.get("excludedContainers") or [],
                    "stagedBytes": export.get("stagedBytes"),
                    "totalBytes": export.get("totalBytes"),
                }
            editor = receipt.get("editor")
            if isinstance(editor, dict):
                item["editor"] = {
                    name: editor.get(name)
                    for name in ("selectedVersion", "executable", "match", "versionDrift")
                    if name in editor
                }
        if key == "editorValidation":
            compile_result = receipt.get("compile")
            if isinstance(compile_result, dict):
                item["compile"] = {
                    name: compile_result.get(name)
                    for name in ("errorCount", "warningCount", "compilationFailed")
                    if name in compile_result
                }
        if key == "repair":
            final_validation = receipt.get("finalValidation")
            if isinstance(final_validation, dict):
                item["finalValidation"] = {
                    name: final_validation.get(name)
                    for name in ("status", "clean", "returnCode", "timedOut")
                    if name in final_validation
                }
                final_compile = final_validation.get("compile")
                if isinstance(final_compile, dict):
                    item["finalValidation"]["compile"] = {
                        name: final_compile.get(name)
                        for name in ("errorCount", "warningCount", "compilationFailed")
                        if name in final_compile
                    }
                final_scenes = final_validation.get("scenes")
                if isinstance(final_scenes, dict):
                    item["finalValidation"]["scenes"] = {
                        name: final_scenes.get(name)
                        for name in ("opened", "total", "missingScripts")
                        if name in final_scenes
                    }
        if key == "managed":
            item["decompiledCount"] = len(receipt.get("decompiled") or [])
            item["failedCount"] = len(receipt.get("failed") or [])
        receipts[key] = item

    probe = receipts["probe"]
    detected = probe.get("detected") if probe.get("present") else None
    issues: list[dict[str, Any]] = []
    terminal_status: str | None = None
    exit_code = 0
    if requested and detected is False and str(probe.get("status") or "").lower() in {"complete", "skipped"}:
        outcome = "not-applicable"
    elif requested and detected is False:
        outcome = "failed"
        terminal_status = "failed"
        exit_code = 1
        issues.append({"stage": "probe", "status": probe.get("status") or "unknown", "reason": "Unity probe failed before it could establish the target type"})
    elif not requested:
        outcome = "not-configured"
    elif detected is not True:
        outcome = "partial"
        terminal_status = "partial"
        exit_code = 1
        issues.append({"stage": "probe", "status": probe.get("status") or "missing", "reason": "Unity detection did not produce a positive receipt"})
    else:
        failed = False
        for key in _UNITY_REQUIRED_STAGES:
            item = receipts[key]
            status = str(item.get("status") or "missing").strip().lower()
            repair_validation = receipts["repair"].get("finalValidation") or {}
            repaired_cleanly = (
                receipts["repair"].get("status") == "complete"
                and isinstance(repair_validation, dict)
                and repair_validation.get("clean") is True
            )
            if key == "repair" and status == "skipped" and receipts["editorValidation"].get("clean") is True:
                continue
            if key == "editorValidation" and repaired_cleanly:
                # The first Editor pass is diagnostic; a successful repair
                # receipt can supersede its compile errors with a clean final pass.
                continue
            if not item.get("present") and status not in _UNITY_FAILURE_STATUSES:
                issues.append({"stage": key, "status": status, "reason": "receipt is missing"})
                continue
            if status == "complete":
                if key == "plan" and (item.get("export") or {}).get("excludedContainers"):
                    omissions = (item.get("export") or {}).get("excludedContainers")
                    issues.append(
                        {
                            "stage": key,
                            "status": status,
                            "reason": "the export plan omits Unity containers",
                            "omittedContainers": omissions,
                        }
                    )
                elif key == "editorValidation" and item.get("clean") is not True:
                    issues.append({"stage": key, "status": status, "reason": "Editor validation did not confirm a clean project"})
                elif key == "export" and item.get("hasProjectVersion") is not True:
                    issues.append({"stage": key, "status": status, "reason": "export lacks ProjectVersion.txt evidence"})
                elif key == "compose" and (item.get("openable") or {}).get("ready") is not True:
                    issues.append({"stage": key, "status": status, "reason": "composed project is missing openable-project markers"})
                continue
            issue = {"stage": key, "status": status, "reason": item.get("reason") or item.get("blockedReason") or "Unity stage did not complete"}
            issues.append(issue)
            if status in _UNITY_FAILURE_STATUSES:
                failed = True
        if failed:
            outcome = "failed"
            terminal_status = "failed"
            exit_code = 1
        elif issues:
            outcome = "partial"
            terminal_status = "partial"
            exit_code = 1
        else:
            outcome = "complete"
            terminal_status = "complete"

    return {
        "status": outcome,
        "requested": bool(requested),
        "configured": bool(resolved_project),
        "detected": detected,
        "terminalStatus": terminal_status,
        "exitCode": exit_code,
        "projectPath": resolved_project,
        "managedSourcePath": str(unity_dir / "managed-csharp"),
        "exportOmissions": (receipts["plan"].get("export") or {}).get("excludedContainers") or [],
        "receipts": receipts,
        "issues": issues,
        "managedSourceBoundary": (
            "decompiled C# is derived from shipped managed assemblies; it is not byte-verified native "
            "C/C++ and does not establish recovery of the developers' original source"
        ),
        "nativeSourceBoundary": (
            "native byte-verification claims remain separate and are reported only by the native "
            "recovery proof receipts"
        ),
    }


def build_recovery_status(work_dir: Path) -> dict[str, Any]:
    """Summarize reconstruct/recover work-dir progress without claiming semantic parity."""

    work_dir = work_dir.resolve()
    report = _load_json(work_dir / "report.json")
    state = _load_json(work_dir / "state.json")
    analysis = _load_json(work_dir / "analysis-target.json")
    claim = _load_json(work_dir / "claim-report.json")
    synth = _load_json(work_dir / "source-synthesis" / "summary.json")
    budget = _load_json(work_dir / "autonomy-budget.json")
    queue = _load_json(work_dir / "state" / "queue.json")
    session = _load_json(work_dir / "state" / "vacuum-session.json")
    seed = _load_json(work_dir / "state" / "vacuum-queue-seed.json")
    export_pkg = _load_json(work_dir / "export" / "manifest.json")
    if export_pkg is None and isinstance((report or {}).get("exportPackage"), dict):
        export_pkg = report.get("exportPackage")  # type: ignore[assignment]
    ladder = _load_json(work_dir / "proof-ladder.json")
    proof_target_queue = _load_json(work_dir / "facts" / "proof-target-queue.json")
    proof_campaign = _load_json(work_dir / "state" / "proof-campaign.json")
    proof_campaign_loop = _load_json(work_dir / "state" / "proof-campaign-loop.json")
    if ladder is None and isinstance((claim or {}).get("proofLadder"), dict):
        ladder = claim.get("proofLadder")  # type: ignore[assignment]
    if ladder is None and isinstance((report or {}).get("proofLadder"), dict):
        ladder = report.get("proofLadder")  # type: ignore[assignment]
    critical = _load_json(work_dir / "critical-path.json")
    if critical is None and isinstance((report or {}).get("criticalPath"), dict):
        critical = report.get("criticalPath")  # type: ignore[assignment]
    if critical is None and (work_dir / "target.json").is_file():
        from .critical_path import build_critical_path

        critical = build_critical_path(work_dir)
    placement = _load_json(work_dir / "acquisition" / "placement.json")
    acquire = _load_json(work_dir / "acquisition" / "acquire.json")
    propose = _load_json(work_dir / "acquisition" / "propose-labels.json")
    context_apply_run = _load_json(work_dir / "state" / "context-apply-run.json")
    near_miss_repair_run = _load_json(work_dir / "state" / "near-miss-repair-run.json")
    agent_closure_run = _load_json(work_dir / "state" / "agent-closure-run.json")
    symbol_provenance = _load_json(work_dir / "facts" / "symbol-provenance.json")
    campaign_checkpoints = _load_json(work_dir / "facts" / "campaign-checkpoints.json")
    pattern_memory = _load_json(work_dir / "facts" / "pattern-memory.json")
    if propose is None and isinstance((acquire or {}).get("proposeLabels"), dict):
        propose = acquire.get("proposeLabels")  # type: ignore[assignment]
    slice_verify = _load_json(work_dir / "slice-verify" / "summary.json")
    if placement is None and isinstance((acquire or {}).get("placement"), dict):
        placement = acquire.get("placement")  # type: ignore[assignment]
    seeds = _load_json(work_dir / "advisory" / "context-seeds" / "manifest.json")
    if seeds is None and isinstance((acquire or {}).get("contextSeeds"), dict):
        seeds = acquire.get("contextSeeds")  # type: ignore[assignment]

    report_data = report or {}
    report_unity = report_data.get("unity") if isinstance(report_data.get("unity"), dict) else {}
    unity = build_unity_recovery_summary(
        work_dir,
        project_path=report_unity.get("projectPath"),
        requested=True if report_unity.get("requested") is True else None,
    )

    terminal = None
    for source in (claim, analysis, state, report):
        if not source:
            continue
        for key in ("terminalStatus", "status"):
            value = source.get(key)
            if value:
                terminal = str(value)
                break
        if terminal:
            break

    # A configured Unity deliverable is part of the reconstruct outcome. Older
    # claim reports may predate Unity receipts, so current receipt evidence wins
    # when it shows a failed or incomplete configured Unity run.
    unity_terminal = unity.get("terminalStatus")
    terminal_rank = {"unknown": 0, "matched": 1, "complete": 1, "partial": 2, "failed": 3}
    current_terminal = terminal or "unknown"
    if (
        unity_terminal in {"failed", "partial"}
        and current_terminal not in {"blocked:toolchain", "cancelled"}
        and terminal_rank.get(str(unity_terminal), 0) > terminal_rank.get(str(current_terminal), 0)
    ):
        terminal = str(unity_terminal)

    stage = None
    if state:
        stage = state.get("currentStage") or state.get("stage") or state.get("lastStage")
    if report and stage is None:
        stage = report.get("currentStage") or report.get("stage")

    verified = work_dir / "verified"
    advisory = work_dir / "advisory"
    verified_count = sum(1 for path in verified.rglob("*") if path.is_file()) if verified.is_dir() else 0
    advisory_count = sum(1 for path in advisory.rglob("*") if path.is_file()) if advisory.is_dir() else 0
    queue_counts = _queue_counts(queue)

    vacuum: dict[str, Any] | None = None
    if budget is not None or queue is not None or session is not None or seed is not None:
        vacuum = {
            "budgetStatus": (budget or {}).get("status"),
            "requested": bool((budget or {}).get("requested")) if budget is not None else False,
            "queueCounts": queue_counts,
            "sessionStatus": (session or {}).get("status") if session is not None else None,
            "seededCount": int((seed or {}).get("seededCount") or 0) if seed is not None else None,
            "seedStatus": (seed or {}).get("status") if seed is not None else None,
            "claimBoundary": (
                "vacuum/budget fields summarize autonomy loop progress only; "
                "they are not objdiff-verified-semantic proof"
            ),
        }

    return {
        "schema": "agentdecompile.recovery-status.v1",
        "workDir": str(work_dir),
        "terminalStatus": terminal or "unknown",
        "stage": stage,
        "hasReport": report is not None,
        "hasClaimReport": claim is not None,
        "unity": unity,
        "counts": {
            "verified": verified_count,
            "advisory": advisory_count,
            "acceptedCandidates": int((synth or {}).get("acceptedCandidates") or (synth or {}).get("accepted") or 0),
            "objdiffVerified": int((claim or {}).get("counts", {}).get("objdiffVerified") or 0),
        },
        "autonomyBudget": budget,
        "vacuum": vacuum,
        "exportPackage": (
            {
                "status": export_pkg.get("status"),
                "viewCount": export_pkg.get("viewCount"),
                "countsByAuthorityClass": export_pkg.get("countsByAuthorityClass"),
                "exportDir": export_pkg.get("exportDir") or str(work_dir / "export"),
                "claimBoundary": export_pkg.get("claimBoundary")
                or (
                    "export package aggregates recovery views with authority classes; "
                    "only objdiff-verified-semantic is accepted source"
                ),
            }
            if export_pkg is not None
            else None
        ),
        "proofLadder": (
            {
                "status": ladder.get("status"),
                "denominator": ladder.get("denominator"),
                "numerator": ladder.get("numerator"),
                "coverage": ladder.get("coverage"),
                "coveragePercent": ladder.get("coveragePercent"),
                "rung": ladder.get("rung"),
                "nextRung": ladder.get("nextRung"),
                "functionsToNextRung": ladder.get("functionsToNextRung"),
                "nextRungTargetNumerator": ladder.get("nextRungTargetNumerator"),
                "claimBoundary": ladder.get("claimBoundary")
                or (
                    "proof ladder coverage is receipt-backed objdiff accepts only; "
                    "not a ≥90% whole-binary recovery claim"
                ),
            }
            if ladder is not None
            else None
        ),
        "proofTargetQueue": (
            {
                "status": proof_target_queue.get("status"),
                "queueCount": proof_target_queue.get("queueCount"),
                "synthesisEligibleCount": proof_target_queue.get("synthesisEligibleCount"),
                "functionsToNextRung": proof_target_queue.get("functionsToNextRung"),
                "nearMissRetryCount": proof_target_queue.get("nearMissRetryCount"),
                "topEntries": (proof_target_queue.get("entries") or [])[:3],
                "claimBoundary": proof_target_queue.get("claimBoundary")
                or "proof-target queue is advisory; does not count toward numerator",
            }
            if proof_target_queue is not None
            else None
        ),
        "proofCampaign": (
            {
                "status": proof_campaign.get("status"),
                "attempted": proof_campaign.get("attempted"),
                "accepts": proof_campaign.get("accepts"),
                "nearMisses": proof_campaign.get("nearMisses"),
                "bestDifference": proof_campaign.get("bestDifference"),
                "rungBefore": proof_campaign.get("rungBefore"),
                "rungAfter": proof_campaign.get("rungAfter"),
                "claimBoundary": proof_campaign.get("claimBoundary"),
            }
            if proof_campaign is not None
            else None
        ),
        "proofCampaignLoop": (
            {
                "status": proof_campaign_loop.get("status"),
                "campaignCount": proof_campaign_loop.get("campaignCount"),
                "maxCampaigns": proof_campaign_loop.get("maxCampaigns"),
                "stopOnAccept": proof_campaign_loop.get("stopOnAccept"),
                "totalAttempted": proof_campaign_loop.get("totalAttempted"),
                "totalAccepts": proof_campaign_loop.get("totalAccepts"),
                "numeratorDelta": proof_campaign_loop.get("numeratorDelta"),
                "bestDifference": proof_campaign_loop.get("bestDifference"),
                "claimBoundary": proof_campaign_loop.get("claimBoundary"),
            }
            if proof_campaign_loop is not None
            else None
        ),
        "contextFusion": (
            {
                "placed": (placement or {}).get("counts", {}).get("placed") if placement else None,
                "unplaced": (placement or {}).get("counts", {}).get("unplaced") if placement else None,
                "conflicts": (placement or {}).get("counts", {}).get("conflicts") if placement else None,
                "skipped": (placement or {}).get("counts", {}).get("skipped") if placement else None,
                "seeds": (seeds or {}).get("counts", {}).get("seeded") if seeds else None,
                "claimBoundary": (placement or {}).get("claimBoundary")
                or (
                    "context fusion is address-keyed advisory evidence only; "
                    "unplaced pieces are not inventively assigned VAs"
                ),
            }
            if placement is not None or seeds is not None
            else None
        ),
        "proposeLabels": (
            {
                "status": propose.get("status"),
                "proposed": (propose.get("counts") or {}).get("proposed"),
                "ready": (propose.get("counts") or {}).get("ready"),
                "conflicts": (propose.get("counts") or {}).get("conflicts"),
                "claimBoundary": propose.get("claimBoundary")
                or (
                    "proposed labels are context hints only; apply via MCP conflict protocol"
                ),
                "nextStep": propose.get("nextStep"),
            }
            if propose is not None
            else None
        ),
        "contextApplyRun": (
            {
                "status": context_apply_run.get("status"),
                "applied": context_apply_run.get("applied"),
                "mcpStatus": context_apply_run.get("mcpStatus"),
                "claimBoundary": context_apply_run.get("claimBoundary"),
            }
            if context_apply_run is not None
            else None
        ),
        "nearMissRepairRun": (
            {
                "status": near_miss_repair_run.get("status"),
                "matchedCount": near_miss_repair_run.get("matchedCount"),
                "claimBoundary": near_miss_repair_run.get("claimBoundary"),
            }
            if near_miss_repair_run is not None
            else None
        ),
        "agentClosureRun": (
            {
                "status": agent_closure_run.get("status"),
                "claimBoundary": agent_closure_run.get("claimBoundary"),
            }
            if agent_closure_run is not None
            else None
        ),
        "symbolProvenance": (
            {
                "status": symbol_provenance.get("status"),
                "symbolCount": symbol_provenance.get("symbolCount"),
                "source": symbol_provenance.get("source"),
                "claimBoundary": symbol_provenance.get("claimBoundary"),
            }
            if symbol_provenance is not None
            else None
        ),
        "campaignCheckpoints": (
            {
                "entryCount": len(campaign_checkpoints.get("entries") or {}),
                "writtenAt": campaign_checkpoints.get("writtenAt"),
                "claimBoundary": campaign_checkpoints.get("claimBoundary"),
            }
            if campaign_checkpoints is not None
            else None
        ),
        "patternMemory": (
            {
                "patternCount": len(pattern_memory.get("patterns") or []),
                "writtenAt": pattern_memory.get("writtenAt"),
                "claimBoundary": pattern_memory.get("claimBoundary"),
            }
            if pattern_memory is not None
            else None
        ),
        "criticalPath": (
            {
                "readiness": critical.get("readiness"),
                "peCriticalPathStopAfter": critical.get("peCriticalPathStopAfter"),
                "nextActions": critical.get("nextActions"),
                "claimBoundary": critical.get("claimBoundary")
                or (
                    "critical path readiness is orchestration metadata only; "
                    "proof ladder objdiff accepts remain the semantic KPI"
                ),
            }
            if critical is not None
            else None
        ),
        "sliceVerify": (
            {
                "status": slice_verify.get("status"),
                "verificationTier": slice_verify.get("verificationTier"),
                "format": slice_verify.get("format"),
                "candidate": slice_verify.get("candidate"),
                "claimBoundary": slice_verify.get("claimBoundary")
                or (
                    "slice verify is weaker byte-roundtrip evidence only; "
                    "does not count toward proof ladder objdiff numerator"
                ),
            }
            if slice_verify is not None
            else None
        ),
        "claimBoundary": (
            "status summarizes orchestration progress only; "
            "objdiff-verified-semantic proof remains required for accepted source"
        ),
        "paths": {
            "report": str(work_dir / "report.json") if report is not None else None,
            "claimReport": str(work_dir / "claim-report.json") if claim is not None else None,
            "autonomyBudget": str(work_dir / "autonomy-budget.json") if budget is not None else None,
            "vacuumQueue": str(work_dir / "state" / "queue.json") if queue is not None else None,
            "proofLadder": str(work_dir / "proof-ladder.json")
            if (work_dir / "proof-ladder.json").is_file()
            else None,
            "proofTargetQueue": str(work_dir / "facts" / "proof-target-queue.json")
            if (work_dir / "facts" / "proof-target-queue.json").is_file()
            else None,
            "proofCampaign": str(work_dir / "state" / "proof-campaign.json")
            if (work_dir / "state" / "proof-campaign.json").is_file()
            else None,
            "proofCampaignLoop": str(work_dir / "state" / "proof-campaign-loop.json")
            if (work_dir / "state" / "proof-campaign-loop.json").is_file()
            else None,
            "criticalPath": str(work_dir / "critical-path.json")
            if (work_dir / "critical-path.json").is_file()
            else None,
            "sliceVerify": str(work_dir / "slice-verify" / "summary.json")
            if (work_dir / "slice-verify" / "summary.json").is_file()
            else None,
            "placement": str(work_dir / "acquisition" / "placement.json")
            if (work_dir / "acquisition" / "placement.json").is_file()
            else None,
            "proposeLabels": str(work_dir / "acquisition" / "propose-labels.json")
            if (work_dir / "acquisition" / "propose-labels.json").is_file()
            else None,
            "contextApplyRun": str(work_dir / "state" / "context-apply-run.json")
            if (work_dir / "state" / "context-apply-run.json").is_file()
            else None,
            "nearMissRepairRun": str(work_dir / "state" / "near-miss-repair-run.json")
            if (work_dir / "state" / "near-miss-repair-run.json").is_file()
            else None,
            "agentClosureRun": str(work_dir / "state" / "agent-closure-run.json")
            if (work_dir / "state" / "agent-closure-run.json").is_file()
            else None,
            "symbolProvenance": str(work_dir / "facts" / "symbol-provenance.json")
            if (work_dir / "facts" / "symbol-provenance.json").is_file()
            else None,
            "contextSeeds": str(work_dir / "advisory" / "context-seeds" / "manifest.json")
            if (work_dir / "advisory" / "context-seeds" / "manifest.json").is_file()
            else None,
            "exportManifest": str(work_dir / "export" / "manifest.json")
            if (work_dir / "export" / "manifest.json").is_file()
            else None,
            "unityProject": unity.get("projectPath"),
            "unityReceipts": {
                key: value.get("receiptPath")
                for key, value in unity.get("receipts", {}).items()
                if value.get("present")
            },
            "verified": str(verified) if verified.is_dir() else None,
            "advisory": str(advisory) if advisory.is_dir() else None,
        },
    }
