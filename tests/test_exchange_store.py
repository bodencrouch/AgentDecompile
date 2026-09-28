"""Unit tests for the donated-compute work exchange store.

The load-bearing cases are the ones that only bite once the queue is shared:
capability filtering, single ownership of a unit, fencing a vanished worker
out, idempotent redelivery, and never destroying live state on a corrupt read.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agentdecompile_recovery.exchange import store as exchange
from agentdecompile_recovery.exchange.store import (
    STATUS_AWAITING_VERIFICATION,
    STATUS_PENDING,
    CapacityExceeded,
    ExchangeStore,
    IdempotencyConflict,
    LeaseRejected,
    RateLimited,
    derive_unit_id,
)

pytestmark = pytest.mark.unit


class FakeClock:
    """Injectable clock: lease expiry must be testable without sleeping."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_store(tmp_path: Path, clock: FakeClock | None = None, **kwargs) -> ExchangeStore:
    return ExchangeStore(tmp_path / "state" / "work-exchange.json", clock=clock or FakeClock(), **kwargs)


REWRITE_PAYLOAD = {
    "functionName": "FUN_00401000",
    "candidateSource": "int f(void) { return 1; }",
    "mismatchClass": "REPLACEMENT",
    "compilerProfile": "msvc-vc7",
}


async def enroll(store: ExchangeStore, *capabilities: str, agent: str = "test") -> str:
    return (await store.enroll(capabilities=list(capabilities), agent=agent))["workerId"]


def test_unit_id_is_content_addressed() -> None:
    reordered = {key: REWRITE_PAYLOAD[key] for key in reversed(list(REWRITE_PAYLOAD))}
    assert derive_unit_id("rewrite", REWRITE_PAYLOAD) == derive_unit_id("rewrite", reordered)

    changed = {**REWRITE_PAYLOAD, "candidateSource": "int f(void) { return 2; }"}
    assert derive_unit_id("rewrite", changed) != derive_unit_id("rewrite", REWRITE_PAYLOAD)
    assert derive_unit_id("permute", REWRITE_PAYLOAD) != derive_unit_id("rewrite", REWRITE_PAYLOAD)

    lane, _, digest = derive_unit_id("rewrite", REWRITE_PAYLOAD).partition(":")
    assert lane == "rewrite"
    assert len(digest) == 16 and int(digest, 16) >= 0


