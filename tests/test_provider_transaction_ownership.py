"""Focused ownership regressions for provider persistence boundaries."""

from __future__ import annotations

import json
import sys

from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from typing import Callable

import pytest

from agentdecompile_cli.mcp_server.providers import import_export, project
from agentdecompile_cli.mcp_server.tool_providers import ToolProvider
from agentdecompile_cli.mcp_server.transaction_readiness import (
    TransactionBusyError,
    observe_transaction_readiness,
    require_transaction_readiness as real_require_transaction_readiness,
    save_project_owned_program,
)


class FakeTransactionInfo:
    def __init__(self, descriptions: list[str]) -> None:
        self.descriptions = descriptions

    def getID(self) -> int:
        return 9001

    def getOpenSubTransactions(self) -> list[str]:
        return list(self.descriptions)


class FakeDomainFile:
    def __init__(
        self,
        path: str = "/A",
        *,
        save_error: Exception | None = None,
        on_save: Callable[[], None] | None = None,
    ) -> None:
        self.path = path
        self.save_error = save_error
        self.on_save = on_save
        self.save_calls = 0
        self.checkin_calls = 0
        self.delete_calls = 0
        self.consumer_tokens: list[object] = []
        self.opened_program: FakeProgram | None = None

    def getPathname(self) -> str:
        return self.path

    def getName(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    def getConsumers(self) -> list[object]:
        return list(self.consumer_tokens)

    def getDomainObject(self, consumer: object, *_args: object) -> FakeProgram | None:
        if consumer not in self.consumer_tokens:
            self.consumer_tokens.append(consumer)
        return self.opened_program

    def save(self, _monitor: object) -> None:
        self.save_calls += 1
        if self.on_save is not None:
            self.on_save()
        if self.save_error is not None:
            raise self.save_error

    def isVersioned(self) -> bool:
        return True

    def isCheckedOut(self) -> bool:
        return True

    def canCheckin(self) -> bool:
        return True

    def checkin(self, _handler: object, _monitor: object) -> None:
        self.checkin_calls += 1

    def delete(self) -> None:
        self.delete_calls += 1


class FakeProgram:
    def __init__(
        self,
        domain_file: FakeDomainFile,
        entries: dict[int, str] | None = None,
        *,
        next_handle: int = 102,
        events: list[object] | None = None,
    ) -> None:
        self.domain_file = domain_file
        self.entries = dict(entries or {})
        self.next_handle = next_handle
        self.end_calls: list[tuple[int, bool]] = []
        self.end_attempts: list[tuple[int, bool]] = []
        self.start_calls: list[str] = []
        self.closed = False
        self.events = events if events is not None else []
        domain_file.opened_program = self

    def getCurrentTransactionInfo(self) -> FakeTransactionInfo | None:
        if not self.entries:
            return None
        return FakeTransactionInfo(list(self.entries.values()))

    def startTransaction(self, label: str) -> int:
        handle = self.next_handle
        self.next_handle += 1
        self.entries[handle] = label
        self.start_calls.append(label)
        return handle

    def endTransaction(self, handle: int, commit: bool) -> None:
        self.end_attempts.append((handle, commit))
        if handle not in self.entries:
            raise RuntimeError("Transaction not found")
        self.end_calls.append((handle, commit))
        self.entries.pop(handle)

    def getDomainFile(self) -> FakeDomainFile:
        return self.domain_file

    def getName(self) -> str:
        return self.domain_file.getName()

    def setEventsEnabled(self, enabled: bool) -> None:
        self.events.append(("events", enabled))

    def save(self, _comment: str, monitor: object) -> None:
        self.domain_file.save(monitor)

    def release(self, consumer: object) -> None:
        if consumer in self.domain_file.consumer_tokens:
            self.domain_file.consumer_tokens.remove(consumer)
        self.closed = not self.domain_file.consumer_tokens

    def isClosed(self) -> bool:
        return self.closed


class FakeOpenPrograms(dict[FakeProgram, int]):
    def put(self, program: FakeProgram, handle: int) -> None:
        self[program] = int(handle)

    def remove(self, program: FakeProgram) -> None:
        self.pop(program, None)


class FakeField:
    def __init__(self, values: FakeOpenPrograms) -> None:
        self.values = values

    def setAccessible(self, _accessible: bool) -> None:
        pass

    def get(self, _project: object) -> FakeOpenPrograms:
        return self.values


class FakeProjectClass:
    def __init__(self, values: FakeOpenPrograms) -> None:
        self.values = values

    def getDeclaredField(self, name: str) -> FakeField:
        assert name == "openPrograms"
        return FakeField(self.values)


class FakeGhidraProject:
    def __init__(self, program: FakeProgram, handle: int = 101, *, events: list[object] | None = None) -> None:
        self.open_programs = FakeOpenPrograms({program: handle})
        self.save_calls = 0
        self.close_calls = 0
        self.events = events if events is not None else []
        program.domain_file.consumer_tokens.append(self)

    def getClass(self) -> FakeProjectClass:
        return FakeProjectClass(self.open_programs)

    def save(self, program: FakeProgram) -> None:
        self.save_calls += 1
        handle = self.open_programs[program]
        program.endTransaction(handle, True)
        program.getDomainFile().save(object())
        replacement = program.startTransaction("")
        self.open_programs.put(program, replacement)

    def close(self, program: FakeProgram) -> None:
        self.close_calls += 1
        handle = self.open_programs.get(program)
        self.open_programs.remove(program)
        if handle is not None:
            program.endTransaction(handle, True)
            program.release(self)
        self.events.append("close")


@pytest.fixture
def fake_java_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    task_monitor = SimpleNamespace(DUMMY=object())
    modules = {
        "ghidra": ModuleType("ghidra"),
        "ghidra.util": ModuleType("ghidra.util"),
        "ghidra.util.task": ModuleType("ghidra.util.task"),
        "ghidra.framework": ModuleType("ghidra.framework"),
        "ghidra.framework.data": ModuleType("ghidra.framework.data"),
        "java": ModuleType("java"),
        "java.lang": ModuleType("java.lang"),
        "jpype": ModuleType("jpype"),
    }
    modules["ghidra.util.task"].TaskMonitor = task_monitor
    modules["ghidra.framework.data"].DefaultCheckinHandler = lambda *args: args
    modules["java.lang"].Integer = int
    modules["java.lang"].System = SimpleNamespace(getProperty=lambda _name: "owner")
    modules["jpype"].synchronized = lambda _value: nullcontext()
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def fast_require(program: object, *, ghidra_project: object = None, **_kwargs: object) -> int | None:
    return real_require_transaction_readiness(program, ghidra_project=ghidra_project, timeout_sec=0.0)


def test_metadata_id_is_observational_and_never_ended() -> None:
    domain_file = FakeDomainFile()
    program = FakeProgram(domain_file, {101: "Batch Processing", 102: "analysis"})

    observation = observe_transaction_readiness(program, owned_batch_handle=101)

    assert observation.ready is False
    assert observation.database_id == 9001
    assert observation.open_descriptions == ("Batch Processing", "analysis")
    assert program.end_calls == []


def test_owned_cli_handle_37_is_released_on_success_and_failure() -> None:
    success = FakeProgram(FakeDomainFile(), next_handle=37)
    failure = FakeProgram(FakeDomainFile(), next_handle=37)

    assert ToolProvider._run_program_transaction(success, "owned", lambda: "ok") == "ok"
    with pytest.raises(ValueError, match="boom"):
        ToolProvider._run_program_transaction(failure, "owned", lambda: (_ for _ in ()).throw(ValueError("boom")))

    assert success.end_calls == [(37, True)]
    assert failure.end_calls == [(37, False)]
    assert all(handle != 9001 for handle, _commit in success.end_calls + failure.end_calls)


def test_project_batch_101_restarts_as_102_and_save_failure_repairs_map(
    monkeypatch: pytest.MonkeyPatch,
    fake_java_modules: None,
) -> None:
    monkeypatch.setattr(import_export, "require_transaction_readiness", fast_require)
    provider = import_export.ImportExportToolProvider()

    domain_file = FakeDomainFile()
    program = FakeProgram(domain_file, {101: "Batch Processing"}, next_handle=102)
    ghidra_project = FakeGhidraProject(program)
    assert provider._local_save_via_reflection(ghidra_project, program, domain_file, "save", timeout_sec=0.0) == "primary"
    assert program.end_calls == [(101, True)]
    assert ghidra_project.open_programs[program] == 102
    assert 9001 not in {handle for handle, _commit in program.end_calls}

    failing_file = FakeDomainFile(save_error=RuntimeError("disk full"))
    failing_program = FakeProgram(failing_file, {101: "Batch Processing"}, next_handle=102)
    failing_project = FakeGhidraProject(failing_program)
    assert provider._local_save_via_reflection(failing_project, failing_program, failing_file, "save", timeout_sec=0.0) is None
    assert failing_project.open_programs[failing_program] == 102
    assert failing_program.end_calls == [(101, True)]

    delegated_file = FakeDomainFile(save_error=RuntimeError("disk full"))
    delegated_program = FakeProgram(delegated_file, {101: "Batch Processing"}, next_handle=102)
    delegated_project = FakeGhidraProject(delegated_program)
    with pytest.raises(RuntimeError, match="disk full"):
        save_project_owned_program(delegated_project, delegated_program, timeout_sec=0.0)
    assert delegated_project.open_programs[delegated_program] == 102
    delegated_file.save_error = None
    assert save_project_owned_program(delegated_project, delegated_program, timeout_sec=0.0) == 103
    assert delegated_program.end_attempts == [(101, True), (102, True)]

    foreign_file = FakeDomainFile(save_error=RuntimeError("disk full"))
    foreign_program = FakeProgram(foreign_file, {101: "Batch Processing"}, next_handle=102)
    foreign_project = FakeGhidraProject(foreign_program)
    foreign_file.on_save = lambda: foreign_program.startTransaction("analysis")
    with pytest.raises(RuntimeError, match="disk full"):
        save_project_owned_program(foreign_project, foreign_program, timeout_sec=0.0)
    assert foreign_program not in foreign_project.open_programs
    foreign_project.close(foreign_program)
    assert foreign_program.entries == {102: "analysis"}
    assert foreign_program.end_attempts == [(101, True)]


@pytest.mark.asyncio
async def test_foreign_nested_entry_makes_checkin_fail_without_save_or_checkin(
    monkeypatch: pytest.MonkeyPatch,
    fake_java_modules: None,
) -> None:
    monkeypatch.setattr(import_export, "require_transaction_readiness", fast_require)
    domain_file = FakeDomainFile()
    program = FakeProgram(domain_file, {101: "Batch Processing", 102: "analysis"})
    ghidra_project = FakeGhidraProject(program)
    info = SimpleNamespace(program=program, current_program=None, decompiler=None, domain_object_consumer=None)
    session = SimpleNamespace(open_programs={"/A": info}, active_program_key="/A")
    provider = import_export.ImportExportToolProvider()
    provider._manager = SimpleNamespace(ghidra_project=ghidra_project)
    monkeypatch.setattr(import_export, "get_current_mcp_session_id", lambda: "tx-test")
    monkeypatch.setattr(import_export.SESSION_CONTEXTS, "get_or_create", lambda _sid: session)
    monkeypatch.setattr(provider, "_shared_repository_has_program_path", lambda _path: False)
    monkeypatch.setattr(
        provider,
        "_require_program_transaction_ready",
        lambda candidate, *, allow_project_batch, timeout_sec=30.0: real_require_transaction_readiness(
            candidate,
            ghidra_project=ghidra_project if allow_project_batch else None,
            timeout_sec=0.0,
        ),
    )

    with pytest.raises(TransactionBusyError):
        provider._save_and_close_project_program(ghidra_project, program, timeout_sec=0.0)
    assert ghidra_project.close_calls == 0
    assert program.end_calls == []

    with monkeypatch.context() as publish_patch:
        publish_patch.setattr(provider, "_bump_versioned_checkout_dirty_bookmark", lambda _program: None)
        publish_patch.setattr(
            provider,
            "_persist_open_program_for_versioned_checkin",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("save failed")),
        )
        with pytest.raises(RuntimeError, match="save failed"):
            provider._prepare_shared_import_program_for_publish(
                ghidra_project,
                program,
                domain_file,
                program_info=info,
            )
    assert domain_file.checkin_calls == 0
    assert ghidra_project.close_calls == 0

    response = await provider._handle_checkin({}, program_info=info)
    payload = json.loads(response[0].text)

    assert payload["success"] is False
    assert payload["results"][0]["success"] is False
    assert domain_file.save_calls == 0
    assert domain_file.checkin_calls == 0
    assert program.end_calls == []


