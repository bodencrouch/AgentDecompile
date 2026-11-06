"""Identical portable work retains every trusted local rewrite destination."""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from agentdecompile_recovery.exchange import producers
from agentdecompile_recovery.exchange.store import ExchangeStore

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_identical_rewrites_keep_all_destinations_after_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "state" / "exchange.json"
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(state_path))
    monkeypatch.chdir(tmp_path)
    destinations = [("first", "request-1"), ("second", "request-1"), ("first", "request-2")]
    ids = []
    for work_dir, request_id in destinations + [("./first", "request-1")]:
        ids.append(producers.offer_rewrite_unit(
            work_dir=work_dir,
            request_id=request_id,
            function_name="example",
            entry="0x401000",
            candidate_source="int example(void) { return 1; }",
        ))
    assert ids[0] is not None
    assert len(set(ids)) == 1
    directory = state_path.parent / producers.SPOOL_DIRNAME
    assert len(list(directory.glob("*.json"))) == 3

    # Each drain can be separated by a coordinator restart. A shared work unit
    # must not cause the second and third destination records to disappear.
    for _ in destinations:
        assert await producers.drain_spool(ExchangeStore(state_path), limit=1) == 1
    assert await producers.drain_spool(ExchangeStore(state_path)) == 0
    records = [json.loads(path.read_text()) for path in (directory / producers.ACCEPTED_DIRNAME).glob("*.json")]
    assert {(record["routing"]["workDir"], record["routing"]["requestId"]) for record in records} == {
        (str(tmp_path / work_dir), request_id) for work_dir, request_id in destinations
    }
    assert {record["unitId"] for record in records} == {ids[0]}
    for record in records:
        assert "workDir" not in record["payload"]
        assert "requestId" not in record["payload"]
    assert (await ExchangeStore(state_path).roster())["units"]["total"] == 1