@pytest.mark.asyncio
async def test_offer_is_idempotent_and_rejects_absolute_paths(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    second = await store.offer(lane="rewrite", payload=dict(REWRITE_PAYLOAD))
    assert first == second
    assert (await store.roster())["units"]["total"] == 1

    # R1: a unit is a value, so it may not point into the coordinator's tree.
    with pytest.raises(ValueError, match="absolute path"):
        await store.offer(lane="match", payload={"db": "/home/agent/work/live/atlas.db"})
    with pytest.raises(ValueError, match="absolute path"):
        await store.offer(lane="match", payload={"db": r"C:\work\live\atlas.db"})


@pytest.mark.asyncio
async def test_claim_never_offers_work_the_worker_cannot_run(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    compile_unit = await store.offer(lane="compile", payload={"source": "int f(void){return 0;}", "profile": "vc7"})
    rewrite_unit = await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)

    browser = await enroll(store, "llm", "node", agent="browser tab")
    for _ in range(3):
        lease = await store.claim(worker_id=browser)
        if lease is None:
            break
        assert lease["unit"]["unitId"] != compile_unit
        assert lease["unit"]["unitId"] == rewrite_unit

    # Even asking for the lane by name does not bypass the capability check.
    assert await store.claim(worker_id=browser, lanes=["compile"]) is None

    runner = await enroll(store, "msvc-vc7", "wine", agent="native runner")
    lease = await store.claim(worker_id=runner, lanes=["compile"])
    assert lease is not None
    assert lease["unit"]["unitId"] == compile_unit
    assert set(lease["unit"]["requiredCapabilities"]) == {"msvc-vc7", "wine"}


@pytest.mark.asyncio
async def test_two_workers_never_hold_the_same_unit(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first_unit = await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    second_unit = await store.offer(lane="rewrite", payload={**REWRITE_PAYLOAD, "candidateSource": "int f(void) { return 2; }"})
    one = await enroll(store, "llm")
    two = await enroll(store, "llm")

    leases = await asyncio.gather(store.claim(worker_id=one), store.claim(worker_id=two))
    claimed = {lease["unit"]["unitId"] for lease in leases}
    assert claimed == {first_unit, second_unit}
    assert len({lease["leaseToken"] for lease in leases}) == 2
    assert len({lease["fence"] for lease in leases}) == 2

    # Nothing pending left: a third worker gets no work rather than a duplicate.
    three = await enroll(store, "llm")
    assert await store.claim(worker_id=three) is None


@pytest.mark.asyncio
async def test_expired_lease_repends_unit_and_fences_the_original_worker_out(tmp_path: Path) -> None:
    clock = FakeClock()
    store = make_store(tmp_path, clock, lease_seconds=60)
    unit_id = await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    vanished = await enroll(store, "llm", agent="closed the tab")
    lease = await store.claim(worker_id=vanished)
    assert lease is not None and lease["unit"]["unitId"] == unit_id

    clock.advance(61)
    assert (await store.unit_state(unit_id))["status"] == STATUS_PENDING

    # The fencing case: the vanished worker comes back with a valid-looking
    # token and the fence it was granted, and is refused. No second claimant is
    # involved -- expiry alone must invalidate the lease.
    with pytest.raises(LeaseRejected):
        await store.submit(
            worker_id=vanished,
            lease_token=lease["leaseToken"],
            fence=lease["fence"],
            idempotency_key="vanished-1",
            artifact={"source": "int f(void){return 1;}"},
            verdict="candidate",
        )

    # And after a takeover, the old fence is still refused while the new one works.
    successor = await enroll(store, "llm", agent="successor")
    retaken = await store.claim(worker_id=successor)
    assert retaken is not None and retaken["unit"]["unitId"] == unit_id
    assert retaken["fence"] > lease["fence"]
    with pytest.raises(LeaseRejected):
        await store.submit(
            worker_id=vanished,
            lease_token=lease["leaseToken"],
            fence=lease["fence"],
            idempotency_key="vanished-2",
            artifact={"source": "int f(void){return 1;}"},
            verdict="candidate",
        )
    # The fence alone, with a currently valid token: a client that remembered
    # the number from its previous lease is refused, so a delayed result can
    # never be attributed to the lease that superseded it.
    with pytest.raises(LeaseRejected):
        await store.submit(
            worker_id=successor,
            lease_token=retaken["leaseToken"],
            fence=lease["fence"],
            idempotency_key="successor-stale-fence",
            artifact={"source": "int f(void){return 1;}"},
            verdict="candidate",
        )

    accepted = await store.submit(
        worker_id=successor,
        lease_token=retaken["leaseToken"],
        fence=retaken["fence"],
        idempotency_key="successor-1",
        artifact={"source": "int f(void){return 1;}"},
        verdict="candidate",
    )
    assert accepted == {"accepted": True, "state": STATUS_AWAITING_VERIFICATION, "unitId": unit_id, "verdict": "candidate"}

    # A proposal is never a commit: the unit awaits the coordinator's gate.
    state = await store.unit_state(unit_id)
    assert state["status"] == STATUS_AWAITING_VERIFICATION
    assert state["submission"]["workerId"] == successor
    assert "sole proof mechanism" in state["submission"]["claimBoundary"]


@pytest.mark.asyncio
async def test_heartbeat_holds_a_lease_that_would_otherwise_expire(tmp_path: Path) -> None:
    clock = FakeClock()
    store = make_store(tmp_path, clock, lease_seconds=60)
    unit_id = await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    worker = await enroll(store, "llm")
    lease = await store.claim(worker_id=worker)

    clock.advance(50)
    beat = await store.heartbeat(worker_id=worker, lease_token=lease["leaseToken"])
    assert beat["leaseExpiresAt"] == clock.value + 60
    assert beat["fence"] == lease["fence"]

    clock.advance(50)
    assert (await store.unit_state(unit_id))["status"] == "claimed"

    clock.advance(61)
    with pytest.raises(LeaseRejected):
        await store.heartbeat(worker_id=worker, lease_token=lease["leaseToken"])


@pytest.mark.asyncio
async def test_submit_is_idempotent_by_key_and_fingerprint(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    worker = await enroll(store, "llm")
    lease = await store.claim(worker_id=worker)
    artifact = {"source": "int f(void) { return 1; }"}

    first = await store.submit(
        worker_id=worker,
        lease_token=lease["leaseToken"],
        fence=lease["fence"],
        idempotency_key="batch-7",
        artifact=artifact,
        verdict="candidate",
    )
    # Redelivery is expected under lease reissue and must be harmless, even
    # though the lease was retired by the first submit.
    replay = await store.submit(
        worker_id=worker,
        lease_token=lease["leaseToken"],
        fence=lease["fence"],
        idempotency_key="batch-7",
        artifact=dict(artifact),
        verdict="candidate",
    )
    assert first == replay

    with pytest.raises(IdempotencyConflict):
        await store.submit(
            worker_id=worker,
            lease_token=lease["leaseToken"],
            fence=lease["fence"],
            idempotency_key="batch-7",
            artifact={"source": "int f(void) { return 2; }"},
            verdict="candidate",
        )

    roster = await store.roster()
    assert roster["units"]["byStatus"] == {STATUS_AWAITING_VERIFICATION: 1}
    assert roster["throughput"]["submissions"] == 1
    assert roster["workers"][0]["submissions"] == 1


@pytest.mark.asyncio
async def test_corrupt_state_is_quarantined_and_never_overwritten_by_an_empty_queue(tmp_path: Path) -> None:
    path = tmp_path / "state" / "work-exchange.json"
    path.parent.mkdir(parents=True)
    live = json.dumps(
        {
            "schema": exchange.SCHEMA,
            "units": {"rewrite:deadbeefdeadbeef": {"lane": "rewrite", "payload": REWRITE_PAYLOAD, "status": "pending"}},
            "workers": {},
        }
    )
    path.write_text(live[: len(live) // 2], encoding="utf-8")  # truncated write

    store = ExchangeStore(path, clock=FakeClock())
    await store.offer(lane="rewrite", payload={"functionName": "other", "candidateSource": "int g(void){return 0;}"})

    quarantined = sorted(path.parent.glob("work-exchange.json.corrupt-*"))
    assert len(quarantined) == 1
    assert store.quarantined_path == quarantined[0]
    # The unreadable bytes survive intact somewhere; they were not replaced by
    # a fresh empty queue, which is rewrite_queue.py's data-loss bug.
    assert quarantined[0].read_text(encoding="utf-8") == live[: len(live) // 2]
    assert json.loads(path.read_text(encoding="utf-8"))["units"]


@pytest.mark.asyncio
async def test_readable_state_survives_a_restart_with_leases_fenced_out(tmp_path: Path) -> None:
    path = tmp_path / "state" / "work-exchange.json"
    first = ExchangeStore(path, clock=FakeClock())
    unit_id = await first.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    worker = await enroll(first, "llm")
    lease = await first.claim(worker_id=worker)

    second = ExchangeStore(path, clock=FakeClock())
    reloaded = await second.unit_state(unit_id)
    assert reloaded["status"] == STATUS_PENDING
    assert reloaded["fence"] > lease["fence"]
    assert reloaded["payload"] == REWRITE_PAYLOAD
    with pytest.raises(LeaseRejected):
        await second.submit(
            worker_id=worker,
            lease_token=lease["leaseToken"],
            fence=lease["fence"],
            idempotency_key="pre-restart",
            artifact={"source": "x"},
            verdict="candidate",
        )


@pytest.mark.asyncio
async def test_store_writes_only_its_own_state_file(tmp_path: Path) -> None:
    """No `verified/` directory, no SQLite, no corpus mutation -- ever."""

    path = tmp_path / "state" / "work-exchange.json"
    store = ExchangeStore(path, clock=FakeClock())
    await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    worker = await enroll(store, "llm")
    lease = await store.claim(worker_id=worker)
    await store.submit(
        worker_id=worker,
        lease_token=lease["leaseToken"],
        fence=lease["fence"],
        idempotency_key="only-file",
        artifact={"source": "int f(void){return 1;}", "verdict": "MATCH 100%"},
        verdict="match",
    )
    await store.roster()

    created = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")}
    assert created == {"state", "state/work-exchange.json", "state/work-exchange.json.lock"}

    source = Path(exchange.__file__).read_text(encoding="utf-8")
    assert "sqlite3" not in source
    assert "live_db" not in source.replace("`live_db()`", "")


@pytest.mark.asyncio
async def test_state_still_persists_without_fcntl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Windows path: no flock, so the cross-process lock degrades to a no-op."""

    monkeypatch.setattr(exchange, "fcntl", None)
    path = tmp_path / "state" / "work-exchange.json"
    store = ExchangeStore(path, clock=FakeClock())
    unit_id = await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    assert json.loads(path.read_text(encoding="utf-8"))["units"][unit_id]["status"] == STATUS_PENDING
    assert not path.with_suffix(".json.lock").exists()


@pytest.mark.asyncio
async def test_router_maps_refusals_to_status_codes(tmp_path: Path) -> None:
    """204 for no work, 409 for a reused key, 410 for a retired lease, 404 for a stranger."""

    import httpx
    from fastapi import FastAPI

    from agentdecompile_recovery.exchange.routes import create_exchange_router

    store = make_store(tmp_path)
    app = FastAPI()
    app.include_router(create_exchange_router(store))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://exchange") as client:
        enrolled = await client.post("/dashboard/api/exchange/enroll", json={"capabilities": ["llm"], "agent": "browser tab"})
        assert enrolled.status_code == 200
        worker_id = enrolled.json()["workerId"]

        assert (await client.post("/dashboard/api/exchange/claim", json={"workerId": worker_id})).status_code == 204
        assert (await client.post("/dashboard/api/exchange/claim", json={"workerId": "stranger"})).status_code == 404

        await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
        claimed = await client.post("/dashboard/api/exchange/claim", json={"workerId": worker_id})
        assert claimed.status_code == 200
        lease = claimed.json()

        beat = await client.post("/dashboard/api/exchange/heartbeat", json={"workerId": worker_id, "leaseToken": lease["leaseToken"]})
        assert beat.status_code == 200

        body = {
            "workerId": worker_id,
            "leaseToken": lease["leaseToken"],
            "fence": lease["fence"],
            "idempotencyKey": "route-1",
            "artifact": {"source": "int f(void) { return 1; }"},
            "verdict": "candidate",
        }
        accepted = await client.post("/dashboard/api/exchange/submit", json=body)
        assert accepted.status_code == 200
        assert accepted.json()["state"] == STATUS_AWAITING_VERIFICATION
        assert (await client.post("/dashboard/api/exchange/submit", json=body)).json() == accepted.json()

        conflict = await client.post("/dashboard/api/exchange/submit", json={**body, "artifact": {"source": "other"}})
        assert conflict.status_code == 409
        # The lease was retired by the accepted submit, so a fresh key is fenced out.
        assert (await client.post("/dashboard/api/exchange/submit", json={**body, "idempotencyKey": "route-2"})).status_code == 410

        roster = await client.get("/dashboard/api/exchange/roster")
        assert roster.status_code == 200
        assert roster.json()["units"]["byStatus"] == {STATUS_AWAITING_VERIFICATION: 1}


@pytest.mark.asyncio
async def test_rate_limit_and_caps_bound_a_broken_client(tmp_path: Path) -> None:
    store = make_store(tmp_path, rate_limit_calls=3, rate_limit_window=60.0, max_workers=2, max_units=1)
    worker = await enroll(store, "llm")
    for _ in range(3):
        assert await store.claim(worker_id=worker) is None
    with pytest.raises(RateLimited):
        await store.claim(worker_id=worker)

    await enroll(store, "llm")
    with pytest.raises(CapacityExceeded):
        await enroll(store, "llm")

    await store.offer(lane="rewrite", payload=REWRITE_PAYLOAD)
    with pytest.raises(CapacityExceeded):
        await store.offer(lane="permute", payload={"entry": "0x401000", "seeds": [1, 2, 3]})
