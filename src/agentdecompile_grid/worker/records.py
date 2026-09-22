"""Record bodies the worker and verifier write — the contract with the frontier (``log.frontier.derive``).

The log layer chains and signs ``core.Record``; the *bodies* are ours.  Every body carries the
writer's key and lineage so independence and poison can be computed from the log alone, and a
``nonce`` so a body re-flushed after a crash is recognisably the same statement (all five are
idempotent by content: a duplicate INTENT, RESULT, POISON, VERIFIED or REFUTED changes nothing).

Bodies (all fields canonical-JSON scalars/lists/maps):

* ``INTENT``   ``{task_id, kind, key_id, lineage, action: hold|renew|release, ttl_s, issued_at, expires_at, nonce}``
               advisory; ``expires_at`` is wall-clock; ``release`` has ``ttl_s = 0``.
* ``RESULT``   ``{task_id, kind, status, result_ref, outputs, producer_key, producer_lineage, elapsed_s, deadline_s, reason, nonce}``
               ``result_ref`` addresses the canonical ``TaskResult.to_record()`` bytes; the same
               bytes sit behind the named pointer ``results/<task_id>/<producer_key>``.
* ``POISON``   ``{task_id, kind, timeouts: [key_id...], lineages, threshold, by, nonce}``
* ``VERIFIED`` / ``REFUTED``
               ``{task_id, result_ref, producer_key, verifier_key, verifier_lineage, method, outcome, evidence | evidence_ref, nonce}``
* ``NOTE``     ``{task_id, kind, key_id, note, detail, nonce}`` — never load-bearing (unverifiable,
               verify-timeout, launch-failed ...).

Readers here use only ``LogStore.read``; nothing enumerates the object store.  ``LogTaskIndex``
assumes a ``TASK`` body equals ``TaskSpec.to_record()`` (the publish side's contract; flagged
for the objects/tasks slice).

Acceptance tests named for the final verification phase: ``test_bodies_roundtrip`` (every body
survives canonical JSON and its reader returns the same fields), ``test_read_results_filters``
(``read_results`` returns proposals for one task in seq order and ignores other types),
``test_task_index_assumption`` (``LogTaskIndex`` reads a published TaskSpec back by id).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..core import LogStore, NodeIdentity, ObjectRef, Record, RecordType, ResultStatus, TaskResult, TaskSpec, Verification, VerificationOutcome

RESULTS_POINTER_PREFIX = "results/"     # results/<task_id>/<producer_key> -> result_ref (utf-8 bytes)
EXPECTED_POINTER_PREFIX = "expected/"   # expected/<task_id> -> canonical JSON {"task_id", "outputs": {name: ref}} (hash-lookup pin)


def results_pointer(task_id: str, producer_key: str) -> str:
    return f"{RESULTS_POINTER_PREFIX}{task_id}/{producer_key}"


def expected_pointer(task_id: str) -> str:
    return f"{EXPECTED_POINTER_PREFIX}{task_id}"


# --------------------------------------------------------------------------- builders
def intent_body(spec: TaskSpec, identity: NodeIdentity, *, action: str, ttl_s: float, now_wall: float, nonce: str) -> dict[str, Any]:
    if action not in ("hold", "renew", "release"):
        raise ValueError(f"intent action must be hold|renew|release, not {action!r}")
    ttl = 0.0 if action == "release" else float(ttl_s)
    return {
        "task_id": spec.task_id, "kind": spec.kind, "key_id": identity.key_id, "lineage": list(identity.invite_lineage),
        "action": action, "ttl_s": ttl, "issued_at": float(now_wall), "expires_at": float(now_wall) + ttl, "nonce": nonce,
    }


def result_body(spec: TaskSpec, result: TaskResult, result_ref: ObjectRef, identity: NodeIdentity, *, deadline_s: float, nonce: str) -> dict[str, Any]:
    return {
        "task_id": spec.task_id, "kind": spec.kind, "status": result.status.value, "result_ref": str(result_ref),
        "outputs": {k: str(v) for k, v in sorted(result.outputs.items())},
        "producer_key": identity.key_id, "producer_lineage": list(identity.invite_lineage),
        "elapsed_s": round(float(result.elapsed_s), 3), "deadline_s": float(deadline_s), "reason": result.reason, "nonce": nonce,
    }


def poison_body(spec: TaskSpec, identity: NodeIdentity, *, timeouts: Sequence[str], lineages: int, threshold: int, nonce: str) -> dict[str, Any]:
    return {"task_id": spec.task_id, "kind": spec.kind, "timeouts": sorted(set(timeouts)), "lineages": int(lineages), "threshold": int(threshold), "by": identity.key_id, "nonce": nonce}


def verification_body(verification: Verification, producer_key: str, identity: NodeIdentity, *, nonce: str, evidence_ref: ObjectRef | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "task_id": verification.task_id, "result_ref": str(verification.result_ref), "producer_key": producer_key,
        "verifier_key": identity.key_id, "verifier_lineage": list(identity.invite_lineage), "method": verification.method,
        "outcome": verification.outcome.value, "nonce": nonce,
    }
    if evidence_ref is not None:
        body["evidence_ref"] = str(evidence_ref)
    else:
        body["evidence"] = dict(verification.evidence)
    return body


def note_body(task_id: str, kind: str, identity: NodeIdentity, *, note: str, detail: Mapping[str, Any], nonce: str) -> dict[str, Any]:
    return {"task_id": task_id, "kind": kind, "key_id": identity.key_id, "note": note, "detail": dict(detail), "nonce": nonce}


# --------------------------------------------------------------------------- object payloads
def task_result_to_bytes(result: TaskResult) -> bytes:
    from ..core import canonical_json
    return canonical_json(result.to_record())


def task_result_from_record(rec: Mapping[str, Any]) -> TaskResult:
    return TaskResult(
        task_id=rec["task_id"], status=ResultStatus(rec["status"]),
        outputs={k: ObjectRef(v) for k, v in dict(rec.get("outputs", {})).items()},
        producer_key=rec["producer_key"], basis_hash=rec["basis_hash"], elapsed_s=float(rec.get("elapsed_s", 0.0)),
        reason=str(rec.get("reason", "")), candidates=tuple(rec.get("candidates", ())), metrics=dict(rec.get("metrics", {})),
    )


def verification_to_record(v: Verification) -> dict[str, Any]:
    return {"task_id": v.task_id, "result_ref": str(v.result_ref), "outcome": v.outcome.value, "verifier_key": v.verifier_key, "method": v.method, "evidence": dict(v.evidence)}


def verification_from_record(rec: Mapping[str, Any]) -> Verification:
    return Verification(task_id=rec["task_id"], result_ref=ObjectRef(rec["result_ref"]), outcome=VerificationOutcome(rec["outcome"]), verifier_key=rec["verifier_key"], method=rec["method"], evidence=dict(rec.get("evidence", {})))


# --------------------------------------------------------------------------- readers
@dataclass(frozen=True)
class Proposal:
    """One RESULT record as the verifier sees it."""

    seq: int
    task_id: str
    kind: str
    status: ResultStatus
    result_ref: ObjectRef
    producer_key: str
    producer_lineage: tuple[str, ...]
    outputs: Mapping[str, ObjectRef]
    elapsed_s: float
    reason: str
    signer_key: str

    @property
    def is_claim(self) -> bool:
        """Only an OK result claims a value; timeouts, errors and refusals are not verifiable."""
        return self.status == ResultStatus.OK


def proposal_from_record(rec: Record) -> Proposal | None:
    if rec.type != RecordType.RESULT:
        return None
    b = rec.body
    try:
        return Proposal(
            seq=rec.seq, task_id=str(b["task_id"]), kind=str(b.get("kind", "")), status=ResultStatus(b["status"]), result_ref=ObjectRef(b["result_ref"]),
            producer_key=str(b["producer_key"]), producer_lineage=tuple(b.get("producer_lineage", ())),
            outputs={k: ObjectRef(v) for k, v in dict(b.get("outputs", {})).items()}, elapsed_s=float(b.get("elapsed_s", 0.0)),
            reason=str(b.get("reason", "")), signer_key=rec.signer_key,
        )
    except (KeyError, ValueError):
        return None


def read_results(log: LogStore, partition: str, task_id: str | None = None, *, since_seq: int = 0) -> list[Proposal]:
    out: list[Proposal] = []
    for rec in log.read(partition, since_seq):
        p = proposal_from_record(rec)
        if p is not None and (task_id is None or p.task_id == task_id):
            out.append(p)
    return out


def read_timeouts(log: LogStore, partition: str, task_id: str) -> list[tuple[str, tuple[str, ...]]]:
    """(producer_key, producer_lineage) for every TIMEOUT result of one task."""
    return [(p.producer_key, p.producer_lineage) for p in read_results(log, partition, task_id) if p.status == ResultStatus.TIMEOUT]


def read_verdicts(log: LogStore, partition: str, task_id: str) -> list[Mapping[str, Any]]:
    """VERIFIED and REFUTED bodies for one task (each carries ``result_ref`` and ``verifier_key``)."""
    return [dict(rec.body) for rec in log.read(partition, 0) if rec.type in (RecordType.VERIFIED, RecordType.REFUTED) and rec.body.get("task_id") == task_id]


def has_poison(log: LogStore, partition: str, task_id: str) -> bool:
    return any(rec.type == RecordType.POISON and rec.body.get("task_id") == task_id for rec in log.read(partition, 0))


def live_intents(log: LogStore, partition: str, task_id: str, *, now_wall: float) -> list[Mapping[str, Any]]:
    """Latest INTENT per key for one task whose expiry is in the future (release wins by being last)."""
    latest: dict[str, Mapping[str, Any]] = {}
    for rec in log.read(partition, 0):
        if rec.type == RecordType.INTENT and rec.body.get("task_id") == task_id:
            latest[str(rec.body.get("key_id"))] = rec.body
    return [b for b in latest.values() if float(b.get("expires_at", 0.0)) > now_wall and b.get("action") != "release"]


class LogTaskIndex:
    """task_id -> TaskSpec from TASK records.  Assumes the TASK body is ``TaskSpec.to_record()``."""

    def __init__(self, log: LogStore, *, partitions: Iterable[str] | None = None) -> None:
        self.log = log
        self._partitions = tuple(partitions) if partitions is not None else None
        self._specs: dict[str, TaskSpec] = {}
        self._seen: dict[str, int] = {}

    def refresh(self) -> int:
        added = 0
        partitions = self._partitions if self._partitions is not None else tuple(self.log.partitions())
        for partition in partitions:
            since = self._seen.get(partition, 0)
            last = since
            for rec in self.log.read(partition, since):
                last = max(last, rec.seq)
                if rec.type == RecordType.TASK:
                    try:
                        spec = TaskSpec.from_record(rec.body)
                    except (KeyError, ValueError):
                        continue
                    if spec.task_id not in self._specs:
                        self._specs[spec.task_id] = spec
                        added += 1
            self._seen[partition] = last
        return added

    def task(self, task_id: str) -> TaskSpec | None:
        if task_id not in self._specs:
            self.refresh()
        return self._specs.get(task_id)

    __call__ = task


__all__ = [
    "EXPECTED_POINTER_PREFIX", "LogTaskIndex", "Proposal", "RESULTS_POINTER_PREFIX", "expected_pointer", "has_poison", "intent_body",
    "live_intents", "note_body", "poison_body", "proposal_from_record", "read_results", "read_timeouts", "read_verdicts", "result_body",
    "results_pointer", "task_result_from_record", "task_result_to_bytes", "verification_body", "verification_from_record", "verification_to_record",
]
