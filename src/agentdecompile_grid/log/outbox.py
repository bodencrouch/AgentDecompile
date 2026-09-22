"""``Appender`` and ``Outbox``: seal drafts against the head and land them with backoff and rotation.

The appender runs the one protocol every writer follows, parameterised by the log adapter's
``ordering_authority``:

  authority = "log"   (``LocalFileLog``): read the tail, seal, ``log.append`` (tail-checked, atomic);
                      a ``ChainConflict`` means another writer landed first -> re-read, re-seal, retry;
                      then ``publish_head`` moves the head store forward (monotonic; a stale head
                      store is repaired here, which is design U122 (b)/(c) in one line).
  authority = "heads" (``S3ObjectLog`` and friends): read ``heads.get``, seal, write the records
                      (orphan-safe, by digest), ``heads.cas`` decides; a lost CAS leaves orphans that
                      the object GC removes, and the batch is re-sealed and retried; on success the
                      adapter's optional ``publish(records)`` writes the seq index.

Retries follow ``backoff.full_jitter`` (seeded, injectable ``sleep``).  ``try_append`` gives up
after ``rotate_after`` consecutive failures with ``HotHead`` so the outbox can rotate to another
partition and come back; ``append`` keeps going until ``max_attempts`` (``AppendGaveUp``).

``Outbox`` accumulates drafts per partition and flushes one batch (at most ``max_batch``) per
partition per pass, visiting partitions in ``PartitionRotation`` order and deferring hot ones to
the end of the pass.  Drafts that did not land stay pending for the next flush; nothing is lost.

The node-side durable queue (``worker.outbox.Outbox``: objects -> named pointers -> records,
restart-safe) flushes its records *through* this appender: ``Appender.write_batch(partition,
entries)`` is the ``worker.outbox.RecordWriter`` protocol (duck-typed on ``.type``/``.body``/
``.basis_hash`` so this package never imports the worker).  ``draft_for`` turns one such pending
record into a ``Draft``; an INTENT body without a fence becomes a fresh issue whose
``issued_seq`` is its own seq at seal time (advisory semantics: a re-issue by the holder renews,
``ttl_s == 0`` releases), which is what a queue that cannot know the seq of an earlier record
needs.  ``transport.local.ChainAppender`` is the documented fallback writer, not the default.

Acceptance tests (named here, written in the verification phase):
  U122 (a) two outboxes on one partition under 50 % induced conflicts: 1,000 records each, no
  writer starved beyond 30 s of injected sleep;
  outbox-rotation: with two hot partitions and one cold, the cold one lands in the first pass;
  outbox-batch: 200 drafts flush as ceil(200 / max_batch) atomic runs with dense seqs;
  outbox-seeded: two appenders with one seed and one conflict script sleep identical durations.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable, Iterable, Mapping, Sequence

from agentdecompile_grid.core import GridError, HeadStore, LogStore, Record, RecordType, Signer
from agentdecompile_grid.log.backoff import DEFAULT_BACKOFF, BackoffPolicy, PartitionRotation, Sleeper, full_jitter
from agentdecompile_grid.log.heads import HeadDiverged, HeadPublishFailed, force_head, publish_head
from agentdecompile_grid.log.local import ChainConflict
from agentdecompile_grid.log.records import Draft, Head, head_of, seal, validate_partition


class HotHead(GridError):
    """``rotate_after`` consecutive conflicts on one partition; rotate and retry later."""

    def __init__(self, partition: str, attempts: int) -> None:
        super().__init__(f"head of {partition!r} rejected {attempts} consecutive appends; rotating")
        self.partition, self.attempts = partition, attempts


class AppendGaveUp(GridError):
    """``max_attempts`` exhausted; the drafts are untouched and may be retried."""


@dataclass(frozen=True)
class OutboxPolicy:
    """Configuration is data.  Design §2.2 defaults: 64 records or 5 s, whichever first."""

    max_batch: int = 64
    flush_interval_s: float = 5.0
    backoff: BackoffPolicy = DEFAULT_BACKOFF

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> OutboxPolicy:
        return cls(max_batch=int(config.get("max_batch", 64)), flush_interval_s=float(config.get("flush_interval_s", 5.0)),
                   backoff=BackoffPolicy.from_config(config.get("backoff", {})))

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "max_batch": {"type": "integer", "default": 64, "minimum": 1},
            "flush_interval_s": {"type": "number", "default": 5.0},
            "backoff": BackoffPolicy.config_schema()}}


DEFAULT_OUTBOX = OutboxPolicy()


class Appender:
    """Seal-and-append one batch to one partition, honouring the adapter's ordering authority."""

    def __init__(self, log: LogStore, heads: HeadStore, signer: Signer, *, backoff: BackoffPolicy = DEFAULT_BACKOFF,
                 seed: int = 0, sleep: Sleeper = time.sleep) -> None:
        self.log = log
        self.heads = heads
        self.signer = signer
        self.backoff = backoff
        self.seed = seed
        self.sleep = sleep
        self.stale_heads = 0
        self.repaired_heads = 0
        self._rounds = 0

    @property
    def authority(self) -> str:
        return str(getattr(self.log, "ordering_authority", "heads"))

    def head(self, partition: str) -> Head:
        """The authoritative head: the log tail when the log orders, else the head store."""
        if self.authority == "log":
            tail = getattr(self.log, "tail", None)
            if callable(tail):
                return tail(partition)
            return self.log.last_seq(partition), self.heads.get(partition)[1]
        return self.heads.get(partition)

    def _once(self, partition: str, drafts: Sequence[Draft]) -> list[Record] | None:
        """One attempt; ``None`` means the head moved under us (retry), a list means landed."""
        head = self.head(partition)
        records = seal(partition, list(drafts), head, self.signer)
        new_head = head_of(records, before=head)
        if self.authority == "log":
            try:
                self.log.append(records)
            except ChainConflict:
                return None
            try:
                publish_head(self.heads, partition, new_head)
            except HeadDiverged:
                # the log is the authority in this branch, so a head store holding another digest at
                # this seq is a stale cache (e.g. after repair + re-append), not a fork: overwrite it
                force_head(self.heads, partition, new_head)
                self.repaired_heads += 1
            except HeadPublishFailed:
                self.stale_heads += 1  # the records landed; rebuild_heads repairs the cache later
            return records
        self.log.append(records)
        if not self.heads.cas(partition, head, new_head):
            return None
        publish = getattr(self.log, "publish", None)
        if callable(publish):
            publish(records)
        return records

    def try_append(self, partition: str, drafts: Sequence[Draft], *, attempts: int | None = None) -> list[Record]:
        """Append with at most ``attempts`` (default ``rotate_after``; ``0`` = no rotation limit) tries;
        ``HotHead`` after that, ``AppendGaveUp`` when the backoff schedule itself runs out."""
        validate_partition(partition)
        if not drafts:
            return []
        limit = attempts if attempts is not None else self.backoff.rotate_after
        self._rounds += 1
        failures = 0
        for step in full_jitter(self.backoff, seed=self.seed * 1_000_003 + self._rounds):
            landed = self._once(partition, drafts)
            if landed is not None:
                return landed
            failures += 1
            if limit and failures >= limit:
                raise HotHead(partition, failures)
            self.sleep(step.delay_s)
        raise AppendGaveUp(f"append to {partition!r} gave up after {failures} attempts")

    def append(self, partition: str, drafts: Sequence[Draft]) -> list[Record]:
        """Append, retrying until it lands or ``backoff.max_attempts`` (default 128) is exhausted:
        ``AppendGaveUp`` by name, never ``HotHead`` (rotation is the outbox's concern, not this
        caller's).  ``max_attempts=None`` retries forever, as an explicit choice."""
        return self.try_append(partition, drafts, attempts=0)

    def append_one(self, partition: str, draft: Draft) -> Record:
        return self.append(partition, [draft])[0]

    def write_batch(self, partition: str, entries: Sequence[Any]) -> Sequence[Record]:
        """``worker.outbox.RecordWriter``: chain, validate, sign and land one batch of pending records.

        ``try_append`` (not ``append``): a hot head raises ``HotHead`` after ``rotate_after`` tries so
        the node outbox defers the batch with its own backoff and rotates partitions instead of
        sleeping through the whole ``max_attempts`` schedule inside a deadlined flush.
        """
        drafts = [draft_for(entry) for entry in entries]
        return self.try_append(partition, drafts)


