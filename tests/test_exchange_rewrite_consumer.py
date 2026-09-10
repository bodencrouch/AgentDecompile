"""Trusted routing, durable retry, and competing fulfiller coverage."""

from __future__ import annotations

import json
import stat

import pytest

from agentdecompile_recovery import rewrite_queue
from agentdecompile_recovery.exchange import producers
from agentdecompile_recovery.exchange.consumers import RewriteConsumer
from agentdecompile_recovery.exchange.store import STATUS_AWAITING_VERIFICATION, ExchangeStore

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

REQUEST = {
    "function_name": "f",
    "entry": "0x1000",
    "candidate_source": "int f(void) { return 1; }",
    "mismatch_class": "REPLACEMENT",
    "mismatch_histogram": {"REPLACEMENT": 1},
    "aligned_diff": [],
    "compiler_profile": "msvc-vc7",
}


async def prepare(tmp_path, monkeypatch, artifact=None):
    store = ExchangeStore(tmp_path / "exchange" / "state.json")
    monkeypatch.setenv("AGENT_DECOMPILE_EXCHANGE_ENABLED", "true")
    monkeypatch.setenv("AGENTDECOMPILE_EXCHANGE_STATE", str(store.state_path))
    work_dir = tmp_path / "recovery"
    request_id = rewrite_queue.write_rewrite_request(work_dir, **REQUEST)
    unit_id = producers.offer_rewrite_unit(work_dir=work_dir, request_id=request_id, **REQUEST)
    assert await producers.drain_spool(store) == 1
    worker = await store.enroll(capabilities=["llm"], agent="test")
    lease = await store.claim(worker_id=worker["workerId"])
    await store.submit(
        worker_id=worker["workerId"], lease_token=lease["leaseToken"], fence=lease["fence"],
        idempotency_key="proposal", artifact={"source": "int f(void) { return 2; }"} if artifact is None else artifact,
        verdict="completed",
    )
    return store, unit_id, work_dir, request_id


async def test_transfer_is_durable_idempotent_and_reaches_late_destination(tmp_path, monkeypatch):
    forged = tmp_path / "forged"
    store, unit_id, work_dir, request_id = await prepare(
        tmp_path, monkeypatch, {"source": "int f(void) { return 2; }", "workDir": str(forged), "requestId": "forged"}
    )
    assert await RewriteConsumer(store).drain() == 1
    entry = rewrite_queue.find_entry(work_dir, request_id)
    assert entry["source"] == "int f(void) { return 2; }"
    assert entry["status"] == "completed" and entry["exchangeReceipt"]
    assert not forged.exists()
    restored = ExchangeStore(store.state_path)
    state = await restored.unit_state(unit_id)
    assert state["status"] == STATUS_AWAITING_VERIFICATION
    assert len(state["submission"]["forwarded"]) == 1
    assert await RewriteConsumer(restored).drain() == 0
    assert rewrite_queue.find_entry(work_dir, request_id) == entry

    second = tmp_path / "second"
    second_request = rewrite_queue.write_rewrite_request(second, **REQUEST)
    assert producers.offer_rewrite_unit(work_dir=second, request_id=second_request, **REQUEST) == unit_id
    assert await producers.drain_spool(restored) == 1
    assert await RewriteConsumer(restored).drain() == 1
    assert rewrite_queue.find_entry(second, second_request)["source"] == entry["source"]
    assert len((await restored.unit_state(unit_id))["submission"]["forwarded"]) == 2


@pytest.mark.parametrize("artifact", [{}, {"source": " "}, {"source": 23}, {"source": "bad\x00source"}])
async def test_malformed_source_stays_awaiting(tmp_path, monkeypatch, artifact):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch, artifact)
    assert await RewriteConsumer(store).drain() == 0
    assert rewrite_queue.find_entry(work_dir, request_id)["status"] == "pending"
    assert "forwarded" not in (await store.unit_state(unit_id))["submission"]


