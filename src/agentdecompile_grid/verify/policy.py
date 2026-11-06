"""Verification policy: independence rules, per-key penalties and revocation, open-enrolment rate limits.

Nothing here decides truth.  Keys attribute, rate-limit and revoke (design §2.5); a refutation
lowers the producer key's *priority weight* only, and a revoked key's records are ignored by the
frontier (``log.frontier.RevocationFilter`` over ``log.keys.RevocationList``, re-exported here).
There is no quorum, credit or reputation anywhere in this module by design.

**The two-lineage invariant is asserted in one place**: ``check_independence`` (producer key and
verifier key are distinct and their self-rooted lineages are disjoint under the configured
policy).  The verifier loop calls it per proposal; the work loop calls it through
``independent_groups`` when it counts lineages for poison; ``assert_two_lineages`` (re-exported
from ``worker.identity``) is the fleet-level form over a verifier key set.

Independence policies (a registry; ``disjoint-lineage`` is the default and the core contract):

* ``disjoint-lineage``  ``{a} | lineage(a)`` and ``{b} | lineage(b)`` share no key.  Two keys minted
                        from one invite are not independent.
* ``ancestry``          design §2.5's weaker wording: neither key is in the other's ancestry.  Two
                        keys from one public invite *are* independent under it, which is why it is
                        only for closed fleets whose keys were all issued by hand.

Acceptance tests named for the final verification phase (U126/U127):
  * ``test_rate_limit_65th_record``: the 65th record of one key in a minute is refused with a
    named reason and ``retry_after_s``.
  * ``test_revoked_key_ignored``: a revocation by a fleet key is honoured; a revocation signed by
    a donor is refused by name.
  * ``test_penalty_weight_only``: a refuted key's weight halves and nothing else changes.
  * ``test_independence_policies``: both policies agree on parent/child and disagree on siblings
    from one invite, and the default is ``disjoint-lineage``.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Protocol

from ..core import NodeIdentity, ObjectStore, Refused, Registry, canonical_json
from ..log.keys import REVOCATIONS_POINTER, Revocation, RevocationList
from ..worker.identity import ROLE_MAY_VERIFY, assert_two_lineages, independent, lineage_set

DEFAULT_INDEPENDENCE_POLICY = "disjoint-lineage"
PENALTIES_POINTER = "policy/penalties"


# --------------------------------------------------------------------------- independence
class IndependencePolicy(Protocol):
    name: str

    def independent(self, a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str]) -> bool: ...
    def explain(self, a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str]) -> str: ...


INDEPENDENCE_POLICIES = Registry("independence policy")


class DisjointLineagePolicy:
    name = "disjoint-lineage"

    def independent(self, a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str]) -> bool:
        return independent(a_key, a_lineage, b_key, b_lineage)

    def explain(self, a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str]) -> str:
        if a_key == b_key:
            return "same-key"
        shared = lineage_set(a_key, a_lineage) & lineage_set(b_key, b_lineage)
        return "independent" if not shared else f"shared-lineage:{','.join(sorted(shared))}"

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "default": True, "rule": "{key}|lineage sets are disjoint"}


class AncestryPolicy:
    name = "ancestry"

    def independent(self, a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str]) -> bool:
        return a_key != b_key and a_key not in set(b_lineage) and b_key not in set(a_lineage)

    def explain(self, a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str]) -> str:
        if a_key == b_key:
            return "same-key"
        if a_key in set(b_lineage):
            return "a-invited-b"
        if b_key in set(a_lineage):
            return "b-invited-a"
        return "independent"

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "default": False, "rule": "neither key in the other's ancestry (design §2.5 wording; siblings from one invite pass — closed fleets only)"}


INDEPENDENCE_POLICIES.register("disjoint-lineage", DisjointLineagePolicy())
INDEPENDENCE_POLICIES.register("ancestry", AncestryPolicy())


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str


def check_independence(a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str], *, policy: str = DEFAULT_INDEPENDENCE_POLICY) -> Verdict:
    """The one place the two-lineage invariant is asserted: ``a`` (producer) and ``b`` (verifier)
    must be different keys with lineages the policy calls independent."""
    p: IndependencePolicy = INDEPENDENCE_POLICIES.get(policy)
    a_l, b_l = tuple(a_lineage), tuple(b_lineage)
    if a_key == b_key:
        return Verdict(False, "same-key")
    return Verdict(p.independent(a_key, a_l, b_key, b_l), p.explain(a_key, a_l, b_key, b_l))


def check_identities(a: NodeIdentity, b: NodeIdentity, *, policy: str = DEFAULT_INDEPENDENCE_POLICY) -> Verdict:
    return check_independence(a.key_id, a.invite_lineage, b.key_id, b.invite_lineage, policy=policy)


def independent_groups(keys: Iterable[tuple[str, Iterable[str]]], *, policy: str = DEFAULT_INDEPENDENCE_POLICY) -> list[list[str]]:
    """Greedy partition into groups whose representatives are pairwise independent.  ``len()`` of
    the result is the number of independent lineages among the keys (used by poison detection)."""
    groups: list[tuple[str, tuple[str, ...], list[str]]] = []
    for key, lineage in keys:
        lineage = tuple(lineage)
        for rep_key, rep_lineage, members in groups:
            if not check_independence(key, lineage, rep_key, rep_lineage, policy=policy).ok:
                members.append(key)
                break
        else:
            groups.append((key, lineage, [key]))
    return [members for _, _, members in groups]


# --------------------------------------------------------------------------- penalties (priority weight only)
@dataclass
class PenaltyEntry:
    refuted: int = 0
    weight: float = 1.0
    last_at: float = 0.0
    reasons: list[str] = field(default_factory=list)


class PenaltyLedger:
    """A refutation halves the key's weight (floor 1/64).  Weight orders which proposal a verifier
    picks first; it never gates anything and never marks a task failed."""

    MIN_WEIGHT = 1.0 / 64

    def __init__(self, entries: Mapping[str, PenaltyEntry] | None = None) -> None:
        self._entries: dict[str, PenaltyEntry] = dict(entries or {})

    def penalize(self, key_id: str, *, reason: str, now: float) -> PenaltyEntry:
        e = self._entries.setdefault(key_id, PenaltyEntry())
        e.refuted += 1
        e.weight = max(self.MIN_WEIGHT, e.weight / 2.0)
        e.last_at = float(now)
        e.reasons = (e.reasons + [reason])[-8:]
        return e

    def weight(self, key_id: str) -> float:
        e = self._entries.get(key_id)
        return e.weight if e else 1.0

    def entry(self, key_id: str) -> PenaltyEntry | None:
        return self._entries.get(key_id)

    def to_record(self) -> dict[str, Any]:
        return {k: {"refuted": e.refuted, "weight": e.weight, "last_at": e.last_at, "reasons": list(e.reasons)} for k, e in sorted(self._entries.items())}

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> "PenaltyLedger":
        return cls({k: PenaltyEntry(int(v.get("refuted", 0)), float(v.get("weight", 1.0)), float(v.get("last_at", 0.0)), list(v.get("reasons", ()))) for k, v in rec.items()})

    def save(self, objects: ObjectStore, name: str = PENALTIES_POINTER) -> None:
        objects.put_named(name, canonical_json(self.to_record()))

    @classmethod
    def load(cls, objects: ObjectStore, name: str = PENALTIES_POINTER) -> "PenaltyLedger":
        raw = objects.get_named(name)
        return cls() if raw is None else cls.from_record(json.loads(raw.decode("utf-8")))


# --------------------------------------------------------------------------- revocation
# ``RevocationList`` is ``log.keys.RevocationList`` (append-only ``{key_id, reason, by, seq}``; any
# fleet or operator key may extend it; ``revoke(key_id, by=identity, reason=..., seq=...)`` keeps
# this module's spelling).  ``REVOCATIONS_POINTER`` names where it lives in the object store.


# --------------------------------------------------------------------------- rate limits
class TokenBucket:
    """Classic token bucket on an injected clock; ``take`` never blocks."""

    def __init__(self, rate_per_s: float, burst: float, *, clock: Callable[[], float]) -> None:
        if rate_per_s <= 0 or burst <= 0:
            raise ValueError("rate_per_s and burst must be positive")
        self.rate = float(rate_per_s)
        self.burst = float(burst)
        self.clock = clock
        self._tokens = float(burst)
        self._updated = clock()

    def _refill(self) -> None:
        now = self.clock()
        self._tokens = min(self.burst, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    def take(self, n: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False

    def retry_after_s(self, n: float = 1.0) -> float:
        self._refill()
        return 0.0 if self._tokens >= n else (n - self._tokens) / self.rate

    def available(self) -> float:
        self._refill()
        return self._tokens


@dataclass(frozen=True)
class RateLimits:
    """Design §6.2: per-key records/minute and bytes/hour; the 65th record in a minute is refused."""

    records_per_minute: int = 64
    bytes_per_hour: int = 512 * 1024 * 1024
    burst_records: int | None = None

    @property
    def record_burst(self) -> int:
        return self.burst_records or self.records_per_minute


@dataclass(frozen=True)
class Admission:
    ok: bool
    reason: str = ""
    retry_after_s: float = 0.0


class KeyRateLimiter:
    def __init__(self, limits: RateLimits, *, clock: Callable[[], float]) -> None:
        self.limits = limits
        self.clock = clock
        self._records: dict[str, TokenBucket] = {}
        self._bytes: dict[str, TokenBucket] = {}

    def _buckets(self, key_id: str) -> tuple[TokenBucket, TokenBucket]:
        if key_id not in self._records:
            self._records[key_id] = TokenBucket(self.limits.records_per_minute / 60.0, self.limits.record_burst, clock=self.clock)
            self._bytes[key_id] = TokenBucket(self.limits.bytes_per_hour / 3600.0, self.limits.bytes_per_hour, clock=self.clock)
        return self._records[key_id], self._bytes[key_id]

    def admit(self, key_id: str, *, records: int = 1, nbytes: int = 0) -> Admission:
        rec_bucket, byte_bucket = self._buckets(key_id)
        if records and rec_bucket.available() < records:
            return Admission(False, f"rate-limit:records-per-minute:{self.limits.records_per_minute}", rec_bucket.retry_after_s(records))
        if nbytes and byte_bucket.available() < nbytes:
            return Admission(False, f"rate-limit:bytes-per-hour:{self.limits.bytes_per_hour}", byte_bucket.retry_after_s(nbytes))
        if records:
            rec_bucket.take(records)
        if nbytes:
            byte_bucket.take(nbytes)
        return Admission(True)


# --------------------------------------------------------------------------- enrolment
@dataclass(frozen=True)
class EnrolmentPolicy:
    """Open enrolment with bounds: how many new keys an issuer's invite may mint per hour and how
    long an invite may live.  Evaluated by whoever accepts a join (the fabric side; a node applies
    it to itself when it mints invites)."""

    open: bool = True
    max_new_keys_per_hour: int = 60
    max_invite_lifetime_s: float = 30 * 24 * 3600
    allowed_roles: tuple[str, ...] = ("donor", "fleet")

    def admit_join(self, *, role: str, invite_lifetime_s: float, recent_joins_for_issuer: int) -> Admission:
        if not self.open:
            return Admission(False, "enrolment-closed")
        if role not in self.allowed_roles:
            return Admission(False, f"role-not-enrollable:{role}")
        if invite_lifetime_s > self.max_invite_lifetime_s:
            return Admission(False, "invite-lifetime-exceeds-policy")
        if recent_joins_for_issuer >= self.max_new_keys_per_hour:
            return Admission(False, f"rate-limit:joins-per-hour:{self.max_new_keys_per_hour}", 3600.0)
        return Admission(True)


# --------------------------------------------------------------------------- backoff
def full_jitter_backoff(attempt: int, *, base_s: float = 0.1, cap_s: float = 5.0, rng: random.Random | None = None) -> float:
    """Design §2.2: full-jitter exponential backoff (base 100 ms, cap 5 s)."""
    r = rng or random
    upper = min(cap_s, base_s * math.pow(2.0, max(0, attempt)))
    return r.uniform(0.0, upper)


__all__ = [
    "Admission", "AncestryPolicy", "DEFAULT_INDEPENDENCE_POLICY", "DisjointLineagePolicy", "EnrolmentPolicy", "INDEPENDENCE_POLICIES",
    "IndependencePolicy", "KeyRateLimiter", "PENALTIES_POINTER", "PenaltyEntry", "PenaltyLedger", "REVOCATIONS_POINTER", "RateLimits",
    "Revocation", "RevocationList", "TokenBucket", "Verdict", "assert_two_lineages", "check_identities", "check_independence",
    "full_jitter_backoff", "independent_groups",
]
