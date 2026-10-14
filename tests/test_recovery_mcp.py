"""Unit tests for curated recovery MCP tools (reconstruct / status / claim-report)."""

from __future__ import annotations

import json

from pathlib import Path
from typing import Any

import pytest

from agentdecompile_cli.mcp_server.providers.recovery import RecoveryToolProvider
from agentdecompile_cli.mcp_server.tool_providers import ToolProviderManager, n
from agentdecompile_cli.registry import Tool, get_advertised_tools_for_list, get_tool_analysis_tier
from agentdecompile_recovery.recovery_status import build_recovery_status

pytestmark = pytest.mark.unit


def test_recovery_tools_are_tier_zero() -> None:
    assert get_tool_analysis_tier(Tool.RECONSTRUCT) == 0
    assert get_tool_analysis_tier(Tool.STATUS) == 0
    assert get_tool_analysis_tier(Tool.CLAIM_REPORT) == 0


def test_recovery_tools_advertised_on_default_surface() -> None:
    advertised = set(get_advertised_tools_for_list())
    assert Tool.RECONSTRUCT.value in advertised
    assert Tool.STATUS.value in advertised
    assert Tool.CLAIM_REPORT.value in advertised


def test_build_recovery_status_from_work_dir(tmp_path: Path) -> None:
    work = tmp_path / "run"
    (work / "verified").mkdir(parents=True)
    (work / "advisory").mkdir(parents=True)
    (work / "verified" / "fn.c").write_text("int f(void){return 0;}\n", encoding="utf-8")
    (work / "advisory" / "fn.c").write_text("/* advisory */\n", encoding="utf-8")
    (work / "state.json").write_text(json.dumps({"terminalStatus": "partial", "currentStage": "report"}), encoding="utf-8")
    (work / "claim-report.json").write_text(
        json.dumps({"terminalStatus": "partial", "counts": {"objdiffVerified": 0}}),
        encoding="utf-8",
    )

    status = build_recovery_status(work)
    assert status["schema"] == "agentdecompile.recovery-status.v1"
    assert status["terminalStatus"] == "partial"
    assert status["stage"] == "report"
    assert status["counts"]["verified"] == 1
    assert status["counts"]["advisory"] == 1
    assert "objdiff-verified-semantic" in status["claimBoundary"] or "objdiff" in status["claimBoundary"]


def test_build_recovery_status_includes_autonomy_and_vacuum(tmp_path: Path) -> None:
    work = tmp_path / "run"
    (work / "state").mkdir(parents=True)
    (work / "autonomy-budget.json").write_text(
        json.dumps(
            {
                "schema": "agentdecompile.autonomy-budget.v1",
                "requested": True,
                "status": "bridged",
                "max_functions": 1,
            }
        ),
        encoding="utf-8",
    )
    (work / "state" / "queue.json").write_text(
        json.dumps(
            {
                "schema": "agentdecompile.vacuum-queue.v1",
                "pending": ["a"],
                "matched": ["b"],
                "integrated": [],
                "failed": [],
                "difficult": [],
                "attempts": {},
            }
        ),
        encoding="utf-8",
    )
    (work / "state" / "vacuum-session.json").write_text(
        json.dumps({"schema": "agentdecompile.vacuum-session.v1", "status": "finished"}),
        encoding="utf-8",
    )

    status = build_recovery_status(work)
    assert status["autonomyBudget"]["status"] == "bridged"
    assert status["vacuum"]["queueCounts"]["pending"] == 1
    assert status["vacuum"]["queueCounts"]["matched"] == 1
    assert status["vacuum"]["sessionStatus"] == "finished"
    assert status["paths"]["autonomyBudget"]
    assert status["paths"]["vacuumQueue"]


def test_build_recovery_status_includes_export_package(tmp_path: Path) -> None:
    work = tmp_path / "run"
    (work / "export").mkdir(parents=True)
    (work / "export" / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "agentdecompile.export-package.v1",
                "status": "complete",
                "viewCount": 3,
                "countsByAuthorityClass": {"objdiff-verified-semantic": 1, "asm-slice": 1, "hex-slice": 1},
                "exportDir": str(work / "export"),
                "claimBoundary": "export package aggregates recovery views",
            }
        ),
        encoding="utf-8",
    )
    status = build_recovery_status(work)
    assert status["exportPackage"]["status"] == "complete"
    assert status["exportPackage"]["viewCount"] == 3
    assert status["paths"]["exportManifest"]