def test_sync_push_foreign_entry_records_error_without_save(
    monkeypatch: pytest.MonkeyPatch,
    fake_java_modules: None,
) -> None:
    monkeypatch.setattr(project, "require_transaction_readiness", fast_require)
    domain_file = FakeDomainFile()
    program = FakeProgram(domain_file, {101: "Batch Processing", 102: "analysis"})
    ghidra_project = FakeGhidraProject(program)
    session = SimpleNamespace(open_programs={})
    provider = project.ProjectToolProvider()
    provider._manager = SimpleNamespace(ghidra_project=ghidra_project, providers=[])
    project_data = SimpleNamespace(getRootFolder=lambda: object(), getFile=lambda _path: domain_file)
    monkeypatch.setattr(provider, "_list_domain_files", lambda _root, _limit: [{"path": "/A", "type": "Program"}])
    monkeypatch.setattr(project, "get_current_mcp_session_id", lambda: "tx-test")
    monkeypatch.setattr(project.SESSION_CONTEXTS, "get_or_create", lambda _sid: session)

    result = provider._push_local_project_to_shared({}, "repo", project_data, program_info=None)

    assert result["transferred"] == 0
    assert len(result["errors"]) == 1
    assert domain_file.save_calls == 0
    assert program.end_calls == []
    assert domain_file.getConsumers() == [ghidra_project]

    import_provider = import_export.ImportExportToolProvider()
    import_provider._manager = SimpleNamespace(ghidra_project=ghidra_project)
    monkeypatch.setattr(import_export, "require_transaction_readiness", fast_require)
    with pytest.raises(TransactionBusyError):
        import_provider._require_domain_file_consumers_ready(
            domain_file,
            allow_project_batch=True,
            timeout_sec=0.0,
        )
    assert domain_file.getConsumers() == [ghidra_project]

    clean_file = FakeDomainFile()
    clean_program = FakeProgram(clean_file, {101: "Batch Processing"}, next_handle=102)
    clean_project = FakeGhidraProject(clean_program)
    provider._manager = SimpleNamespace(ghidra_project=clean_project, providers=[])
    clean_project_data = SimpleNamespace(getRootFolder=lambda: object(), getFile=lambda _path: clean_file)
    clean_result = provider._push_local_project_to_shared({}, "repo", clean_project_data, program_info=None)
    assert clean_result["transferred"] == 1
    assert clean_result["errors"] == []
    assert clean_file.save_calls == 1
    assert clean_program.end_calls == [(101, True)]
    assert clean_file.getConsumers() == [clean_project]


