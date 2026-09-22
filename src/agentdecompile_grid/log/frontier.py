"""The work frontier as a pure function of (records, object existence, ``now``).

Two halves.  ``fold`` turns a partition's records into a ``PartitionState`` (per task: spec,
proposals, verifications, poison, highest-fence intent).  ``classify`` turns states plus
``objects.exists`` plus ``now`` into a ``FrontierReport`` (a ``core.Frontier`` with more detail).
``derive`` is the composition and the public entry.  No clock is read anywhere; every output list
is sorted by ``(kind, task_id)``; two nodes with the same records, the same objects and the same
``now`` produce equal reports (design U122 (e)).

Frontier rules (precedence top-down; ``done`` and ``poisoned`` are exclusive, the rest may overlap
only where the policy says so):
  done       : a VERIFIED record exists for the task.
  poisoned   : a POISON record exists (and no VERIFIED).
  awaiting_verification : >= 1 RESULT proposal with ``status == ok`` whose ``result_ref`` object
               exists, no VERIFIED/REFUTED for that ref.  Listed *before* ``ready`` in ``offer_order``
               so verification drains ahead of generation (design §2.6, H8).
  ready      : published (TASK seen), not done/poisoned, fewer than ``proposal_cap`` unverified
               proposals, not deterministically refused, no live INTENT at ``now``, inputs present.
               With ``offer_while_pending=False`` (§2.6 strict) any unverified proposal also blocks.
  refused/held/blocked/orphans/dangling : named reasons for what is *not* ready, so a worker can
               say why it is idle instead of spinning.

Intents.  The fence is ``issued_seq`` = the seq of the issuing INTENT record; renewals and releases
carry it.  The holder is the highest fence seen; an equal fence from the same key updates the lease
(renew or release with ``ttl_s == 0``); a lower fence is stale and ignored; an equal fence from
another key is a forgery and ignored.  A lease is live at ``now`` iff ``ttl_s > 0`` and
``issued_at + ttl_s > now``.

Acceptance tests (named here, written in the verification phase):
  U122 (e) the frontier over a partition is identical on two nodes given the same objects;
  U123 a node bootstrapping from checkpoint + tail derives the same frontier as a full replay;
  frontier-cap: the ``proposal_cap``-th ok proposal removes a task from ``ready``; a REFUTED frees
  the slot; a dangling ``result_ref`` never counts;
  frontier-order: ``offer_order`` lists every verify entry before any run entry and each half is
  sorted by ``(kind, task_id)``;
  frontier-intent: a live intent hides a task; ``now`` past ``issued_at + ttl_s`` shows it again; a
  stale renewal (lower fence) does not evict a newer holder; ``ttl_s == 0`` releases.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
from collections.abc import Iterable, Iterator, Mapping, Sequence

from agentdecompile_grid.core import Frontier, GridError, LogStore, ObjectRef, ObjectStore, Record, RecordType, ResultStatus, TaskSpec
from agentdecompile_grid.log.heads import partition_family

DEFAULT_PROPOSAL_CAP = 4


class FoldOrder(GridError):
    """Records were folded out of order or into the wrong partition state."""


class PrefixPruned(GridError):
    """The log's stored prefix starts after the reader's position: a checkpoint is required."""


# --------------------------------------------------------------------------- state
@dataclass(frozen=True)
class IntentState:
    task_id: str
    key_id: str
    issued_seq: int     # the fence
    issued_at: float
    ttl_s: int
    seq: int            # record seq of the latest issue/renewal/release

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl_s

    def live(self, now: float) -> bool:
        return self.ttl_s > 0 and now < self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "key_id": self.key_id, "issued_seq": self.issued_seq,
                "issued_at": self.issued_at, "ttl_s": self.ttl_s, "seq": self.seq}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> IntentState:
        return cls(task_id=str(data["task_id"]), key_id=str(data["key_id"]), issued_seq=int(data["issued_seq"]),
                   issued_at=float(data["issued_at"]), ttl_s=int(data["ttl_s"]), seq=int(data["seq"]))


@dataclass
class TaskState:
    """Everything the log says about one task id; mutable while folding, serialisable for checkpoints."""

    task_id: str
    kind: str = ""
    spec: dict[str, Any] | None = None          # TaskSpec.to_record() once published
    published_seq: int = 0
    proposals: dict[str, str] = field(default_factory=dict)   # result_ref -> producer_key, in log order
    verified: list[str] = field(default_factory=list)         # result refs with a VERIFIED record
    refuted: list[str] = field(default_factory=list)          # result refs with a REFUTED record
    counts: dict[str, int] = field(default_factory=dict)      # non-ok RESULT statuses -> count
    poison: str | None = None
    poison_evidence: dict[str, Any] | None = None
    intent: IntentState | None = None                         # highest fence seen

    # -- fold
    def fold(self, record: Record) -> None:
        body = record.body
        if record.type is RecordType.TASK:
            if self.spec is None:
                self.spec = dict(body)
                self.kind = str(body["kind"])
                self.published_seq = record.seq
        elif record.type is RecordType.INTENT:
            self._fold_intent(record)
        elif record.type is RecordType.RESULT:
            status = str(body["status"])
            ref = str(body["result_ref"])
            if status == ResultStatus.OK.value:
                if ref not in self.verified and ref not in self.refuted and ref not in self.proposals:
                    self.proposals[ref] = str(body["producer_key"])
            else:
                self.counts[status] = self.counts.get(status, 0) + 1
        elif record.type is RecordType.VERIFIED:
            ref = str(body["result_ref"])
            self.proposals.pop(ref, None)
            if ref not in self.verified:
                self.verified.append(ref)
        elif record.type is RecordType.REFUTED:
            ref = str(body["result_ref"])
            self.proposals.pop(ref, None)
            if ref not in self.refuted:
                self.refuted.append(ref)
        elif record.type is RecordType.POISON:
            if self.poison is None:
                self.poison = str(body["reason"])
                self.poison_evidence = dict(body.get("evidence", {}))

    def _fold_intent(self, record: Record) -> None:
        body = record.body
        fence = int(body["issued_seq"])
        if fence > record.seq:
            return  # a fence from the future; validate_record refuses it, a reader ignores it
        candidate = IntentState(task_id=self.task_id, key_id=str(body["key_id"]), issued_seq=fence,
                                issued_at=float(body["issued_at"]), ttl_s=int(body["ttl_s"]), seq=record.seq)
        current = self.intent
        if fence == record.seq:
            # an issue: a new lease generation; it always outranks older fences
            if current is None or fence > current.issued_seq:
                self.intent = candidate
            return
        # a renewal or release: only honoured on the holder's own fence, by the holder's own key
        if current is not None and current.issued_seq == fence and current.key_id == candidate.key_id:
            self.intent = candidate

    # -- queries
    @property
    def published(self) -> bool:
        return self.spec is not None

    @property
    def done(self) -> bool:
        return bool(self.verified)

    @property
    def poisoned(self) -> bool:
        return self.poison is not None

    @property
    def refused(self) -> bool:
        return self.counts.get(ResultStatus.REFUSED.value, 0) > 0

    def holder(self, now: float) -> IntentState | None:
        return self.intent if self.intent is not None and self.intent.live(now) else None

    # -- serialisation (deterministic: sorted where order is not semantic)
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "kind": self.kind, "spec": self.spec, "published_seq": self.published_seq,
            "proposals": [[ref, key] for ref, key in self.proposals.items()],
            "verified": sorted(self.verified), "refuted": sorted(self.refuted),
            "counts": {k: self.counts[k] for k in sorted(self.counts)},
            "poison": self.poison, "poison_evidence": self.poison_evidence,
            "intent": self.intent.to_dict() if self.intent else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TaskState:
        return cls(
            task_id=str(data["task_id"]), kind=str(data.get("kind", "")),
            spec=(dict(data["spec"]) if data.get("spec") is not None else None),
            published_seq=int(data.get("published_seq", 0)),
            proposals={str(ref): str(key) for ref, key in data.get("proposals", [])},
            verified=list(data.get("verified", [])), refuted=list(data.get("refuted", [])),
            counts={str(k): int(v) for k, v in data.get("counts", {}).items()},
            poison=data.get("poison"), poison_evidence=(dict(data["poison_evidence"]) if data.get("poison_evidence") else None),
            intent=(IntentState.from_dict(data["intent"]) if data.get("intent") else None),
        )


@dataclass
class PartitionState:
    """Fold state of one partition through ``through_seq``; the payload of a checkpoint summary."""

    partition: str
    through_seq: int = 0
    through_digest: str = ""
    tasks: dict[str, TaskState] = field(default_factory=dict)
    checkpoint_seqs: list[int] = field(default_factory=list)

    def task(self, task_id: str) -> TaskState:
        state = self.tasks.get(task_id)
        if state is None:
            state = self.tasks[task_id] = TaskState(task_id=task_id)
        return state

    def fold(self, record: Record) -> None:
        if record.partition != self.partition:
            raise FoldOrder(f"record of partition {record.partition!r} folded into state of {self.partition!r}")
        if record.seq <= self.through_seq:
            raise FoldOrder(f"record {record.partition!r}#{record.seq} folded after through_seq {self.through_seq}")
        if record.type is RecordType.CHECKPOINT:
            self.checkpoint_seqs.append(record.seq)
        elif record.type is not RecordType.NOTE:
            self.task(str(record.body["task_id"])).fold(record)
        self.through_seq = record.seq
        self.through_digest = record.digest()

    def fold_all(self, records: Iterable[Record]) -> PartitionState:
        for record in records:
            self.fold(record)
        return self

    def copy(self) -> PartitionState:
        return PartitionState.from_dict(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "partition": self.partition, "through_seq": self.through_seq, "through_digest": self.through_digest,
            "tasks": [self.tasks[tid].to_dict() for tid in sorted(self.tasks)],
            "checkpoint_seqs": list(self.checkpoint_seqs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PartitionState:
        tasks = [TaskState.from_dict(t) for t in data.get("tasks", [])]
        return cls(partition=str(data["partition"]), through_seq=int(data.get("through_seq", 0)),
                   through_digest=str(data.get("through_digest", "")), tasks={t.task_id: t for t in tasks},
                   checkpoint_seqs=[int(s) for s in data.get("checkpoint_seqs", [])])


def fold(records: Iterable[Record], state: PartitionState | None = None, *, partition: str | None = None) -> PartitionState:
    """Fold records into ``state`` (or a fresh state for ``partition`` / the first record's partition)."""
    iterator = iter(records)
    if state is None:
        if partition is None:
            first = next(iterator, None)
            if first is None:
                raise FoldOrder("fold of no records needs an explicit partition")
            state = PartitionState(first.partition)
            state.fold(first)
        else:
            state = PartitionState(partition)
    return state.fold_all(iterator)


# --------------------------------------------------------------------------- policy and report
@dataclass(frozen=True)
class FrontierPolicy:
    """Configuration is data.  ``offer_while_pending=False`` is the design §2.6 strict variant."""

    proposal_cap: int = DEFAULT_PROPOSAL_CAP
    offer_while_pending: bool = True
    reoffer_refused: bool = False
    require_inputs: bool = True
    require_result_object: bool = True

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> FrontierPolicy:
        return cls(
            proposal_cap=int(config.get("proposal_cap", DEFAULT_PROPOSAL_CAP)),
            offer_while_pending=bool(config.get("offer_while_pending", True)),
            reoffer_refused=bool(config.get("reoffer_refused", False)),
            require_inputs=bool(config.get("require_inputs", True)),
            require_result_object=bool(config.get("require_result_object", True)),
        )

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "proposal_cap": {"type": "integer", "default": DEFAULT_PROPOSAL_CAP, "minimum": 1},
            "offer_while_pending": {"type": "boolean", "default": True},
            "reoffer_refused": {"type": "boolean", "default": False},
            "require_inputs": {"type": "boolean", "default": True},
            "require_result_object": {"type": "boolean", "default": True}}}


