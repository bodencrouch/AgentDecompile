"""Work exchange: capability-labeled recovery units leased to donated compute.

`store` holds the lifecycle, `routes` exposes it over FastAPI, and `producers`
publishes units from the recovery pipeline. The proxy mounts the router behind
the experimental `--enable-exchange` flag. Note the observer path still has to
stop starving the executor before strangers are invited to connect at scale.
"""

from __future__ import annotations

from .producers import drain_spool, exchange_enabled, offer_rewrite_unit, spool_dir
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
    "drain_spool",
    "exchange_enabled",
    "offer_rewrite_unit",
    "spool_dir",
]