def test_forced_pull_preserves_foreign_target_and_closes_owned_batch_before_delete(
    monkeypatch: pytest.MonkeyPatch,
    fake_java_modules: None,
) -> None:
    monkeypatch.setattr(project, "require_transaction_readiness", fast_require)
    provider = project.ProjectToolProvider()
    events: list[object] = []
    domain_file = FakeDomainFile()
    program = FakeProgram(domain_file, {101: "Batch Processing", 102: "analysis"}, events=events)
    info = SimpleNamespace(program=program, current_program=None, decompiler=None, domain_object_consumer=None)
    ghidra_project = FakeGhidraProject(program, events=events)
    provider._manager = SimpleNamespace(ghidra_project=ghidra_project)
    session = SimpleNamespace(open_programs={"/A": info}, active_program_key="/A")
    monkeypatch.setattr(project, "get_current_mcp_session_id", lambda: "tx-test")
    monkeypatch.setattr(project.SESSION_CONTEXTS, "get_or_create", lambda _sid: session)
    monkeypatch.setattr(project.SESSION_CONTEXTS, "get_project_binaries", lambda *_args, **_kwargs: [{"path": "/A"}])
    project_data = SimpleNamespace(getFile=lambda _path: domain_file)

    result = provider._pull_shared_repository_to_local(
        {"force": True},
        SimpleNamespace(),
        "repo",
        project_data,
        program_info=info,
    )
    assert result["transferred"] == 0
    assert len(result["errors"]) == 1
    assert domain_file.delete_calls == 0
    assert program.end_calls == []

    program.entries.pop(102)
    parent = SimpleNamespace(createFile=lambda *_args: events.append("create"))
    remote = SimpleNamespace(release=lambda _consumer: events.append("remote-release"))
    monkeypatch.setattr(provider, "_ensure_project_folder", lambda *_args: parent)
    monkeypatch.setattr(provider, "_get_domain_object_compat", lambda *_args: remote)
    original_delete = domain_file.delete

    def delete() -> None:
        events.append("delete")
        original_delete()

    domain_file.delete = delete  # type: ignore[method-assign]
    result = provider._pull_shared_repository_to_local(
        {"force": True},
        SimpleNamespace(),
        "repo",
        project_data,
        program_info=info,
    )
    assert result["transferred"] == 1
    assert events.index("close") < events.index("delete")
    assert program.end_calls == [(101, True)]


