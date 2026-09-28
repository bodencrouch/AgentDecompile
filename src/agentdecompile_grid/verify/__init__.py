"""agentdecompile_grid.verify — independent-key verification: the loop, the methods, the policy.

Trust the hash, never votes.  Importing this package registers the ``hash-lookup``, ``recompute``
and ``parity`` methods in ``core.VERIFIERS`` and the independence policies in
``policy.INDEPENDENCE_POLICIES``.  ``quorum`` is documented as not provided in ``methods``.
``VerifierLoop``/``VerifierConfig`` resolve lazily (they build on ``worker.loop``, which imports
``policy`` from here).
"""
from __future__ import annotations

import importlib
from typing import Any

from . import methods as methods  # noqa: F401  (registers VERIFIERS entries)
from .methods import NOT_PROVIDED, describe_methods
from .policy import (
    DEFAULT_INDEPENDENCE_POLICY, INDEPENDENCE_POLICIES, Admission, EnrolmentPolicy, KeyRateLimiter, PenaltyLedger, RateLimits, RevocationList, TokenBucket, Verdict,
    check_identities, check_independence, full_jitter_backoff, independent_groups,
)

_LAZY: dict[str, str] = {"DEFAULT_PROPOSAL_CAP": "loop", "VerifierConfig": "loop", "VerifierLoop": "loop"}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{__name__}.{module}"), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


__all__ = [
    "Admission", "DEFAULT_INDEPENDENCE_POLICY", "EnrolmentPolicy", "INDEPENDENCE_POLICIES", "KeyRateLimiter", "NOT_PROVIDED", "PenaltyLedger", "RateLimits",
    "RevocationList", "TokenBucket", "Verdict", "check_identities", "check_independence", "describe_methods", "full_jitter_backoff", "independent_groups", *sorted(_LAZY),
]