@pytest.mark.parametrize("fail_directory_sync", [False, True])
async def test_queue_fsync_failure_never_acknowledges_and_retry_recovers(tmp_path, monkeypatch, fail_directory_sync):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)
    real_sync = rewrite_queue.os.fsync

    def fail_sync(fd):
        if stat.S_ISDIR(rewrite_queue.os.fstat(fd).st_mode) == fail_directory_sync:
            raise OSError("injected queue fsync failure")
        real_sync(fd)

    monkeypatch.setattr(rewrite_queue.os, "fsync", fail_sync)
    assert await RewriteConsumer(store).drain() == 0
    assert "forwarded" not in (await store.unit_state(unit_id))["submission"]
    # Failed file sync preserves the old queue; failed directory sync leaves a
    # visible receipt whose durable acknowledgement still needs retrying.
    assert rewrite_queue.find_entry(work_dir, request_id)["status"] == ("completed" if fail_directory_sync else "pending")
    monkeypatch.setattr(rewrite_queue.os, "fsync", real_sync)
    assert await RewriteConsumer(store).drain() == 1


async def test_later_queue_replacement_preserves_forwarded_result_on_sync_failure(tmp_path, monkeypatch):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)
    assert await RewriteConsumer(store).drain() == 1
    forwarded_entry = rewrite_queue.find_entry(work_dir, request_id)
    path = rewrite_queue.queue_path(work_dir)
    before = path.read_bytes()
    real_sync = rewrite_queue.os.fsync

    def fail_sync(fd):
        raise OSError("injected later queue fsync failure")

    monkeypatch.setattr(rewrite_queue.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="later queue fsync"):
        rewrite_queue.write_rewrite_request(work_dir, **{**REQUEST, "function_name": "second"})
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))
    monkeypatch.setattr(rewrite_queue.os, "fsync", real_sync)
    second_id = rewrite_queue.write_rewrite_request(work_dir, **{**REQUEST, "function_name": "second"})
    assert rewrite_queue.find_entry(work_dir, request_id) == forwarded_entry
    assert rewrite_queue.find_entry(work_dir, second_id)["status"] == "pending"
    restored = ExchangeStore(store.state_path)
    assert len((await restored.unit_state(unit_id))["submission"]["forwarded"]) == 1
    assert await RewriteConsumer(restored).drain() == 0


async def test_queue_mutations_preserve_forwarded_result_on_read_failure(tmp_path, monkeypatch):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)
    assert await RewriteConsumer(store).drain() == 1
    forwarded_entry = rewrite_queue.find_entry(work_dir, request_id)
    path = rewrite_queue.queue_path(work_dir)
    before = path.read_bytes()
    real_read = rewrite_queue.read_json

    def fail_read(path):
        raise OSError("injected queue read failure")

    monkeypatch.setattr(rewrite_queue, "read_json", fail_read)
    mutations = (
        lambda: rewrite_queue.write_rewrite_request(work_dir, **{**REQUEST, "function_name": "second"}),
        lambda: rewrite_queue.claim_pending_entry(work_dir, request_id, claimant="local"),
        lambda: rewrite_queue.release_claim(work_dir, request_id, claimant="local"),
        lambda: rewrite_queue.write_claimed_result(work_dir, request_id, claimant="local", status="completed"),
        lambda: rewrite_queue.prune_consumed_entries(work_dir, [request_id]),
        lambda: rewrite_queue.import_exchange_result(work_dir, request_id, payload={}, source="x", receipt="x"),
    )
    for mutate in mutations:
        with pytest.raises(OSError, match="queue read failure"):
            mutate()
        assert path.read_bytes() == before
    assert rewrite_queue.read_rewrite_queue(work_dir)["entries"] == {}

    monkeypatch.setattr(rewrite_queue, "read_json", real_read)
    second_id = mutations[0]()
    assert rewrite_queue.find_entry(work_dir, request_id) == forwarded_entry
    assert rewrite_queue.find_entry(work_dir, second_id)["status"] == "pending"
    restored = ExchangeStore(store.state_path)
    assert len((await restored.unit_state(unit_id))["submission"]["forwarded"]) == 1
    assert await RewriteConsumer(restored).drain() == 0


@pytest.mark.parametrize("contents", ["{broken", "[]", '{}', '{"schema":"agentdecompile.rewrite-queue.v1","entries":{},"requestCounts":[]}'])
async def test_queue_mutation_does_not_replace_malformed_existing_file(tmp_path, contents):
    path = rewrite_queue.queue_path(tmp_path)
    path.parent.mkdir()
    path.write_text(contents)
    with pytest.raises(ValueError):
        rewrite_queue.write_rewrite_request(tmp_path, **REQUEST)
    assert path.read_text() == contents


