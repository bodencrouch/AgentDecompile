"""Unit tests for the Unity stages' wiring into RecoveryRunner.

The behaviour worth protecting here is not what the Unity modules compute --
that is covered by their own tests -- but that these stages are *inert and
resumable* for every target that is not a Unity game. The existing pipeline is
PE/ELF function-recovery oriented and runs on everything, so a Unity stage that
raised, or that skipped without writing its declared output, would break
unrelated runs (the resume gate requires declared outputs to exist).
"""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from agentdecompile_recovery.pipeline import RecoveryConfig, RecoveryRunner, Stage

pytestmark = pytest.mark.unit


UNITY_STAGE_NAMES = [
    "unity-probe",
    "unity-plan",
    "unity-export-assets",
    "unity-decompile-managed",
    "unity-compose-project",
    "unity-editor-validate",
    "unity-repair",
]


def _runner(tmp_path: Path, input_path: Path | None = None, **overrides: object) -> RecoveryRunner:
    config = RecoveryConfig(
        input_path=input_path or (tmp_path / "game"),
        work_dir=tmp_path / "work",
        **overrides,  # type: ignore[arg-type]
    )
    (config.work_dir).mkdir(parents=True, exist_ok=True)
    return RecoveryRunner(config)


def _stage(runner: RecoveryRunner, name: str):
    return next(stage for stage in runner.stages if stage.name == name)


def _run(runner: RecoveryRunner, name: str) -> dict:
    stage = _stage(runner, name)
    return stage.run(runner, stage)


# --- registration ------------------------------------------------------------


def test_unity_stages_are_registered_in_dependency_order(tmp_path: Path) -> None:
    names = [stage.name for stage in _runner(tmp_path).stages]
    unity = [name for name in names if name.startswith("unity-")]
    assert unity == UNITY_STAGE_NAMES


def test_report_stage_remains_last(tmp_path: Path) -> None:
    names = [stage.name for stage in _runner(tmp_path).stages]
    assert names[-1] == "report"


def test_unity_only_selects_unity_stages_and_requires_project_output(tmp_path: Path) -> None:
    runner = _runner(tmp_path, unity_only=True, unity_project_out=tmp_path / "project")

    assert runner.selected_stages() == set(UNITY_STAGE_NAMES)
    assert "report" not in runner.selected_stages()
    assert not runner.selected_stages().intersection({"discover", "enrich-decompile", "inventory-binary"})

    missing_output = _runner(tmp_path / "missing", unity_only=True)
    with pytest.raises(SystemExit, match="--unity-only requires --unity-project-out"):
        missing_output.selected_stages()


def test_unity_only_stop_after_is_relative_to_unity_stages(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        unity_only=True,
        unity_project_out=tmp_path / "project",
        stop_after="unity-export-assets",
    )

    assert runner.selected_stages() == set(UNITY_STAGE_NAMES[:3])