@pytest.mark.asyncio
async def test_clean_direct_and_project_batch_paths_persist_once(
    monkeypatch: pytest.MonkeyPatch,
    fake_java_modules: None,
) -> None:
    direct_file = FakeDomainFile()
    direct_file.isVersioned = lambda: False  # type: ignore[method-assign]
    direct_program = FakeProgram(direct_file)
    direct_info = SimpleNamespace(program=direct_program, current_program=None, decompiler=None, domain_object_consumer=None)
    direct_session = SimpleNamespace(open_programs={"/direct": direct_info}, active_program_key="/direct")
    direct_provider = import_export.ImportExportToolProvider()
    direct_provider._manager = SimpleNamespace(ghidra_project=None)
    monkeypatch.setattr(import_export, "get_current_mcp_session_id", lambda: "tx-test")
    monkeypatch.setattr(import_export.SESSION_CONTEXTS, "get_or_create", lambda _sid: direct_session)
    monkeypatch.setattr(direct_provider, "_canonical_program_path_for_session", lambda path: path)
    monkeypatch.setattr(direct_provider, "_resolve_domain_file_for_checkout_status", lambda *_args, **_kwargs: (direct_file, "direct"))
    monkeypatch.setattr(direct_provider, "_resolve_program_for_domain_file", lambda *_args, **_kwargs: direct_program)
    monkeypatch.setattr(direct_provider, "_shared_repository_has_program_path", lambda _path: False)
    from agentdecompile_cli.mcp_utils import program_analysis

    monkeypatch.setattr(program_analysis, "wait_for_program_analysis_idle", lambda *_args, **_kwargs: True)
    direct_response = await direct_provider._handle_checkin({"programPath": "/direct"}, program_info=direct_info)
    direct_payload = json.loads(direct_response[0].text)
    assert direct_payload["success"] is True
    assert direct_file.save_calls == 1

    monkeypatch.setattr(import_export, "require_transaction_readiness", fast_require)
    batch_file = FakeDomainFile()
    batch_program = FakeProgram(batch_file, {101: "Batch Processing"}, next_handle=102)
    ghidra_project = FakeGhidraProject(batch_program)
    info = SimpleNamespace(program=batch_program, current_program=None, decompiler=None, domain_object_consumer=None)
    session = SimpleNamespace(open_programs={"/A": info}, active_program_key="/A")
    provider = import_export.ImportExportToolProvider()
    provider._manager = SimpleNamespace(ghidra_project=ghidra_project)
    monkeypatch.setattr(import_export, "get_current_mcp_session_id", lambda: "tx-test")
    monkeypatch.setattr(import_export.SESSION_CONTEXTS, "get_or_create", lambda _sid: session)
    monkeypatch.setattr(provider, "_shared_repository_has_program_path", lambda _path: False)
    monkeypatch.setattr(
        provider,
        "_save_domain_file_before_versioned_checkin",
        lambda _domain_file, candidate, *, program_info: provider._persist_open_program_for_versioned_checkin(
            candidate,
            program_info=program_info,
        ),
    )
    monkeypatch.setattr(
        provider,
        "_require_program_transaction_ready",
        lambda candidate, *, allow_project_batch, timeout_sec=30.0: real_require_transaction_readiness(
            candidate,
            ghidra_project=ghidra_project if allow_project_batch else None,
            timeout_sec=0.0,
        ),
    )

    response = await provider._handle_checkin({}, program_info=info)
    payload = json.loads(response[0].text)

    assert payload["success"] is True
    assert ghidra_project.save_calls == 1
    assert ghidra_project.close_calls == 1
    assert batch_file.save_calls == 1
    assert batch_file.checkin_calls == 1
    assert batch_program.end_calls == [(101, True), (102, True)]
    assert 9001 not in {handle for handle, _commit in batch_program.end_calls}