def test_build_recovery_status_includes_unity_receipts_and_effective_outcome(tmp_path: Path) -> None:
    work = tmp_path / "run"
    unity = work / "unity"
    unity.mkdir(parents=True)
    project = tmp_path / "unity-project"
    (work / "state.json").write_text(
        json.dumps(
            {
                "stages": {
                    "unity-probe": {
                        "config": {"unitySettings": {"projectOut": str(project)}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (work / "claim-report.json").write_text(json.dumps({"terminalStatus": "matched"}), encoding="utf-8")
    (work / "report.json").write_text(json.dumps({"terminalStatus": "matched"}), encoding="utf-8")
    unity_receipts = {
        "probe.json": {"status": "complete", "detected": True, "unityVersion": "2022.3.62f2"},
        "plan.json": {"status": "complete", "export": {"mode": "staged", "excludedContainers": ["resources.assets"]}},
        "assetripper.json": {"status": "complete", "hasProjectVersion": True, "exportedProject": str(tmp_path / "exported")},
        "managed.json": {"status": "error", "reason": "synthetic ilspy failure", "failed": ["Assembly-CSharp"]},
        "compose.json": {"status": "partial", "targetProject": str(project)},
        "validate.json": {"status": "skipped", "clean": False, "reason": "no editor"},
        "repair.json": {"status": "skipped", "reason": "no editor"},
    }
    for filename, receipt in unity_receipts.items():
        (unity / filename).write_text(json.dumps(receipt), encoding="utf-8")

    status = build_recovery_status(work)

    assert status["terminalStatus"] == "failed"
    assert status["unity"]["status"] == "failed"
    assert status["unity"]["projectPath"] == str(project.resolve())
    assert status["unity"]["receipts"]["plan"]["export"]["excludedContainers"] == ["resources.assets"]
    assert status["unity"]["receipts"]["managed"]["status"] == "error"
    assert "not byte-verified native" in status["unity"]["managedSourceBoundary"]
    assert set(status["paths"]["unityReceipts"]) == {
        "probe",
        "plan",
        "export",
        "managed",
        "compose",
        "editorValidation",
        "repair",
    }


def test_unity_clean_repair_supersedes_initial_editor_diagnostics(tmp_path: Path) -> None:
    from agentdecompile_recovery.recovery_status import build_unity_recovery_summary

    work = tmp_path / "run"
    unity = work / "unity"
    unity.mkdir(parents=True)
    receipts = {
        "probe.json": {"status": "complete", "detected": True},
        "plan.json": {"status": "complete"},
        "assetripper.json": {"status": "complete", "hasProjectVersion": True},
        "managed.json": {"status": "complete", "decompiled": ["Assembly-CSharp"], "failed": []},
        "compose.json": {"status": "complete", "openable": {"ready": True}},
        "validate.json": {"status": "failed", "clean": False},
        "repair.json": {"status": "complete", "finalValidation": {"status": "complete", "clean": True}},
    }
    for name, payload in receipts.items():
        (unity / name).write_text(json.dumps(payload), encoding="utf-8")

    outcome = build_unity_recovery_summary(work, project_path=tmp_path / "project", requested=True)

    assert outcome["status"] == "complete"
    assert outcome["terminalStatus"] == "complete"
    assert outcome["exitCode"] == 0


def test_unity_staged_export_is_reported_as_partial(tmp_path: Path) -> None:
    from agentdecompile_recovery.recovery_status import build_unity_recovery_summary

    work = tmp_path / "run"
    unity = work / "unity"
    unity.mkdir(parents=True)
    receipts = {
        "probe.json": {"status": "complete", "detected": True},
        "plan.json": {"status": "complete", "export": {"mode": "staged", "excludedContainers": ["resources.assets"]}},
        "assetripper.json": {"status": "complete", "hasProjectVersion": True, "mode": "staged"},
        "managed.json": {"status": "complete", "decompiled": ["Assembly-CSharp"], "failed": []},
        "compose.json": {"status": "complete", "openable": {"ready": True}},
        "validate.json": {"status": "complete", "clean": True},
        "repair.json": {"status": "skipped", "reason": "validation reported a clean project"},
    }
    for name, payload in receipts.items():
        (unity / name).write_text(json.dumps(payload), encoding="utf-8")

    outcome = build_unity_recovery_summary(work, project_path=tmp_path / "project", requested=True)

    assert outcome["status"] == "partial"
    assert outcome["terminalStatus"] == "partial"
    assert outcome["exitCode"] == 1
    assert outcome["exportOmissions"] == ["resources.assets"]


def test_unity_incompleteness_does_not_hide_toolchain_block(tmp_path: Path) -> None:
    work = tmp_path / "run"
    unity = work / "unity"
    unity.mkdir(parents=True)
    (work / "claim-report.json").write_text(json.dumps({"terminalStatus": "blocked:toolchain"}), encoding="utf-8")
    (work / "state.json").write_text(
        json.dumps({"stages": {"unity-probe": {"config": {"unitySettings": {"projectOut": str(tmp_path / "project")}}}}}),
        encoding="utf-8",
    )
    (unity / "probe.json").write_text(json.dumps({"status": "complete", "detected": True}), encoding="utf-8")

    assert build_recovery_status(work)["terminalStatus"] == "blocked:toolchain"


def test_current_unity_settings_clear_stale_report_project_path(tmp_path: Path) -> None:
    from agentdecompile_recovery.recovery_status import build_unity_recovery_summary

    work = tmp_path / "run"
    work.mkdir()
    (work / "state.json").write_text(
        json.dumps({"stages": {"unity-probe": {"config": {"unitySettings": {"projectOut": None}}}}}),
        encoding="utf-8",
    )
    (work / "report.json").write_text(
        json.dumps({"unity": {"requested": True, "projectPath": str(tmp_path / "old-project")}}),
        encoding="utf-8",
    )

    summary = build_unity_recovery_summary(work)

    assert summary["requested"] is False
    assert summary["projectPath"] is None


@pytest.mark.asyncio
async def test_provider_status_and_claim_report(tmp_path: Path) -> None:
    work = tmp_path / "run"
    work.mkdir()
    (work / "advisory").mkdir()
    (work / "advisory" / "x.c").write_text("void x(void){}\n", encoding="utf-8")

    provider = RecoveryToolProvider()
    status_result = await provider._handle_status({n("workDir"): str(work)})
    status_payload = json.loads(status_result[0].text)
    assert status_payload["tool"] == "status"
    assert status_payload["counts"]["advisory"] == 1

    claim_result = await provider._handle_claim_report(
        {n("workDir"): str(work), n("terminalStatus"): "partial", n("write"): True}
    )
    claim_payload = json.loads(claim_result[0].text)
    assert claim_payload["tool"] == "claim-report"
    assert claim_payload["schema"] == "agentdecompile.claim-report.v1"
    assert (work / "claim-report.json").is_file()
    assert any(c.get("class") == "advisory-decompiler" for c in claim_payload["claims"])


@pytest.mark.asyncio
async def test_provider_reconstruct_uses_job_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary = tmp_path / "sample.bin"
    binary.write_bytes(b"MZ\x00\x00")
    work = tmp_path / "work"

    def fake_job(input_path: Path, **kwargs: Any) -> dict[str, Any]:
        assert input_path == binary
        assert kwargs.get("stop_after") == "inventory-binary"
        work.mkdir(parents=True, exist_ok=True)
        return {
            "tool": "reconstruct",
            "exitCode": 0,
            "terminalStatus": "partial",
            "workDir": str(work),
            "claimBoundary": "orchestration outcome only",
        }

    monkeypatch.setattr("agentdecompile_recovery.frontdoor.run_reconstruct_job", fake_job)
    provider = RecoveryToolProvider()
    result = await provider._handle_reconstruct(
        {
            n("binaryPath"): str(binary),
            n("workDir"): str(work),
            n("stopAfter"): "inventory-binary",
        }
    )
    payload = json.loads(result[0].text)
    assert payload["tool"] == "reconstruct"
    assert payload["terminalStatus"] == "partial"


def test_frontdoor_preserves_unity_partial_exit_without_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentdecompile_recovery import frontdoor

    binary = tmp_path / "game"
    binary.write_bytes(b"MZ")
    work = tmp_path / "work"
    args = frontdoor.build_parser().parse_args(
        [str(binary), "--work-dir", str(work), "--unity-project-out", str(tmp_path / "project"), "--json"]
    )

    class PartialRunner:
        def __init__(self, config: Any) -> None:
            self.work_dir = config.work_dir

        def run(self) -> int:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            (self.work_dir / "state.json").write_text(
                json.dumps({"terminalStatus": "partial", "status": "partial"}),
                encoding="utf-8",
            )
            return 1

    written_claims: list[str] = []
    monkeypatch.setattr(frontdoor, "RecoveryRunner", PartialRunner)
    monkeypatch.setattr(frontdoor, "write_critical_path", lambda _work: {})
    monkeypatch.setattr(
        frontdoor,
        "write_claim_report",
        lambda _work, *, terminal_status: written_claims.append(terminal_status) or work / "claim-report.json",
    )

    assert frontdoor.run_one_shot(args) == 1
    assert written_claims == ["partial"]


def test_frontdoor_maps_remote_assetripper_options_without_connecting(tmp_path: Path) -> None:
    from agentdecompile_recovery import frontdoor

    binary = tmp_path / "game"
    binary.write_bytes(b"MZ")
    args = frontdoor.build_parser().parse_args(
        [
            str(binary),
            "--unity-only",
            "--unity-project-out",
            str(tmp_path / "project"),
            "--unity-assetripper-remote-host",
            "root@192.0.2.10",
            "--unity-assetripper-remote-root",
            "/tmp/tvs-run",
            "--unity-assetripper-remote-input",
            "/tmp/tvs-run/input",
            "--unity-assetripper-remote-port",
            "18085",
            "--unity-assetripper-ssh-host-key-alias",
            "100.64.0.8",
        ]
    )

    options = frontdoor.frontdoor_unity_config_kwargs(args)
    assert options["unity_only"] is True
    assert options["unity_assetripper_remote_host"] == "root@192.0.2.10"
    assert options["unity_assetripper_remote_root"] == "/tmp/tvs-run"
    assert options["unity_assetripper_remote_input"] == "/tmp/tvs-run/input"
    assert options["unity_assetripper_remote_port"] == 18085
    assert options["unity_assetripper_ssh_host_key_alias"] == "100.64.0.8"


def test_manager_registers_recovery_tools() -> None:
    manager = ToolProviderManager()
    manager.register_all_providers()
    names = {tool.name for tool in manager.list_tools()}
    assert "reconstruct" in names
    assert "status" in names
    assert "claim-report" in names
