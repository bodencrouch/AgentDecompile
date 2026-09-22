"""Checkpoints: a deterministic summary of a partition through ``seq``, so readers can skip the prefix.

A ``CheckpointSummary`` is the folded ``PartitionState`` (open task specs, done/poisoned ids with
their kinds, per-task highest-fence intent even when lapsed, unverified and refuted result refs,
non-ok result counts) plus ``through_seq`` and ``through_digest``.  It carries no timestamp and no
writer identity, so two nodes compacting the same prefix write the *same* object and
``summary_ref`` is identical (design §2.2: idempotent checkpoint-index).  The summary lives in the
object store; the CHECKPOINT record ``{through_seq, through_digest, summary_ref}`` points at it.

A reader starts from the latest checkpoint whose summary object exists, verifies that the first
tail record's ``prev`` equals ``through_digest`` (the tail chains onto the summary), folds the
tail, and derives the same frontier as a full replay (design U123).

``compact`` never deletes anything.  ``prune`` is the separate destructive verb: it takes a
``RetentionPolicy`` (a registry: ``keep-everything``, ``keep-since-latest-checkpoint``,
``keep-tail``), refuses by name to drop any record no checkpoint summarises, and then calls the
log adapter's ``prune`` (only ``LocalFileLog`` has one; others raise ``NotConfigured``).

Acceptance tests (named here, written in the verification phase):
  U123 a node bootstrapping from snapshot + tail derives the same frontier as one replaying the
  full chain; a prior-basis partition is archived under one checkpoint and its records are
  prunable; the resident set for 100 partitions stays under the stated bound;
  compaction-idempotent: two nodes compacting through the same seq produce one ``summary_ref``;
  compaction-tail-chains: a tail whose first ``prev`` != ``through_digest`` is refused by name;
  compaction-prune-guard: ``prune`` with no covering checkpoint raises ``PruneRefused``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from collections.abc import Iterator, Mapping, Sequence

from agentdecompile_grid.core import GridError, LogStore, NotConfigured, ObjectRef, ObjectStore, Record, RecordType, Registry, canonical_json
from agentdecompile_grid.log.frontier import FrontierPolicy, FrontierReport, PartitionState, derive, expand_partitions
from agentdecompile_grid.log.local import PruneRefused
from agentdecompile_grid.log.outbox import Appender
from agentdecompile_grid.log.records import ChainBroken, Draft

CHECKPOINT_SCHEMA = 1


class CheckpointMismatch(GridError):
    """A CHECKPOINT record and its summary object disagree, or the summary is not decodable."""


class NothingToCompact(GridError):
    """No records past the base state: a checkpoint would summarise nothing new."""


@dataclass(frozen=True)
class CheckpointSummary:
    partition: str
    through_seq: int
    through_digest: str
    state: Mapping[str, Any]          # PartitionState.to_dict()
    schema: int = CHECKPOINT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "partition": self.partition, "through_seq": self.through_seq,
                "through_digest": self.through_digest, "state": dict(self.state)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CheckpointSummary:
        schema = int(data.get("schema", -1))
        if schema != CHECKPOINT_SCHEMA:
            raise CheckpointMismatch(f"checkpoint summary schema {schema} is not {CHECKPOINT_SCHEMA}")
        return cls(partition=str(data["partition"]), through_seq=int(data["through_seq"]),
                   through_digest=str(data["through_digest"]), state=dict(data["state"]), schema=schema)

    @classmethod
    def from_state(cls, state: PartitionState) -> CheckpointSummary:
        return cls(partition=state.partition, through_seq=state.through_seq, through_digest=state.through_digest, state=state.to_dict())

    def to_state(self) -> PartitionState:
        state = PartitionState.from_dict(self.state)
        if state.partition != self.partition or state.through_seq != self.through_seq:
            raise CheckpointMismatch(f"summary state ({state.partition!r}, {state.through_seq}) disagrees with its envelope "
                                     f"({self.partition!r}, {self.through_seq})")
        return state

    @property
    def bytes(self) -> bytes:
        return canonical_json(self.to_dict())

    @property
    def ref(self) -> ObjectRef:
        return ObjectRef.of_bytes(self.bytes)

    def body(self) -> dict[str, Any]:
        return {"through_seq": self.through_seq, "through_digest": self.through_digest, "summary_ref": str(self.ref)}


@dataclass(frozen=True)
class CompactionResult:
    summary: CheckpointSummary
    summary_ref: ObjectRef
    record: Record


def compact(log: LogStore, objects: ObjectStore, appender: Appender, partition: str, *, base: CheckpointSummary | None = None,
            through_seq: int | None = None, allow_empty: bool = False) -> CompactionResult:
    """Fold ``base`` (or nothing) plus the tail up to ``through_seq`` (default: the tail), write the
    summary object, append the CHECKPOINT record.  Deletes nothing."""
    state = base.to_state() if base is not None else PartitionState(partition)
    folded = 0
    for record in log.read(partition, since_seq=state.through_seq):
        if through_seq is not None and record.seq > through_seq:
            break
        state.fold(record)
        folded += 1
    if folded == 0 and not allow_empty:
        raise NothingToCompact(f"{partition!r}: no records after seq {state.through_seq}")
    summary = CheckpointSummary.from_state(state)
    ref = objects.put(summary.bytes)
    if str(ref) != str(summary.ref):
        raise CheckpointMismatch(f"object store returned {ref} for a summary whose content address is {summary.ref}")
    record = appender.append_one(partition, Draft(RecordType.CHECKPOINT, summary.body()))
    return CompactionResult(summary=summary, summary_ref=summary.ref, record=record)


def checkpoint_records(log: LogStore, partition: str) -> list[Record]:
    return [r for r in log.read(partition) if r.type is RecordType.CHECKPOINT]


def load_summary(objects: ObjectStore, record: Record) -> CheckpointSummary | None:
    """The summary a CHECKPOINT record points at, or ``None`` when the object is absent."""
    ref = ObjectRef(str(record.body["summary_ref"]))
    if not objects.exists(ref):
        return None
    try:
        summary = CheckpointSummary.from_dict(json.loads(objects.get(ref).decode("utf-8")))
    except (ValueError, KeyError, TypeError) as exc:
        raise CheckpointMismatch(f"summary object {ref} does not decode: {exc}") from exc
    if summary.partition != record.partition or summary.through_seq != int(record.body["through_seq"]):
        raise CheckpointMismatch(f"summary {ref} is for ({summary.partition!r}, {summary.through_seq}), the record says "
                                 f"({record.partition!r}, {record.body['through_seq']})")
    if record.body.get("through_digest") and summary.through_digest != record.body["through_digest"]:
        raise CheckpointMismatch(f"summary {ref} through_digest differs from the CHECKPOINT record's")
    return summary


def latest_checkpoint(log: LogStore, objects: ObjectStore, partition: str) -> CheckpointSummary | None:
    """The newest CHECKPOINT whose summary object exists; ``None`` when there is none."""
    latest: CheckpointSummary | None = None
    for record in checkpoint_records(log, partition):
        summary = load_summary(objects, record)
        if summary is not None:
            latest = summary
    return latest


def tail_after(log: LogStore, summary: CheckpointSummary) -> Iterator[Record]:
    """Records after the summary, checking the first one chains onto ``through_digest``."""
    first = True
    for record in log.read(summary.partition, since_seq=summary.through_seq):
        if first:
            if record.prev != summary.through_digest:
                raise ChainBroken(summary.partition, record.seq, "prev (checkpoint through_digest)", summary.through_digest, record.prev)
            first = False
        yield record


def read_from_checkpoint(log: LogStore, objects: ObjectStore, partition: str) -> tuple[PartitionState, Iterator[Record]]:
    """``(state to start from, tail records)``; a fresh state and the full log when no checkpoint exists."""
    summary = latest_checkpoint(log, objects, partition)
    if summary is None:
        return PartitionState(partition), log.read(partition)
    return summary.to_state(), tail_after(log, summary)


def states_from_checkpoints(log: LogStore, objects: ObjectStore, partitions: Sequence[str] | None = None) -> dict[str, PartitionState]:
    """Base states for ``frontier.derive(..., checkpoints=...)`` from the latest checkpoints."""
    bases: dict[str, PartitionState] = {}
    for partition in expand_partitions(log, partitions):
        summary = latest_checkpoint(log, objects, partition)
        if summary is not None:
            bases[partition] = summary.to_state()
    return bases


def derive_from_latest(log: LogStore, objects: ObjectStore, now: float, *, partitions: Sequence[str] | None = None,
                       policy: FrontierPolicy | None = None, kinds: Sequence[str] | None = None,
                       proposal_cap: int | None = None) -> FrontierReport:
    """``frontier.derive`` starting every partition from its latest checkpoint (U123's reader path)."""
    return derive(log, objects, now, proposal_cap=proposal_cap, kinds=kinds, partitions=partitions,
                  checkpoints=states_from_checkpoints(log, objects, partitions), policy=policy)


def lag(log: LogStore, partition: str, summary: CheckpointSummary | None) -> int:
    """Records past the summary; the staleness measure (design §2.2 uses 60 s, here records)."""
    return log.last_seq(partition) - (summary.through_seq if summary else 0)


def should_compact(log: LogStore, partition: str, summary: CheckpointSummary | None, *, max_lag_records: int = 64) -> bool:
    return lag(log, partition, summary) >= max_lag_records


# --------------------------------------------------------------------------- retention (pruning is separate)
@runtime_checkable
class RetentionPolicy(Protocol):
    """Decides the first seq to keep; pruning below it is only allowed when a checkpoint covers it."""

    name: str

    def keep_from(self, partition: str, checkpoints: Sequence[CheckpointSummary], tail_seq: int) -> int: ...


RETENTION_POLICIES = Registry("retention policy")


class KeepEverything:
    name = "keep-everything"

    def keep_from(self, partition: str, checkpoints: Sequence[CheckpointSummary], tail_seq: int) -> int:
        return 1

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> KeepEverything:
        return cls()


class KeepSinceLatestCheckpoint:
    """Keep from ``through_seq + 1`` of the n-th newest checkpoint (n = ``keep_checkpoints``)."""

    name = "keep-since-latest-checkpoint"

    def __init__(self, keep_checkpoints: int = 1) -> None:
        self.keep_checkpoints = max(1, int(keep_checkpoints))

    def keep_from(self, partition: str, checkpoints: Sequence[CheckpointSummary], tail_seq: int) -> int:
        if len(checkpoints) < self.keep_checkpoints:
            return 1
        return checkpoints[-self.keep_checkpoints].through_seq + 1

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> KeepSinceLatestCheckpoint:
        return cls(int(config.get("keep_checkpoints", 1)))


class KeepTail:
    """Keep the last ``records`` records, never more than a checkpoint allows."""

    name = "keep-tail"

    def __init__(self, records: int = 1000) -> None:
        self.records = max(0, int(records))

    def keep_from(self, partition: str, checkpoints: Sequence[CheckpointSummary], tail_seq: int) -> int:
        wanted = max(1, tail_seq - self.records + 1)
        covered = max((c.through_seq + 1 for c in checkpoints), default=1)
        return min(wanted, covered)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> KeepTail:
        return cls(int(config.get("records", 1000)))


for _cls in (KeepEverything, KeepSinceLatestCheckpoint, KeepTail):
    RETENTION_POLICIES.register(_cls.name, _cls, replace=True)


def retention_from_config(config: Mapping[str, Any]) -> RetentionPolicy:
    return RETENTION_POLICIES.get(str(config.get("policy", "keep-everything"))).from_config(config)


def prune(log: LogStore, objects: ObjectStore, partition: str, policy: RetentionPolicy) -> int:
    """Drop records below the policy's ``keep_from``; refuses by name unless a checkpoint covers them."""
    do_prune = getattr(log, "prune", None)
    if not callable(do_prune):
        raise NotConfigured(f"log adapter {getattr(log, 'name', type(log).__name__)!r} has no prune verb")
    summaries = [s for s in (load_summary(objects, r) for r in checkpoint_records(log, partition)) if s is not None]
    tail_seq = log.last_seq(partition)
    keep_from = int(policy.keep_from(partition, summaries, tail_seq))
    if keep_from <= 1:
        return 0
    if not any(s.through_seq >= keep_from - 1 for s in summaries):
        raise PruneRefused(f"{partition!r}: no checkpoint summarises records below seq {keep_from}; compact first")
    return int(do_prune(partition, keep_from))


__all__ = [
    "CHECKPOINT_SCHEMA", "CheckpointMismatch", "CheckpointSummary", "CompactionResult", "KeepEverything",
    "KeepSinceLatestCheckpoint", "KeepTail", "NothingToCompact", "RETENTION_POLICIES", "RetentionPolicy",
    "checkpoint_records", "compact", "derive_from_latest", "lag", "latest_checkpoint", "load_summary", "prune",
    "read_from_checkpoint", "retention_from_config", "should_compact", "states_from_checkpoints", "tail_after",
]
