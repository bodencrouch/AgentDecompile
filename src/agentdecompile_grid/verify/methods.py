"""Verification methods: ``core.VERIFIERS`` entries callable as ``(spec, result, objects, scratch, verifier_key) -> Verification``.

Every entry is a machine check by an *independent* key (the loop enforces independence; the
method only computes).  Working:

* ``hash-lookup``  the result's outputs must equal a pinned expected object set when one exists
                   (named pointer ``expected/<task_id>`` → canonical JSON ``{"task_id", "outputs"}``);
                   no pin → UNVERIFIABLE by name (``no-pin``), never a pass.
* ``recompute``    re-run the kind under this node's key and compare output refs and status;
                   a kind that declares ``deterministic = False`` is UNVERIFIABLE by name
                   (``stochastic-kind``) — recomputation is a check only for pure functions of
                   pinned inputs (design §2.5).

Declared: ``parity`` (needs the ``parity:<checker hash>`` capability and the checker runner from
the parity lane; ``NotConfigured`` names both).

**``quorum`` is deliberately not provided and must never be.**  Two runs agreeing is either a
recomputation check of a deterministic function (that is ``recompute``) or a vote; votes are how
a Sybil with N keys buys truth, and the design forbids quorum, credit and reputation outright
(§2.5, §9.4 S1).  ``NOT_PROVIDED`` records the reason so a dispatch loop and a reviewer both
find it; the name is absent from the registry so nothing can select it.

Acceptance tests named for the final verification phase (U127):
  * ``test_hash_lookup_pin``: matching outputs verify; a differing ref refutes with evidence
    naming the output; no pin is UNVERIFIABLE.
  * ``test_recompute_deterministic``: a pure kind recomputed under another key verifies; a kind
    whose output differs refutes; ``deterministic = False`` is UNVERIFIABLE.
  * ``test_quorum_absent``: ``"quorum" not in VERIFIERS`` and ``NOT_PROVIDED["quorum"]`` names
    the reason.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Mapping, Protocol

from ..core import TASK_KINDS, VERIFIERS, NotConfigured, ObjectStore, Refused, ResultStatus, TaskResult, TaskSpec, Verification, VerificationOutcome
from ..worker.records import expected_pointer

VerifierMethod = Callable[[TaskSpec, TaskResult, ObjectStore, str, str], Verification]

NOT_PROVIDED: Mapping[str, str] = {
    "quorum": "agreement between keys is not evidence: either the function is deterministic (use 'recompute') or it is a vote, and votes are Sybil-purchasable; design §2.5 and §9.4 S1 forbid quorum, credit and reputation",
}


class DescribedMethod(Protocol):
    name: str

    def __call__(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str, verifier_key: str) -> Verification: ...
    def describe(self) -> Mapping[str, Any]: ...


def _unverifiable(spec: TaskSpec, result: TaskResult, verifier_key: str, method: str, reason: str, **evidence: Any) -> Verification:
    return Verification(spec.task_id, _result_ref(result), VerificationOutcome.UNVERIFIABLE, verifier_key, method, {"reason": reason, **evidence})


def _result_ref(result: TaskResult):
    from ..core import ObjectRef
    from ..worker.records import task_result_to_bytes
    return ObjectRef.of_bytes(task_result_to_bytes(result))


class HashLookup:
    name = "hash-lookup"

    def __call__(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str, verifier_key: str) -> Verification:
        if result.status != ResultStatus.OK:
            return _unverifiable(spec, result, verifier_key, self.name, "not-a-claim", status=result.status.value)
        raw = objects.get_named(expected_pointer(spec.task_id))
        if raw is None:
            return _unverifiable(spec, result, verifier_key, self.name, "no-pin")
        try:
            pin = json.loads(raw.decode("utf-8"))
            expected = {str(k): str(v) for k, v in dict(pin["outputs"]).items()}
        except (ValueError, KeyError, TypeError, AttributeError):
            return _unverifiable(spec, result, verifier_key, self.name, "pin-unparseable")
        if str(pin.get("task_id", spec.task_id)) != spec.task_id:
            return _unverifiable(spec, result, verifier_key, self.name, "pin-for-other-task")
        got = {str(k): str(v) for k, v in result.outputs.items()}
        differing = sorted(k for k in set(expected) | set(got) if expected.get(k) != got.get(k))
        outcome = VerificationOutcome.VERIFIED if not differing else VerificationOutcome.REFUTED
        return Verification(spec.task_id, _result_ref(result), outcome, verifier_key, self.name, {"expected": expected, "got": got, "differing": differing})

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "needs": [], "pin": "named pointer expected/<task_id> -> {task_id, outputs}"}


class Recompute:
    name = "recompute"

    def __call__(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str, verifier_key: str) -> Verification:
        if result.status != ResultStatus.OK:
            return _unverifiable(spec, result, verifier_key, self.name, "not-a-claim", status=result.status.value)
        kind = TASK_KINDS.get(spec.kind)
        kind = kind() if isinstance(kind, type) else kind
        if getattr(kind, "deterministic", True) is False:
            return _unverifiable(spec, result, verifier_key, self.name, "stochastic-kind")
        started = time.monotonic()
        try:
            mine = kind.run(spec, objects, scratch)
        except Refused as exc:
            return Verification(spec.task_id, _result_ref(result), VerificationOutcome.REFUTED, verifier_key, self.name, {"reason": "recompute-refused", "refusal": exc.reason})
        elapsed = time.monotonic() - started
        theirs = {str(k): str(v) for k, v in result.outputs.items()}
        ours = {str(k): str(v) for k, v in mine.outputs.items()}
        differing = sorted(k for k in set(theirs) | set(ours) if theirs.get(k) != ours.get(k))
        same = mine.status == ResultStatus.OK and not differing
        outcome = VerificationOutcome.VERIFIED if same else VerificationOutcome.REFUTED
        return Verification(spec.task_id, _result_ref(result), outcome, verifier_key, self.name, {"recomputed_status": mine.status.value, "recomputed_outputs": ours, "differing": differing, "elapsed_s": round(elapsed, 3)})

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "needs": ["the kind registered in this process", "its capabilities proven on this node"], "rule": "same inputs + basis -> same output refs; stochastic kinds opt out with deterministic = False"}


class Parity:
    name = "parity"
    CONFIG_SCHEMA: Mapping[str, str] = {"checker_hash": "pinned parity checker hash (capability parity:<hash>)", "runner": "grid_lanes/parity check runner (U136)"}

    def __call__(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str, verifier_key: str) -> Verification:
        raise NotConfigured("verification method 'parity' is declared only; it needs the parity checker binary proven by the 'parity:<hash>' canary and the runner from grid_lanes/parity (U136)")

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "declared", "needs": list(self.CONFIG_SCHEMA.values()), "config_schema": dict(self.CONFIG_SCHEMA)}


VERIFIERS.register("hash-lookup", HashLookup())
VERIFIERS.register("recompute", Recompute())
VERIFIERS.register("parity", Parity())


def describe_methods() -> dict[str, Any]:
    out = {name: (m.describe() if hasattr(m, "describe") else {"name": name}) for name, m in VERIFIERS.items()}
    out.update({name: {"name": name, "status": "not-provided", "reason": reason} for name, reason in NOT_PROVIDED.items()})
    return out


__all__ = ["DescribedMethod", "HashLookup", "NOT_PROVIDED", "Parity", "Recompute", "VerifierMethod", "describe_methods"]
