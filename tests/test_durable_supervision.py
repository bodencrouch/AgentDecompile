"""No game/compiler/Ghidra launches: controlled process and storage boundaries."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agentdecompile_recovery.corpus import recovery_orchestrator as orchestrator
from agentdecompile_recovery.corpus.supervision import (
    SupervisionError, decide, execution_basis, load_state, owner_lock, save_state,
)


def record(**changes):
    return {"state": "failed_exit", "basis": "a", "failed_exits": 2,
            "next_eligible_at": 10, **changes}


def test_pure_budget_cooldown_and_changed_basis():
    assert decide(record(), "a", 9, 3) == "cooldown"
    assert decide(record(), "a", 10, 3) == "launch"
    assert decide(record(failed_exits=3), "a", 100, 3) == "budget_exhausted"
    assert decide(record(failed_exits=3), "b", 100, 3) == "launch"
    for state in ("running", "launch_intent", "needs_reconciliation"):
        assert decide(record(state=state), "b", 100, 3) == "needs_reconciliation"


def test_basis_explicit_only():
    assert execution_basis(["x", "--a"], "code", "input") == execution_basis(["x", "--a"], "code", "input")
    assert len({execution_basis(["x"], code, inp) for code, inp in
                [("v1", "i1"), ("v2", "i1"), ("v1", "i2")]}) == 3


def test_durable_roundtrip_and_corrupt_state(tmp_path):
    path = tmp_path / "state.json"
    state = {"version": 1, "scope": {}, "stages": {"a": record()}}
    save_state(path, state)
    assert load_state(path, {}) == state
    with pytest.raises(SupervisionError):
        load_state(path, {"different": True})
    path.write_text('{broken')
    with pytest.raises(SupervisionError):
        load_state(path, {})


def test_single_output_owner(tmp_path):
    with owner_lock(tmp_path):
        with pytest.raises(SupervisionError):
            with owner_lock(tmp_path):
                pass


def options(tmp_path, once=True):
    return SimpleNamespace(input_basis="immutable-manifest-1", log_dir=str(tmp_path),
                           max_failed_exits=2, success_backoff=10, backoff=20,
                           stagger=0, poll=0, once=once)


def setup_specs(monkeypatch):
    monkeypatch.setattr(orchestrator, "build_specs", lambda _: [{"name": "fake", "argv": ["never-launched"]}])
    monkeypatch.setattr(orchestrator, "provider_revision", lambda _: "revision")
    monkeypatch.setattr(orchestrator, "session_clearance", lambda _: "clear")


def test_intent_precedes_dispatch_and_restart_refuses(tmp_path, monkeypatch):
    setup_specs(monkeypatch)
    path = tmp_path / "state.json"
    child = Mock(pid=987654)
    child.poll.return_value = None
    def dispatch(*args, **kwargs):
        assert json.loads(path.read_text())["stages"]["fake"]["state"] == "launch_intent"
        return child
    spawn = Mock(side_effect=dispatch)
    monkeypatch.setattr(orchestrator.subprocess, "Popen", spawn)
    assert orchestrator.supervise(options(tmp_path), {}, path) == 0
    assert load_state(path, {})["stages"]["fake"]["state"] == "running"
    assert orchestrator.supervise(options(tmp_path), {}, path) == 3
    assert spawn.call_count == 1
    child.terminate.assert_not_called()


def test_failed_intent_commit_prevents_dispatch(tmp_path, monkeypatch):
    setup_specs(monkeypatch)
    spawn = Mock()
    monkeypatch.setattr(orchestrator.subprocess, "Popen", spawn)
    monkeypatch.setattr(orchestrator, "save_state", Mock(side_effect=OSError("full")))
    with pytest.raises(OSError):
        orchestrator.supervise(options(tmp_path), {}, tmp_path / "state.json")
    spawn.assert_not_called()


def test_failed_exit_budget_survives_restart(tmp_path, monkeypatch):
    setup_specs(monkeypatch)
    path = tmp_path / "state.json"
    child = Mock(pid=987654)
    child.poll.return_value = 1
    spawn = Mock(return_value=child)
    monkeypatch.setattr(orchestrator.subprocess, "Popen", spawn)
    monkeypatch.setattr(orchestrator.time, "sleep", lambda _: None)
    ticks = iter(range(0, 10000, 30))
    monkeypatch.setattr(orchestrator.time, "time", lambda: next(ticks))
    assert orchestrator.supervise(options(tmp_path, once=False), {}, path) == 4
    assert spawn.call_count == 2
    assert load_state(path, {})["stages"]["fake"]["failed_exits"] == 2
    assert orchestrator.supervise(options(tmp_path), {}, path) == 0
    assert spawn.call_count == 2


def test_success_is_pass_done_not_recovery(tmp_path, monkeypatch):
    setup_specs(monkeypatch)
    path = tmp_path / "state.json"
    child = Mock(pid=987654)
    child.poll.return_value = 0
    monkeypatch.setattr(orchestrator.subprocess, "Popen", Mock(return_value=child))
    calls = 0
    def stop_after_poll(_):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt
    monkeypatch.setattr(orchestrator.time, "sleep", stop_after_poll)
    assert orchestrator.supervise(options(tmp_path, once=False), {}, path) == 130
    saved = load_state(path, {})["stages"]["fake"]
    assert saved["state"] == "pass_done"
    assert saved["failed_exits"] == 0
    assert "recovered" not in saved


def test_status_does_not_create_storage(tmp_path, capsys):
    output = tmp_path / "not-created"
    args = ["--program", "fake", "--repo", str(tmp_path), "--db", str(tmp_path / "db"),
            "--out-dir", str(output), "--kb", str(tmp_path / "kb"),
            "--raw", str(tmp_path / "raw"), "--binary-id", "1", "--status"]
    assert orchestrator.main(args) == 0
    assert json.loads(capsys.readouterr().out)["snapshot_only"]
    assert not output.exists()


def test_post_dispatch_commit_failure_retains_ambiguous_intent(tmp_path, monkeypatch):
    setup_specs(monkeypatch)
    path = tmp_path / "state.json"
    child = Mock(pid=987654)
    spawn = Mock(return_value=child)
    monkeypatch.setattr(orchestrator.subprocess, "Popen", spawn)
    real_save = orchestrator.save_state
    count = 0
    def fail_second(path, state):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("storage lost after dispatch")
        real_save(path, state)
    monkeypatch.setattr(orchestrator, "save_state", fail_second)
    with pytest.raises(OSError):
        orchestrator.supervise(options(tmp_path), {}, path)
    assert load_state(path, {})["stages"]["fake"]["state"] == "launch_intent"
    monkeypatch.setattr(orchestrator, "save_state", real_save)
    assert orchestrator.supervise(options(tmp_path), {}, path) == 3
    assert spawn.call_count == 1


def test_verify_policy_arguments_forwarded(tmp_path, monkeypatch):
    observed = []
    def inspect(a, scope, path):
        observed.extend(orchestrator.build_specs(a))
        return 0
    monkeypatch.setattr(orchestrator, "supervise", inspect)
    args = ["--program", "fake", "--repo", "logical/../repo-id", "--db", str(tmp_path / "db"),
            "--out-dir", str(tmp_path / "out"), "--kb", str(tmp_path / "kb"),
            "--raw", str(tmp_path / "raw"), "--binary-id", "1", "--input-basis", "manifest",
            "--cache-input-manifest", str(tmp_path / "closure.json"),
            "--transient-retry-seconds", "45", "--full-interval-seconds", "900"]
    assert orchestrator.main(args) == 0
    cascade = next(s["argv"] for s in observed if s["name"] == "cascade")
    assert cascade[cascade.index("--repo") + 1] == "logical/../repo-id"
    command = next(s["argv"] for s in observed if s["name"] == "verify")
    assert "--full-every" not in command
    assert command[command.index("--full-interval-seconds") + 1] == "900.0"
    assert command[command.index("--transient-retry-seconds") + 1] == "45.0"
    assert command[command.index("--cache-input-manifest") + 1] == str(tmp_path / "closure.json")


def test_interpreter_is_current_provider():
    import sys
    assert orchestrator._py("example.module") == [sys.executable, "-m", "example.module"]


def test_unsupported_lock_host_refuses_before_storage(tmp_path, monkeypatch):
    import builtins
    original = builtins.__import__
    def no_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("not supported")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_fcntl)
    directory = tmp_path / "not-created"
    with pytest.raises(SupervisionError, match="POSIX flock"):
        with owner_lock(directory):
            pass
    assert not directory.exists()
    assert load_state(directory / "state.json", {})["stages"] == {}


def test_distinct_output_scopes_have_distinct_logs(tmp_path, monkeypatch):
    setup_specs(monkeypatch)
    child = Mock(pid=987654)
    monkeypatch.setattr(orchestrator.subprocess, "Popen", Mock(return_value=child))
    for name in ("one", "two"):
        directory = tmp_path / name / ".supervision"
        directory.mkdir(parents=True)
        assert orchestrator.supervise(options(tmp_path), {}, directory / "state.json") == 0
    assert len(list(tmp_path.glob("orch_*_fake.log"))) == 2


@pytest.mark.parametrize("clearance", ["occupied", "unknown"])
def test_leader_exit_retains_reservation_with_uncleared_descendants(tmp_path, monkeypatch, clearance):
    setup_specs(monkeypatch)
    monkeypatch.setattr(orchestrator, "session_clearance", lambda _: clearance)
    monkeypatch.setattr(orchestrator.time, "sleep", lambda _: None)
    child = Mock(pid=987654)
    child.poll.return_value = 0
    spawn = Mock(return_value=child)
    monkeypatch.setattr(orchestrator.subprocess, "Popen", spawn)
    path = tmp_path / "state.json"
    assert orchestrator.supervise(options(tmp_path, once=False), {}, path) == 3
    assert load_state(path, {})["stages"]["fake"]["state"] == "needs_reconciliation"
    assert orchestrator.supervise(options(tmp_path), {}, path) == 3
    assert spawn.call_count == 1


def test_session_membership_and_unknown_identity(tmp_path):
    from agentdecompile_recovery.corpus.supervision import session_clearance
    boot = tmp_path / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text("boot")
    identity = {"pid": 100, "start_ticks": "5", "boot_id": "boot"}
    assert session_clearance({}, tmp_path) == "unknown"
    assert session_clearance(identity, tmp_path) == "clear"
    process = tmp_path / "101"
    process.mkdir()
    (process / "stat").write_text("101 (child) S 1 101 100")
    assert session_clearance(identity, tmp_path) == "occupied"
    (process / "stat").write_text("corrupt")
    assert session_clearance(identity, tmp_path) == "unknown"


def test_provider_revision_excludes_dashboard_edits(tmp_path):
    from agentdecompile_recovery.corpus.supervision import provider_revision
    (tmp_path / "worker.py").write_text("provider = 1")
    (tmp_path / "dashboard").mkdir()
    ui = tmp_path / "dashboard/view.py"
    ui.write_text("view = 1")
    first = provider_revision(tmp_path)
    ui.write_text("view = 2")
    assert provider_revision(tmp_path) == first
    (tmp_path / "worker.py").write_text("provider = 2")
    assert provider_revision(tmp_path) != first
