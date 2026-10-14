"""Generic imperative pipeline runner."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from . import acquisition_registry
from .acquisition_bundle import load_bundle, validate_bundle_target
from .context_export import ExportConfig, export_context
from .context_pack import build_context_pack
from .export_package import build_export_package
from .functions import (
    analyze_function_candidates_with_objdump,
    dedupe_same_address_candidates,
    discover_function_candidates,
    summarize_candidates,
    write_function_candidates,
)
from .inventory import build_binary_inventory, write_inventory
from .critical_path import write_critical_path
from .proof_ladder import write_proof_ladder
from .sourcegen import generate_source_candidates
from .source_export import export_recovered_source
from .source_parity_synthesize import main as source_parity_synthesize_main
from .source_plugin_runner import SourcePluginRunConfig, run_source_plugin_pipeline
from .state import RunState, atomic_write_json, config_fingerprint, now
from .strategy import build_strategy
from .snapshot import snapshot_existing_recovery
from .targets import TargetIdentity, identify_binary
from .languages import RecoveryLanguageProfile
from .tools import (
    ASSETRIPPER_ENV,
    ILSPYCMD_ENV,
    UNITY_EDITOR_ENV,
    ToolchainError,
    detect_pe_packed,
    inspect_capabilities,
    resolve_assetripper_cli,
    resolve_ilspycmd,
    resolve_script_asset,
    resolve_steamless_cli,
    run_steamless,
)


ROOT = Path(__file__).resolve().parents[2]

_MEDIA_TYPES = frozenset({"Texture2D", "Sprite", "AudioClip", "TextAsset", "Font"})


def stage_summary_needs_retry(summary: Any) -> bool:
    if not isinstance(summary, dict):
        return False
    status = str(summary.get("status") or "")
    return status in {"error", "failed"} or status.startswith("paused-")


def _unity_source_identity(path: Path) -> dict[str, int | str]:
    info = path.stat()
    return {
        "name": path.name,
        "sizeBytes": info.st_size,
        "mtimeNs": info.st_mtime_ns,
        "ctimeNs": info.st_ctime_ns,
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def _unity_resource_companion_owner_names(name: str) -> set[str]:
    """Return conventional serialized-owner names for a stream companion."""

    if name.endswith(".resS"):
        return {name.removesuffix(".resS")}
    if name.endswith(".resource"):
        stem = name.removesuffix(".resource")
        return {stem, stem if stem.endswith(".assets") else f"{stem}.assets"}
    return set()


def _unity_excluded_media_sources(data_dir: Path, excluded: set[str]) -> dict[str, Any]:
    """Resolve excluded serialized owners and their external stream companions."""

    from .unity_assets import discover_data_files, discover_resource_companions

    owners = {path.name: path for path in discover_data_files(data_dir)}
    planned_companions = {
        name for name in excluded if _unity_resource_companion_owner_names(name)
    }
    planned_owners = excluded - planned_companions
    selected_owners = [
        owners[name] for name in sorted(planned_owners & owners.keys())
    ]
    selected_owner_names = {path.name for path in selected_owners}
    companions = discover_resource_companions(data_dir)
    associated_companions = [
        path
        for path in companions
        if _unity_resource_companion_owner_names(path.name) & selected_owner_names
    ]
    available_companion_names = {path.name for path in companions}
    associated_names = {path.name for path in associated_companions}
    return {
        "selectedOwners": selected_owners,
        "associatedCompanions": associated_companions,
        "missingOwners": sorted(planned_owners - owners.keys()),
        "plannedCompanions": sorted(planned_companions),
        "unavailablePlannedCompanions": sorted(
            planned_companions - available_companion_names
        ),
        "unassociatedPlannedCompanions": sorted(
            (planned_companions & available_companion_names) - associated_names
        ),
    }


def _media_file_identity(path: Path) -> dict[str, int] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "sizeBytes": info.st_size,
        "mtimeNs": info.st_mtime_ns,
    }


def _media_conflict_identity(path: Path) -> dict[str, int | str] | None:
    file_identity = _media_file_identity(path)
    if file_identity is not None:
        return file_identity
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        return None
    return {
        "kind": "directory",
        "device": info.st_dev,
        "inode": info.st_ino,
        "sizeBytes": info.st_size,
        "mtimeNs": info.st_mtime_ns,
    }


def _media_output_files(output_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not output_dir.exists():
        return files
    for type_name in _MEDIA_TYPES:
        type_dir = output_dir / type_name
        if type_dir.is_symlink():
            raise ValueError(f"media output contains a symlinked type directory: {type_dir}")
        if not type_dir.is_dir():
            continue
        for path in type_dir.iterdir():
            if path.is_symlink():
                raise ValueError(f"media output contains a symlinked file: {path}")
            if path.is_file():
                files[f"{type_name}/{path.name}"] = path
    return files


def _media_owned_files(receipt: dict[str, Any], project_root: Path, output_dir: Path) -> dict[str, dict[str, int]]:
    if (receipt.get("ownershipSchema") != "agentdecompile.unity-media-ownership.v1"
            or receipt.get("targetProject") != str(project_root)
            or receipt.get("outputDir") != str(output_dir)):
        return {}
    owned: dict[str, dict[str, int]] = {}
    items = receipt.get("ownedFiles")
    if not isinstance(items, list):
        return {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        parts = Path(item["path"]).parts
        if (len(parts) == 2 and parts[0] in _MEDIA_TYPES
                and parts[1] not in {".", ".."}
                and isinstance(item.get("identity"), dict)):
            # Earlier receipts included ctime, which changes when an original
            # inode is moved to and restored from an Assets-local backup.
            owned[item["path"]] = {
                key: item["identity"].get(key)
                for key in ("device", "inode", "sizeBytes", "mtimeNs")
            }
    return owned


def _media_receipt_matches_output(receipt: dict[str, Any], project_root: Path) -> bool:
    """Check every recorded media file without following output symlinks."""

    assets_dir = project_root / "Assets"
    output_dir = assets_dir / "RecoveredPrimaryContent"
    if (receipt.get("ownershipSchema") != "agentdecompile.unity-media-ownership.v1"
            or receipt.get("targetProject") != str(project_root)
            or receipt.get("outputDir") != str(output_dir)
            or assets_dir.is_symlink() or not assets_dir.is_dir()
            or output_dir.is_symlink()
            or (output_dir.exists() and not output_dir.is_dir())):
        return False

    reconciliation = receipt.get("reconciliation")
    owned = receipt.get("ownedFiles")
    conflicts = reconciliation.get("preservedConflictFiles") if isinstance(reconciliation, dict) else None
    conflict_paths = reconciliation.get("preservedChangedOrConflictingFiles") if isinstance(reconciliation, dict) else None
    if not isinstance(owned, list) or not isinstance(conflicts, list) or not isinstance(conflict_paths, list):
        return False
    if (not all(isinstance(path, str) for path in conflict_paths)
            or len(conflicts) != len(conflict_paths)
            or len(set(conflict_paths)) != len(conflict_paths)):
        return False

    seen: set[str] = set()
    for index, item in enumerate([*owned, *conflicts]):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return False
        relative = item["path"]
        parts = Path(relative).parts
        if (len(parts) != 2 or parts[0] not in _MEDIA_TYPES
                or parts[1] in {".", ".."}
                or relative != f"{parts[0]}/{parts[1]}"
                or relative in seen):
            return False
        seen.add(relative)
        identity = item.get("identity")
        if (not isinstance(identity, dict)
                or any(type(identity.get(key)) is not int for key in ("device", "inode", "sizeBytes", "mtimeNs"))):
            return False
        is_conflict = index >= len(owned)
        kind = identity.get("kind")
        if kind is not None and (not is_conflict or kind != "directory"):
            return False
        parent = output_dir / parts[0]
        if parent.is_symlink() or not parent.is_dir():
            return False
        expected: dict[str, int | str] = {
            key: identity[key] for key in ("device", "inode", "sizeBytes", "mtimeNs")
        }
        if kind == "directory":
            expected["kind"] = kind
        actual = (_media_conflict_identity(parent / parts[1]) if is_conflict
                  else _media_file_identity(parent / parts[1]))
        if actual != expected:
            return False
    return {item["path"] for item in conflicts} == set(conflict_paths)


# Stages that consume acquisition / context-pack facts. Early inventory stages must
# remain resumable when mid-run ``--context`` only changes acquisition identity.
ACQUISITION_SENSITIVE_STAGES = frozenset(
    {
        "generate-source-candidates",
        "synthesize-source-tasks",
        "plan-strategy",
        "report",
    }
)

# Explicit reruns are currently supported only for the source-recovery chain,
# whose downstream invalidation is declared with ``Stage.depends_on`` below.
# Other pipeline stages still rely on ``--force`` until their dependency edges
# are modeled; accepting them here would make resume reuse stale downstream work.
RERUN_SAFE_STAGES = frozenset(
    {"generate-source-candidates", "synthesize-source-tasks", "plan-strategy"}
)


@dataclass(frozen=True)
class Stage:
    name: str
    description: str
    outputs: tuple[Path, ...]
    run: Callable[["RecoveryRunner", "Stage"], dict[str, Any]]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryConfig:
    input_path: Path
    work_dir: Path
    preferred_name: str | None = None
    resume: bool = False
    force: bool = False
    rerun_stages: tuple[str, ...] = ()
    stop_after: str | None = None
    json_output: bool = False
    progress_width: int = 24
    stage_timeout: int = 300
    enable_byte_authority: bool = False
    enable_legacy_adapters: bool = False
    snapshot_existing_label: str | None = None
    function_analysis: str = "auto"
    function_facts_jsonl: Path | None = None
    context_paths: tuple[Path, ...] = ()
    context_pack: Path | None = None
    acquisition_bundle: Path | None = None
    source_task_limit: int = 500
    source_task_offset: int = 0
    source_synthesis_engine: str = "legacy"
    source_synthesis_mode: str = "clang"
    source_synthesis_limit: int = 25
    source_synthesis_offset: int = 0
    source_synthesis_max_variants: int = 4
    source_synthesis_diagnostic_priority_states: tuple[Path, ...] = ()
    source_synthesis_semantic_only: bool = False
    source_synthesis_skip_boundary_suspect: bool = False
    source_synthesis_verify_packaged_source: bool = False
    source_synthesis_upgrade_packaged_source: bool = False
    source_synthesis_strategies: tuple[str, ...] = ()
    source_synthesis_source_qualities: tuple[str, ...] = ()
    source_synthesis_vc_root: Path | None = None
    source_synthesis_wine: str = "wine"
    source_synthesis_wineprefix: Path | None = None
    steamless_cli: Path | None = None
    verify_workers: int = 0
    force_rematch: bool = False
    context_format: str = "json"
    context_binary_analysis: str = "standard"
    context_max_files: int = 1000
    context_max_depth: int = 4
    context_strings_limit: int = 500
    context_max_index_text_chars: int = 2_000
    context_extract_containers: bool = True
    context_include_low_signal_members: bool = False
    skip_enrichment: bool = False
    project: Path | None = None
    project_program: str | None = None
    ghidra_source_project: Path | None = None
    ghidra_source_program: str | None = None
    unity_project_out: Path | None = None
    unity_editor: Path | None = None
    unity_editor_version: str | None = None
    unity_max_memory_gb: float | None = None
    unity_max_texture_pixels: int | None = None
    unity_include_resources_assets: bool | None = None
    unity_repair_attempts: int = 3
    unity_editor_timeout: int = 3600
    unity_assetripper_cli: Path | None = None
    unity_assetripper_remote_host: str | None = None
    unity_assetripper_remote_input: str | None = None
    unity_assetripper_remote_output: str | None = None
    unity_assetripper_remote_port: int = 18086
    unity_assetripper_ssh_port: int = 22
    unity_ilspycmd: Path | None = None
    unity_install_mcp_bridge: bool = False
    # Program name used in operator-facing diagnostics emitted by the runner.
    # Callers with a live argparse ``prog`` (the recover CLI, the reconstruct
    # front door) should pass their effective name; this default preserves
    # the historical wording for callers that construct the config directly.
    display_prog: str = "agentdecompile-reconstruct"


class RecoveryRunner:
    def __init__(self, config: RecoveryConfig) -> None:
        self.config = config
        self.target: TargetIdentity | None = None
        self.run_dir = config.work_dir
        self.state = RunState(self.run_dir)
        self.cancelled = False
        self.completed_in_run: set[str] = set()
        self.stages = self._build_stages()

    def _build_stages(self) -> list[Stage]:
        return [
            Stage("discover", "resolve target binary and content identity", (self.run_dir / "target.json",), RecoveryRunner.stage_discover),
            Stage("inspect-capabilities", "inspect local tools and reusable proof surfaces", (self.run_dir / "capabilities.json",), RecoveryRunner.stage_inspect_capabilities),
            Stage("prepare-analysis-image", "prepare the binary image used for static analysis", (self.run_dir / "analysis-target.json",), RecoveryRunner.stage_prepare_analysis_image, ("discover",)),
            Stage("export-context", "export app/archive/resource context into LLM-readable files", (self.run_dir / "context-export/manifest.json",), RecoveryRunner.stage_export_context, ("discover",)),
            Stage("inventory-binary", "derive executable sections, imports, symbols, and code/data ranges", (self.run_dir / "binary-inventory.json",), RecoveryRunner.stage_inventory_binary, ("prepare-analysis-image",)),
            Stage("discover-functions", "join Ghidra-recorded function bodies with executable-image candidates", (self.run_dir / "function-candidates.json",), RecoveryRunner.stage_discover_functions, ("inventory-binary",)),
            Stage("analyze-functions", "enrich function candidates with tool-backed boundary analysis", (self.run_dir / "function-analysis.json",), RecoveryRunner.stage_analyze_functions, ("discover-functions", "inspect-capabilities")),
            Stage(
                "enrich-decompile",
                "PyGhidra enrich DB and decompile facts before source generation",
                (self.run_dir / "facts" / "enrich-receipt.json",),
                RecoveryRunner.stage_enrich_decompile,
                ("analyze-functions",),
            ),
            Stage("generate-source-candidates", "generate automatic source-candidate tasks from decompiler facts", (self.run_dir / "source-generation/summary.json",), RecoveryRunner.stage_generate_source_candidates, ("analyze-functions", "enrich-decompile")),
            Stage("synthesize-source-tasks", "compile and objdiff generated source tasks against bounded target slices", (self.run_dir / "source-synthesis/summary.json",), RecoveryRunner.stage_synthesize_source_tasks, ("generate-source-candidates",)),
            Stage("plan-strategy", "derive recovery strategy and required proof inputs", (self.run_dir / "strategy.json",), RecoveryRunner.stage_plan_strategy, ("synthesize-source-tasks",)),
            Stage("byte-authority", "optionally emit a byte-exact source authority package", (self.run_dir / "byte-authority/result.json",), RecoveryRunner.stage_byte_authority),
            Stage("legacy-adapter", "optionally dispatch compatible legacy target-specific adapters", (self.run_dir / "legacy-adapter.json",), RecoveryRunner.stage_legacy_adapter),
            Stage("snapshot-existing-recovery", "snapshot previously verified recovery artifacts for this target", (self.run_dir / "snapshot-existing-recovery.json",), RecoveryRunner.stage_snapshot_existing_recovery),
            Stage("unity-probe", "detect a Unity player and derive its version, backend, scenes, and assemblies", (self.run_dir / "unity/probe.json",), RecoveryRunner.stage_unity_probe),
            Stage("unity-plan", "plan Unity asset export against a memory budget and select an editor", (self.run_dir / "unity/plan.json",), RecoveryRunner.stage_unity_plan),
            Stage("unity-export-assets", "export Unity scenes/prefabs/assets into a reopenable project tree", (self.run_dir / "unity/assetripper.json",), RecoveryRunner.stage_unity_export_assets),
            Stage("unity-decompile-managed", "decompile shipped game assemblies to editable C#", (self.run_dir / "unity/managed.json",), RecoveryRunner.stage_unity_decompile_managed),
            Stage("unity-compose-project", "compose an openable Unity project from exported assets and decompiled source", (self.run_dir / "unity/compose.json",), RecoveryRunner.stage_unity_compose_project),
            Stage("unity-recover-excluded-media", "recover importable media from containers omitted by the memory-budgeted project export", (self.run_dir / "unity/primary-content.json",), RecoveryRunner.stage_unity_recover_excluded_media),
            Stage("unity-editor-validate", "open the composed project headlessly and record compile/scene errors", (self.run_dir / "unity/validate.json",), RecoveryRunner.stage_unity_editor_validate),
            Stage("unity-repair", "apply diagnostic-driven repairs until the project opens cleanly or stops converging", (self.run_dir / "unity/repair.json",), RecoveryRunner.stage_unity_repair),
            Stage("report", "write aggregate run report", (self.run_dir / "report.json",), RecoveryRunner.stage_report),
        ]

    def run(self) -> int:
        signal.signal(signal.SIGINT, self._cancel)
        signal.signal(signal.SIGTERM, self._cancel)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        selected = self.selected_stages()
        invalidated_stages = self.rerun_dependency_closure()
        if invalidated_stages:
            for stage_name in invalidated_stages - selected:
                receipt = self.state.data.get("stages", {}).get(stage_name)
                if isinstance(receipt, dict) and receipt.get("status") == "complete":
                    receipt["status"] = "invalidated"
                    receipt["invalidatedBy"] = sorted(self.config.rerun_stages)
                    receipt["invalidationReason"] = "an upstream stage was explicitly rerun"
            self.state.save()
        stage_timings: list[dict[str, Any]] = []
        for index, stage in enumerate(self.stages, start=1):
            if stage.name not in selected:
                continue
            if self.cancelled:
                self.mark_cancelled(stage.name)
                self._write_stage_timings(stage_timings)
                return 130
            if self.should_skip(stage):
                self.progress(index, stage, "resume: existing complete receipt")
                self.state.event("stage-skip", stage=stage.name, reason="resume-complete")
                stage_timings.append(
                    {
                        "stage": stage.name,
                        "status": "skipped-resume",
                        "durationSeconds": 0,
                    }
                )
                continue
            self.invalidate_downstream(stage.name)
            started = time.monotonic()
            self.progress(index, stage, stage.description)
            receipt = self.state.stage_receipt(stage.name)
            receipt.update(
                {
                    "status": "running",
                    "startedAt": now(),
                    "description": stage.description,
                    "config": self.stage_config(stage),
                    "configFingerprint": self.stage_fingerprint(stage),
                }
            )
            self.state.save()
            self.state.event("stage-start", stage=stage.name, description=stage.description)
            try:
                summary = stage.run(self, stage)
            except ToolchainError as exc:
                stage_timings.append(
                    {
                        "stage": stage.name,
                        "status": "blocked:toolchain",
                        "durationSeconds": round(time.monotonic() - started, 3),
                        "error": str(exc),
                    }
                )
                self._write_stage_timings(stage_timings)
                self.stage_failed(stage, started, str(exc), 2)
                self.state.data["status"] = "blocked:toolchain"
                self.state.data["terminalStatus"] = "blocked:toolchain"
                self.state.save()
                return 2
            except subprocess.CalledProcessError as exc:
                stage_timings.append(
                    {
                        "stage": stage.name,
                        "status": "failed",
                        "durationSeconds": round(time.monotonic() - started, 3),
                        "error": command_error(exc),
                    }
                )
                self._write_stage_timings(stage_timings)
                self.stage_failed(stage, started, command_error(exc), exc.returncode)
                return exc.returncode or 1
            except Exception as exc:
                stage_timings.append(
                    {
                        "stage": stage.name,
                        "status": "failed",
                        "durationSeconds": round(time.monotonic() - started, 3),
                        "error": str(exc),
                    }
                )
                self._write_stage_timings(stage_timings)
                self.stage_failed(stage, started, str(exc), 1)
                return 1
            if stage_summary_needs_retry(summary):
                duration = round(time.monotonic() - started, 3)
                reason = str(summary.get("reason") or summary.get("error") or f"{stage.name} reported {summary['status']}")
                reported_code = summary.get("returnCode")
                if reported_code is None:
                    reported_code = summary.get("exitCode")
                if reported_code is None:
                    reported_code = summary.get("tunnelExitCode")
                try:
                    return_code = int(reported_code)
                    if return_code == 0:
                        return_code = 1
                except (TypeError, ValueError):
                    return_code = 1
                stage_timings.append(
                    {
                        "stage": stage.name,
                        "status": "failed",
                        "durationSeconds": duration,
                        "error": reason,
                    }
                )
                self._write_stage_timings(stage_timings)
                self.stage_failed(stage, started, reason, return_code)
                receipt = self.state.stage_receipt(stage.name)
                receipt["summary"] = summary
                self.state.save()
                return return_code
            self.completed_in_run.add(stage.name)
            duration = round(time.monotonic() - started, 3)
            receipt.update(
                {
                    "status": "complete",
                    "completedAt": now(),
                    "durationSeconds": duration,
                    "outputs": [str(path) for path in stage.outputs],
                    "summary": summary,
                    "config": self.stage_config(stage),
                    "configFingerprint": self.stage_fingerprint(stage),
                }
            )
            self.state.save()
            self.state.event("stage-complete", stage=stage.name, summary=summary)
            stage_timings.append({"stage": stage.name, "status": "complete", "durationSeconds": duration})
            print(
                f"stage-timing: {stage.name} {duration}s",
                file=sys.stderr,
                flush=True,
            )
        self._write_stage_timings(stage_timings)
        return 0

    def _write_stage_timings(self, rows: list[dict[str, Any]]) -> None:
        payload = {
            "schema": "agentdecompile.stage-timings.v1",
            "workDir": str(self.run_dir),
            "stages": rows,
            "totalSeconds": round(sum(float(row.get("durationSeconds") or 0) for row in rows), 3),
        }
        atomic_write_json(self.run_dir / "stage-timings.json", payload)

    def selected_stages(self) -> set[str]:
        names = [stage.name for stage in self.stages]
        unknown_reruns = sorted(set(self.config.rerun_stages) - set(names))
        if unknown_reruns:
            raise SystemExit(f"unknown --rerun-stage {unknown_reruns[0]!r}; choices: {', '.join(names)}")
        unsupported_reruns = sorted(set(self.config.rerun_stages) - RERUN_SAFE_STAGES)
        if unsupported_reruns:
            choices = ", ".join(sorted(RERUN_SAFE_STAGES))
            raise SystemExit(
                f"--rerun-stage is currently supported only for {choices}; "
                "use --force until dependency invalidation is modeled for other stages"
            )
        if self.config.stop_after is None:
            return set(names)
        if self.config.stop_after not in names:
            raise SystemExit(f"unknown --stop-after {self.config.stop_after!r}; choices: {', '.join(names)}")
        return set(names[: names.index(self.config.stop_after) + 1])

    def should_skip(self, stage: Stage) -> bool:
        if not self.config.resume:
            return False
        if self.config.force:
            return False
        if stage.name in self.rerun_dependency_closure():
            return False
        if stage.name == "report" and self.completed_in_run:
            return False
        if set(stage.depends_on) & self.completed_in_run:
            return False
        if self.config.force_rematch and stage.name == "synthesize-source-tasks":
            return False
        receipt = self.state.data.get("stages", {}).get(stage.name, {})
        if receipt.get("status") != "complete":
            return False
        summary = receipt.get("summary")
        if stage_summary_needs_retry(summary):
            return False
        if stage.name == "unity-recover-excluded-media" and isinstance(summary, dict):
            if summary.get("missingPlannedContainers"):
                return False
            failed = summary.get("failed")
            if isinstance(failed, (int, float)) and failed > 0:
                return False
        if receipt.get("configFingerprint") != self.stage_fingerprint(stage):
            return False
        if stage.name == "unity-recover-excluded-media":
            primary_receipt = self._load_unity_json("primary-content.json")
            if primary_receipt.get("ownershipSchema") or not isinstance(summary, dict) or summary.get("status") != "skipped":
                project_out = self.config.unity_project_out
                if project_out is None:
                    return False
                try:
                    if not _media_receipt_matches_output(primary_receipt, project_out.expanduser().resolve()):
                        return False
                except (OSError, ValueError):
                    return False
        return all(path.exists() for path in stage.outputs)

    def invalidate_downstream(self, stage_name: str) -> None:
        """Persist dependency invalidation before rerunning an upstream stage.

        This keeps a stop-after/resume boundary safe: downstream receipts cannot
        remain reusable merely because the upstream refresh happened in a prior
        process. Their artifacts stay on disk as salvageable evidence.
        """

        affected = {stage_name}
        changed = True
        while changed:
            changed = False
            for stage in self.stages:
                if stage.name not in affected and set(stage.depends_on) & affected:
                    affected.add(stage.name)
                    changed = True
        if stage_name != "report":
            affected.add("report")
        invalidated: list[str] = []
        for name in sorted(affected - {stage_name}):
            receipt = self.state.data.get("stages", {}).get(name)
            if isinstance(receipt, dict) and receipt.get("status") == "complete":
                receipt["status"] = "invalidated"
                receipt["invalidatedBy"] = stage_name
                receipt["invalidationReason"] = "an upstream stage is being refreshed"
                invalidated.append(name)
        if invalidated:
            self.state.save()

    def rerun_dependency_closure(self) -> set[str]:
        """Include declared downstream stages and always refresh the aggregate report."""
        affected = set(self.config.rerun_stages)
        changed = True
        while changed:
            changed = False
            for stage in self.stages:
                if stage.name not in affected and set(stage.depends_on) & affected:
                    affected.add(stage.name)
                    changed = True
        if affected:
            affected.add("report")
        return affected

    def stage_config(self, stage: Stage) -> dict[str, Any]:
        source_batch_stage = stage.name in {"generate-source-candidates", "synthesize-source-tasks", "report"}
        compiler_stage = stage.name in {"synthesize-source-tasks", "plan-strategy", "report"}
        config: dict[str, Any] = {
            "input": str(self.config.input_path),
            "preferredName": self.config.preferred_name,
            "enableByteAuthority": self.config.enable_byte_authority if stage.name in {"byte-authority", "report"} else None,
            "enableLegacyAdapters": self.config.enable_legacy_adapters,
            "snapshotExistingLabel": self.config.snapshot_existing_label,
            "functionAnalysis": self.config.function_analysis,
            "skipEnrichment": self.config.skip_enrichment,
            "sourceTaskLimit": self.config.source_task_limit if source_batch_stage else 500,
            "sourceTaskOffset": self.config.source_task_offset if source_batch_stage else 0,
            "sourceSynthesisEngine": self.config.source_synthesis_engine,
            "sourceSynthesisMode": self.config.source_synthesis_mode,
            "sourceSynthesisLimit": self.config.source_synthesis_limit if compiler_stage else 50,
            "sourceSynthesisOffset": self.config.source_synthesis_offset if compiler_stage else 0,
            "sourceSynthesisMaxVariants": self.config.source_synthesis_max_variants,
            "sourceSynthesisDiagnosticPriorityStates": (
                [
                    {
                        "path": str(path.expanduser().resolve()),
                        "sha256": sha256_file(path.expanduser().resolve())
                        if path.expanduser().resolve().is_file()
                        else None,
                    }
                    for path in self.config.source_synthesis_diagnostic_priority_states
                ]
                if stage.name == "synthesize-source-tasks"
                else None
            ),
            "sourceSynthesisSemanticOnly": self.config.source_synthesis_semantic_only,
            "sourceSynthesisSkipBoundarySuspect": self.config.source_synthesis_skip_boundary_suspect,
            "sourceSynthesisVerifyPackagedSource": self.config.source_synthesis_verify_packaged_source,
            "sourceSynthesisUpgradePackagedSource": self.config.source_synthesis_upgrade_packaged_source,
            "sourceSynthesisStrategies": list(self.config.source_synthesis_strategies),
            "sourceSynthesisSourceQualities": list(self.config.source_synthesis_source_qualities),
            "sourceSynthesisVcRoot": (
                str(self.config.source_synthesis_vc_root)
                if self.config.source_synthesis_vc_root
                and compiler_stage
                else None
            ),
            "sourceSynthesisWine": self.config.source_synthesis_wine,
            "sourceSynthesisWineprefix": (
                str(self.config.source_synthesis_wineprefix)
                if self.config.source_synthesis_wineprefix
                and compiler_stage
                else None
            ),
            "steamlessCli": str(self.config.steamless_cli) if self.config.steamless_cli else None,
            "contextFormat": self.config.context_format,
            "contextBinaryAnalysis": self.config.context_binary_analysis,
            "contextMaxFiles": self.config.context_max_files,
            "contextMaxDepth": self.config.context_max_depth,
            "contextStringsLimit": self.config.context_strings_limit,
            "contextMaxIndexTextChars": self.config.context_max_index_text_chars,
            "contextExtractContainers": self.config.context_extract_containers,
            "contextIncludeLowSignalMembers": self.config.context_include_low_signal_members,
            "stageTimeout": self.config.stage_timeout,
            "stage": stage.name,
        }
        if stage.name == "unity-export-assets":
            config["unityAssetRipperRemote"] = {
                "host": self.config.unity_assetripper_remote_host,
                "input": self.config.unity_assetripper_remote_input,
                "output": self.config.unity_assetripper_remote_output,
                "port": self.config.unity_assetripper_remote_port,
                "sshPort": self.config.unity_assetripper_ssh_port,
            }
        if stage.name == "unity-plan":
            config["unityPlan"] = {
                "maxMemoryGb": self.config.unity_max_memory_gb,
                "includeResourcesAssets": self.config.unity_include_resources_assets,
                "editorVersion": self.config.unity_editor_version,
                "editorPath": str(self.config.unity_editor) if self.config.unity_editor else None,
            }
        if stage.name in {"unity-compose-project", "unity-recover-excluded-media", "unity-editor-validate", "unity-repair"}:
            config["unityProjectOut"] = (
                str(self.config.unity_project_out.expanduser().resolve())
                if self.config.unity_project_out
                else None
            )
        if stage.name == "unity-recover-excluded-media":
            probe = self._load_unity_json("probe.json")
            plan = self._load_unity_json("plan.json")
            export_plan = plan.get("export") or {}
            data_dir = Path(str(probe["dataDir"])) if probe.get("dataDir") else None
            excluded = set(export_plan.get("excludedContainers") or [])
            sources = (
                _unity_excluded_media_sources(data_dir, excluded)
                if data_dir is not None and data_dir.is_dir()
                else {
                    "selectedOwners": [],
                    "associatedCompanions": [],
                    "missingOwners": sorted(
                        name for name in excluded
                        if not _unity_resource_companion_owner_names(name)
                    ),
                    "plannedCompanions": sorted(
                        name for name in excluded
                        if _unity_resource_companion_owner_names(name)
                    ),
                    "unavailablePlannedCompanions": sorted(
                        name for name in excluded
                        if _unity_resource_companion_owner_names(name)
                    ),
                    "unassociatedPlannedCompanions": [],
                }
            )
            config["excludedMediaRecovery"] = {
                "dataDir": str(data_dir.resolve()) if data_dir else None,
                "excludedContainers": sorted(excluded),
                "sourceFiles": [
                    _unity_source_identity(path)
                    for path in sources["selectedOwners"]
                ],
                "resourceCompanions": [
                    _unity_source_identity(path)
                    for path in sources["associatedCompanions"]
                ],
                "plannedResourceCompanions": sources["plannedCompanions"],
                "unavailableResourceCompanions": sources[
                    "unavailablePlannedCompanions"
                ],
                "unassociatedResourceCompanions": sources[
                    "unassociatedPlannedCompanions"
                ],
                "missingPlannedContainers": sources["missingOwners"],
            }
        if stage.name in ACQUISITION_SENSITIVE_STAGES:
            # Stable bundle identity — not ephemeral --context path lists — so mid-run
            # re-acquire invalidates only stages that consume acquisition facts.
            config["acquisitionIdentity"] = self.acquisition_identity()
            config["freshEnrichmentIdentity"] = self.fresh_enrichment_identity()
        if stage.name in {"discover-functions", "enrich-decompile"} and self.config.ghidra_source_project is not None:
            config["ghidraFunctionSource"] = self.ghidra_function_source_identity()
        if stage.name == "enrich-decompile" and self.config.project is not None:
            from .reconstruct_enrich import resolve_existing_project_source

            try:
                config["sourceProject"] = resolve_existing_project_source(
                    self.config.project,
                    self.config.project_program,
                )
            except Exception as exc:  # stage reports the full error when it runs
                config["sourceProject"] = {
                    "project": str(self.config.project.expanduser().resolve()),
                    "program": self.config.project_program,
                    "error": str(exc),
                }
        return config

    def ghidra_function_source_identity(self) -> dict[str, Any]:
        """Include the selected project database revision in discovery resume keys."""

        from .ghidra_db import find_program, list_programs, resolve_project_root

        root = resolve_project_root(self.config.ghidra_source_project).resolve()
        wanted = self.config.ghidra_source_program
        entry = find_program(root, wanted) if wanted else None
        if entry is None and not wanted:
            entries = list_programs(root)
            if len(entries) == 1:
                entry = entries[0]
        if entry is None:
            return {
                "root": str(root),
                "program": wanted,
                "status": "missing-or-ambiguous",
            }
        info = entry.database_path.stat()
        return {
            "root": str(root),
            "program": entry.project_path,
            "databaseVersion": entry.version,
            "databasePath": str(entry.database_path.resolve()),
            "databaseSize": info.st_size,
            "databaseMtimeNs": info.st_mtime_ns,
            "databaseDevice": info.st_dev,
            "databaseInode": info.st_ino,
        }

    def fresh_enrichment_identity(self) -> dict[str, Any] | None:
        """Identify fresh, target-bound Ghidra facts produced by this run.

        Acquisition may legitimately contain no decompiler projection.  Source
        generation must still notice when the preceding enrich stage produced
        facts, and resume must invalidate its later receipts when those facts
        change.
        """
        receipt_path = self.run_dir / "facts" / "enrich-receipt.json"
        if not receipt_path.is_file():
            return None
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None
        if receipt.get("status") != "complete":
            return None
        target_path = self.run_dir / "target.json"
        if target_path.is_file():
            try:
                target = json.loads(target_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                return None
            if receipt.get("analysisBinarySha256") != target.get("sha256"):
                return None
        facts_path = Path(str(receipt.get("factsJsonl") or self.run_dir / "facts" / "function-facts.jsonl"))
        if not facts_path.is_file() or facts_path.stat().st_size == 0:
            return None
        return {
            "kind": "freshEnrichmentFacts",
            "path": str(facts_path),
            "analysisBinarySha256": receipt.get("analysisBinarySha256"),
            "functionCount": receipt.get("functionCount"),
            "sha256": hashlib.sha256(facts_path.read_bytes()).hexdigest(),
        }

    def fresh_enrichment_facts_path(self, target: dict[str, Any]) -> Path | None:
        identity = self.fresh_enrichment_identity()
        if identity is None or identity.get("analysisBinarySha256") != target.get("sha256"):
            return None
        path = Path(str(identity["path"]))
        return path if path.is_file() and path.stat().st_size else None

    def merge_function_fact_sources(self, sources: list[Path]) -> Path | None:
        unique: list[Path] = []
        seen: set[Path] = set()
        for source in sources:
            if not source.is_file() or source.stat().st_size == 0:
                continue
            resolved = source.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(source)
        if not unique:
            return None
        if len(unique) == 1:
            return unique[0]
        merged = self.run_dir / "context-pack" / "merged-function-facts.jsonl"
        merged.parent.mkdir(parents=True, exist_ok=True)
        pending = merged.with_suffix(".jsonl.tmp")
        with pending.open("w", encoding="utf-8") as out:
            for source in unique:
                source_text = source.read_text(encoding="utf-8", errors="replace")
                out.write(source_text)
                if source_text and not source_text.endswith("\n"):
                    out.write("\n")
        pending.replace(merged)
        return merged

    def acquisition_identity(self) -> dict[str, Any]:
        """Content-stable acquisition identity for resume fingerprints.

        Prefer an explicit / registered acquisition bundle over CLI path lists so
        mid-run ``--context`` does not force every stage to re-run.
        """
        bundle_dir = self._resolve_acquisition_bundle_for_identity()
        if bundle_dir is not None:
            identity: dict[str, Any] = {
                "kind": "bundle",
                "bundleDir": str(bundle_dir.resolve()),
            }
            manifest_path = bundle_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    manifest = {}
                for key in ("targetFingerprint", "entityCount", "sourceCount", "conflictCount", "createdAt"):
                    if key in manifest:
                        identity[key] = manifest[key]
                facts_name = str(manifest.get("factsJsonl") or "function-facts.jsonl")
                facts_path = bundle_dir / facts_name
                if facts_path.is_file():
                    identity["factsSha256"] = hashlib.sha256(facts_path.read_bytes()).hexdigest()
            return identity
        if self.config.function_facts_jsonl is not None:
            facts = self.config.function_facts_jsonl
            identity = {"kind": "functionFacts", "path": str(facts)}
            if facts.is_file():
                identity["sha256"] = hashlib.sha256(facts.read_bytes()).hexdigest()
            return identity
        if self.config.context_pack is not None:
            return {"kind": "contextPack", "path": str(self.config.context_pack.resolve())}
        if self.config.context_paths:
            return {
                "kind": "contextPaths",
                "paths": sorted(str(path.resolve()) for path in self.config.context_paths),
            }
        return {"kind": "none"}

    def _resolve_acquisition_bundle_for_identity(self) -> Path | None:
        """Locate the acquisition bundle without mutating the run directory."""
        if self.config.acquisition_bundle is not None:
            candidate = self.config.acquisition_bundle
            if (candidate / "manifest.json").exists():
                return candidate
        if self.config.context_pack is not None:
            candidate = self.config.context_pack
            if (candidate / "manifest.json").exists() and (candidate / "entities.jsonl").exists():
                return candidate
            nested = candidate / "acquisition-bundle"
            if (nested / "manifest.json").exists():
                return nested
        latest = self.run_dir / "acquisition" / "latest.json"
        if latest.exists():
            try:
                pointer = json.loads(latest.read_text(encoding="utf-8"))
                candidate = Path(str(pointer.get("bundleDir") or ""))
                if candidate.is_dir() and (candidate / "manifest.json").exists():
                    return candidate
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        return None

    def stage_fingerprint(self, stage: Stage) -> str:
        return config_fingerprint(self.stage_config(stage))

    def progress(self, index: int, stage: Stage, message: str) -> None:
        if self.config.json_output:
            print(json.dumps({"event": "progress", "stage": stage.name, "index": index, "total": len(self.stages), "message": message}), flush=True)
            return
        done = int(self.config.progress_width * (index - 1) / max(len(self.stages), 1))
        bar = "#" * done + "-" * (self.config.progress_width - done)
        print(f"[{bar}] {index}/{len(self.stages)} {stage.name}: {message}", flush=True)

    def _cancel(self, signum: int, _frame: Any) -> None:
        self.cancelled = True
        self.state.event("cancel-requested", signal=signum)

    def mark_cancelled(self, stage_name: str) -> None:
        self.state.data["status"] = "cancelled"
        self.state.data["cancelledAt"] = now()
        self.state.data["cancelledDuring"] = stage_name
        self.state.save()

    def stage_failed(self, stage: Stage, started: float, reason: str, return_code: int) -> None:
        receipt = self.state.stage_receipt(stage.name)
        receipt.update(
            {
                "status": "failed",
                "completedAt": now(),
                "durationSeconds": round(time.monotonic() - started, 3),
                "reason": reason,
                "returnCode": return_code,
            }
        )
        self.state.save()
        self.state.event("stage-failed", stage=stage.name, reason=reason, returnCode=return_code)

    def load_target(self) -> TargetIdentity:
        if self.target is not None:
            return self.target
        target_path = self.run_dir / "target.json"
        if target_path.exists():
            data = json.loads(target_path.read_text(encoding="utf-8"))
            self.target = TargetIdentity(
                input_path=Path(data["inputPath"]),
                binary_path=Path(data["binaryPath"]),
                sha256=data["sha256"],
                size=int(data["size"]),
                format=data["format"],
                architecture_hint=data["architectureHint"],
                stable_id=data["stableId"],
            )
            return self.target
        self.target = identify_binary(self.config.input_path, self.config.preferred_name)
        return self.target

    def load_analysis_target(self) -> TargetIdentity:
        target = self.load_target()
        analysis_path = target.binary_path
        analysis_file = self.run_dir / "analysis-target.json"
        analysis_data: dict[str, Any] = {}
        if analysis_file.exists():
            analysis_data = json.loads(analysis_file.read_text(encoding="utf-8"))
            analysis_path = Path(analysis_data.get("analysisBinaryPath") or analysis_path)
        if analysis_path == target.binary_path:
            return target
        container = analysis_data.get("container") if isinstance(analysis_data.get("container"), dict) else {}
        primary = container.get("primary") if isinstance(container.get("primary"), dict) else {}
        container_format = str(container.get("format") or analysis_data.get("craftPlatform") or target.format)
        if container_format == "nds" and primary:
            from .targets import sha256_file

            return TargetIdentity(
                input_path=target.input_path,
                binary_path=analysis_path,
                sha256=sha256_file(analysis_path),
                size=analysis_path.stat().st_size,
                format="nds",
                architecture_hint=str(primary.get("architectureHint") or target.architecture_hint or "armv5te"),
                stable_id=target.stable_id,
            )
        analysis = identify_binary(analysis_path, analysis_path.name)
        return TargetIdentity(
            input_path=target.input_path,
            binary_path=analysis.binary_path,
            sha256=analysis.sha256,
            size=analysis.size,
            format=analysis.format,
            architecture_hint=analysis.architecture_hint,
            stable_id=target.stable_id,
        )

    def stage_discover(self, _stage: Stage) -> dict[str, Any]:
        self.target = identify_binary(self.config.input_path, self.config.preferred_name)
        target_json = self.target.to_json()
        from .prompt_builder import craft_platform_for_target_format

        craft_platform = craft_platform_for_target_format(self.target.format)
        if craft_platform:
            target_json["craftPlatform"] = craft_platform
        atomic_write_json(self.run_dir / "target.json", target_json)
        self.state.data["target"] = target_json
        self.state.save()
        return target_json

    def stage_inspect_capabilities(self, _stage: Stage) -> dict[str, Any]:
        capabilities = inspect_capabilities(ROOT)
        atomic_write_json(self.run_dir / "capabilities.json", capabilities)
        return capabilities

    def stage_prepare_analysis_image(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_target()
        out_path = self.run_dir / "analysis-target.json"
        summary: dict[str, Any] = {
            "schema": "agentdecompile.analysis-target.v1",
            "originalBinaryPath": str(target.binary_path),
            "analysisBinaryPath": str(target.binary_path),
            "status": "original",
            "transform": None,
            "terminalStatus": None,
            "claimBoundary": "analysis image is for static recovery inputs; target identity remains the original binary",
        }
        if target.format == "nds":
            from .containers import prepare_container_for_analysis

            container = prepare_container_for_analysis(target.binary_path, self.run_dir)
            if container and container.get("analysisPath"):
                analysis_path = Path(str(container["analysisPath"]))
                summary.update(
                    {
                        "analysisBinaryPath": str(analysis_path),
                        "status": "transformed",
                        "transform": container.get("handling") or "container-extract",
                        "analysisSha256": sha256_file(analysis_path),
                        "analysisSize": analysis_path.stat().st_size,
                        "container": container.get("container"),
                        "craftPlatform": "nds",
                    }
                )
                if container.get("overlays"):
                    summary["containerOverlays"] = container["overlays"]
            atomic_write_json(out_path, summary)
            return summary
        if target.format == "pe":
            capabilities = json.loads((self.run_dir / "capabilities.json").read_text(encoding="utf-8"))
            mono = ((capabilities.get("tools") or {}).get("mono") or {}).get("available")
            packed = detect_pe_packed(target.binary_path, ROOT)
            try:
                steamless = resolve_steamless_cli(ROOT, self.config.steamless_cli)
            except ToolchainError as exc:
                if packed is not False:
                    summary.update(
                        {
                            "status": "blocked",
                            "terminalStatus": "blocked:toolchain",
                            "transformAttempted": "steamless-unpacked-pe",
                            "transformResult": str(exc.reason),
                            "transformDetail": exc.detail,
                        }
                    )
                    atomic_write_json(out_path, summary)
                    raise ToolchainError(exc.reason, detail=exc.detail) from exc
                steamless = None
            if packed and (not mono or steamless is None):
                summary.update(
                    {
                        "status": "blocked",
                        "terminalStatus": "blocked:toolchain",
                        "transformAttempted": "steamless-unpacked-pe",
                        "transformResult": "mono-or-steamless-unavailable",
                        "packedDetected": packed,
                    }
                )
                atomic_write_json(out_path, summary)
                raise ToolchainError(
                    "steamless-unavailable",
                    detail="packed PE requires mono + Steamless; refusing to continue on packed .text/.bind",
                )
            if mono and steamless is not None:
                image_dir = (self.run_dir / "analysis-image").resolve()
                image_dir.mkdir(parents=True, exist_ok=True)
                original_copy = image_dir / target.binary_path.name
                if not original_copy.exists() or original_copy.stat().st_size != target.binary_path.stat().st_size:
                    shutil.copy2(target.binary_path, original_copy)
                unpacked = Path(str(original_copy) + ".unpacked.exe")
                steamless_result: subprocess.CompletedProcess[str] | None = None
                if unpacked.exists():
                    # Never trust a leftover unpack without a fresh successful run.
                    unpacked.unlink()
                steamless_result = run_steamless(
                    steamless,
                    original_copy,
                    timeout=self.config.stage_timeout,
                )
                if steamless_result.returncode != 0 and unpacked.exists():
                    quarantine = unpacked.with_suffix(unpacked.suffix + ".failed")
                    unpacked.replace(quarantine)
                if steamless_result.returncode == 0 and unpacked.exists():
                    summary.update(
                        {
                            "analysisBinaryPath": str(unpacked),
                            "status": "transformed",
                            "transform": "steamless-unpacked-pe",
                            "transformTool": str(steamless),
                            "transformReturnCode": steamless_result.returncode,
                            "analysisSha256": sha256_file(unpacked),
                            "analysisSize": unpacked.stat().st_size,
                        }
                    )
                else:
                    summary.update(
                        {
                            "status": "original",
                            "transformAttempted": "steamless-unpacked-pe",
                            "transformTool": str(steamless),
                            "transformResult": "not-produced",
                            "transformReturnCode": steamless_result.returncode,
                            "transformStdout": steamless_result.stdout[-4000:],
                            "transformStderr": steamless_result.stderr[-4000:],
                            "packedDetected": packed,
                        }
                    )
                    if packed is not False:
                        summary["status"] = "blocked"
                        summary["terminalStatus"] = "blocked:toolchain"
                        atomic_write_json(out_path, summary)
                        raise ToolchainError(
                            "steamless-unpack-failed",
                            detail="Steamless failed or produced no unpack for a packed PE",
                        )
        atomic_write_json(out_path, summary)
        return summary

    def stage_export_context(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_target()
        manifest = export_context(
            ExportConfig(
                input_path=target.input_path,
                out_dir=self.run_dir / "context-export",
                output_format=self.config.context_format,
                binary_analysis=self.config.context_binary_analysis,
                extract_containers=self.config.context_extract_containers,
                include_low_signal_members=self.config.context_include_low_signal_members,
                max_files=self.config.context_max_files,
                max_depth=self.config.context_max_depth,
                strings_limit=self.config.context_strings_limit,
                max_index_text_chars=self.config.context_max_index_text_chars,
            )
        )
        return {
            "status": "complete",
            "manifest": str(self.run_dir / "context-export/manifest.json"),
            "filesVisited": manifest.get("filesVisited"),
            "filesExported": manifest.get("filesExported"),
            "truncated": manifest.get("truncated"),
            "outputFormat": manifest.get("outputFormat"),
        }

    def stage_inventory_binary(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_analysis_target()
        analysis_payload: dict[str, Any] = {}
        analysis_file = self.run_dir / "analysis-target.json"
        if analysis_file.exists():
            analysis_payload = json.loads(analysis_file.read_text(encoding="utf-8"))
        inventory = build_binary_inventory(target, analysis_target=analysis_payload)
        write_inventory(self.run_dir / "binary-inventory.json", inventory)
        summary = inventory.get("summary", {})
        return {
            "format": inventory.get("format"),
            "status": inventory.get("status"),
            "entryVa": inventory.get("entryVa"),
            "summary": summary,
        }

    def stage_discover_functions(self, _stage: Stage) -> dict[str, Any]:
        inventory = json.loads((self.run_dir / "binary-inventory.json").read_text(encoding="utf-8"))
        candidates = discover_function_candidates(inventory)
        project_summary: dict[str, Any] | None = None
        if self.config.ghidra_source_project is not None:
            candidates, project_summary = self.merge_ghidra_project_functions(
                candidates, inventory
            )
        write_function_candidates(self.run_dir / "function-candidates.json", candidates)
        summary = dict(candidates.get("summary") or {})
        if project_summary is not None:
            summary["ghidraProject"] = project_summary
        if inventory.get("format") in {"elf", "macho"}:
            from .slice_verify import write_slice_verify_summary

            slice_summary = write_slice_verify_summary(self.run_dir, inventory, candidates)
            summary["sliceVerify"] = slice_summary.get("status")
        return summary

    def merge_ghidra_project_functions(
        self,
        candidates: dict[str, Any],
        inventory: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Join exact Ghidra function identities and recorded bodies to discovery.

        Project metadata is admitted only after its original FileBytes hash is
        shown to be the current recovery target. Function body ranges are
        rebased by image-relative offsets and never flattened when discontiguous.
        """

        from .ghidra_db import find_program, list_programs, open_project_program, resolve_project_root

        root = resolve_project_root(self.config.ghidra_source_project).resolve()
        wanted = self.config.ghidra_source_program
        entry = find_program(root, wanted) if wanted else None
        if entry is None and not wanted:
            entries = list_programs(root)
            if len(entries) == 1:
                entry = entries[0]
        if entry is None:
            raise ValueError(
                f"Ghidra function source does not select exactly one program: {root} ({wanted or 'unspecified'})"
            )

        target = self.load_target()
        database_path = entry.database_path
        before = database_path.stat()
        with open_project_program(root, entry.project_path) as program:
            sources = program.file_bytes_sources()
            if len(sources) != 1:
                raise ValueError(
                    f"{entry.project_path}: expected one original FileBytes source before joining Ghidra functions; "
                    f"found {len(sources)}"
                )
            digest = hashlib.sha256()
            byte_count = 0
            for chunk in program.iter_original_file_chunks(sources[0].source_id):
                digest.update(chunk)
                byte_count += len(chunk)
            if digest.hexdigest() != target.sha256 or byte_count != target.size:
                raise ValueError(
                    f"Ghidra function source FileBytes does not match the recovery target "
                    f"({digest.hexdigest()} / {byte_count} bytes != {target.sha256} / {target.size})"
                )

            scope_table_present = program.table("Range Map - SCOPE ADDRESSES") is not None
            bodies = program.function_body_ranges()
            project_functions = list(program.functions())
            target_image_base = inventory.get("imageBase")
            target_image_base = int(target_image_base) if target_image_base is not None else None
            existing = list(candidates.get("candidates") or [])
            names_at_address: dict[int, str] = {}
            for row in existing:
                address = row.get("address")
                name = str(row.get("name") or "")
                if address is not None and name and not name.startswith(("FUN_", "SUB_", "entry_", "range_")):
                    names_at_address.setdefault(int(address), name)

            added: list[dict[str, Any]] = []
            body_function_count = 0
            noncontiguous_count = 0
            missing_body_count = 0
            out_of_file_count = 0

            def target_address(decoded: Any) -> int:
                if decoded.is_image_relative and target_image_base is not None:
                    return target_image_base + decoded.offset
                return decoded.offset

            code_ranges = inventory.get("codeRanges") or []
            for function in project_functions:
                if function.address is None or not function.address.is_memory:
                    continue
                address = target_address(function.address)
                function_ranges = bodies.get(function.symbol_id, [])
                rows = []
                for body in function_ranges:
                    start = target_address(body.start)
                    end = target_address(body.end)
                    if end < start:
                        raise ValueError(
                            f"{entry.project_path}: rebased function {function.symbol_id} range is reversed"
                        )
                    rows.append(
                        {
                            "startVa": start,
                            "endVaInclusive": end,
                            "size": end - start + 1,
                            "addressSpace": body.start.space_name,
                            "imageRelative": body.start.is_image_relative,
                        }
                    )
                starts_at_entry = any(int(row["startVa"]) == address for row in rows)
                if not scope_table_present:
                    boundary_status = "unavailable"
                    size = 0
                elif not rows:
                    boundary_status = "missing"
                    missing_body_count += 1
                    size = 0
                elif len(rows) > 1:
                    boundary_status = "noncontiguous"
                    noncontiguous_count += 1
                    size = 0
                elif not starts_at_entry:
                    boundary_status = "entry-not-at-body-start"
                    size = 0
                else:
                    only = rows[0]
                    size = int(only["size"])
                    boundary_status = "contiguous"
                    body_function_count += 1
                    rva = address - target_image_base if target_image_base is not None else address
                    matching = next(
                        (
                            section
                            for section in code_ranges
                            if int(section.get("rva") or 0) <= rva
                            and rva < int(section.get("rva") or 0) + int(section.get("fileSize") or 0)
                        ),
                        None,
                    )
                    if matching is None or size > (
                        int(matching.get("fileSize") or 0)
                        - (rva - int(matching.get("rva") or 0))
                    ):
                        boundary_status = "outside-file-backed-code"
                        size = 0
                        body_function_count -= 1
                        out_of_file_count += 1

                name = function.name or names_at_address.get(address) or f"FUN_{address:08x}"
                row: dict[str, Any] = {
                    "name": name,
                    "address": address,
                    "size": size,
                    "source": "ghidra-project-function",
                    "confidence": "high",
                    "bodyBoundaryStatus": boundary_status,
                    "bodyRanges": rows,
                    "ghidraFunction": function.to_json(),
                    "evidence": {
                        "sources": ["ghidra-project-function", "ghidra-project-scope-addresses"]
                        if scope_table_present
                        else ["ghidra-project-function"],
                        "projectProgram": entry.project_path,
                        "projectDatabaseVersion": entry.version,
                        "functionSymbolId": function.symbol_id,
                        "boundaryAuthority": "Ghidra recorded function body" if boundary_status == "contiguous" else boundary_status,
                    },
                }
                if size > 0:
                    row["sizeSource"] = "ghidra-project-function-body"
                    row["sizeConfidence"] = "recorded"
                added.append(row)

            merged = dedupe_same_address_candidates(existing + added)
            merged.sort(key=lambda row: (int(row.get("address") or row.get("rva") or 0), row.get("name", "")))
            after = database_path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
            ):
                raise ValueError(
                    f"Ghidra database changed while its function metadata was being read: {database_path}"
                )
            result = {
                **candidates,
                "candidates": merged,
                "summary": summarize_candidates(merged),
            }
            return result, {
                "status": "complete",
                "projectProgram": entry.project_path,
                "projectDatabaseVersion": entry.version,
                "fileBytesSha256": digest.hexdigest(),
                "functionSymbols": len(project_functions),
                "functionCandidatesAdded": len(added),
                "distinctFunctionStarts": len({int(row["address"]) for row in added}),
                "recordedContiguousBodies": body_function_count,
                "recordedNoncontiguousBodies": noncontiguous_count,
                "functionsMissingRecordedBody": missing_body_count,
                "bodyOutsideFileBackedCode": out_of_file_count,
                "scopeAddressTablePresent": scope_table_present,
                "claimBoundary": "Ghidra stored function boundaries are analysis metadata, not recovered source or compilation proof",
            }

    def stage_analyze_functions(self, _stage: Stage) -> dict[str, Any]:
        out_path = self.run_dir / "function-analysis.json"
        candidates_path = self.run_dir / "function-candidates.json"
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        if self.config.function_analysis == "none":
            summary = {"status": "skipped", "reason": "--function-analysis none"}
            atomic_write_json(out_path, summary)
            return summary
        capabilities = json.loads((self.run_dir / "capabilities.json").read_text(encoding="utf-8"))
        objdump = (capabilities.get("tools") or {}).get("objdump") or {}
        if self.config.function_analysis in {"auto", "objdump"} and objdump.get("available"):
            target = self.load_analysis_target()
            analyzed = analyze_function_candidates_with_objdump(candidates, target.binary_path, self.config.stage_timeout)
            write_function_candidates(candidates_path, analyzed)
            atomic_write_json(out_path, analyzed.get("toolAnalysis", {}))
            if self.config.function_analysis == "objdump" or int((analyzed.get("toolAnalysis") or {}).get("candidatesAdded") or 0) > 0:
                return analyzed.get("toolAnalysis", {})
            candidates = analyzed
        summary = {"status": "skipped", "reason": f"no available analyzer for mode {self.config.function_analysis!r}"}
        atomic_write_json(out_path, summary)
        return summary

    def stage_enrich_decompile(self, _stage: Stage) -> dict[str, Any]:
        from .reconstruct_enrich import analysis_binary_from_work_dir, run_reconstruct_enrich

        candidates = json.loads((self.run_dir / "function-candidates.json").read_text(encoding="utf-8"))
        binary = analysis_binary_from_work_dir(self.run_dir)
        if binary is None:
            binary = self.load_analysis_target().binary_path
        if self.config.ghidra_source_project is not None:
            # The project already supplies the authoritative function manager.
            # Do not ask PyGhidra to decompile thousands of heuristic call/prologue
            # labels that are not recorded functions in that project.
            project_functions = [
                row
                for row in candidates.get("candidates") or []
                if row.get("source") == "ghidra-project-function"
            ]
            candidates = {**candidates, "candidates": project_functions}
        analysis_project = self.config.project
        analysis_program = self.config.project_program
        project_snapshot: dict[str, Any] | None = None
        if analysis_project is None and self.config.ghidra_source_project is not None:
            expected = (
                (self.state.data.get("stages", {}).get("discover-functions", {}).get("config") or {})
                .get("ghidraFunctionSource")
            )
            before = self.ghidra_function_source_identity()
            if expected is not None and expected != before:
                raise ValueError(
                    "Ghidra project changed after function discovery; resume so candidates are refreshed "
                    "before project-backed decompilation"
                )
            from .ghidra_db import resolve_project_root
            from .ghidra_db.store import native_local_checkout

            source_root = resolve_project_root(self.config.ghidra_source_project).resolve()
            analysis_project, project_snapshot = native_local_checkout(source_root, self.run_dir)
            after = self.ghidra_function_source_identity()
            if before != after:
                raise ValueError(
                    "Ghidra project changed while its local analysis snapshot was being admitted; "
                    "resume after the shared project is stable"
                )
            analysis_program = self.config.ghidra_source_program

        summary = run_reconstruct_enrich(
            binary=binary,
            work_dir=self.run_dir,
            candidates_payload=candidates,
            skip=self.config.skip_enrichment,
            project=analysis_project,
            project_program=analysis_program,
        )
        if project_snapshot is not None:
            summary = {**summary, "sharedProjectSnapshot": project_snapshot}
            atomic_write_json(self.run_dir / "facts" / "enrich-receipt.json", summary)
        return summary

    def resolve_acquisition_facts_source(self, target: dict[str, Any]) -> Path | None:
        # Prefer an explicit acquisition bundle (e.g. frontdoor mid-run snapshot with
        # prior merge) over rebuilding a path-only pack that would drop fused facts.
        bundle_dir: Path | None = self.config.acquisition_bundle
        compatibility_projection: Path | None = None
        legacy_sources: list[Path] = []
        if self.config.function_facts_jsonl:
            legacy_sources.append(self.config.function_facts_jsonl)
        if bundle_dir is None and self.config.context_pack:
            candidate = self.config.context_pack
            if (candidate / "manifest.json").exists() and (candidate / "entities.jsonl").exists():
                bundle_dir = candidate
            elif (candidate / "acquisition-bundle" / "manifest.json").exists():
                bundle_dir = candidate / "acquisition-bundle"
            else:
                packed = candidate / "function-facts.jsonl"
                if packed.exists():
                    legacy_sources.append(packed)
        if bundle_dir is None and self.config.context_paths:
            build_context_pack(
                contexts=list(self.config.context_paths),
                out_dir=self.run_dir / "context-pack",
                target=target,
                repo_root=ROOT,
            )
            bundle_dir = self.run_dir / "context-pack" / "acquisition-bundle"
            compatibility_projection = self.run_dir / "context-pack" / "function-facts.jsonl"
        if bundle_dir is None and not legacy_sources:
            bundle_dir = acquisition_registry.resolve_bundle(target=target, repo_root=ROOT)
        if bundle_dir:
            manifest, _entities, conflicts = load_bundle(bundle_dir)
            target_status = validate_bundle_target(manifest, target)
            facts_path = bundle_dir / str(manifest.get("factsJsonl") or "function-facts.jsonl")
            if not facts_path.exists():
                raise FileNotFoundError(f"bundle legacy facts projection missing: {facts_path}")
            fresh_facts = self.fresh_enrichment_facts_path(target)
            selected_facts = self.merge_function_fact_sources(
                [compatibility_projection or facts_path, fresh_facts] if fresh_facts else [compatibility_projection or facts_path]
            )
            atomic_write_json(
                self.run_dir / "acquisition-bundle.json",
                {
                    "schema": "agentdecompile.acquisition-bundle-binding.v1",
                    "status": target_status["status"],
                    "bundleDir": str(bundle_dir),
                    "bundleTargetFingerprint": manifest.get("targetFingerprint"),
                    "targetMatched": target_status["targetMatched"],
                    "conflictCount": len(conflicts),
                    "factsJsonl": str(facts_path),
                    "freshEnrichmentFactsJsonl": str(fresh_facts) if fresh_facts else None,
                    "selectedFactsJsonl": str(selected_facts) if selected_facts else None,
                    "claimBoundary": "bundle context is advisory acquisition evidence only; compile and objdiff gates remain required.",
                },
            )
            return selected_facts
        fresh_facts = self.fresh_enrichment_facts_path(target)
        if fresh_facts:
            legacy_sources.append(fresh_facts)
        sources = [path for path in legacy_sources if path.exists()]
        return self.merge_function_fact_sources(sources)

    def stage_plan_strategy(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_target()
        capabilities_path = self.run_dir / "capabilities.json"
        capabilities = json.loads(capabilities_path.read_text(encoding="utf-8"))
        inventory = json.loads((self.run_dir / "binary-inventory.json").read_text(encoding="utf-8"))
        functions = json.loads((self.run_dir / "function-candidates.json").read_text(encoding="utf-8"))
        source_generation = json.loads((self.run_dir / "source-generation/summary.json").read_text(encoding="utf-8"))
        source_synthesis = json.loads((self.run_dir / "source-synthesis/summary.json").read_text(encoding="utf-8"))
        strategy = build_strategy(target, capabilities, inventory, functions, source_generation, source_synthesis)
        atomic_write_json(self.run_dir / "strategy.json", strategy)
        return {
            "format": target.format,
            "architectureHint": target.architecture_hint,
            "blockers": strategy["blockers"],
            "lanes": {lane["name"]: lane["status"] for lane in strategy["lanes"]},
        }

    def stage_generate_source_candidates(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_target()
        candidates = json.loads((self.run_dir / "function-candidates.json").read_text(encoding="utf-8"))
        inventory = json.loads((self.run_dir / "binary-inventory.json").read_text(encoding="utf-8"))
        facts_jsonl = self.resolve_acquisition_facts_source(target.to_json()) or default_function_facts_path(self.run_dir)
        # A verification run must not silently discard acquired candidates.  The
        # old fixed window made a "complete" run process only the first slice
        # of the inventory, even when all source context was already present.
        source_limit = self.config.source_task_limit
        if self.config.source_synthesis_verify_packaged_source:
            # Candidate expansion can add acquired-context aliases beyond the
            # raw inventory; leave room for that deterministic expansion.
            source_limit = max(source_limit, len(candidates) * 2)
        summary = generate_source_candidates(
            target=RecoveryLanguageProfile.merge_into_target(target.to_json()),
            function_candidates=candidates,
            out_dir=self.run_dir / "source-generation",
            inventory=inventory,
            function_facts_jsonl=facts_jsonl,
            limit=source_limit,
            offset=self.config.source_task_offset,
        )
        truncation = summary.get("candidateTruncation") if isinstance(summary, dict) else None
        if isinstance(truncation, dict) and truncation.get("warning"):
            # A truncated run still reports success, so the only way an operator
            # learns the inventory was cut is if we say so here.
            print(f"{self.config.display_prog}: warning: {truncation['warning']}", file=sys.stderr)
        atomic_write_json(self.run_dir / "source-generation/summary.json", summary)
        return summary

    def stage_synthesize_source_tasks(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_target()
        out_dir = self.run_dir / "source-synthesis"
        summary_path = out_dir / "summary.json"
        mode = self.config.source_synthesis_mode
        tasks_path = self.run_dir / "source-generation" / "tasks.jsonl"
        if mode == "none":
            summary = {
                "schema": "agentdecompile.source-parity-synthesis-summary.v1",
                "status": "skipped",
                "reason": "disabled with --source-synthesis none",
                "sourceTasks": [str(tasks_path)],
                "claimBoundary": "source synthesis skipped; no source parity claim",
            }
            atomic_write_json(summary_path, summary)
            return summary
        if not tasks_path.exists():
            summary = {
                "schema": "agentdecompile.source-parity-synthesis-summary.v1",
                "status": "skipped",
                "reason": "source-generation/tasks.jsonl missing",
                "sourceTasks": [str(tasks_path)],
                "claimBoundary": "source synthesis skipped; no source parity claim",
            }
            atomic_write_json(summary_path, summary)
            return summary
        if self.config.source_synthesis_engine == "plugin":
            (out_dir / "empty-queue.jsonl").parent.mkdir(parents=True, exist_ok=True)
            (out_dir / "empty-queue.jsonl").write_text("", encoding="utf-8")
            summary = run_source_plugin_pipeline(
                SourcePluginRunConfig(
                    queue=out_dir / "empty-queue.jsonl",
                    source_tasks=[tasks_path],
                    source_tasks_only=True,
                    out_dir=out_dir,
                    limit=self.config.source_synthesis_limit,
                    offset=self.config.source_synthesis_offset,
                    max_variants_per_function=self.config.source_synthesis_max_variants,
                    max_retries=self.config.source_synthesis_max_variants,
                    strategies=set(self.config.source_synthesis_strategies) or None,
                    source_qualities=set(self.config.source_synthesis_source_qualities) or None,
                    compiler=compiler_for_source_synthesis_mode(mode),
                    clang="clang-cl" if mode == "clang-cl" else "clang",
                    dry_run=mode == "dry-run",
                    semantic_only=self.config.source_synthesis_semantic_only or mode == "msvc",
                    skip_boundary_suspect=self.config.source_synthesis_skip_boundary_suspect or mode == "msvc",
                    work_dir=self.run_dir,
                    clean=not self.config.resume,
                    resume=self.config.resume,
                    force_fresh=self.config.force_rematch,
                    vc_root=self.config.source_synthesis_vc_root,
                    wine=self.config.source_synthesis_wine,
                    wineprefix=self.config.source_synthesis_wineprefix,
                    timeout=self.config.stage_timeout,
                    target_sha=target.sha256,
                    bind_unlabeled_source_tasks_to_target=True,
                    diagnostic_priority_states=list(
                        self.config.source_synthesis_diagnostic_priority_states
                    ),
                )
            )
            export_summary = self.export_synthesized_source_slices(summary)
            summary["runRootRecoveredSourceExport"] = export_summary
            atomic_write_json(summary_path, summary)
            return summary
        if self.config.source_synthesis_engine != "legacy":
            raise ValueError(f"unknown source synthesis engine: {self.config.source_synthesis_engine}")
        argv = [
            "--queue",
            str(self.run_dir / "source-synthesis" / "empty-queue.jsonl"),
            "--source-tasks",
            str(tasks_path),
            "--source-tasks-only",
            "--remaining-features",
            str(self.run_dir / "source-synthesis" / "empty-remaining-features.jsonl"),
            "--retrieval",
            str(self.run_dir / "source-synthesis" / "empty-retrieval.jsonl"),
            "--out-dir",
            str(out_dir),
            "--limit",
            str(self.config.source_synthesis_limit),
            "--offset",
            str(self.config.source_synthesis_offset),
            "--max-variants-per-function",
            str(self.config.source_synthesis_max_variants),
            "--timeout",
            str(self.config.stage_timeout),
        ]
        if mode == "dry-run":
            argv.append("--dry-run")
        elif mode == "clang":
            argv.extend(["--compiler", "clang"])
        elif mode == "clang-cl":
            argv.extend(["--compiler", "clang-cl", "--clang", "clang-cl"])
        elif mode == "msvc":
            argv.extend(["--compiler", "msvc"])
            argv.append("--semantic-only")
            argv.append("--skip-boundary-suspect")
            argv.extend(
                [
                    "--diagnostic-cache-dir",
                    str((self.run_dir / "source-synthesis-diagnostics").resolve()),
                ]
            )
        else:
            raise ValueError(f"unknown source synthesis mode: {mode}")
        if self.config.source_synthesis_semantic_only and "--semantic-only" not in argv:
            argv.append("--semantic-only")
        if self.config.source_synthesis_skip_boundary_suspect and "--skip-boundary-suspect" not in argv:
            argv.append("--skip-boundary-suspect")
        if self.config.source_synthesis_verify_packaged_source:
            argv.append("--verify-packaged-source")
        if self.config.source_synthesis_upgrade_packaged_source:
            argv.append("--upgrade-packaged-source")
        if self.config.source_synthesis_strategies:
            argv.extend(["--strategies", ",".join(self.config.source_synthesis_strategies)])
        for quality in self.config.source_synthesis_source_qualities:
            argv.extend(["--source-quality", quality])
        if self.config.source_synthesis_vc_root:
            argv.extend(["--vc-root", str(self.config.source_synthesis_vc_root)])
        if self.config.source_synthesis_wine:
            argv.extend(["--wine", self.config.source_synthesis_wine])
        if self.config.source_synthesis_wineprefix:
            argv.extend(["--wineprefix", str(self.config.source_synthesis_wineprefix)])
        if self.config.verify_workers:
            argv.extend(["--workers", str(self.config.verify_workers)])
        if self.config.force_rematch:
            argv.append("--force-rematch")
        for state_path in self.config.source_synthesis_diagnostic_priority_states:
            argv.extend(["--diagnostic-priority-state", str(state_path.expanduser().resolve())])
        if self.config.source_synthesis_diagnostic_priority_states:
            argv.extend(["--target-sha", target.sha256])
            argv.extend(["--source-task-target-sha", target.sha256])
        (out_dir / "empty-queue.jsonl").parent.mkdir(parents=True, exist_ok=True)
        for empty in ("empty-queue.jsonl", "empty-remaining-features.jsonl", "empty-retrieval.jsonl"):
            (out_dir / empty).write_text("", encoding="utf-8")
        stdout = StringIO()
        with redirect_stdout(stdout):
            rc = source_parity_synthesize_main(argv)
        raw_stdout = stdout.getvalue()
        (out_dir / "synthesis.stdout").write_text(raw_stdout, encoding="utf-8")
        if rc != 0:
            raise subprocess.CalledProcessError(rc, ["source_parity_synthesize", *argv], output=raw_stdout)
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        else:
            summary = json.loads(raw_stdout)
        export_summary = self.export_synthesized_source_slices(summary)
        summary["recoveredSourceExport"] = export_summary
        atomic_write_json(summary_path, summary)
        return summary

    def export_synthesized_source_slices(self, synthesis_summary: dict[str, Any]) -> dict[str, Any]:
        summaries = []
        for key in ("codeSliceMatchesPath", "sourceShapeMatchesPath", "acceptedPath"):
            value = synthesis_summary.get(key)
            if value:
                summaries.append(Path(str(value)))
        if not summaries:
            return {
                "schema": "agentdecompile.recovered-source-export.v1",
                "status": "skipped",
                "reason": "source synthesis did not publish match JSONL paths",
                "claimBoundary": "no recovered source export was produced",
            }
        return export_recovered_source(
            summaries,
            out_dir=self.run_dir / "recovered-source",
            source_name="source_slices.c",
        )

    def stage_byte_authority(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_target()
        out_dir = self.run_dir / "byte-authority"
        result_path = out_dir / "result.json"
        if not self.config.enable_byte_authority:
            summary = {"status": "skipped", "reason": "enable with --byte-authority", "claimBoundary": "no semantic source claim"}
            atomic_write_json(result_path, summary)
            return summary
        rebuilt = out_dir / "package" / "rebuilt.bin"
        if rebuilt.is_file() and sha256_file(rebuilt) == target.sha256:
            summary = {
                "schema": "agentdecompile.byte-authority.v1",
                "status": "complete",
                "identical": True,
                "sha256Original": target.sha256,
                "sha256Rebuilt": target.sha256,
                "rebuilt": str(rebuilt),
                "claimBoundary": "Byte-identical assembly substrate; not recovered authored C/C++.",
            }
            atomic_write_json(result_path, summary)
            return summary
        one_shot_script = resolve_script_asset(ROOT, "one-shot-source.py")
        if one_shot_script is None:
            raise FileNotFoundError("one-shot-source.py is not available in checkout scripts or installed package data")
        cmd = [
            sys.executable,
            str(one_shot_script),
            "--binary",
            str(target.binary_path),
            "--out",
            str(out_dir / "package"),
            "--result-out",
            str(result_path),
        ]
        subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True, timeout=self.config.stage_timeout)
        return json.loads(result_path.read_text(encoding="utf-8"))

    def stage_legacy_adapter(self, _stage: Stage) -> dict[str, Any]:
        target = self.load_target()
        out_path = self.run_dir / "legacy-adapter.json"
        if not self.config.enable_legacy_adapters:
            summary = {"status": "skipped", "reason": "enable with --legacy-adapters"}
            atomic_write_json(out_path, summary)
            return summary
        summary = {
            "status": "not-dispatched",
            "reason": "legacy adapters remain target-specific and are intentionally isolated behind this explicit flag",
            "target": target.to_json(),
        }
        atomic_write_json(out_path, summary)
        return summary

    def stage_snapshot_existing_recovery(self, _stage: Stage) -> dict[str, Any]:
        out_path = self.run_dir / "snapshot-existing-recovery.json"
        label = self.config.snapshot_existing_label
        if not label:
            summary = {"status": "skipped", "reason": "enable with --snapshot-existing-recovery <label>"}
            atomic_write_json(out_path, summary)
            return summary
        target = self.load_target()
        summary = snapshot_existing_recovery(target.sha256, self.run_dir / "snapshots", label)
        atomic_write_json(out_path, summary)
        return summary

    # --- Unity reconstruction -------------------------------------------------
    #
    # These stages are inert for non-Unity targets: each writes a `skipped`
    # receipt and returns. They are ordered so that a `--stop-after` on any one
    # of them leaves a coherent, inspectable partial result.

    def unity_install_root(self) -> Path:
        """The game install directory (input may be the folder or the player exe)."""

        candidate = self.config.input_path.resolve()
        return candidate if candidate.is_dir() else candidate.parent

    def _unity_dir(self) -> Path:
        return self.run_dir / "unity"

    def _load_unity_json(self, name: str) -> dict[str, Any]:
        path = self._unity_dir() / name
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _unity_skip(self, out_path: Path, reason: str) -> dict[str, Any]:
        summary = {"status": "skipped", "reason": reason}
        atomic_write_json(out_path, summary)
        return summary

    def stage_unity_probe(self, _stage: Stage) -> dict[str, Any]:
        from .unity_probe import probe_unity_install

        out_path = self._unity_dir() / "probe.json"
        probe = probe_unity_install(self.unity_install_root())
        atomic_write_json(out_path, probe)
        return {
            "status": probe.get("status"),
            "detected": probe.get("detected"),
            "unityVersion": probe.get("unityVersion"),
            "scriptingBackend": probe.get("scriptingBackend"),
            "sceneCount": probe.get("sceneCount"),
            "managedAssemblyCount": probe.get("managedAssemblyCount"),
        }

    def stage_unity_plan(self, _stage: Stage) -> dict[str, Any]:
        from .unity_probe import build_unity_plan

        out_path = self._unity_dir() / "plan.json"
        probe = self._load_unity_json("probe.json")
        if not probe.get("detected"):
            return self._unity_skip(out_path, "target is not a Unity game")
        installed = None
        if self.config.unity_editor is not None:
            # An explicit editor path wins over Hub discovery; label it with the
            # requested version so drift reporting stays meaningful.
            version = self.config.unity_editor_version or str(probe.get("unityVersion") or "explicit")
            installed = {version: self.config.unity_editor}
        plan = build_unity_plan(
            probe,
            max_memory_gb=self.config.unity_max_memory_gb,
            include_resources_assets=self.config.unity_include_resources_assets,
            requested_editor_version=self.config.unity_editor_version,
            installed_editors=installed,
        )
        atomic_write_json(out_path, plan)
        return {
            "status": plan.get("status"),
            "blockedReason": plan.get("blockedReason"),
            "exportMode": (plan.get("export") or {}).get("mode"),
            "editorVersion": (plan.get("editor") or {}).get("selectedVersion"),
            "editorMatch": (plan.get("editor") or {}).get("match"),
            "versionDrift": (plan.get("editor") or {}).get("versionDrift"),
        }

    def stage_unity_export_assets(self, _stage: Stage) -> dict[str, Any]:
        from .unity_export import export_unity_project

        out_path = self._unity_dir() / "assetripper.json"
        probe = self._load_unity_json("probe.json")
        plan = self._load_unity_json("plan.json")
        if not probe.get("detected"):
            return self._unity_skip(out_path, "target is not a Unity game")
        if plan.get("status") == "blocked" and not self.config.unity_assetripper_remote_host:
            return self._unity_skip(out_path, str(plan.get("blockedReason") or "plan blocked"))

        remote_host = self.config.unity_assetripper_remote_host
        cli = None if remote_host else resolve_assetripper_cli(ROOT, self.config.unity_assetripper_cli)
        if cli is None and not remote_host:
            raise ToolchainError(
                "assetripper-missing",
                detail=f"set {ASSETRIPPER_ENV} or place an AssetRipper binary under target/assetripper/",
            )
        receipt = export_unity_project(
            self.unity_install_root(),
            self._unity_dir() / "assetripper",
            assetripper_cli=cli,
            plan=plan,
            staging_dir=self._unity_dir() / "staging",
            remote_host=remote_host,
            remote_input_path=self.config.unity_assetripper_remote_input,
            remote_output_path=self.config.unity_assetripper_remote_output,
            remote_port=self.config.unity_assetripper_remote_port,
            ssh_port=self.config.unity_assetripper_ssh_port,
        )
        atomic_write_json(out_path, receipt)
        return {
            "status": receipt.get("status"),
            "mode": receipt.get("mode"),
            "exportedProject": receipt.get("exportedProject"),
            "hasProjectVersion": receipt.get("hasProjectVersion"),
            "memoryFailureSuspected": receipt.get("memoryFailureSuspected"),
            "reason": receipt.get("reason"),
            "exitCode": receipt.get("exitCode"),
            "tunnelExitCode": receipt.get("tunnelExitCode"),
            "remoteExportResponseAccepted": receipt.get("remoteExportResponseAccepted"),
        }

    def stage_unity_decompile_managed(self, _stage: Stage) -> dict[str, Any]:
        from .unity_managed import decompile_game_assemblies

        out_path = self._unity_dir() / "managed.json"
        probe = self._load_unity_json("probe.json")
        if not probe.get("detected"):
            return self._unity_skip(out_path, "target is not a Unity game")
        if probe.get("scriptingBackend") != "mono":
            return self._unity_skip(
                out_path,
                f"scripting backend is {probe.get('scriptingBackend')}; managed decompilation needs Mono assemblies",
            )
        ilspycmd = resolve_ilspycmd(self.config.unity_ilspycmd)
        if ilspycmd is None:
            raise ToolchainError(
                "ilspycmd-missing",
                detail=f"install with `dotnet tool install -g ilspycmd` or set {ILSPYCMD_ENV}",
            )
        receipt = decompile_game_assemblies(
            Path(str(probe["dataDir"])),
            self._unity_dir() / "managed-csharp",
            ilspycmd=ilspycmd,
        )
        atomic_write_json(out_path, receipt)
        return {
            "status": receipt.get("status"),
            "requested": receipt.get("requested"),
            "decompiled": receipt.get("decompiled"),
            "failed": receipt.get("failed"),
            "totalFileCount": receipt.get("totalFileCount"),
            "strippedCount": receipt.get("strippedCount"),
        }

    def stage_unity_compose_project(self, _stage: Stage) -> dict[str, Any]:
        from .unity_compose import compose_unity_project

        out_path = self._unity_dir() / "compose.json"
        probe = self._load_unity_json("probe.json")
        if not probe.get("detected"):
            return self._unity_skip(out_path, "target is not a Unity game")
        if self.config.unity_project_out is None:
            return self._unity_skip(out_path, "no target project; pass --unity-project-out <dir>")
        export = self._load_unity_json("assetripper.json")
        exported_project = export.get("exportedProject")
        if not exported_project:
            return self._unity_skip(out_path, "no AssetRipper ExportedProject to compose from")

        managed = self._unity_dir() / "managed-csharp"
        receipt = compose_unity_project(
            Path(str(exported_project)),
            self.config.unity_project_out,
            managed_source=managed if managed.is_dir() else None,
            extra_packages=probe.get("impliedPackages") or {},
            install_root=self.unity_install_root(),
        )
        atomic_write_json(out_path, receipt)
        openable = receipt.get("openable") or {}
        return {
            "status": receipt.get("status"),
            "targetProject": str(self.config.unity_project_out),
            "openable": openable.get("ready"),
            "missing": openable.get("missing"),
            "filesCopied": receipt.get("totalFilesCopied"),
            "packagesAdded": (receipt.get("packages") or {}).get("added"),
            "warnings": receipt.get("warnings"),
        }

    def stage_unity_recover_excluded_media(self, _stage: Stage) -> dict[str, Any]:
        from .unity_assets import export_primary_content

        out_path = self._unity_dir() / "primary-content.json"
        probe = self._load_unity_json("probe.json")
        if not probe.get("detected"):
            return self._unity_skip(out_path, "target is not a Unity game")
        project_out = self.config.unity_project_out
        if project_out is None:
            return self._unity_skip(out_path, "no target project; pass --unity-project-out <dir>")
        composition = self._load_unity_json("compose.json")
        if composition.get("status") not in {"complete", "partial"}:
            return self._unity_skip(out_path, "the Unity project was not composed successfully")

        plan = self._load_unity_json("plan.json")
        export_plan = plan.get("export") or {}
        excluded = set(export_plan.get("excludedContainers") or [])
        data_dir = Path(str(probe.get("dataDir") or self.unity_install_root()))
        sources = _unity_excluded_media_sources(data_dir, excluded)
        selected = sources["selectedOwners"]
        companions = sources["associatedCompanions"]
        missing_planned = sources["missingOwners"]

        project_root = project_out.expanduser().resolve()
        assets_dir = project_root / "Assets"
        output_dir = assets_dir / "RecoveredPrimaryContent"
        if assets_dir.is_symlink() or not assets_dir.is_dir():
            atomic_write_json(out_path, {"status": "error", "reason": "project Assets directory is missing or is a symlink"})
            return {"status": "error", "reason": "project Assets directory is missing or is a symlink"}
        if output_dir.is_symlink() or not output_dir.resolve().is_relative_to(project_root):
            atomic_write_json(out_path, {"status": "error", "reason": "media output path escapes the target project through a symlink"})
            return {"status": "error", "reason": "media output path escapes the target project through a symlink"}
        if output_dir.exists() and not output_dir.is_dir():
            raise ValueError(f"media output path is not a directory: {output_dir}")
        existing = _media_output_files(output_dir)
        previous = self._load_unity_json("primary-content.json")
        owned = _media_owned_files(previous, project_root, output_dir)
        legacy_ownership = bool(existing) and "ownershipSchema" not in previous
        generated: dict[str, dict[str, int]] = {}
        preserved: list[str] = []
        removed: list[str] = []
        staging_root = Path(tempfile.mkdtemp(prefix=".RecoveredPrimaryContent-", dir=assets_dir))
        backups: list[tuple[Path, Path]] = []
        installed: list[tuple[Path, dict[str, int]]] = []
        created_dirs: list[Path] = []
        clean_staging = False
        try:
            if selected:
                staging_dir = staging_root / "export"
                receipt = export_primary_content(
                    install_root=self.unity_install_root(),
                    output_dir=staging_dir,
                    data_files=selected,
                    max_texture_pixels=self.config.unity_max_texture_pixels,
                )
            else:
                receipt = {
                    "schema": "agentdecompile.unity-primary-content-export.v1",
                    "status": "skipped",
                    "reason": "the memory-budgeted plan selected no excluded serialized owner files",
                    "outputDir": str(output_dir),
                    "selectedFiles": [],
                    "selectedTypes": [],
                }

            staged_files = _media_output_files(staging_root / "export") if receipt.get("status") != "error" else {}
            install_plan: list[tuple[str, Path, Path, dict[str, int] | None]] = []
            for relative, staged in sorted(staged_files.items()):
                target = output_dir / relative
                current = _media_file_identity(target)
                if target.exists() or target.is_symlink():
                    if current is None or current != owned.get(relative):
                        preserved.append(relative)
                        continue
                if target.parent.is_symlink() or (target.parent.exists() and not target.parent.is_dir()):
                    raise ValueError(f"media output type path is not a directory: {target.parent}")
                install_plan.append((relative, staged, target, current))

            remove_plan: list[tuple[str, Path, dict[str, int]]] = []
            # Reconcile only unchanged files recorded for this exact project.
            for relative, identity in sorted(owned.items()):
                if relative in staged_files or relative in preserved:
                    continue
                target = output_dir / relative
                current = _media_file_identity(target)
                if current is None:
                    if target.exists() or target.is_symlink():
                        preserved.append(relative)
                    continue
                if current != identity:
                    preserved.append(relative)
                    continue
                if missing_planned or (selected and (receipt.get("status") == "error" or receipt.get("totalFailed") or receipt.get("totalSkipped"))):
                    generated[relative] = identity
                else:
                    remove_plan.append((relative, target, identity))

            # Move old owned files into Assets-local backups before installing.
            # The receipt is the commit point; until then every move is reversible.
            backup_dir = staging_root / "backup"
            backup_dir.mkdir()
            if install_plan and not output_dir.exists():
                output_dir.mkdir()
                created_dirs.append(output_dir)
            for index, (relative, staged, target, expected) in enumerate(install_plan):
                if _media_file_identity(target) != expected or (expected is None and (target.exists() or target.is_symlink())):
                    raise RuntimeError(f"media destination changed after preflight: {target}")
                if target.parent.is_symlink() or (target.parent.exists() and not target.parent.is_dir()):
                    raise RuntimeError(f"media output type path changed after preflight: {target.parent}")
                if not target.parent.exists():
                    target.parent.mkdir()
                    created_dirs.append(target.parent)
                if expected is not None:
                    backup = backup_dir / f"install-{index}"
                    os.replace(target, backup)
                    backups.append((target, backup))
                staged_identity = _media_file_identity(staged)
                if staged_identity is None:
                    raise OSError(f"staged media is not a regular file: {staged}")
                os.replace(staged, target)
                installed.append((target, staged_identity))
                identity = _media_file_identity(target)
                if identity != staged_identity:
                    raise OSError(f"installed media changed after replacement: {target}")
                generated[relative] = identity

            for index, (relative, target, expected) in enumerate(remove_plan):
                if _media_file_identity(target) != expected:
                    raise RuntimeError(f"owned media changed after preflight: {target}")
                backup = backup_dir / f"remove-{index}"
                os.replace(target, backup)
                backups.append((target, backup))
                removed.append(relative)

            if preserved and receipt.get("status") in {"complete", "skipped"}:
                receipt["status"] = "partial"
            if missing_planned:
                receipt["status"] = "error"
                receipt["reason"] = (
                    "planned excluded Unity serialized owner files are missing; "
                    "retry after restoring the sources"
                )
            receipt["missingPlannedContainers"] = missing_planned
            receipt["targetProject"] = str(project_root)
            receipt["excludedContainers"] = sorted(excluded)
            receipt["selectedSerializedOwners"] = [path.name for path in selected]
            receipt["resourceCompanions"] = [path.name for path in companions]
            receipt["plannedResourceCompanions"] = sources["plannedCompanions"]
            receipt["unavailableResourceCompanions"] = sources[
                "unavailablePlannedCompanions"
            ]
            receipt["unassociatedResourceCompanions"] = sources[
                "unassociatedPlannedCompanions"
            ]
            receipt["outputDir"] = str(output_dir)
            receipt["ownershipSchema"] = "agentdecompile.unity-media-ownership.v1"
            receipt["ownedFiles"] = [
                {"path": relative, "identity": identity}
                for relative, identity in sorted(generated.items())
            ]
            receipt["reconciliation"] = {
                "removedOwnedFiles": removed,
                "preservedUnownedFiles": sorted(set(existing) - set(owned)),
                "preservedChangedOrConflictingFiles": sorted(set(preserved)),
                "preservedConflictFiles": [
                    {"path": relative, "identity": _media_conflict_identity(output_dir / relative)}
                    for relative in sorted(set(preserved))
                ],
                "legacyOwnershipUnknown": legacy_ownership,
            }
            atomic_write_json(out_path, receipt)
            clean_staging = True
        except BaseException:
            rollback_errors: list[str] = []
            for target, identity in reversed(installed):
                try:
                    if _media_file_identity(target) != identity:
                        raise RuntimeError("installed file changed during rollback")
                    target.unlink()
                except OSError as exc:
                    rollback_errors.append(f"{target}: {exc}")
                except RuntimeError as exc:
                    rollback_errors.append(f"{target}: {exc}")
            for target, backup in reversed(backups):
                try:
                    if target.exists() or target.is_symlink():
                        raise RuntimeError("destination occupied during rollback")
                    os.replace(backup, target)
                except (OSError, RuntimeError) as exc:
                    rollback_errors.append(f"{target}: {exc}")
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if rollback_errors:
                raise RuntimeError(
                    f"media install rollback incomplete; backups retained at {staging_root}: "
                    + "; ".join(rollback_errors)
                ) from None
            clean_staging = True
            raise
        finally:
            if clean_staging:
                shutil.rmtree(staging_root, ignore_errors=True)
        return {
            "status": receipt.get("status"),
            "reason": receipt.get("reason"),
            "targetProject": str(project_out),
            "selectedFiles": receipt.get("selectedFiles"),
            "exported": receipt.get("totalExported"),
            "failed": receipt.get("totalFailed"),
            "missingPlannedContainers": missing_planned,
            "selectedSerializedOwners": receipt["selectedSerializedOwners"],
            "resourceCompanions": receipt["resourceCompanions"],
            "unavailableResourceCompanions": receipt[
                "unavailableResourceCompanions"
            ],
            "unassociatedResourceCompanions": receipt[
                "unassociatedResourceCompanions"
            ],
            "skipped": receipt.get("totalSkipped"),
            "reconciliation": receipt["reconciliation"],
        }

    def stage_unity_editor_validate(self, _stage: Stage) -> dict[str, Any]:
        from .unity_editor import validate_unity_project

        out_path = self._unity_dir() / "validate.json"
        probe = self._load_unity_json("probe.json")
        plan = self._load_unity_json("plan.json")
        if not probe.get("detected"):
            return self._unity_skip(out_path, "target is not a Unity game")
        if self.config.unity_project_out is None:
            return self._unity_skip(out_path, "no target project; pass --unity-project-out <dir>")
        editor = self.config.unity_editor or ((plan.get("editor") or {}).get("executable"))
        if not editor:
            raise ToolchainError(
                "unity-editor-missing",
                detail=f"no Unity Editor found; install one via Unity Hub or set {UNITY_EDITOR_ENV}",
            )
        receipt = validate_unity_project(
            self.config.unity_project_out,
            editor=Path(str(editor)),
            timeout=self.config.unity_editor_timeout,
            log_dir=self._unity_dir() / "editor-logs",
        )
        atomic_write_json(out_path, receipt)
        scenes = receipt.get("scenes") or {}
        return {
            "status": receipt.get("status"),
            "clean": receipt.get("clean"),
            "compileErrorCount": (receipt.get("compile") or {}).get("errorCount"),
            "scenesOpened": scenes.get("opened"),
            "sceneTotal": scenes.get("total"),
            "missingScriptTotal": scenes.get("missingScriptTotal"),
            "packageErrorCount": receipt.get("packageErrorCount"),
            "logPath": receipt.get("logPath"),
        }

    def stage_unity_repair(self, _stage: Stage) -> dict[str, Any]:
        from .unity_editor import repair_unity_project

        out_path = self._unity_dir() / "repair.json"
        probe = self._load_unity_json("probe.json")
        plan = self._load_unity_json("plan.json")
        validate = self._load_unity_json("validate.json")
        if not probe.get("detected"):
            return self._unity_skip(out_path, "target is not a Unity game")
        if self.config.unity_project_out is None:
            return self._unity_skip(out_path, "no target project; pass --unity-project-out <dir>")
        if validate.get("clean"):
            return self._unity_skip(out_path, "validation reported a clean project; nothing to repair")
        editor = self.config.unity_editor or ((plan.get("editor") or {}).get("executable"))
        if not editor:
            return self._unity_skip(out_path, "no Unity Editor available to re-validate repairs")
        receipt = repair_unity_project(
            self.config.unity_project_out,
            editor=Path(str(editor)),
            max_attempts=self.config.unity_repair_attempts,
            timeout=self.config.unity_editor_timeout,
        )
        atomic_write_json(out_path, receipt)
        return {
            "status": receipt.get("status"),
            "disposition": receipt.get("disposition"),
            "attemptCount": receipt.get("attemptCount"),
            "finalErrorCount": receipt.get("finalErrorCount"),
            "unfixedErrorCount": receipt.get("unfixedErrorCount"),
            "unimplementedRecipeCounts": receipt.get("unimplementedRecipeCounts"),
            "unverifiedRepairs": receipt.get("unverifiedRepairs"),
        }

    def stage_report(self, _stage: Stage) -> dict[str, Any]:
        from .readability_repair import write_readability_repair_queue
        from .proof_target import write_proof_target_queue

        write_readability_repair_queue(self.run_dir)
        proof_target_queue = write_proof_target_queue(self.run_dir)
        export_manifest = build_export_package(self.run_dir)
        proof_ladder = write_proof_ladder(self.run_dir)
        critical_path = write_critical_path(self.run_dir)
        report = {
            "schema": "agentdecompile.recover.report.v1",
            "generatedAt": now(),
            "state": str(self.state.state_path),
            "events": str(self.state.events_path),
            "target": json.loads((self.run_dir / "target.json").read_text(encoding="utf-8")),
            "analysisImage": json.loads((self.run_dir / "analysis-target.json").read_text(encoding="utf-8")),
            "contextExport": json.loads((self.run_dir / "context-export/manifest.json").read_text(encoding="utf-8")),
            "binaryInventory": json.loads((self.run_dir / "binary-inventory.json").read_text(encoding="utf-8")),
            "functionCandidates": json.loads((self.run_dir / "function-candidates.json").read_text(encoding="utf-8")),
            "functionAnalysis": json.loads((self.run_dir / "function-analysis.json").read_text(encoding="utf-8")),
            "sourceGeneration": json.loads((self.run_dir / "source-generation/summary.json").read_text(encoding="utf-8")),
            "sourceSynthesis": json.loads((self.run_dir / "source-synthesis/summary.json").read_text(encoding="utf-8")),
            "recoveredSource": json.loads((self.run_dir / "recovered-source/simple_matches.manifest.json").read_text(encoding="utf-8"))
            if (self.run_dir / "recovered-source/simple_matches.manifest.json").exists()
            else {"status": "missing", "claimBoundary": "no recovered source manifest exists"},
            "exportPackage": {
                "status": export_manifest.get("status"),
                "exportDir": export_manifest.get("exportDir"),
                "viewCount": export_manifest.get("viewCount"),
                "countsByAuthorityClass": export_manifest.get("countsByAuthorityClass"),
                "claimBoundary": export_manifest.get("claimBoundary"),
            },
            "proofLadder": {
                "status": proof_ladder.get("status"),
                "denominator": proof_ladder.get("denominator"),
                "numerator": proof_ladder.get("numerator"),
                "coverage": proof_ladder.get("coverage"),
                "coveragePercent": proof_ladder.get("coveragePercent"),
                "rung": proof_ladder.get("rung"),
                "nextRung": proof_ladder.get("nextRung"),
                "functionsToNextRung": proof_ladder.get("functionsToNextRung"),
                "nextRungTargetNumerator": proof_ladder.get("nextRungTargetNumerator"),
                "claimBoundary": proof_ladder.get("claimBoundary"),
            },
            "proofTargetQueue": {
                "status": proof_target_queue.get("status"),
                "queueCount": proof_target_queue.get("queueCount"),
                "synthesisEligibleCount": proof_target_queue.get("synthesisEligibleCount"),
                "functionsToNextRung": proof_target_queue.get("functionsToNextRung"),
                "topEntries": (proof_target_queue.get("entries") or [])[:5],
                "claimBoundary": proof_target_queue.get("claimBoundary"),
            },
            "criticalPath": {
                "readiness": critical_path.get("readiness"),
                "peCriticalPathStopAfter": critical_path.get("peCriticalPathStopAfter"),
                "nextActions": critical_path.get("nextActions"),
                "claimBoundary": critical_path.get("claimBoundary"),
            },
            "strategy": json.loads((self.run_dir / "strategy.json").read_text(encoding="utf-8")),
            "byteAuthority": json.loads((self.run_dir / "byte-authority/result.json").read_text(encoding="utf-8")),
            "legacyAdapter": json.loads((self.run_dir / "legacy-adapter.json").read_text(encoding="utf-8")),
            "snapshotExistingRecovery": json.loads((self.run_dir / "snapshot-existing-recovery.json").read_text(encoding="utf-8")),
            "fullSourceParity": False,
        }
        atomic_write_json(self.run_dir / "report.json", report)
        self.state.data["status"] = "complete"
        self.state.data["report"] = str(self.run_dir / "report.json")
        self.state.save()
        return {
            "report": str(self.run_dir / "report.json"),
            "exportPackage": str(self.run_dir / "export" / "manifest.json"),
            "proofLadder": str(self.run_dir / "proof-ladder.json"),
            "criticalPath": str(self.run_dir / "critical-path.json"),
            "fullSourceParity": False,
        }


def resolve_source_synthesis_mode(
    mode: str | None,
    *,
    target_format: str | None,
    vc_root_available: bool,
    compiler_hint: dict[str, Any] | None = None,
) -> str:
    """Pick the compiler lane when `--source-synthesis` is left at `auto`.

    A candidate object is only comparable to the target when both came from
    compatible toolchains. Diffing a clang-built object against an MSVC-built PE
    slice diverges on calling convention, prologue shape, and register
    allocation before any source-shape question is reached -- so a clang default
    caps the accept rate for every Windows target regardless of how good
    candidate generation becomes.

    Mirrors the format/stem-derived profile rule in STRATEGY.md. An explicit
    mode always wins; this only fills in `auto`.
    """

    if mode and mode != "auto":
        return mode
    if str((compiler_hint or {}).get("family") or "").strip().lower() == "msvc":
        return "msvc" if vc_root_available else "clang-cl"
    if (target_format or "").strip().lower() == "pe":
        # clang-cl is the fallback rather than clang: it at least matches MSVC
        # calling conventions and name decoration.
        return "msvc" if vc_root_available else "clang-cl"
    if (target_format or "").strip().lower() == "nds":
        return "clang"
    return "clang"


def compiler_for_source_synthesis_mode(mode: str) -> str:
    if mode in {"dry-run", "none"}:
        return "clang"
    if mode in {"clang", "clang-cl", "msvc"}:
        return mode
    raise ValueError(f"unknown source synthesis mode: {mode}")


def command_error(exc: subprocess.CalledProcessError) -> str:
    stderr = (exc.stderr or "").strip()
    stdout = (exc.output or "").strip()
    return (stderr or stdout or str(exc))[-4000:]


def default_function_facts_path(run_dir: Path) -> Path | None:
    for path in (run_dir / "facts" / "function-facts.jsonl", run_dir / "function-facts.jsonl"):
        if path.exists():
            return path
    return None


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
