"""Record bodies the worker and verifier write — the contract with the frontier (``log.frontier.derive``).

The log layer chains and signs ``core.Record``; the *bodies* are ours.  Every body carries the
writer's key and lineage so independence and poison can be computed from the log alone, and a
``nonce`` so a body re-flushed after a crash is recognisably the same statement (all five are
idempotent by content: a duplicate INTENT, RESULT, POISON, VERIFIED or REFUTED changes nothing).

Bodies (all fields canonical-JSON scalars/lists/maps).  The authority for the required keys is
``log.records.BODY_VALIDATORS`` (every record is validated at append time); the shapes here are
those validators' shapes plus the attribution fields this side needs:

* ``INTENT``   ``{task_id, key_id, ttl_s (int), issued_seq, issued_at, kind, lineage, action: hold|renew|release, expires_at, scope, nonce}``
               advisory; ``expires_at`` is wall-clock; ``release`` has ``ttl_s = 0``.  ``issued_seq``
               is the fence and is filled at seal time (``log.outbox.draft_for``: every intent this
               side writes is a fresh issue whose fence is its own seq, so a renewal by the holder
               extends and a release with ``ttl_s == 0`` releases without knowing an earlier seq).
* ``RESULT``   ``{task_id, result_ref, producer_key, status, kind, outputs, producer_lineage, elapsed_s, deadline_s, reason, nonce}``
               ``result_ref`` addresses the canonical ``TaskResult.to_record()`` bytes; the same
               bytes sit behind the named pointer ``tasks.results.result_name(task_id, producer_key)``.
* ``POISON``   ``{task_id, reason, evidence: {timeouts: [key_id...], lineages, threshold, by}, kind, timeouts, lineages, threshold, by, nonce}``
* ``VERIFIED`` / ``REFUTED``
               ``{task_id, result_ref, outcome, verifier_key, method, producer_key, verifier_lineage, evidence | evidence_ref, nonce}``
               (the verdict *object* is ``tasks.results.verification_to_record`` — the one tagged spelling;
               ``verification_to_record`` here delegates to it)
* ``NOTE``     ``{task_id, kind, key_id, note, detail, nonce}`` — never load-bearing (unverifiable,
               verify-timeout, launch-failed ...).

Readers here use only ``LogStore.read``; nothing enumerates the object store.  ``LogTaskIndex``
assumes a ``TASK`` body equals ``TaskSpec.to_record()`` (the publish side's contract; flagged
for the objects/tasks slice).

**Who said it is the signer, and the signer must be trusted.**  Every reader here takes a
``keyring`` (``log.signing.Keyring``, built from ``GridConfig.keyring_locator()``) and passes each
record through ``signing.authorize_record`` before it trusts it: the signer is in the keyring,
the signature verifies, and a TASK is signed by an operator key.  A refused record is dropped and,
when the caller passes a ``refused`` list, named there as ``(partition, seq, reason)``;
``keyring=None`` means an empty keyring (``allow_null`` = ``trust_unsigned``), so an unwired reader
refuses rather than trusts.  A RESULT whose ``producer_key`` differs from the
record's authenticated ``signer_key`` is dropped by every reader here (a forged producer could
otherwise poison a task with invented keys or make two siblings look independent).  Unsigned
records are those whose signer is the null signer (``signer_key`` ``null`` or ``null:<label>``,
``log.signing.NullSigner``: hash chain only, no authorship) or empty; they are accepted only with
``trust_unsigned=True`` (``GridConfig.keyring.allow_null``), and even then the body's key must
equal the signer key.  Lineage is *not* attested by this module: ``producer_lineage`` is the
claimant's statement and readers take an optional ``lineage_lookup`` (key id → lineage from a
signed enrolment record) that overrides it — the cross-slice requirement is recorded in the
report, not solved here.

Acceptance tests named for the final verification phase: ``test_bodies_roundtrip`` (every body
survives canonical JSON and its reader returns the same fields), ``test_read_results_filters``
(``read_results`` returns proposals for one task in seq order and ignores other types),
``test_task_index_assumption`` (``LogTaskIndex`` reads a published TaskSpec back by id).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..core import LogStore, NodeIdentity, ObjectRef, Record, RecordType, ResultStatus, TaskResult, TaskSpec, Verification, VerificationOutcome
from ..log.signing import Keyring, refusal_reason

RefusedRecords = list[tuple[str, int, str]]
"""Where a reader names the records it would not trust: ``(partition, seq, reason)``."""


def _trusted(rec: Record, keyring: Keyring | None, trust_unsigned: bool, refused: RefusedRecords | None) -> bool:
    """``signing.authorize_record`` as a filter; ``keyring=None`` = an empty keyring (null only with ``trust_unsigned``)."""
    reason = refusal_reason(rec, keyring if keyring is not None else Keyring(allow_null=trust_unsigned))
    if reason is not None and refused is not None:
        refused.append((rec.partition, rec.seq, reason))
    return reason is None

RESULTS_POINTER_PREFIX = "results/"     # results/<task_id>/<producer_key> -> result_ref (utf-8 bytes)
EXPECTED_POINTER_PREFIX = "expected/"   # expected/<task_id> -> canonical JSON {"task_id", "outputs": {name: ref}} (hash-lookup pin)


def results_pointer(task_id: str, producer_key: str) -> str:
    """The per-producer result pointer; ``tasks.results.result_name`` owns the spelling."""
    from ..tasks.results import result_name

    return result_name(task_id, producer_key)


def is_unsigned(signer_key: str) -> bool:
    """A record nobody vouches for: no signer, or the null signer (``null`` / ``null:<label>``)."""
    return not signer_key or signer_key == "null" or signer_key.startswith("null:")


def expected_pointer(task_id: str) -> str:
    return f"{EXPECTED_POINTER_PREFIX}{task_id}"


# --------------------------------------------------------------------------- builders
def intent_body(spec: TaskSpec, identity: NodeIdentity, *, action: str, ttl_s: float, now_wall: float, nonce: str, issued_seq: int = 0) -> dict[str, Any]:
    """``issued_seq`` 0 = "fill the fence at seal time" (``log.outbox.draft_for``); a caller holding a
    ``log.intents.Lease`` passes the lease's fence instead."""
    if action not in ("hold", "renew", "release"):
        raise ValueError(f"intent action must be hold|renew|release, not {action!r}")
    ttl = 0 if action == "release" else int(math.ceil(float(ttl_s)))
    return {
        "task_id": spec.task_id, "kind": spec.kind, "key_id": identity.key_id, "lineage": list(identity.invite_lineage),
        "action": action, "ttl_s": ttl, "issued_seq": int(issued_seq), "issued_at": float(now_wall), "expires_at": float(now_wall) + ttl, "nonce": nonce,
    }


