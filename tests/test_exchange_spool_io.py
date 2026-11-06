"""Spool disk work must leave the proxy event loop free to serve other calls."""

from __future__ import annotations

import json
import threading

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.exchange import producers

pytestmark = pytest.mark.unit


def test_scan_stops_after_a_bounded_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    visited = []
    closed = []

    @contextmanager
    def scan(directory):
        def entries():
            for name in ("accepted", "rewrite-c.json", "rewrite-a.json", "rewrite-b.json"):
                visited.append(name)
                yield SimpleNamespace(name=name, path=str(directory / name), is_file=lambda: True)
            pytest.fail("scan exhausted the unbounded queue")

        try:
            yield entries()
        finally:
            closed.append(True)

    monkeypatch.setattr(producers.os, "scandir", scan)
    directory = Path("spool")
    assert producers._spool_entries(directory, 2) == [directory / "rewrite-a.json", directory / "rewrite-c.json"]
    assert visited == ["accepted", "rewrite-c.json", "rewrite-a.json"]
    assert closed == [True]


@pytest.mark.asyncio
async def test_drain_offloads_disk_work_and_preserves_offer_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    loop_thread = threading.get_ident()
    directory = Path("injected-state") / producers.SPOOL_DIRNAME
    paths = [directory / f"{name}.json" for name in ("valid", "unreadable", "schema", "payload", "retry")]
    archived = []
    quarantined = []
    offers = []

    def off_loop():
        assert threading.get_ident() != loop_thread

    def scan(path, limit):
        off_loop()
        assert path == directory
        assert limit == 5
        return paths

    def read(path):
        off_loop()
        if path.stem == "unreadable":
            raise json.JSONDecodeError("invalid", "", 0)
        if path.stem == "schema":
            return []
        return {"lane": "rewrite", "payload": {"name": path.stem}}

    def archive(path):
        off_loop()
        archived.append(path.stem)

    def quarantine(path):
        off_loop()
        quarantined.append(path.stem)

    async def offer(*, lane, payload):
        assert threading.get_ident() == loop_thread
        assert lane == "rewrite"
        offers.append(payload["name"])
        if payload["name"] == "payload":
            raise ValueError("nonportable payload")
        if payload["name"] == "retry":
            raise OSError("snapshot unavailable")

    monkeypatch.setattr(producers, "_spool_entries", scan)
    monkeypatch.setattr(producers, "_read_record", read)
    monkeypatch.setattr(producers, "_archive", archive)
    monkeypatch.setattr(producers, "_quarantine", quarantine)
    store = SimpleNamespace(state_path=Path("injected-state/state.json"), offer=offer)
    assert await producers.drain_spool(store, limit=5) == 1
    assert offers == ["valid", "payload", "retry"]
    assert archived == ["valid"]
    assert quarantined == ["unreadable", "schema", "payload"]
    assert await producers.drain_spool(store, limit=0) == 0
    assert await producers.drain_spool(store, limit=-1) == 0