def test_every_unity_stage_declares_a_single_output(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    for name in UNITY_STAGE_NAMES:
        outputs = _stage(runner, name).outputs
        assert len(outputs) == 1, name
        assert outputs[0].parent == runner.run_dir / "unity", name


def test_unity_stages_have_distinct_fingerprints_from_each_other(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    fingerprints = {name: runner.stage_fingerprint(_stage(runner, name)) for name in UNITY_STAGE_NAMES}
    assert len(set(fingerprints.values())) == len(UNITY_STAGE_NAMES)


# --- inertness on non-Unity targets ------------------------------------------


def test_probe_reports_not_detected_for_non_unity_target(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    (game / "thing.exe").write_bytes(b"MZ")

    summary = _run(_runner(tmp_path, input_path=game), "unity-probe")

    assert summary["status"] == "complete"
    assert summary["detected"] is False


def test_downstream_unity_stages_skip_when_not_a_unity_game(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    runner = _runner(tmp_path, input_path=game)
    _run(runner, "unity-probe")

    for name in UNITY_STAGE_NAMES[1:]:
        summary = _run(runner, name)
        assert summary["status"] == "skipped", name
        # The resume gate keys off declared outputs existing, so a skip must
        # still leave its receipt behind or the stage reruns forever.
        assert _stage(runner, name).outputs[0].exists(), name


def test_skipped_stage_receipt_records_a_reason(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    runner = _runner(tmp_path, input_path=game)
    _run(runner, "unity-probe")
    _run(runner, "unity-plan")

    payload = json.loads((runner.run_dir / "unity" / "plan.json").read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert payload["reason"]


# --- install-root resolution -------------------------------------------------


def test_install_root_uses_directory_input_directly(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    assert _runner(tmp_path, input_path=game).unity_install_root() == game.resolve()


def test_install_root_uses_parent_for_executable_input(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    exe = game / "Player.exe"
    exe.write_bytes(b"MZ")
    assert _runner(tmp_path, input_path=exe).unity_install_root() == game.resolve()


# --- compose/validate guards -------------------------------------------------


def _unity_game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    data = game / "Game_Data"
    data.mkdir(parents=True)
    (data / "globalgamemanagers").write_bytes(b"\x00" * 16 + b"2022.3.62f2" + b"\x00" * 16)
    (data / "level0").write_bytes(b"x")
    managed = data / "Managed"
    managed.mkdir()
    (managed / "Assembly-CSharp.dll").write_bytes(b"MZ")
    return game


def test_compose_skips_without_a_target_project(tmp_path: Path) -> None:
    runner = _runner(tmp_path, input_path=_unity_game(tmp_path))
    _run(runner, "unity-probe")

    summary = _run(runner, "unity-compose-project")

    assert summary["status"] == "skipped"
    assert "--unity-project-out" in summary["reason"]


def test_validate_skips_without_a_target_project(tmp_path: Path) -> None:
    runner = _runner(tmp_path, input_path=_unity_game(tmp_path))
    _run(runner, "unity-probe")

    summary = _run(runner, "unity-editor-validate")

    assert summary["status"] == "skipped"


def test_repair_skips_when_validation_was_clean(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        input_path=_unity_game(tmp_path),
        unity_project_out=tmp_path / "project",
    )
    _run(runner, "unity-probe")
    unity_dir = runner.run_dir / "unity"
    unity_dir.mkdir(parents=True, exist_ok=True)
    (unity_dir / "validate.json").write_text(json.dumps({"status": "complete", "clean": True}), encoding="utf-8")

    summary = _run(runner, "unity-repair")

    assert summary["status"] == "skipped"
    assert "clean" in summary["reason"]


def test_managed_decompile_skips_on_il2cpp(tmp_path: Path) -> None:
    game = _unity_game(tmp_path)
    # IL2CPP markers alongside Managed/ flip the backend away from mono.
    (game / "Game_Data" / "il2cpp_data").mkdir()
    (game / "GameAssembly.dll").write_bytes(b"MZ")
    runner = _runner(tmp_path, input_path=game)
    _run(runner, "unity-probe")

    summary = _run(runner, "unity-decompile-managed")

    assert summary["status"] == "skipped"
    assert "il2cpp" in summary["reason"]


def test_export_skips_when_plan_is_blocked(tmp_path: Path) -> None:
    game = _unity_game(tmp_path)
    (game / "Game_Data" / "il2cpp_data").mkdir()
    (game / "GameAssembly.dll").write_bytes(b"MZ")
    runner = _runner(tmp_path, input_path=game)
    _run(runner, "unity-probe")
    _run(runner, "unity-plan")

    summary = _run(runner, "unity-export-assets")

    assert summary["status"] == "skipped"
    assert "il2cpp" in summary["reason"]


def test_remote_asset_ripper_stage_uses_ipv4_adapter_without_local_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentdecompile_recovery import unity_remote

    game = _unity_game(tmp_path)
    runner = _runner(
        tmp_path,
        input_path=game,
        unity_assetripper_remote_host="root@192.0.2.10",
        unity_assetripper_remote_root="/tmp/tvs-run",
        unity_assetripper_remote_input="/tmp/tvs-run/input",
        unity_assetripper_remote_port=18085,
        unity_assetripper_ssh_host_key_alias="100.64.0.8",
    )
    _run(runner, "unity-probe")
    _run(runner, "unity-plan")
    seen: dict[str, object] = {}

    def fake_remote(install_root: Path, output_dir: Path, **kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        seen["install_root"] = install_root
        seen["output_dir"] = output_dir
        return {
            "status": "complete",
            "exportedProject": str(output_dir / "remote-assetripper" / "run" / "ExportedProject"),
            "hasProjectVersion": True,
            "transport": "ssh-rsync-ipv4",
            "addressFamily": "IPv4",
            "remoteRunRoot": "/tmp/tvs-run/runs/run",
            "outputRsyncStats": {"fileCount": 4, "totalBytes": 1200},
        }

    monkeypatch.setattr(unity_remote, "export_unity_project_remote", fake_remote)
    monkeypatch.setattr(
        "agentdecompile_recovery.pipeline.resolve_assetripper_cli",
        lambda *_args, **_kwargs: pytest.fail("remote mode must not resolve a local AssetRipper executable"),
    )

    summary = _run(runner, "unity-export-assets")

    assert summary["status"] == "complete"
    assert summary["transport"] == "ssh-rsync-ipv4"
    assert summary["addressFamily"] == "IPv4"
    assert summary["outputRsyncStats"]["totalBytes"] == 1200
    assert summary["assetPlan"]["mode"] == "full"
    assert seen["ssh_target"] == "root@192.0.2.10"
    assert seen["remote_root"] == "/tmp/tvs-run"
    assert seen["remote_input_path"] == "/tmp/tvs-run/input"
    assert seen["server_port"] == 18085
    assert seen["ssh_host_key_alias"] == "100.64.0.8"


def test_remote_assetripper_refuses_unapplied_staged_container_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentdecompile_recovery import unity_remote
    from agentdecompile_recovery.tools import ToolchainError

    game = _unity_game(tmp_path)
    runner = _runner(
        tmp_path,
        input_path=game,
        unity_assetripper_remote_host="root@192.0.2.10",
        unity_assetripper_remote_root="/tmp/tvs-run",
    )
    _run(runner, "unity-probe")
    _run(runner, "unity-plan")
    (runner.run_dir / "unity" / "plan.json").write_text(
        json.dumps({"status": "complete", "export": {"mode": "staged", "excludedContainers": ["resources.assets"]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        unity_remote,
        "export_unity_project_remote",
        lambda *_args, **_kwargs: pytest.fail("incompatible staged plan must not contact the remote service"),
    )

    with pytest.raises(ToolchainError, match="cannot apply a staged container filter"):
        _run(runner, "unity-export-assets")


def test_remote_asset_ripper_configuration_changes_unity_stage_fingerprint(tmp_path: Path) -> None:
    local = _runner(tmp_path / "local")
    remote = _runner(
        tmp_path / "remote",
        unity_assetripper_remote_host="root@192.0.2.10",
        unity_assetripper_remote_root="/tmp/tvs-run",
        unity_assetripper_remote_port=18085,
    )

    assert local.stage_fingerprint(_stage(local, "unity-export-assets")) != remote.stage_fingerprint(
        _stage(remote, "unity-export-assets")
    )


@pytest.mark.parametrize("receipt_status", ["error", "partial"])
def test_unity_receipt_outcome_is_not_recorded_as_complete_or_resumed(
    tmp_path: Path,
    receipt_status: str,
) -> None:
    runner = _runner(tmp_path)
    receipt_path = runner.run_dir / "unity" / "probe.json"

    def return_receipt(current: RecoveryRunner, _stage: Stage) -> dict:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps({"status": receipt_status, "detected": True}), encoding="utf-8")
        return {"status": receipt_status}

    stage = Stage("unity-probe", "synthetic receipt", (receipt_path,), return_receipt)
    runner.stages = [stage]

    assert runner.run() == 0  # Unconfigured Unity work is observational only.
    state = json.loads((runner.run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["stages"]["unity-probe"]["status"] == receipt_status
    assert not runner.should_skip(stage)


def test_configured_unity_error_sets_failed_terminal_and_nonzero_exit(tmp_path: Path) -> None:
    runner = _runner(tmp_path, unity_project_out=tmp_path / "editable-project")
    probe_path = runner.run_dir / "unity" / "probe.json"
    export_path = runner.run_dir / "unity" / "assetripper.json"

    def write_probe(current: RecoveryRunner, _stage: Stage) -> dict:
        probe_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": "complete", "detected": True, "unityVersion": "2022.3.1f1"}
        probe_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def write_export_error(_current: RecoveryRunner, _stage: Stage) -> dict:
        payload = {"status": "error", "reason": "synthetic AssetRipper failure"}
        export_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    runner.stages = [
        Stage("unity-probe", "probe", (probe_path,), write_probe),
        Stage("unity-export-assets", "export", (export_path,), write_export_error),
    ]

    assert runner.run() == 1
    state = json.loads((runner.run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["terminalStatus"] == "failed"
    assert state["stages"]["unity-export-assets"]["status"] == "error"
    unity_summary = json.loads((runner.run_dir / "unity" / "summary.json").read_text(encoding="utf-8"))
    assert unity_summary["terminalStatus"] == "failed"


def test_configured_missing_unity_stages_sets_partial_terminal_and_nonzero_exit(tmp_path: Path) -> None:
    runner = _runner(tmp_path, unity_project_out=tmp_path / "editable-project")
    probe_path = runner.run_dir / "unity" / "probe.json"

    def write_probe(_current: RecoveryRunner, _stage: Stage) -> dict:
        probe_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": "complete", "detected": True}
        probe_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    runner.stages = [Stage("unity-probe", "probe", (probe_path,), write_probe)]

    assert runner.run() == 1
    state = json.loads((runner.run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "partial"
    assert state["terminalStatus"] == "partial"


def test_configured_non_unity_skips_remain_benign(tmp_path: Path) -> None:
    game = tmp_path / "non-unity"
    game.mkdir()
    (game / "game.exe").write_bytes(b"MZ")
    runner = _runner(tmp_path, input_path=game, unity_project_out=tmp_path / "editable-project")
    runner.stages = [stage for stage in runner.stages if stage.name.startswith("unity-")]

    assert runner.run() == 0
    state = json.loads((runner.run_dir / "state.json").read_text(encoding="utf-8"))
    assert "terminalStatus" not in state
    assert state["stages"]["unity-probe"]["status"] == "complete"
    assert state["stages"]["unity-compose-project"]["status"] == "skipped"


def test_report_includes_unity_receipts_project_and_source_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentdecompile_recovery import pipeline as pipeline_module

    runner = _runner(tmp_path, unity_project_out=tmp_path / "editable-project")
    payloads = {
        "target.json": {},
        "analysis-target.json": {},
        "context-export/manifest.json": {},
        "binary-inventory.json": {},
        "function-candidates.json": {},
        "function-analysis.json": {},
        "source-generation/summary.json": {},
        "source-synthesis/summary.json": {},
        "strategy.json": {},
        "byte-authority/result.json": {},
        "legacy-adapter.json": {},
        "snapshot-existing-recovery.json": {},
    }
    for relative, payload in payloads.items():
        path = runner.run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    unity_dir = runner.run_dir / "unity"
    unity_dir.mkdir(parents=True, exist_ok=True)
    (unity_dir / "probe.json").write_text(json.dumps({"status": "complete", "detected": True}), encoding="utf-8")
    (unity_dir / "managed.json").write_text(
        json.dumps({"status": "partial", "decompiled": ["Assembly-CSharp"], "failed": ["Other"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr("agentdecompile_recovery.readability_repair.write_readability_repair_queue", lambda _path: {})
    monkeypatch.setattr("agentdecompile_recovery.proof_target.write_proof_target_queue", lambda _path: {})
    monkeypatch.setattr(pipeline_module, "build_export_package", lambda _path: {})
    monkeypatch.setattr(pipeline_module, "write_proof_ladder", lambda _path: {})
    monkeypatch.setattr(pipeline_module, "write_critical_path", lambda _path: {})

    runner.stage_report(_stage(runner, "report"))
    report = json.loads((runner.run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["unity"]["projectPath"] == str((tmp_path / "editable-project").resolve())
    assert report["unity"]["receipts"]["probe"]["detected"] is True
    assert report["unity"]["receipts"]["managed"]["status"] == "partial"
    assert "not byte-verified native" in report["unity"]["managedSourceBoundary"]
