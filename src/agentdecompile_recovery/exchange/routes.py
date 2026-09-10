"""HTTP surface for the work exchange: enroll, claim, heartbeat, submit, roster.

Outbound-only by construction, so a contributor behind NAT works with no
inbound port. There is no authentication -- enrollment is open per the
project's stated posture -- and none is needed for correctness, because a
submission is a proposal that the coordinator's compile-verify gate refutes for
orders of magnitude less than it cost to fabricate. What the store does enforce
is a per-worker rate limit and hard caps, so one broken client cannot drain the
queue.

Mounted only by the proxy (`proxy_server.py`), and only behind the experimental
`--enable-exchange` flag; the dashboard's own `router.py` does not mount it. The
design doc's §6b observer-path fixes -- one shared SSE snapshot, a connection
cap, hidden-tab gating -- are still outstanding, so enabling this on a server
with many spectators will contend for the same executor they already saturate.
"""

from __future__ import annotations

import json

from typing import Annotated, Any

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator

from .consumers import RewriteConsumer
from .producers import drain_spool
from .store import ExchangeError, ExchangeStore, default_state_path

# Every full-snapshot write re-serializes every stored submission's artifact,
# so an unbounded artifact from one open-enrollment contributor makes every
# subsequent claim/heartbeat/submit call more expensive and grows the state
# file without bound. 64 KiB is generous for a candidate C source plus a short
# verdict and small enough that a flood of submissions cannot grow the
# snapshot unboundedly.
MAX_ARTIFACT_BYTES = 64 * 1024
# Capability labels are persisted in every worker snapshot. Existing labels
# (for example ``matcher-input-v1``) are short; leave room for versioned
# protocol names without admitting arbitrarily large strings from this open
# endpoint. Lanes are the fixed, short scheduler vocabulary.
MAX_CAPABILITY_LENGTH = 64
MAX_LANE_LENGTH = 16

CapabilityName = Annotated[str, Field(max_length=MAX_CAPABILITY_LENGTH)]
LaneName = Annotated[str, Field(max_length=MAX_LANE_LENGTH)]


class EnrollBody(BaseModel):
    capabilities: list[CapabilityName] = Field(default_factory=list, max_length=64)
    agent: str = Field(default="anonymous", max_length=200)


class ClaimBody(BaseModel):
    workerId: str = Field(min_length=1, max_length=128)
    lanes: list[LaneName] | None = Field(default=None, max_length=16)


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

    @field_validator("artifact")
    @classmethod
    def _bound_artifact_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject an artifact whose serialized form exceeds MAX_ARTIFACT_BYTES.

        Field's min/max bounds only constrain scalars; artifact is a nested
        structure, so its size can only be checked after serializing it.
        """

        size = len(json.dumps(value, default=str).encode("utf-8"))
        if size > MAX_ARTIFACT_BYTES:
            raise ValueError(
                f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes when serialized (got {size})"
            )
        return value


def _refusal(exc: ExchangeError) -> JSONResponse:
    """Map a store refusal to its status: 404 / 409 / 410 / 429 / 503."""

    return JSONResponse({"error": str(exc), "code": exc.code}, status_code=exc.status)


class ExchangeRoute(APIRoute):
    """Keep exchange validation errors in its small public error contract."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def exchange_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    {"error": "request validation failed", "code": "validation-error"},
                    status_code=422,
                )

        return exchange_handler


def create_exchange_router(store: ExchangeStore | None = None) -> APIRouter:
    """Build the exchange router. Creating it touches no disk; the store loads lazily."""

    router = APIRouter(route_class=ExchangeRoute)
    resolved = store
    consumer: RewriteConsumer | None = None

    def _store() -> ExchangeStore:
        nonlocal resolved
        if resolved is None:
            resolved = ExchangeStore(default_state_path())
        return resolved

    async def maintenance() -> None:
        nonlocal consumer
        if consumer is None:
            consumer = RewriteConsumer(_store())
        await drain_spool(_store())
        await consumer.drain()

    @router.post("/dashboard/api/exchange/enroll")
    async def enroll(body: EnrollBody):
        try:
            return await _store().enroll(capabilities=body.capabilities, agent=body.agent)
        except ExchangeError as exc:
            return _refusal(exc)

    @router.post("/dashboard/api/exchange/claim")
    async def claim(body: ClaimBody):
        # Pipeline stages are subprocesses and cannot touch the snapshot, so
        # they spool units instead. Ingesting on claim is what makes a
        # producer's work visible without a background sweeper.
        await maintenance()
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
        # Drain here too, so the roster reports queued work the pipeline has
        # produced even when no contributor has claimed anything yet.
        await maintenance()
        return await _store().roster()

    return router
