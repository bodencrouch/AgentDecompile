from __future__ import annotations

import asyncio
import threading

from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.dashboard.entity_activity import (
    ActivityBroadcaster,
    ActivityObserverLimitError,
    _ActivityStreamingResponse,
    add_facet,
    attach_dimensions,
    origin_evidence,
)
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_activity_broadcaster_shares_one_snapshot_per_scope() -> None:
    calls = 0

    def snapshotter(locator: str, slug: str, program: str) -> dict:
        nonlocal calls
        calls += 1
        assert (locator, slug, program) == ("/project", "game.exe", "game.exe")
        return {"ok": True, "revision": 1, "entities": []}

    broadcaster = ActivityBroadcaster(interval_seconds=60, max_observers=2, snapshotter=snapshotter)
    first = await broadcaster.subscribe("/project", "game.exe", "game.exe")
    second = await broadcaster.subscribe("/project", "game.exe", "game.exe")
    assert await asyncio.wait_for(first.get(), timeout=1) == ("snapshot", {"ok": True, "revision": 1, "entities": []}, 0)
    assert await asyncio.wait_for(second.get(), timeout=1) == ("snapshot", {"ok": True, "revision": 1, "entities": []}, 0)
    assert calls == 1
    assert broadcaster.observer_count == 2
    await broadcaster.unsubscribe("/project", "game.exe", "game.exe", first)
    await broadcaster.unsubscribe("/project", "game.exe", "game.exe", second)
    assert broadcaster.observer_count == 0


@pytest.mark.asyncio
async def test_activity_broadcaster_rejects_connections_over_cap() -> None:
    broadcaster = ActivityBroadcaster(interval_seconds=60, max_observers=1, snapshotter=lambda *_: {"ok": True, "revision": 1, "entities": []})
    queue = await broadcaster.subscribe("", "", "")
    with pytest.raises(ActivityObserverLimitError, match="observer limit"):
        await broadcaster.subscribe("", "", "")
    await broadcaster.unsubscribe("", "", "", queue)


@pytest.mark.asyncio
async def test_activity_broadcaster_reuses_inflight_snapshot_across_reconnect() -> None:
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def snapshotter(*_args: str) -> dict:
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(timeout=1)
        return {"ok": True, "revision": 1, "entities": []}

    broadcaster = ActivityBroadcaster(interval_seconds=60, max_observers=1, snapshotter=snapshotter)
    first = await broadcaster.subscribe("", "", "")
    await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1)
    first_task = next(iter(broadcaster._tasks.values()))
    await broadcaster.unsubscribe("", "", "", first)
    second = await broadcaster.subscribe("", "", "")
    assert next(iter(broadcaster._tasks.values())) is first_task
    assert calls == 1
    release.set()
    assert (await asyncio.wait_for(second.get(), timeout=1))[0] == "snapshot"
    await broadcaster.unsubscribe("", "", "", second)


@pytest.mark.asyncio
async def test_activity_broadcaster_republishes_snapshot_after_unavailable() -> None:
    attempts = 0

    def snapshotter(*_args: str) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("temporary read failure")
        return {"ok": True, "revision": 1, "entities": []}

    broadcaster = ActivityBroadcaster(interval_seconds=0.001, max_observers=1, snapshotter=snapshotter)
    queue = await broadcaster.subscribe("", "", "")
    assert (await asyncio.wait_for(queue.get(), timeout=1))[0] == "snapshot"
    assert (await asyncio.wait_for(queue.get(), timeout=1))[0] == "unavailable"
    assert (await asyncio.wait_for(queue.get(), timeout=1))[0] == "snapshot"
    await broadcaster.unsubscribe("", "", "", queue)


@pytest.mark.asyncio
async def test_activity_broadcaster_marks_lower_revision_as_authoritative_reset() -> None:
    revisions = iter((100, 1))
    broadcaster = ActivityBroadcaster(
        interval_seconds=0.001,
        max_observers=1,
        snapshotter=lambda *_: {"ok": True, "revision": next(revisions), "entities": []},
    )
    queue = await broadcaster.subscribe("", "", "")
    assert (await asyncio.wait_for(queue.get(), timeout=1))[0] == "snapshot"
    assert (await asyncio.wait_for(queue.get(), timeout=1))[0] == "reset"
    await broadcaster.unsubscribe("", "", "", queue)


@pytest.mark.asyncio
async def test_activity_broadcaster_keeps_reset_generation_when_queue_coalesces() -> None:
    values = iter((100, 1, 2))

    def snapshotter(*_args: str) -> dict:
        try:
            revision = next(values)
        except StopIteration:
            revision = 2
        return {"ok": True, "revision": revision, "entities": []}

    broadcaster = ActivityBroadcaster(interval_seconds=0.001, max_observers=1, snapshotter=snapshotter)
    queue = await broadcaster.subscribe("", "", "")
    assert (await asyncio.wait_for(queue.get(), timeout=1))[1]["revision"] == 100
    await asyncio.sleep(0.02)
    event, item, generation = await asyncio.wait_for(queue.get(), timeout=1)
    assert event == "snapshot"
    assert item["revision"] == 2
    assert generation == 1
    await broadcaster.unsubscribe("", "", "", queue)