async def test_exchange_ack_failure_replays_queue_receipt_after_restart(tmp_path, monkeypatch):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)

    async def fail_persist(*args):
        raise OSError("injected acknowledgement failure")

    monkeypatch.setattr(store, "_persist", fail_persist)
    assert await RewriteConsumer(store).drain() == 0
    before = rewrite_queue.find_entry(work_dir, request_id)
    restored = ExchangeStore(store.state_path)
    assert "forwarded" not in (await restored.unit_state(unit_id))["submission"]
    assert await RewriteConsumer(restored).drain() == 1
    assert rewrite_queue.find_entry(work_dir, request_id) == before


async def test_competing_claim_and_changed_request_are_preserved(tmp_path, monkeypatch):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)
    original_import = rewrite_queue.import_exchange_result

    def concurrent_claim(*args, **kwargs):
        assert rewrite_queue.claim_pending_entry(work_dir, request_id, claimant="local")
        return original_import(*args, **kwargs)

    monkeypatch.setattr(rewrite_queue, "import_exchange_result", concurrent_claim)
    assert await RewriteConsumer(store).drain() == 0
    assert rewrite_queue.find_entry(work_dir, request_id)["claimedBy"] == "local"
    assert "forwarded" not in (await store.unit_state(unit_id))["submission"]
    monkeypatch.setattr(rewrite_queue, "import_exchange_result", original_import)
    assert rewrite_queue.release_claim(work_dir, request_id, claimant="local")
    queue = rewrite_queue.read_rewrite_queue(work_dir)
    queue["entries"][request_id]["compilerProfile"] = "changed"
    rewrite_queue.atomic_write_json(rewrite_queue.queue_path(work_dir), queue)
    assert await RewriteConsumer(store).drain() == 0
    assert rewrite_queue.find_entry(work_dir, request_id)["status"] == "pending"


async def test_malformed_routing_and_corrupt_queue_fail_closed(tmp_path, monkeypatch):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)
    accepted = store.state_path.parent / producers.SPOOL_DIRNAME / producers.ACCEPTED_DIRNAME
    path = next(accepted.glob("*.json"))
    record = json.loads(path.read_text())
    record["unitId"] = "rewrite:forged"
    path.write_text(json.dumps(record))
    assert await RewriteConsumer(store).drain() == 0
    assert rewrite_queue.find_entry(work_dir, request_id)["status"] == "pending"
    record["unitId"] = unit_id
    path.write_text(json.dumps(record))
    rewrite_queue.queue_path(work_dir).write_text("{broken")
    assert await RewriteConsumer(store).drain() == 0
    assert rewrite_queue.queue_path(work_dir).read_text() == "{broken"
    assert "forwarded" not in (await store.unit_state(unit_id))["submission"]


async def test_cursor_rotates_past_busy_destinations(tmp_path, monkeypatch):
    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)
    second = tmp_path / "second"
    second_request = rewrite_queue.write_rewrite_request(second, **REQUEST)
    producers.offer_rewrite_unit(work_dir=second, request_id=second_request, **REQUEST)
    await producers.drain_spool(store)
    assert rewrite_queue.claim_pending_entry(work_dir, request_id, claimant="local")
    consumer = RewriteConsumer(store)
    results = [await consumer.drain(limit=1) for _ in range(3)]
    assert sum(results) == 1
    assert rewrite_queue.find_entry(second, second_request)["status"] == "completed"
    assert rewrite_queue.find_entry(work_dir, request_id)["status"] == "claimed"


async def test_roster_maintenance_retries_forwarding(tmp_path, monkeypatch):
    import httpx

    from agentdecompile_recovery.exchange.routes import create_exchange_router
    from fastapi import FastAPI

    store, unit_id, work_dir, request_id = await prepare(tmp_path, monkeypatch)
    app = FastAPI()
    app.include_router(create_exchange_router(store))
    assert rewrite_queue.claim_pending_entry(work_dir, request_id, claimant="local")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/dashboard/api/exchange/roster")
        assert response.status_code == 200
        assert rewrite_queue.find_entry(work_dir, request_id)["status"] == "claimed"
        assert rewrite_queue.release_claim(work_dir, request_id, claimant="local")
        response = await client.get("/dashboard/api/exchange/roster")
        assert response.status_code == 200
        assert response.json()["units"]["byStatus"] == {STATUS_AWAITING_VERIFICATION: 1}
    assert rewrite_queue.find_entry(work_dir, request_id)["status"] == "completed"