DEFAULT_POLICY = FrontierPolicy()


@dataclass(frozen=True)
class FrontierReport(Frontier):
    """A ``core.Frontier`` plus the reasons for everything that is not ready.  All lists sorted."""

    refused: Sequence[str] = ()                                  # task_ids with a deterministic refusal
    held: Sequence[tuple[str, str, float]] = ()                  # (task_id, holder key_id, expires_at)
    blocked: Sequence[tuple[str, str]] = ()                      # (task_id, reason)
    capped: Sequence[str] = ()                                   # at the proposal cap
    orphans: Sequence[str] = ()                                  # results/intents for a task never published here
    dangling: Sequence[tuple[str, str]] = ()                     # (task_id, result_ref) proposals whose object is absent
    pending: Mapping[str, Sequence[str]] = field(default_factory=dict)   # task_id -> unverified result refs
    offer_order: Sequence[tuple[str, str]] = ()                  # ("verify"|"run", task_id): verify first
    through: Mapping[str, tuple[int, str]] = field(default_factory=dict)  # partition -> (seq, digest) folded
    kinds_of: Mapping[str, str] = field(default_factory=dict)    # task_id -> kind for every listed task

    def counts(self) -> dict[str, int]:
        return {"ready": len(self.ready), "awaiting_verification": len(self.awaiting_verification),
                "poisoned": len(self.poisoned), "done": len(self.done), "refused": len(self.refused),
                "held": len(self.held), "blocked": len(self.blocked), "capped": len(self.capped),
                "orphans": len(self.orphans), "dangling": len(self.dangling)}