def result_body(spec: TaskSpec, result: TaskResult, result_ref: ObjectRef, identity: NodeIdentity, *, deadline_s: float, nonce: str) -> dict[str, Any]:
    return {
        "task_id": spec.task_id, "kind": spec.kind, "status": result.status.value, "result_ref": str(result_ref),
        "outputs": {k: str(v) for k, v in sorted(result.outputs.items())},
        "producer_key": identity.key_id, "producer_lineage": list(identity.invite_lineage),
        "elapsed_s": round(float(result.elapsed_s), 3), "deadline_s": float(deadline_s), "reason": result.reason, "nonce": nonce,
    }


def poison_body(spec: TaskSpec, identity: NodeIdentity, *, timeouts: Sequence[str], lineages: int, threshold: int, nonce: str, reason: str = "") -> dict[str, Any]:
    keys = sorted(set(timeouts))
    evidence = {"timeouts": keys, "lineages": int(lineages), "threshold": int(threshold), "by": identity.key_id}
    return {"task_id": spec.task_id, "reason": reason or f"timeouts:{len(keys)}:lineages:{int(lineages)}", "evidence": evidence,
            "kind": spec.kind, "timeouts": keys, "lineages": int(lineages), "threshold": int(threshold), "by": identity.key_id, "nonce": nonce}


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
    """One spelling: ``tasks.results.verification_to_record`` (tagged ``schema``/``record``/``refs``);
    the sandbox child and the verifier loop both emit and read this shape."""
    from ..tasks.results import verification_to_record as _tagged

    return _tagged(v)


def verification_from_record(rec: Mapping[str, Any]) -> Verification:
    from ..tasks.results import verification_from_record as _tagged

    return _tagged(rec)


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


LineageLookup = Callable[[str], Sequence[str] | None]


