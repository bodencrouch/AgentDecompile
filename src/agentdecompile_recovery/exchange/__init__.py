"""Work exchange: capability-labeled recovery units leased to donated compute.

`store` holds the lifecycle; `routes` exposes it over the dashboard's FastAPI
app. The router is deliberately not mounted anywhere yet -- the observer path
has to stop starving the executor before strangers are invited to connect.
"""

from __future__ import annotations

from .store import (
    CLAIM_BOUNDARY,
    LANE_CAPABILITIES,
    LANES,
    SCHEMA,
    STATUS_AWAITING_VERIFICATION,
    STATUS_CLAIMED,
    STATUS_FAILED,
    STATUS_PENDING,
    CapacityExceeded,
    ExchangeError,
    ExchangeStore,
    IdempotencyConflict,
    LeaseRejected,
    RateLimited,
    UnknownWorker,
    WorkUnit,
    derive_unit_id,
)

__all__ = [
    "CLAIM_BOUNDARY",
    "LANES",
    "LANE_CAPABILITIES",
    "SCHEMA",
    "STATUS_AWAITING_VERIFICATION",
    "STATUS_CLAIMED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "CapacityExceeded",
    "ExchangeError",
    "ExchangeStore",
    "IdempotencyConflict",
    "LeaseRejected",
    "RateLimited",
    "UnknownWorker",
    "WorkUnit",
    "derive_unit_id",
]