def classify(states: Mapping[str, PartitionState], objects: ObjectStore, now: float, *,
             policy: FrontierPolicy = DEFAULT_POLICY, kinds: Iterable[str] | None = None) -> FrontierReport:
    """Pure classification of folded states.  See the module docstring for the rules."""
    wanted = set(kinds) if kinds is not None else None
    ready: list[tuple[tuple[str, str], TaskSpec]] = []
    awaiting: list[tuple[str, str]] = []
    poisoned: list[tuple[str, str]] = []
    done: list[tuple[str, str]] = []
    refused: list[tuple[str, str]] = []
    held: list[tuple[tuple[str, str], str, float]] = []
    blocked: list[tuple[tuple[str, str], str]] = []
    capped: list[tuple[str, str]] = []
    orphans: list[tuple[str, str]] = []
    dangling: list[tuple[tuple[str, str], str]] = []
    pending: dict[str, list[str]] = {}
    kinds_of: dict[str, str] = {}
    exists_cache: dict[str, bool] = {}

    def exists(ref: str) -> bool:
        if ref not in exists_cache:
            exists_cache[ref] = bool(objects.exists(ObjectRef(ref)))
        return exists_cache[ref]

    for partition in sorted(states):
        for task_id in sorted(states[partition].tasks):
            task = states[partition].tasks[task_id]
            if wanted is not None and task.kind not in wanted:
                continue
            key = (task.kind, task_id)
            kinds_of[task_id] = task.kind
            if task.done:
                done.append(key)
                continue
            if task.poisoned:
                poisoned.append(key)
                continue
            live_refs: list[str] = []
            for ref in task.proposals:
                if policy.require_result_object and not exists(ref):
                    dangling.append((key, ref))
                else:
                    live_refs.append(ref)
            if live_refs:
                awaiting.append(key)
                pending[task_id] = sorted(live_refs)
            if not task.published:
                orphans.append(key)
                continue
            if len(live_refs) >= policy.proposal_cap:
                capped.append(key)
                continue
            if live_refs and not policy.offer_while_pending:
                continue
            if task.refused and not policy.reoffer_refused:
                refused.append(key)
                continue
            holder = task.holder(now)
            if holder is not None:
                held.append((key, holder.key_id, holder.expires_at))
                continue
            spec = TaskSpec.from_record(task.spec or {})
            if policy.require_inputs:
                missing = sorted(name for name, ref in spec.inputs.items() if not exists(str(ref)))
                if missing:
                    blocked.append((key, "missing inputs: " + ",".join(missing)))
                    continue
            ready.append((key, spec))

    ready.sort(key=lambda item: item[0])
    for seq_ in (awaiting, poisoned, done, refused, capped, orphans):
        seq_.sort()
    held.sort(key=lambda item: item[0])
    blocked.sort(key=lambda item: item[0])
    dangling.sort()
    offer_order = [("verify", key[1]) for key in awaiting] + [("run", key[1]) for key, _spec in ready]
    return FrontierReport(
        ready=tuple(spec for _key, spec in ready),
        awaiting_verification=tuple(key[1] for key in awaiting),
        poisoned=tuple(key[1] for key in poisoned),
        done=tuple(key[1] for key in done),
        refused=tuple(key[1] for key in refused),
        held=tuple((key[1], holder_key, expires) for key, holder_key, expires in held),
        blocked=tuple((key[1], reason) for key, reason in blocked),
        capped=tuple(key[1] for key in capped),
        orphans=tuple(key[1] for key in orphans),
        dangling=tuple((key[1], ref) for key, ref in dangling),
        pending={tid: tuple(refs) for tid, refs in sorted(pending.items())},
        offer_order=tuple(offer_order),
        through={p: (states[p].through_seq, states[p].through_digest) for p in sorted(states)},
        kinds_of=kinds_of,
    )