@pytest.mark.asyncio
async def test_activity_broadcaster_retires_empty_scope_after_failed_snapshot() -> None:
    broadcaster = ActivityBroadcaster(interval_seconds=60, max_observers=1, snapshotter=lambda *_: (_ for _ in ()).throw(OSError("workspace unavailable")))
    queue = await broadcaster.subscribe("", "", "")
    assert (await asyncio.wait_for(queue.get(), timeout=1))[0] == "unavailable"
    await broadcaster.unsubscribe("", "", "", queue)
    for _ in range(10):
        if not broadcaster._tasks:
            break
        await asyncio.sleep(0)
    assert broadcaster._tasks == {}


@pytest.mark.asyncio
async def test_activity_stream_response_releases_admission_before_body_iteration() -> None:
    broadcaster = ActivityBroadcaster(interval_seconds=60, max_observers=1, snapshotter=lambda *_: {"ok": True, "revision": 1, "entities": []})
    queue = await broadcaster.subscribe("", "", "")

    async def body():
        yield b"data: never reached\\n\\n"

    async def receive() -> dict:
        return {"type": "http.request"}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            raise RuntimeError("client disconnected before stream body")

    response = _ActivityStreamingResponse(body(), media_type="text/event-stream", cleanup=lambda: broadcaster.unsubscribe("", "", "", queue))
    with pytest.raises(RuntimeError, match="disconnected"):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert broadcaster.observer_count == 0


def test_origin_evidence_keeps_human_stabs_and_match() -> None:
    kinds = {row["kind"] for row in origin_evidence("human", logical_id=12)}
    assert kinds == {"human", "match"}
    kinds = {row["kind"] for row in origin_evidence("stabs", logical_id=12)}
    assert kinds == {"debug", "match"}


def test_add_facet_does_not_replace_stabs_with_human() -> None:
    entity = {"facets": [{"kind": "debug", "label": "STABS types"}]}
    add_facet(entity, {"kind": "human", "label": "Human name"})
    add_facet(entity, {"kind": "match", "label": "Cross-match recorded"})
    add_facet(entity, {"kind": "human", "label": "Human name"})
    assert [row["kind"] for row in entity["facets"]] == ["debug", "human", "match"]


def test_attach_dimensions_split_proof_from_evidence() -> None:
    entity = {
        "status": "running",
        "stage": "Compare related builds",
        "action": "corpus.match-pair",
        "jobId": "job-1",
        "facets": [
            {"kind": "debug", "label": "STABS types"},
            {"kind": "human", "label": "Human names preserved"},
            {"kind": "match", "label": "Cross-match recorded"},
            {"kind": "recorded-proof", "label": "Recorded receipt", "source": "/tmp/receipt.json"},
        ],
        "proofReceipts": [{"label": "Recorded objdiff receipt", "path": "/tmp/objdiff.json"}],
    }
    attach_dimensions(entity)
    assert {row["kind"] for row in entity["evidence"]} == {"debug", "human", "match"}
    assert all(row["kind"] != "recorded-proof" for row in entity["evidence"])
    assert {row["kind"] for row in entity["proof"]} == {"recorded-proof"}
    assert entity["activity"]["status"] == "running"
    assert entity["activity"]["action"] == "corpus.match-pair"


def test_snapshot_reports_stabs_human_and_match_together(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "corpus.sqlite"
    source = tmp_path / "game.exe"
    source.write_bytes(b"MZ" + b"\0" * 64)
    con = connect(db)
    con.execute("INSERT INTO binary (repo_path, slug) VALUES (?, ?)", (str(source), "game.exe"))
    binary_id = con.execute("SELECT id FROM binary").fetchone()[0]
    con.execute(
        "INSERT INTO func (binary_id, addr, name, name_origin, source) VALUES (?,?,?,?,?)",
        (binary_id, 0x401000, "Init", "human", "USER_DEFINED"),
    )
    con.execute(
        "INSERT INTO stabs_type (binary_id, name, kind, stab) VALUES (?,?,?,?)",
        (binary_id, "int", "typedef", "int:t(0,1)"),
    )
    con.execute("INSERT INTO logical_function (best_name) VALUES ('Init')")
    logical_id = con.execute("SELECT id FROM logical_function").fetchone()[0]
    con.execute(
        "INSERT INTO identity (logical_id, binary_id, addr, confidence, method) VALUES (?,?,?,?,?)",
        (logical_id, binary_id, 0x401000, 0.9, "match:engine"),
    )
    con.commit()
    con.close()
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_DB", str(db))
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_WORK_DIR", str(tmp_path / "work"))
    from agentdecompile_recovery.corpus.dashboard import entity_activity as activity
    from agentdecompile_recovery.corpus.dashboard.common import query_db

    rows, error = query_db("SELECT slug FROM binary")
    assert error is None
    assert rows == [("game.exe",)]
    activity._LIBRARY = ("", 0, {})
    payload = activity.snapshot("", "game.exe")
    binary = next(row for row in payload["entities"] if row["kind"] == "binary" and row["slug"] == "game.exe")
    kinds = {row["kind"] for row in binary["evidence"]}
    assert "debug" in kinds
    assert "human" in kinds
    assert "match" in kinds
    assert all(row["kind"] != "recorded-proof" for row in binary["evidence"])
    assert binary["activity"]["status"] in {"idle", "running", "queued", "waiting", "cancelling"}