@pytest.mark.parametrize("save_fails", [False, True])
def test_sync_push_saves_exact_requested_file_with_same_basename(
    monkeypatch: pytest.MonkeyPatch,
    fake_java_modules: None,
    save_fails: bool,
) -> None:
    monkeypatch.setattr(project, "require_transaction_readiness", fast_require)
    unrelated_file = FakeDomainFile("/A/foo")
    unrelated_program = FakeProgram(unrelated_file)
    unrelated_info = SimpleNamespace(program=unrelated_program, current_program=None)
    requested_file = FakeDomainFile(
        "/B/foo", save_error=RuntimeError("requested save failed") if save_fails else None,
    )
    requested_program = FakeProgram(requested_file)
    existing_owner = object()
    requested_file.consumer_tokens.append(existing_owner)
    session = SimpleNamespace(open_programs={"/A/foo": unrelated_info})
    provider = project.ProjectToolProvider()
    provider._manager = SimpleNamespace(ghidra_project=None, providers=[])
    project_data = SimpleNamespace(
        getRootFolder=lambda: object(),
        getFile=lambda path: requested_file if path == "/B/foo" else None,
    )
    monkeypatch.setattr(provider, "_list_domain_files", lambda _root, _limit: [{"path": "/B/foo", "type": "Program"}])
    monkeypatch.setattr(project, "get_current_mcp_session_id", lambda: "identity-test")
    monkeypatch.setattr(project.SESSION_CONTEXTS, "get_or_create", lambda _sid: session)

    result = provider._push_local_project_to_shared({}, "repo", project_data, program_info=unrelated_info)

    assert unrelated_file.save_calls == 0
    assert requested_file.save_calls == 1
    assert requested_file.consumer_tokens == [existing_owner]
    assert not requested_program.closed
    assert result["transferred"] == (0 if save_fails else 1)
    if save_fails:
        assert len(result["errors"]) == 1
        assert "requested save failed" in result["errors"][0]["error"]
    else:
        assert result["errors"] == []