# --------------------------------------------------------------------------- derive
def derive(
    log: LogStore,
    objects: ObjectStore,
    now: float,
    *,
    proposal_cap: int | None = None,
    kinds: Iterable[str] | None = None,
    partitions: Iterable[str] | None = None,
    checkpoints: Mapping[str, PartitionState] | None = None,
    policy: FrontierPolicy | None = None,
) -> FrontierReport:
    """The frontier over ``partitions`` (default: all) at ``now``.  Pure: no clock, sorted outputs.

    ``checkpoints`` maps a partition to a folded state to start from (see ``compaction``); the log
    is then read with ``since_seq = state.through_seq``.  ``proposal_cap`` overrides the policy's.
    A partition whose stored prefix was pruned past the start position raises ``PrefixPruned``.
    """
    effective = policy or DEFAULT_POLICY
    if proposal_cap is not None:
        effective = replace(effective, proposal_cap=int(proposal_cap))
    names = expand_partitions(log, partitions)
    states: dict[str, PartitionState] = {}
    start = getattr(log, "start", None)
    for partition in names:
        base = (checkpoints or {}).get(partition)
        state = base.copy() if base is not None else PartitionState(partition)
        if callable(start):
            stored_from = start(partition)[0]
            if stored_from > state.through_seq:
                raise PrefixPruned(f"{partition!r}: stored records start after seq {stored_from} but the reader is at "
                                   f"{state.through_seq}; start from a checkpoint (compaction.latest_checkpoint)")
        state.fold_all(log.read(partition, since_seq=state.through_seq))
        states[partition] = state
    return classify(states, objects, now, policy=effective, kinds=kinds)


