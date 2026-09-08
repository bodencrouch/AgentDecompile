"""HTTP surface for the work exchange: enroll, claim, heartbeat, submit, roster.

Outbound-only by construction, so a contributor behind NAT works with no
inbound port. There is no authentication -- enrollment is open per the
project's stated posture -- and none is needed for correctness, because a
submission is a proposal that the coordinator's compile-verify gate refutes for
orders of magnitude less than it cost to fabricate. What the store does enforce
is a per-worker rate limit and hard caps, so one broken client cannot drain the
queue.

The router is not mounted by `router.py` yet. Mounting it is a separate
decision that depends on the observer-path fixes in the design doc's §6b.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .store import ExchangeError, ExchangeStore, default_state_path


class EnrollBody(BaseModel):
    capabilities: list[str] = Field(default_factory=list, max_length=64)
    agent: str = Field(default="anonymous", max_length=200)


class ClaimBody(BaseModel):
    workerId: str = Field(min_length=1, max_length=128)
    lanes: list[str] | None = Field(default=None, max_length=16)


class HeartbeatBody(BaseModel):
    workerId: str = Field(min_length=1, max_length=128)
    leaseToken: str = Field(min_length=1, max_length=128)


class SubmitBody(BaseModel):
    workerId: str = Field(min_length=1, max_length=128)
    leaseToken: str = Field(min_length=1, max_length=128)
    fence: int = Field(ge=0)
    # Bounds mirror react_api.submit_batch's submission key.
    idempotencyKey: str = Field(min_length=1, max_length=128)
    artifact: dict[str, Any] = Field(default_factory=dict)
    verdict: str = Field(min_length=1, max_length=64)


def _refusal(exc: ExchangeError) -> JSONResponse:
    """Map a store refusal to its status: 404 / 409 / 410 / 429 / 503."""

    return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.status)


def create_exchange_router(store: ExchangeStore | None = None) -> APIRouter:
    """Build the exchange router. Creating it touches no disk; the store loads lazily."""

    router = APIRouter()
    resolved = store

    def _store() -> ExchangeStore:
        nonlocal resolved
        if resolved is None:
            resolved = ExchangeStore(default_state_path())
        return resolved

    @router.post("/dashboard/api/exchange/enroll")
    async def enroll(body: EnrollBody):
        try:
            return await _store().enroll(capabilities=body.capabilities, agent=body.agent)
        except ExchangeError as exc:
            return _refusal(exc)

    @router.post("/dashboard/api/exchange/claim")
    async def claim(body: ClaimBody):
        try:
            lease = await _store().claim(worker_id=body.workerId, lanes=body.lanes)
        except ExchangeError as exc:
            return _refusal(exc)
        # No work this worker can run. 204 carries no body by definition.
        return lease if lease is not None else Response(status_code=204)

    @router.post("/dashboard/api/exchange/heartbeat")
    async def heartbeat(body: HeartbeatBody):
        try:
            return await _store().heartbeat(worker_id=body.workerId, lease_token=body.leaseToken)
        except ExchangeError as exc:
            return _refusal(exc)

    @router.post("/dashboard/api/exchange/submit")
    async def submit(body: SubmitBody):
        try:
            return await _store().submit(
                worker_id=body.workerId,
                lease_token=body.leaseToken,
                fence=body.fence,
                idempotency_key=body.idempotencyKey,
                artifact=body.artifact,
                verdict=body.verdict,
            )
        except ExchangeError as exc:
            return _refusal(exc)

    @router.get("/dashboard/api/exchange/roster")
    async def roster():
        return await _store().roster()

    return router
