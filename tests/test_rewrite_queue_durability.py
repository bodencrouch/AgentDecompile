"""New queue directories carry durable initialization intent across restarts."""

from __future__ import annotations

import errno
import importlib

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery import rewrite_queue

pytestmark = pytest.mark.unit
REQUEST = dict(function_name="f", entry="0x1000", candidate_source="int f(void) { return 1; }", mismatch_class=None, mismatch_histogram={})


def test_initial_queue_publish_follows_new_directory_and_parent_sync(tmp_path, monkeypatch):
    work_dir = tmp_path / "new" / "recovery"
    directory = rewrite_queue.queue_path(work_dir).parent
    synced = []
    real_sync, real_replace = rewrite_queue._sync_directory, Path.replace

    def sync(path, **kwargs):
        synced.append(path)
        return real_sync(path, **kwargs)

    def replace(path, target):
        assert synced[:5] == [tmp_path, directory, work_dir, work_dir.parent, tmp_path]
        return real_replace(path, target)

    monkeypatch.setattr(rewrite_queue, "_sync_directory", sync)
    monkeypatch.setattr(Path, "replace", replace)
    request_id = rewrite_queue.write_rewrite_request(work_dir, **REQUEST)
    assert rewrite_queue.find_entry(work_dir, request_id)["status"] == "pending"
    assert not list(tmp_path.glob(".rewrite-queue-init-*.pending"))


def test_initial_directory_sync_failure_survives_module_restart(tmp_path, monkeypatch):
    directory = rewrite_queue.queue_path(tmp_path).parent
    real_sync = rewrite_queue._sync_directory

    def fail_anchor(path, **kwargs):
        if path == tmp_path and directory.exists():
            raise OSError("injected new state anchor failure")
        return real_sync(path, **kwargs)

    monkeypatch.setattr(rewrite_queue, "_sync_directory", fail_anchor)
    with pytest.raises(OSError, match="new state anchor failure"):
        rewrite_queue.write_rewrite_request(tmp_path, **REQUEST)
    marker, = tmp_path.glob(".rewrite-queue-init-*.pending")
    assert directory.is_dir()
    assert not rewrite_queue.queue_path(tmp_path).exists()

    importlib.reload(rewrite_queue)
    retried = []
    real_sync = rewrite_queue._sync_directory

    def sync(path, **kwargs):
        retried.append(path)
        return real_sync(path, **kwargs)

    monkeypatch.setattr(rewrite_queue, "_sync_directory", sync)
    request_id = rewrite_queue.write_rewrite_request(tmp_path, **REQUEST)
    assert tmp_path in retried and directory in retried
    assert not marker.exists()
    assert rewrite_queue.find_entry(tmp_path, request_id)["status"] == "pending"


def test_unsupported_directory_sync_retains_intent_for_strict_forwarding(tmp_path, monkeypatch):
    real_sync = rewrite_queue._sync_directory
    monkeypatch.setattr(rewrite_queue, "_sync_directory", lambda *args, **kwargs: False)
    request_id = rewrite_queue.write_rewrite_request(tmp_path, **REQUEST)
    marker, = tmp_path.glob(".rewrite-queue-init-*.pending")
    monkeypatch.setattr(rewrite_queue, "_sync_directory", real_sync)
    payload = rewrite_queue.find_entry(tmp_path, request_id)
    assert rewrite_queue.import_exchange_result(tmp_path, request_id, payload=payload, source="int f(void) { return 2; }", receipt="receipt")
    assert not marker.exists()


def test_windows_directory_sync_is_optional_only_for_ordinary_queue_writes(monkeypatch):
    path = Path("state")
    monkeypatch.setattr(rewrite_queue, "os", SimpleNamespace(name="nt"))
    assert rewrite_queue._sync_directory(path) is False
    with pytest.raises(OSError) as error:
        rewrite_queue._sync_directory(path, required=True)
    assert error.value.errno == errno.ENOTSUP
