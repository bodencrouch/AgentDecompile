"""Acknowledgements require synchronized snapshot contents and directory entries."""

from __future__ import annotations

import errno
import json
import os
import stat

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.exchange import store as exchange

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["offer", "submit"])
@pytest.mark.parametrize("failure_stage", ["file", "directory"])
async def test_sync_failure_rejects_acknowledgement_and_retry_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, failure_stage: str
) -> None:
    if os.name == "nt" and failure_stage == "directory":
        pytest.skip("Windows does not support directory fsync")
    path = tmp_path / "new" / "state" / "exchange.json"
    store = exchange.ExchangeStore(path)
    payload = {"source": "int f(void) { return 1; }"}
    artifact = {"source": "int f(void) { return 2; }"}
    submission = None
    if operation == "submit":
        await store.offer(lane="rewrite", payload=payload)
        worker_id = (await store.enroll(capabilities=["llm"], agent="sync-test"))["workerId"]
        lease = await store.claim(worker_id=worker_id)
        assert lease is not None
        submission = dict(
            worker_id=worker_id,
            lease_token=lease["leaseToken"],
            fence=lease["fence"],
            idempotency_key="sync-retry",
            artifact=artifact,
            verdict="candidate",
        )

    committed_before = store._committed_generation
    real_fsync = os.fsync
    sync_events = []
    fail = True

    def checked_fsync(descriptor: int) -> None:
        stage = "directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file"
        sync_events.append(stage)
        if fail and stage == failure_stage:
            raise OSError(errno.EIO, "injected sync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(exchange.os, "fsync", checked_fsync)

    async def perform():
        if submission is not None:
            return await store.submit(**submission)
        return await store.offer(lane="rewrite", payload=payload)

    with pytest.raises(OSError, match="injected sync failure"):
        await perform()
    assert store._committed_generation == committed_before
    assert not list(path.parent.glob("*.tmp"))
    assert sync_events[0] == "file"
    if failure_stage == "directory":
        assert sync_events[1] == "directory"

    fail = False
    sync_events.clear()
    response = await perform()
    assert store._committed_generation > committed_before
    assert sync_events[0] == "file"
    if os.name != "nt":
        assert "directory" in sync_events[1:]
    unit_id = exchange.derive_unit_id("rewrite", payload)
    restored = exchange.ExchangeStore(path)
    unit = await restored.unit_state(unit_id)
    if operation == "submit":
        assert response["accepted"] is True
        assert unit["submission"]["artifact"] == artifact
        assert await restored.submit(**submission) == response
    else:
        assert response == unit_id
        assert unit["payload"] == payload


def test_file_contents_are_flushed_before_sync_and_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "exchange.json"
    store = exchange.ExchangeStore(path)
    real_fsync = os.fsync
    events = []

    def inspect_sync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            assert json.loads(path.read_text()) == {"snapshot": "new"}
            events.append("directory")
        else:
            temporary_files = list(tmp_path.glob("*.tmp"))
            assert len(temporary_files) == 1
            assert json.loads(temporary_files[0].read_text()) == {"snapshot": "new"}
            assert not path.exists()
            events.append("file")
        real_fsync(descriptor)

    monkeypatch.setattr(exchange.os, "fsync", inspect_sync)
    store._write_snapshot('{"snapshot": "new"}', 1)
    assert events[0] == "file"
    if os.name != "nt":
        assert events[1:] and set(events[1:]) == {"directory"}


def test_first_write_retries_ancestor_directory_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = exchange.ExchangeStore(tmp_path / "new" / "state" / "exchange.json")
    ancestor = tmp_path / "new"
    fail = True
    synced = []

    def sync_directory(path: Path) -> None:
        synced.append(path)
        if fail and path == ancestor:
            raise OSError(errno.EIO, "ancestor sync failed")

    monkeypatch.setattr(exchange, "_sync_directory", sync_directory)
    with pytest.raises(OSError, match="ancestor sync failed"):
        store._write_snapshot("{}", 1)
    assert store._committed_generation == 0
    fail = False
    synced.clear()
    store._write_snapshot("{}", 1)
    assert synced == [ancestor / "state", ancestor, tmp_path]
    assert store._committed_generation == 1
    synced.clear()
    store._write_snapshot("{}", 2)
    assert synced == [ancestor / "state"]


@pytest.mark.parametrize("existing_directory", [False, True])
def test_snapshot_syncs_only_created_entries_and_state_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_directory: bool
) -> None:
    state_directory = tmp_path / "new" / "state"
    if existing_directory:
        state_directory.mkdir(parents=True)
    store = exchange.ExchangeStore(state_directory / "exchange.json")
    expected = [state_directory] if existing_directory else [state_directory, state_directory.parent, tmp_path]
    synced = []

    def sync_directory(path: Path) -> None:
        if path not in expected:
            # Existing ancestors may allow traversal but forbid opening for
            # directory fsync; their unchanged entries do not need a sync.
            raise PermissionError(errno.EACCES, "traverse-only ancestor")
        synced.append(path)

    monkeypatch.setattr(exchange, "_sync_directory", sync_directory)
    store._write_snapshot("{}", 1)
    assert synced == expected
    assert store._committed_generation == 1


@pytest.mark.asyncio
async def test_ancestor_sync_obligation_survives_store_reconstruction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "new" / "state" / "exchange.json"
    payload = {"source": "int f(void) { return 1; }"}
    fail = True
    synced = []

    def sync_directory(directory: Path) -> None:
        assert directory in [path.parent, path.parent.parent, tmp_path]
        synced.append(directory)
        if fail and directory == tmp_path:
            raise OSError(errno.EIO, "ancestor sync failed")

    monkeypatch.setattr(exchange, "_sync_directory", sync_directory)
    with pytest.raises(OSError, match="ancestor sync failed"):
        await exchange.ExchangeStore(path).offer(lane="rewrite", payload=payload)
    assert path.exists()

    # A fresh store must still refuse acknowledgement while the ancestor
    # entry cannot be synchronized, despite the snapshot already existing.
    restored = exchange.ExchangeStore(path)
    with pytest.raises(OSError, match="ancestor sync failed"):
        await restored.offer(lane="rewrite", payload=payload)
    assert restored._committed_generation == 0
    fail = False
    synced.clear()
    assert await restored.offer(lane="rewrite", payload=payload) == exchange.derive_unit_id("rewrite", payload)
    assert synced == [path.parent, path.parent.parent, tmp_path]

    synced.clear()
    await restored.offer(lane="rewrite", payload=payload)
    assert synced == [path.parent]
    assert "pendingDirectorySyncDepth" not in json.loads(path.read_text())


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory synchronization")
def test_directory_sync_ignores_only_unsupported_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unsupported(descriptor: int) -> None:
        raise OSError(errno.EINVAL, "directory fsync unsupported")

    monkeypatch.setattr(exchange.os, "fsync", unsupported)
    exchange._sync_directory(tmp_path)

    def io_error(descriptor: int) -> None:
        raise OSError(errno.EIO, "disk error")

    monkeypatch.setattr(exchange.os, "fsync", io_error)
    with pytest.raises(OSError, match="disk error"):
        exchange._sync_directory(tmp_path)


def test_windows_skips_directory_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exchange, "os", SimpleNamespace(name="nt"))
    exchange._sync_directory(tmp_path)
