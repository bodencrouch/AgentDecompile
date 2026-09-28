"""The node's durable outbox: what must reach upstream, in order, surviving restarts.

One entry = ``{objects, named, record}`` written atomically (tmp → fsync → rename) *before* the
work loop drops its intent, so a crash at any point leaves either nothing or a complete entry.
Flush order inside a round is objects → named pointers → records, and a record is never
appended while any object it lists is missing upstream (a proposal must never dangle).  Records
are batched per partition (design §2.2: one append per flush interval or 64 records) and paced
by a token bucket; every upstream failure defers the entry with full-jitter backoff (CAS: base
100 ms / cap 5 s; transport: base 1 s / cap 5 min) and the round moves to the next partition so
one hot head never starves the rest.  Re-flushing after a crash is idempotent: object puts are
content-addressed, named pointers are last-writer-wins on the same value, and every record body
carries a nonce and is idempotent by content (see ``records``).

Every ``flush`` has a wall-clock deadline and returns a ``FlushReport`` naming what stopped it
(``deadline``, ``throttled``, per-entry reasons) — it never waits.

Distinct from the log layer's ``log/outbox.py`` (design §15.0 U122, the batch-append path over
the head CAS): this is the worker-side queue that *feeds* that path through ``RecordWriter``.

Acceptance tests named for the final verification phase (U122 (b), U124):
  * ``test_outbox_survives_restart``: entries enqueued, process "crashes" (new Outbox on the same
    root), flush delivers every object and record exactly once, in seq order.
  * ``test_objects_before_records``: an entry whose object put fails leaves its record unflushed;
    once the object lands the record follows.
  * ``test_flush_deadline_and_backoff``: a writer that always raises defers entries with
    increasing ``next_attempt_at`` and the flush stops at its deadline by name.
  * ``test_rate_limit_pacing``: with a 64/min limit the 65th record in a round is ``throttled``
    with ``retry_after_s`` and flushed in a later round.
"""
from __future__ import annotations

import json
import os
import random
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..core import GridError, LogStore, ObjectRef, ObjectStore, Record, RecordType
from ..verify.policy import KeyRateLimiter, full_jitter_backoff

PENDING_DIR = "pending"
DEFAULT_FLUSH_INTERVAL_S = 5.0
DEFAULT_FLUSH_BATCH = 64


class OutboxError(GridError):
    """The outbox directory is unusable (disk full, not writable): a named failure, never silent loss."""


@dataclass(frozen=True)
class PendingRecord:
    partition: str
    type: RecordType
    body: Mapping[str, Any]
    basis_hash: str = ""

    def to_record(self) -> dict[str, Any]:
        return {"partition": self.partition, "type": self.type.value, "body": dict(self.body), "basis_hash": self.basis_hash}

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> "PendingRecord":
        return cls(rec["partition"], RecordType(rec["type"]), dict(rec.get("body", {})), str(rec.get("basis_hash", "")))


class RecordWriter(Protocol):
    """Chains, signs and appends a batch for one partition (the log layer's append path; the
    fallback ``transport.local.ChainAppender`` exists so a single-host grid works today)."""

    def write_batch(self, partition: str, entries: Sequence[PendingRecord]) -> Sequence[Record]: ...


@dataclass
class OutboxEntry:
    seq: int
    nonce: str
    enqueued_at: float
    objects: tuple[str, ...]
    named: tuple[tuple[str, str], ...]         # (name, utf-8 text value — usually an ObjectRef)
    record: PendingRecord | None
    path: Path
    attempts: int = 0
    next_attempt_at: float = 0.0
    last_error: str = ""

    def to_record(self) -> dict[str, Any]:
        return {"seq": self.seq, "nonce": self.nonce, "enqueued_at": self.enqueued_at, "objects": list(self.objects), "named": [list(n) for n in self.named], "record": self.record.to_record() if self.record else None}


@dataclass
class FlushReport:
    objects: int = 0
    named: int = 0
    records: int = 0
    removed: int = 0
    deferred: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)
    stopped_by: str = ""                      # "" | deadline | throttled
    retry_after_s: float = 0.0
    remaining: int = 0
    elapsed_s: float = 0.0

    def to_record(self) -> dict[str, Any]:
        return {"objects": self.objects, "named": self.named, "records": self.records, "removed": self.removed, "deferred": self.deferred, "failed": [list(f) for f in self.failed], "stopped_by": self.stopped_by, "retry_after_s": round(self.retry_after_s, 3), "remaining": self.remaining, "elapsed_s": round(self.elapsed_s, 3)}


