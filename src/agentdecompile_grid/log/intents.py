"""Advisory leases as INTENT records: issue, renew, drop; a fence so stale renewals lose.

Why advisory: a result is a content-addressed proposal, so two nodes running one task produce the
same object (a cache hit) or two proposals (verified independently).  A lost, duplicated or stolen
lease therefore wastes compute and can never produce a wrong commit; the frontier merely hides a
task while a lease is live so that waste is rare.

The fence.  ``issue_intent`` appends ``{task_id, key_id, ttl_s, issued_seq, issued_at}`` with
``issued_seq`` = the record's own seq (a body factory fills it at seal time) and returns a ``Lease``
carrying that fence.  ``renew_intent`` and ``drop_intent`` append INTENT records with the same
``issued_seq``; the fold honours them only while that fence is still the highest for the task and
the key matches.  A newer holder has a higher fence by construction (its issuing record is later),
so a stale renewal cannot evict it: ``renew_intent`` reads the state first and raises ``IntentFenced``
by name instead of appending a record the fold would ignore anyway.

``ttl_s == 0`` is a release.  ``issued_at`` is the issuer's ``now`` (injected, never read here);
clock skew between nodes only shifts when a lease lapses, which is waste, not wrongness.

Acceptance tests (named here, written in the verification phase):
  intents-fence: key A issues, lapses; key B issues; A's renewal raises ``IntentFenced`` and the
  frontier still names B as holder;
  intents-renew: a renewal by the holder extends ``expires_at`` without changing the fence;
  intents-drop: after ``drop_intent`` the task is ready at the same ``now``;
  intents-body: the issuing record's ``issued_seq`` equals its ``seq``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Mapping

from agentdecompile_grid.core import GridError, LogStore, Record, RecordType
from agentdecompile_grid.log.frontier import IntentState, PartitionState, TaskState, states_of
from agentdecompile_grid.log.signing import Keyring
from agentdecompile_grid.log.outbox import Appender
from agentdecompile_grid.log.records import Draft


class IntentFenced(GridError):
    """A newer holder exists for the task; the renewal or drop carries an older fence."""

    def __init__(self, task_id: str, fence: int, holder: IntentState) -> None:
        super().__init__(f"intent on {task_id} with fence {fence} is fenced out by {holder.key_id!r} (fence {holder.issued_seq})")
        self.task_id, self.fence, self.holder = task_id, fence, holder


class IntentNotHeld(GridError):
    """The task has no lease with this fence at all (never issued here, or pruned)."""


@dataclass(frozen=True)
class Lease:
    """What a holder keeps: enough to renew or drop, and when it lapses."""

    partition: str
    task_id: str
    key_id: str
    issued_seq: int
    issued_at: float
    ttl_s: int
    seq: int

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl_s

    def live(self, now: float) -> bool:
        return self.ttl_s > 0 and now < self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {"partition": self.partition, "task_id": self.task_id, "key_id": self.key_id, "issued_seq": self.issued_seq,
                "issued_at": self.issued_at, "ttl_s": self.ttl_s, "seq": self.seq}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Lease:
        return cls(partition=str(data["partition"]), task_id=str(data["task_id"]), key_id=str(data["key_id"]),
                   issued_seq=int(data["issued_seq"]), issued_at=float(data["issued_at"]), ttl_s=int(data["ttl_s"]),
                   seq=int(data["seq"]))

    @classmethod
    def from_record(cls, record: Record) -> Lease:
        body = record.body
        return cls(partition=record.partition, task_id=str(body["task_id"]), key_id=str(body["key_id"]),
                   issued_seq=int(body["issued_seq"]), issued_at=float(body["issued_at"]), ttl_s=int(body["ttl_s"]), seq=record.seq)


def intent_body(task_id: str, key_id: str, ttl_s: int, issued_seq: int, issued_at: float) -> dict[str, Any]:
    return {"task_id": task_id, "key_id": key_id, "ttl_s": int(ttl_s), "issued_seq": int(issued_seq), "issued_at": float(issued_at)}


def issue_intent(appender: Appender, partition: str, task_id: str, ttl_s: int, now: float, *, key_id: str | None = None) -> Lease:
    """Append an issuing INTENT (fence = its own seq) and return the lease.

    ``key_id`` defaults to the appender's signer (the record invariant requires them equal).  The
    frontier already hid tasks with a live holder; issuing over one is allowed and merely evicts it
    (advisory semantics), so no read happens here.
    """
    holder = key_id or appender.signer.key_id
    draft = Draft(RecordType.INTENT, lambda seq: intent_body(task_id, holder, ttl_s, seq, now))
    record = appender.append_one(partition, draft)
    return Lease.from_record(record)


def _task_state(log: LogStore, partition: str, task_id: str, state: PartitionState | None, keyring: Keyring | None = None) -> TaskState | None:
    """The task's folded state; folding authorises every record against ``keyring`` (``None`` = empty keyring)."""
    folded = state if state is not None else states_of(log, [partition], keyring=keyring).get(partition)
    if folded is None:
        return None
    return folded.tasks.get(task_id)


def fence_check(task: TaskState | None, lease: Lease) -> IntentState:
    """The current highest-fence intent if it is this lease's; else ``IntentFenced``/``IntentNotHeld``."""
    current = task.intent if task is not None else None
    if current is None:
        raise IntentNotHeld(f"no intent on {lease.task_id} in {lease.partition!r}")
    if current.issued_seq > lease.issued_seq or current.key_id != lease.key_id:
        raise IntentFenced(lease.task_id, lease.issued_seq, current)
    if current.issued_seq < lease.issued_seq:
        raise IntentNotHeld(f"intent fence {lease.issued_seq} on {lease.task_id} is unknown to the log (holder fence {current.issued_seq})")
    return current


def renew_intent(appender: Appender, log: LogStore, lease: Lease, now: float, *, ttl_s: int | None = None,
                 state: PartitionState | None = None, keyring: Keyring | None = None) -> Lease:
    """Extend the lease from ``now`` with the same fence; refuses by name when fenced out.  Without
    ``state``, the log is folded through ``keyring`` (the holder's own key must be in it)."""
    fence_check(_task_state(log, lease.partition, lease.task_id, state, keyring), lease)
    ttl = lease.ttl_s if ttl_s is None else int(ttl_s)
    record = appender.append_one(lease.partition, Draft(RecordType.INTENT, intent_body(lease.task_id, lease.key_id, ttl, lease.issued_seq, now)))
    return Lease.from_record(record)


def drop_intent(appender: Appender, log: LogStore, lease: Lease, now: float, *, state: PartitionState | None = None,
                keyring: Keyring | None = None) -> Lease | None:
    """Release the lease (``ttl_s == 0``).  Returns ``None`` when it was already fenced out: nothing to drop."""
    try:
        fence_check(_task_state(log, lease.partition, lease.task_id, state, keyring), lease)
    except IntentFenced:
        return None
    record = appender.append_one(lease.partition, Draft(RecordType.INTENT, intent_body(lease.task_id, lease.key_id, 0, lease.issued_seq, now)))
    return Lease.from_record(record)


def holder_of(state: PartitionState, task_id: str, now: float) -> IntentState | None:
    """The live holder at ``now`` from a folded state, or ``None``."""
    task = state.tasks.get(task_id)
    return task.holder(now) if task is not None else None


__all__ = ["IntentFenced", "IntentNotHeld", "Lease", "drop_intent", "fence_check", "holder_of", "intent_body", "issue_intent", "renew_intent"]