def expand_partitions(log: LogStore, partitions: Iterable[str] | None) -> list[str]:
    """``None`` -> every partition; a base name -> itself plus its ``base/<prefix>`` sub-partitions."""
    known = sorted(log.partitions())
    if partitions is None:
        return known
    names: set[str] = set()
    for base in partitions:
        names.add(base)
        names.update(partition_family(known, base))
    return sorted(names)


def states_of(log: LogStore, partitions: Iterable[str] | None = None,
              checkpoints: Mapping[str, PartitionState] | None = None) -> dict[str, PartitionState]:
    """Fold without classifying; what ``compaction`` and ``intents`` use."""
    names = expand_partitions(log, partitions)
    states: dict[str, PartitionState] = {}
    for partition in names:
        base = (checkpoints or {}).get(partition)
        state = base.copy() if base is not None else PartitionState(partition)
        state.fold_all(log.read(partition, since_seq=state.through_seq))
        states[partition] = state
    return states


def iter_tasks(states: Mapping[str, PartitionState]) -> Iterator[tuple[str, TaskState]]:
    for partition in sorted(states):
        for task_id in sorted(states[partition].tasks):
            yield partition, states[partition].tasks[task_id]


__all__ = [
    "DEFAULT_POLICY", "DEFAULT_PROPOSAL_CAP", "FoldOrder", "FrontierPolicy", "FrontierReport", "IntentState", "PartitionState",
    "PrefixPruned", "TaskState", "classify", "derive", "expand_partitions", "fold", "iter_tasks", "states_of",
]