class Outbox:
    def __init__(self, root: str | os.PathLike[str], *, clock: Callable[[], float] = time.monotonic, rng: random.Random | None = None,
                 cas_backoff: tuple[float, float] = (0.1, 5.0), transport_backoff: tuple[float, float] = (1.0, 300.0), max_entries: int = 100_000) -> None:
        self.root = Path(root)
        self.pending_dir = self.root / PENDING_DIR
        self.clock = clock
        self.rng = rng or random.Random()
        self.cas_backoff = cas_backoff
        self.transport_backoff = transport_backoff
        self.max_entries = max_entries
        self.last_flush_at: float = clock()
        self._state: dict[int, tuple[int, float, str]] = {}     # seq -> (attempts, next_attempt_at, last_error); in memory only
        self._confirmed: dict[str, None] = {}                     # refs known to be upstream (bounded); saves an exists() per object per round
        try:
            self.pending_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutboxError(f"outbox root {self.root} is not writable: {exc.__class__.__name__}") from exc
        for stale in self.pending_dir.glob("*.tmp"):
            stale.unlink(missing_ok=True)
        self._seq = max((e.seq for e in self.pending()), default=0)

    # -- enqueue
    def enqueue(self, *, objects: Sequence[ObjectRef | str] = (), named: Sequence[tuple[str, str]] = (), record: PendingRecord | None = None, nonce: str | None = None) -> OutboxEntry:
        if not objects and not named and record is None:
            raise ValueError("an outbox entry needs at least one object, named pointer or record")
        if self.depth() >= self.max_entries:
            raise OutboxError(f"outbox at its cap ({self.max_entries} entries); upstream unreachable for too long")
        self._seq += 1
        nonce = nonce or secrets.token_hex(8)
        entry = OutboxEntry(self._seq, nonce, self.clock(), tuple(str(o) for o in objects), tuple((str(n), str(v)) for n, v in named), record, self.pending_dir / f"{self._seq:012d}-{nonce}.json")
        try:
            _write_atomic(entry.path, json.dumps(entry.to_record(), sort_keys=True).encode("utf-8"))
        except OSError as exc:
            raise OutboxError(f"cannot persist outbox entry: {exc.__class__.__name__}") from exc
        return entry

    # -- inspection
    def pending(self) -> list[OutboxEntry]:
        entries = []
        for path in sorted(self.pending_dir.glob("*.json")):
            try:
                rec = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            entry = OutboxEntry(int(rec["seq"]), str(rec["nonce"]), float(rec.get("enqueued_at", 0.0)), tuple(rec.get("objects", ())), tuple((n, v) for n, v in rec.get("named", ())), PendingRecord.from_record(rec["record"]) if rec.get("record") else None, path)
            attempts, next_at, err = self._state.get(entry.seq, (0, 0.0, ""))
            entry.attempts, entry.next_attempt_at, entry.last_error = attempts, next_at, err
            entries.append(entry)
        entries.sort(key=lambda e: e.seq)
        return entries

    def depth(self) -> int:
        return sum(1 for _ in self.pending_dir.glob("*.json"))

    def due(self, now: float | None = None, *, interval_s: float = DEFAULT_FLUSH_INTERVAL_S, batch: int = DEFAULT_FLUSH_BATCH) -> bool:
        now = self.clock() if now is None else now
        depth = self.depth()
        return depth > 0 and (depth >= batch or now - self.last_flush_at >= interval_s)

    # -- flush
    def flush(self, local: ObjectStore, upstream: ObjectStore, writer: RecordWriter | None, *, deadline_s: float = 30.0, max_records: int = DEFAULT_FLUSH_BATCH,
              limiter: KeyRateLimiter | None = None, key_id: str = "", same_store: bool | None = None) -> FlushReport:
        started = self.clock()
        self.last_flush_at = started
        report = FlushReport()
        same = (local is upstream) if same_store is None else same_store
        entries = self.pending()
        ready: list[OutboxEntry] = []

        def out_of_time() -> bool:
            return self.clock() - started >= deadline_s

        # phase 1: objects and named pointers, in seq order
        for entry in entries:
            if out_of_time():
                report.stopped_by = "deadline"
                break
            if entry.next_attempt_at > self.clock():
                report.deferred += 1
                continue
            try:
                for ref in entry.objects:
                    oref = ObjectRef(ref)
                    if same or ref in self._confirmed:
                        continue
                    if not upstream.exists(oref):
                        got = upstream.put(local.get(oref))
                        if str(got) != ref:
                            raise OutboxError(f"object-mismatch:{ref[:20]}")
                        report.objects += 1
                    self._confirmed[ref] = None
                    if len(self._confirmed) > 10_000:
                        del self._confirmed[next(iter(self._confirmed))]
                for name, value in entry.named:
                    upstream.put_named(name, value.encode("utf-8"))
                    report.named += 1
            except Exception as exc:
                self._defer(entry, report, f"objects:{exc.__class__.__name__}", self.transport_backoff)
                continue
            if entry.record is None:
                self._remove(entry, report)
            else:
                ready.append(entry)

        # phase 2: records, batched per partition; a failing partition is skipped this round (rotation)
        if ready and writer is None:
            for entry in ready:
                self._defer(entry, report, "no-writer", self.transport_backoff)
        elif ready and report.stopped_by != "deadline":
            by_partition: dict[str, list[OutboxEntry]] = {}
            for entry in ready:
                assert entry.record is not None
                by_partition.setdefault(entry.record.partition, []).append(entry)
            for partition, group in by_partition.items():
                if report.stopped_by:
                    break
                for start in range(0, len(group), max_records):
                    if out_of_time():
                        report.stopped_by = "deadline"
                        break
                    chunk = group[start:start + max_records]
                    if limiter is not None:
                        admission = limiter.admit(key_id, records=len(chunk))
                        if not admission.ok:
                            report.stopped_by = "throttled"
                            report.retry_after_s = admission.retry_after_s
                            break
                    try:
                        assert writer is not None
                        writer.write_batch(partition, [e.record for e in chunk if e.record is not None])
                    except Exception as exc:
                        for entry in chunk:
                            self._defer(entry, report, f"append:{exc.__class__.__name__}", self.cas_backoff)
                        break            # rotate to the next partition; this one is retried later
                    for entry in chunk:
                        report.records += 1
                        self._remove(entry, report)
        report.remaining = self.depth()
        report.elapsed_s = self.clock() - started
        return report

    def clear_state(self) -> None:
        self._state.clear()

    def _defer(self, entry: OutboxEntry, report: FlushReport, reason: str, backoff: tuple[float, float]) -> None:
        attempts = entry.attempts + 1
        delay = full_jitter_backoff(attempts, base_s=backoff[0], cap_s=backoff[1], rng=self.rng)
        self._state[entry.seq] = (attempts, self.clock() + delay, reason)
        report.failed.append((entry.seq, reason))

    def _remove(self, entry: OutboxEntry, report: FlushReport) -> None:
        try:
            entry.path.unlink()
        except FileNotFoundError:
            pass
        self._state.pop(entry.seq, None)
        report.removed += 1


class MemoryRecordWriter:
    """A ``RecordWriter`` that appends unsigned, unchained records straight into a ``LogStore``:
    for harnesses whose log adapter chains internally.  Not for production; the fallback for a
    working single-host grid is ``transport.local.ChainAppender``."""

    def __init__(self, log: LogStore, *, signer_key: str = "") -> None:
        self.log = log
        self.signer_key = signer_key
        self.written: list[Record] = []

    def write_batch(self, partition: str, entries: Sequence[PendingRecord]) -> Sequence[Record]:
        seq = self.log.last_seq(partition)
        prev = ""
        for rec in self.log.read(partition, max(0, seq - 1)):
            prev = rec.digest()
        out: list[Record] = []
        for pending in entries:
            seq += 1
            record = Record(partition, seq, pending.type, dict(pending.body), prev, self.signer_key, "", pending.basis_hash)
            prev = record.digest()
            out.append(record)
        self.log.append(out)
        self.written.extend(out)
        return out


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


__all__ = ["DEFAULT_FLUSH_BATCH", "DEFAULT_FLUSH_INTERVAL_S", "FlushReport", "MemoryRecordWriter", "Outbox", "OutboxEntry", "OutboxError", "PENDING_DIR", "PendingRecord", "RecordWriter"]