def draft_for(entry: Any) -> Draft:
    """A ``Draft`` for a pending record (anything with ``.type``, ``.body`` and ``.basis_hash``).

    INTENT bodies carry the fence rule: without a positive ``issued_seq`` the body is sealed as an
    issue with ``issued_seq`` = its own seq (see ``intents``); ``ttl_s`` is coerced to the int the
    validator requires.  Every other type is sealed as-is.
    """
    record_type = entry.type if isinstance(entry.type, RecordType) else RecordType(str(entry.type))
    body = dict(entry.body)
    basis_hash = str(getattr(entry, "basis_hash", "") or "")
    if record_type is RecordType.INTENT:
        if "ttl_s" in body and not isinstance(body["ttl_s"], bool):
            body["ttl_s"] = int(math.ceil(float(body["ttl_s"])))
        fence = body.get("issued_seq")
        if isinstance(fence, bool) or not isinstance(fence, int) or fence <= 0:
            def factory(seq: int, body: dict[str, Any] = body) -> Mapping[str, Any]:
                return {**body, "issued_seq": seq}
            return Draft(record_type, factory, basis_hash)
    return Draft(record_type, body, basis_hash)


class Outbox:
    """Per-partition draft queues flushed as batches with rotation away from hot heads."""

    def __init__(self, appender: Appender, *, policy: OutboxPolicy = DEFAULT_OUTBOX, seed: int = 0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.appender = appender
        self.policy = policy
        self.clock = clock
        self._pending: dict[str, list[Draft]] = {}
        self._first_added: dict[str, float] = {}
        self._rotation = PartitionRotation(seed=seed)
        self.landed: int = 0

    # -- queueing
    def add(self, partition: str, draft: Draft) -> None:
        validate_partition(partition)
        queue = self._pending.setdefault(partition, [])
        if not queue:
            self._first_added[partition] = self.clock()
            self._rotation.add(partition)
        queue.append(draft)

    def add_many(self, partition: str, drafts: Iterable[Draft]) -> None:
        for draft in drafts:
            self.add(partition, draft)

    def pending(self) -> dict[str, int]:
        return {p: len(q) for p, q in sorted(self._pending.items()) if q}

    def due(self, now: float | None = None) -> list[str]:
        """Partitions whose queue is full or older than ``flush_interval_s``."""
        now = self.clock() if now is None else now
        return sorted(p for p, q in self._pending.items()
                      if q and (len(q) >= self.policy.max_batch or now - self._first_added[p] >= self.policy.flush_interval_s))

    # -- flushing
    def flush(self, partitions: Iterable[str] | None = None, *, batches_per_partition: int = 1) -> dict[str, list[Record]]:
        """One pass: for each partition in rotation order land up to ``batches_per_partition`` batches.

        A hot partition (``HotHead``) is deferred to the end of the pass and retried once; whatever
        still fails stays pending.  Returns what landed, per partition.
        """
        wanted = set(partitions) if partitions is not None else None
        landed: dict[str, list[Record]] = {}
        deferred: list[str] = []
        for partition in self._rotation.order():
            if wanted is not None and partition not in wanted:
                continue
            if not self._flush_partition(partition, batches_per_partition, landed):
                deferred.append(partition)
                self._rotation.defer(partition)
        for partition in deferred:
            self._flush_partition(partition, batches_per_partition, landed)
        self._rotation.advance()
        return landed

    def _flush_partition(self, partition: str, batches: int, landed: dict[str, list[Record]]) -> bool:
        queue = self._pending.get(partition)
        for _ in range(batches):
            if not queue:
                return True
            batch = queue[: self.policy.max_batch]
            try:
                records = self.appender.try_append(partition, batch)
            except HotHead:
                return False
            del queue[: len(batch)]
            self.landed += len(records)
            landed.setdefault(partition, []).extend(records)
            if queue:
                self._first_added[partition] = self.clock()
        return True

    def flush_all(self, *, max_passes: int = 10_000) -> dict[str, list[Record]]:
        """Flush until nothing is pending; the appender's backoff paces the retries."""
        landed: dict[str, list[Record]] = {}
        for _ in range(max_passes):
            if not self.pending():
                return landed
            for partition, records in self.flush().items():
                landed.setdefault(partition, []).extend(records)
        raise AppendGaveUp(f"outbox still has {self.pending()} pending after {max_passes} passes")


__all__ = ["DEFAULT_OUTBOX", "AppendGaveUp", "Appender", "HotHead", "Outbox", "OutboxPolicy", "draft_for"]
