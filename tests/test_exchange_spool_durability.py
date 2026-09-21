"""A routing record is not acknowledged until its directory entry is stable."""

from __future__ import annotations

import errno
import hashlib
import os
import stat

from pathlib import Path

import pytest

from agentdecompile_recovery.exchange import producers
from agentdecompile_recovery.exchange.store import ExchangeStore

pytestmark = pytest.mark.unit

REQUEST = {
    "function_name": "f",
    "entry": "0x1000",
    "candidate_source": "int f(void) { return 1; }",
}


def test_offer_flushes_record_before_publish_then_syncs_route_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "state" / "exchange.json"
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(state_path))
    real_fsync = os.fsync
    real_replace = Path.replace
    events: list[str] = []

    def fsync(descriptor: int) -> None:
        assert not stat.S_ISDIR(os.fstat(descriptor).st_mode)
        events.append("file")
        real_fsync(descriptor)

    def replace(source: Path, target: Path) -> Path:
        events.append("replace")
        return real_replace(source, target)

    def sync(directory: Path) -> None:
        events.append("directory")

    monkeypatch.setattr(producers.os, "fsync", fsync)
    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(producers, "_sync_directory", sync)
    assert producers.offer_rewrite_unit(work_dir=tmp_path / "recovery", request_id="request", **REQUEST)
    assert "replace" in events
    assert events[-1] == "directory"
    spool = state_path.parent / producers.SPOOL_DIRNAME
    assert list(spool.glob("*.json"))


def test_offer_retries_visible_record_after_directory_sync_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "state" / "exchange.json"
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(state_path))
    fail = True

    def sync(_: Path) -> None:
        if fail:
            raise OSError("injected spool directory sync failure")

    monkeypatch.setattr(producers, "_sync_directory", sync)
    assert producers.offer_rewrite_unit(work_dir=tmp_path / "recovery", request_id="request", **REQUEST) is None
    spool = state_path.parent / producers.SPOOL_DIRNAME
    # The durable setup marker makes failure happen before publishing a route;
    # retry discovers that marker and completes the same creation obligation.
    assert len(list(spool.glob("*.json"))) == 0
    fail = False
    assert producers.offer_rewrite_unit(work_dir=tmp_path / "recovery", request_id="request", **REQUEST)


@pytest.mark.asyncio
async def test_archive_keeps_pending_route_until_accepted_copy_is_synced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "state" / "exchange.json"
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(state_path))
    assert producers.offer_rewrite_unit(work_dir=tmp_path / "recovery", request_id="request", **REQUEST)
    spool = state_path.parent / producers.SPOOL_DIRNAME
    pending = next(spool.glob("*.json"))
    fail = True

    def sync(directory: Path) -> None:
        if fail and directory.name == producers.ACCEPTED_DIRNAME:
            raise OSError("injected accepted directory sync failure")

    monkeypatch.setattr(producers, "_sync_directory", sync)
    store = ExchangeStore(state_path)
    assert await producers.drain_spool(store) == 0
    assert pending.exists()
    archived = spool / producers.ACCEPTED_DIRNAME / pending.name
    # The parent anchor failed before copying; the pending route remains the
    # sole durable copy and is never deleted in this state.
    assert not archived.exists()

    fail = False
    assert await producers.drain_spool(store) == 1
    assert not pending.exists()
    assert archived.exists()


def test_directory_setup_retries_a_failed_parent_anchor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "state" / producers.SPOOL_DIRNAME / producers.ACCEPTED_DIRNAME
    anchor = tmp_path
    fail = True

    def sync(directory: Path) -> None:
        if fail and directory == anchor:
            raise OSError("injected parent anchor failure")

    monkeypatch.setattr(producers, "_sync_directory", sync)
    with pytest.raises(OSError, match="parent anchor failure"):
        producers._ensure_directory(target)
    marker = next(anchor.glob(".exchange-spool-init-*.pending"))
    assert marker.exists()

    fail = False
    producers._ensure_directory(target)
    assert target.is_dir()
    assert not marker.exists()


def test_offer_recovers_a_pending_store_directory_anchor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "state" / "exchange.json"
    state_path.parent.mkdir()
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(state_path))
    marker = tmp_path / (".exchange-init-" + hashlib.sha256(os.fsencode(state_path.absolute())).hexdigest() + ".pending")
    marker.write_text("", encoding="utf-8")
    synced: list[Path] = []
    monkeypatch.setattr(producers, "_sync_directory", synced.append)

    assert producers.offer_rewrite_unit(work_dir=tmp_path / "recovery", request_id="request", **REQUEST)
    assert state_path.parent in synced
    assert tmp_path in synced
    assert not marker.exists()


def test_offer_recovers_exchange_and_rewrite_markers_through_outermost_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "new" / "state" / "exchange.json"
    state_path.parent.mkdir(parents=True)
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(state_path))
    exchange_marker = state_path.parent / (
        ".exchange-init-" + hashlib.sha256(os.fsencode(state_path.absolute())).hexdigest() + ".pending"
    )
    rewrite_marker = tmp_path / (
        ".rewrite-queue-init-" + hashlib.sha256(os.fsencode(state_path.parent.absolute())).hexdigest() + ".pending"
    )
    exchange_marker.write_text("", encoding="utf-8")
    rewrite_marker.write_text("", encoding="utf-8")
    synced: list[tuple[Path, bool]] = []

    def sync(directory: Path, *, required: bool = False) -> bool:
        synced.append((directory, required))
        return True

    monkeypatch.setattr(producers, "_sync_directory", sync)
    assert producers.offer_rewrite_unit(work_dir=tmp_path / "recovery", request_id="request", **REQUEST)
    assert {(state_path.parent, True), (state_path.parent.parent, True), (tmp_path, True)} <= set(synced)
    assert not exchange_marker.exists()
    assert not rewrite_marker.exists()


def test_offer_retains_adopted_rewrite_marker_when_directory_fsync_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "state" / "exchange.json"
    state_path.parent.mkdir()
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(state_path))
    marker = tmp_path / (
        ".rewrite-queue-init-" + hashlib.sha256(os.fsencode(state_path.parent.absolute())).hexdigest() + ".pending"
    )
    marker.write_text("", encoding="utf-8")

    def unsupported(_: Path, *, required: bool = False) -> bool:
        if required:
            raise OSError(errno.ENOTSUP, "directory fsync unsupported")
        return False

    monkeypatch.setattr(producers, "_sync_directory", unsupported)
    assert producers.offer_rewrite_unit(work_dir=tmp_path / "recovery", request_id="request", **REQUEST) is None
    assert marker.exists()
    assert not (state_path.parent / producers.SPOOL_DIRNAME).exists()
