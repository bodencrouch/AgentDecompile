"""Only admitted claims and bounded observer polling trigger exchange drains."""

from __future__ import annotations

import asyncio

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from fastapi import FastAPI

from agentdecompile_recovery.exchange import routes
from agentdecompile_recovery.exchange.store import ExchangeStore

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
BASE = "/dashboard/api/exchange"


def client_for(store):
    app = FastAPI()
    app.include_router(routes.create_exchange_router(store))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_invalid_and_rate_limited_claims_never_drain(tmp_path, monkeypatch):
    store = ExchangeStore(tmp_path / "state.json", rate_limit_calls=1)
    worker = await store.enroll(capabilities=["llm"], agent="test")
    spool, consume = AsyncMock(), AsyncMock()
    monkeypatch.setattr(routes, "drain_spool", spool)
    monkeypatch.setattr(routes.RewriteConsumer, "drain", consume)
    async with client_for(store) as client:
        assert (await client.post(BASE + "/claim", json={"workerId": ""})).status_code == 422
        assert (await client.post(BASE + "/claim", json={"workerId": "unknown"})).status_code == 404
        spool.assert_not_awaited()
        consume.assert_not_awaited()
        assert (await client.post(BASE + "/claim", json={"workerId": worker["workerId"]})).status_code == 204
        spool.assert_awaited_once()
        consume.assert_awaited_once()
        store._next_maintenance_at = 0
        for _ in range(5):
            assert (await client.post(BASE + "/claim", json={"workerId": worker["workerId"]})).status_code == 429
        spool.assert_awaited_once()
        consume.assert_awaited_once()


@pytest.mark.parametrize("cancel_first", [False, True])
async def test_concurrent_roster_and_claim_share_one_drain_without_waiting(tmp_path, monkeypatch, cancel_first):
    store = ExchangeStore(tmp_path / "state.json")
    worker = await store.enroll(capabilities=["llm"], agent="test")
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def drain(current):
        assert current is store
        calls.append("spool")
        started.set()
        await release.wait()

    consume = AsyncMock()
    monkeypatch.setattr(routes, "drain_spool", drain)
    monkeypatch.setattr(routes.RewriteConsumer, "drain", consume)
    # Two independently mounted routers still share the store's drain bound.
    async with client_for(store) as client, client_for(store) as second:
        first = asyncio.create_task(client.get(BASE + "/roster"))
        try:
            await asyncio.wait_for(started.wait(), 1)
            if cancel_first:
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
            requests = [second.get(BASE + "/roster") for _ in range(20)]
            requests.append(second.post(BASE + "/claim", json={"workerId": worker["workerId"]}))
            responses = await asyncio.wait_for(asyncio.gather(*requests), 1)
            assert [response.status_code for response in responses] == [200] * 20 + [204]
            assert calls == ["spool"]
            consume.assert_not_awaited()
        finally:
            release.set()
            await store._maintenance_task
            if not cancel_first:
                assert (await first).status_code == 200
        consume.assert_awaited_once()
        for _ in range(5):
            assert (await second.get(BASE + "/roster")).status_code == 200
        assert calls == ["spool"]


async def test_maintenance_retries_after_cooldown_and_claim_sees_ingestion(tmp_path, monkeypatch):
    clock = [100.0]
    store = ExchangeStore(tmp_path / "state.json", lease_seconds=7, clock=lambda: 10.0)
    worker = await store.enroll(capabilities=["llm"], agent="test")
    monkeypatch.setattr(routes, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    attempts = []

    async def drain(current):
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise OSError("temporary spool failure")
        await current.offer(lane="rewrite", payload={"functionName": "f"})

    consume = AsyncMock()
    monkeypatch.setattr(routes, "drain_spool", drain)
    monkeypatch.setattr(routes.RewriteConsumer, "drain", consume)
    async with client_for(store) as client:
        with pytest.raises(OSError, match="temporary spool failure"):
            await client.get(BASE + "/roster")
        assert (await client.get(BASE + "/roster")).status_code == 200
        assert attempts == [0]
        clock[0] += routes.MAINTENANCE_INTERVAL_SECONDS
        response = await client.post(BASE + "/claim", json={"workerId": worker["workerId"]})
        assert response.status_code == 200
        lease = response.json()
        assert lease["unit"]["payload"] == {"functionName": "f"}
        assert lease["leaseSeconds"] == 7 and lease["leaseExpiresAt"] == 17
        renewal = await client.post(BASE + "/heartbeat", json={"workerId": worker["workerId"], "leaseToken": lease["leaseToken"]})
        assert renewal.status_code == 200
        assert renewal.json()["leaseSeconds"] == 7
        consume.assert_awaited_once()