def proposal_from_record(rec: Record, *, trust_unsigned: bool = False, lineage_lookup: LineageLookup | None = None,
                         keyring: Keyring | None = None, refused: RefusedRecords | None = None) -> Proposal | None:
    """A RESULT record as a Proposal, or None when it is not one, its signer is not trusted by
    ``keyring`` (named in ``refused``), or its producer claim is not the authenticated signer
    (``signer_key``).  ``lineage_lookup`` replaces the claimed lineage."""
    if rec.type != RecordType.RESULT:
        return None
    if not _trusted(rec, keyring, trust_unsigned, refused):
        return None
    b = rec.body
    try:
        producer_key = str(b["producer_key"])
        if rec.signer_key and producer_key != rec.signer_key:
            return None                                       # forged or mis-attributed: never a proposal
        if is_unsigned(rec.signer_key) and not trust_unsigned:
            return None                                       # nobody vouches for it and this reader does not trust that
        lineage = tuple(b.get("producer_lineage", ()))
        if lineage_lookup is not None:
            attested = lineage_lookup(producer_key)
            lineage = tuple(attested) if attested is not None else lineage
        return Proposal(
            seq=rec.seq, task_id=str(b["task_id"]), kind=str(b.get("kind", "")), status=ResultStatus(b["status"]), result_ref=ObjectRef(b["result_ref"]),
            producer_key=producer_key, producer_lineage=lineage,
            outputs={k: ObjectRef(v) for k, v in dict(b.get("outputs", {})).items()}, elapsed_s=float(b.get("elapsed_s", 0.0)),
            reason=str(b.get("reason", "")), signer_key=rec.signer_key or producer_key,
        )
    except (KeyError, ValueError):
        return None


def read_results(log: LogStore, partition: str, task_id: str | None = None, *, since_seq: int = 0, trust_unsigned: bool = False, lineage_lookup: LineageLookup | None = None,
                 keyring: Keyring | None = None, refused: RefusedRecords | None = None) -> list[Proposal]:
    out: list[Proposal] = []
    for rec in log.read(partition, since_seq):
        p = proposal_from_record(rec, trust_unsigned=trust_unsigned, lineage_lookup=lineage_lookup, keyring=keyring, refused=refused)
        if p is not None and (task_id is None or p.task_id == task_id):
            out.append(p)
    return out


def read_timeouts(log: LogStore, partition: str, task_id: str, *, trust_unsigned: bool = False, lineage_lookup: LineageLookup | None = None,
                  keyring: Keyring | None = None) -> list[tuple[str, tuple[str, ...]]]:
    """(signer_key, lineage) for every TIMEOUT result of one task — the authenticated key, never the body's claim."""
    return [(p.signer_key, p.producer_lineage) for p in read_results(log, partition, task_id, trust_unsigned=trust_unsigned, lineage_lookup=lineage_lookup, keyring=keyring)
            if p.status == ResultStatus.TIMEOUT]


def read_verdicts(log: LogStore, partition: str, task_id: str | None, *, keyring: Keyring | None = None, trust_unsigned: bool = False,
                  refused: RefusedRecords | None = None) -> list[Mapping[str, Any]]:
    """Trusted VERIFIED/REFUTED bodies for one task, or every task when ``task_id`` is ``None``."""
    return [dict(rec.body) for rec in log.read(partition, 0)
            if rec.type in (RecordType.VERIFIED, RecordType.REFUTED)
            and (task_id is None or rec.body.get("task_id") == task_id)
            and _trusted(rec, keyring, trust_unsigned, refused)]


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
    """task_id -> TaskSpec from TASK records.  Assumes the TASK body is ``TaskSpec.to_record()``.

    Only TASK records ``keyring`` authorises (operator-signed) are indexed; the rest are named in
    ``refused`` as ``(partition, seq, reason)``.  ``keyring=None`` = empty keyring: nothing indexed."""

    def __init__(self, log: LogStore, *, partitions: Iterable[str] | None = None, keyring: Keyring | None = None,
                 trust_unsigned: bool = False) -> None:
        self.log = log
        self._partitions = tuple(partitions) if partitions is not None else None
        self._specs: dict[str, TaskSpec] = {}
        self._seen: dict[str, int] = {}
        self.keyring = keyring
        self.trust_unsigned = trust_unsigned
        self.refused: RefusedRecords = []

    def refresh(self) -> int:
        added = 0
        partitions = self._partitions if self._partitions is not None else tuple(self.log.partitions())
        for partition in partitions:
            since = self._seen.get(partition, 0)
            last = since
            for rec in self.log.read(partition, since):
                last = max(last, rec.seq)
                if rec.type == RecordType.TASK:
                    if not _trusted(rec, self.keyring, self.trust_unsigned, self.refused):
                        continue
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
    "EXPECTED_POINTER_PREFIX", "LineageLookup", "LogTaskIndex", "Proposal", "RESULTS_POINTER_PREFIX", "expected_pointer", "has_poison", "intent_body", "is_unsigned",
    "live_intents", "note_body", "poison_body", "proposal_from_record", "read_results", "read_timeouts", "read_verdicts", "result_body",
    "results_pointer", "task_result_from_record", "task_result_to_bytes", "verification_body", "verification_from_record", "verification_to_record",
]
