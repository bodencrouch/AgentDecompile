"""``LocalFileLog``: one append-only JSONL file per partition, the fully working ``LogStore``.

Layout under ``root``: ``log/<partition components>/records.jsonl`` plus a ``records.lock`` beside
it.  One line per record (canonical JSON + newline).  A batch is one contiguous chained run for one
partition and lands with one write under the partition's exclusive lock, so a reader sees all of a
batch or none of it; a crash mid-write leaves at most one *torn last line*.  Lock-free readers
(``read``, ``tail``, ``start``) simply do not see a trailing fragment, because from outside the lock
it is indistinguishable from a writer mid-batch; the locked paths (``append``, ``repair``) know no
writer is active and judge it: ``LogCorrupt`` by name, repaired only by the explicit ``repair`` verb
(or automatically under ``torn_tail="truncate"``).

Ordering authority.  For this adapter the file tail *is* the order: ``append`` re-reads the tail
under the lock and refuses (``ChainConflict``) a batch whose first record does not chain from it.
That is the file-system equivalent of a conditional PUT.  A head store next to this log is a
published cache that ``heads.publish_head`` keeps monotonic and ``heads.rebuild_heads`` can rebuild
from a chain scan (design U122 (c)).

Reads.  ``read(partition, since_seq)`` yields records with ``seq > since_seq`` in order and verifies
the linkage of every line it scans from the stored start (``verify="chain"``); the first stored
record's ``prev`` is the chain's origin (``""`` or the pruned predecessor's digest).  Reads never
touch the lock or the head store.

Acceptance tests (named here, written in the verification phase):
  U122 (a) two writers appending to one partition under 50 % induced ChainConflict reach 1,000
  records each with no writer starved beyond 30 s;
  U122 (c) ``rebuild_heads`` from ``verify_chain`` equals the live heads;
  local-atomic-batch: a batch of 64 is present in full or not at all after a simulated crash;
  local-torn-tail: a partial last line raises ``LogCorrupt`` by name, ``repair`` truncates it and
  reports the dropped byte count, and the next append lands at the right seq;
  local-prune: after ``prune(keep_from_seq)`` the first line's ``prev`` is the pruned predecessor's
  digest and ``verify_chain`` from ``start`` still succeeds.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from collections.abc import Iterator, Sequence

from agentdecompile_grid.core import GridError, LogStore, Record
from agentdecompile_grid.log._fs import (
    append_all,
    exclusive_lock,
    fsync_dir,
    partition_dir,
    partition_name,
    validate_partition,
    write_atomic,
)
from agentdecompile_grid.log.records import (
    EMPTY_HEAD,
    ChainBroken,
    Head,
    SignatureVerifier,
    decode_line,
    encode_line,
    validate_record,
    verify_chain,
)

RECORDS_FILE = "records.jsonl"
LOCK_FILE = "records.lock"
_TAIL_BLOCK = 64 * 1024


class LogCorrupt(GridError):
    """The stored file is not a clean JSONL chain: a torn last line seen under the lock, or an undecodable line."""


class ChainConflict(GridError):
    """An append did not chain from the real tail: someone else appended first.  Re-seal and retry."""

    def __init__(self, partition: str, expected: Head, found: Head) -> None:
        super().__init__(f"append to {partition!r} expected tail {expected!r}, found {found!r}")
        self.partition, self.expected, self.found = partition, expected, found


class PruneRefused(GridError):
    """A prune would drop records that no checkpoint summarises, or points outside the stored range."""


class LocalFileLog:
    """Append-only JSONL log per partition; the file tail is the ordering authority."""

    name = "local"
    ordering_authority = "log"

    def __init__(self, root: str | os.PathLike[str], *, torn_tail: str = "raise", fsync: bool = True, verify: str = "chain") -> None:
        if torn_tail not in ("raise", "truncate"):
            raise ValueError("torn_tail must be 'raise' or 'truncate'")
        if verify not in ("chain", "seq", "none"):
            raise ValueError("verify must be 'chain', 'seq' or 'none'")
        self.root = Path(root)
        self.torn_tail = torn_tail
        self.fsync = fsync
        self.verify = verify

    # ------------------------------------------------------------------ paths
    @property
    def log_root(self) -> Path:
        return self.root / "log"

    def _dir(self, partition: str) -> Path:
        return partition_dir(self.log_root, partition)

    def _file(self, partition: str) -> Path:
        return self._dir(partition) / RECORDS_FILE

    # ------------------------------------------------------------------ LogStore
    def append(self, records: Sequence[Record]) -> None:
        """Append one or more contiguous per-partition runs, each atomically and tail-checked."""
        if not records:
            return
        groups: list[list[Record]] = []
        for record in records:
            if groups and groups[-1][-1].partition == record.partition:
                groups[-1].append(record)
            else:
                groups.append([record])
        for group in groups:
            self._append_run(group)

    def _append_run(self, run: list[Record]) -> None:
        partition = validate_partition(run[0].partition)
        claimed: Head = (run[0].seq - 1, run[0].prev)
        verify_chain(run, head=claimed, partition=partition)  # links, validators, identity binding
        payload = b"".join(encode_line(r) for r in run)
        directory = self._dir(partition)
        directory.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(directory / LOCK_FILE):
            tail = self._tail_locked(partition)
            if tail != claimed:
                raise ChainConflict(partition, claimed, tail)
            fd = os.open(str(directory / RECORDS_FILE), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                append_all(fd, payload)
                if self.fsync:
                    os.fsync(fd)
            finally:
                os.close(fd)

    def read(self, partition: str, since_seq: int = 0) -> Iterator[Record]:
        """Records with ``seq > since_seq``; linkage of every scanned line is verified per ``self.verify``."""
        validate_partition(partition)
        path = self._file(partition)
        if not path.is_file():
            return iter(())
        return self._iter(partition, path, since_seq)

    def _iter(self, partition: str, path: Path, since_seq: int) -> Iterator[Record]:
        seq = prev = None
        with path.open("rb") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.endswith(b"\n"):
                    break  # a trailing fragment: a writer mid-batch or a crash; invisible to lock-free readers
                try:
                    record = decode_line(line.rstrip(b"\n"))
                except GridError as exc:
                    raise LogCorrupt(f"{path}: line {line_no}: {exc}") from exc
                if record.partition != partition:
                    raise LogCorrupt(f"{path}: line {line_no} belongs to partition {record.partition!r}")
                if seq is not None and self.verify != "none":
                    if record.seq != seq + 1:
                        raise ChainBroken(partition, record.seq, "seq", seq + 1, record.seq)
                    if self.verify == "chain" and record.prev != prev:
                        raise ChainBroken(partition, record.seq, "prev", prev, record.prev)
                seq = record.seq
                prev = record.digest() if self.verify == "chain" else record.prev
                if record.seq > since_seq:
                    yield record

    def partitions(self) -> Iterator[str]:
        if not self.log_root.is_dir():
            return iter(())
        found = []
        for dirpath, _dirnames, filenames in os.walk(self.log_root):
            if RECORDS_FILE in filenames:
                found.append(partition_name(self.log_root, Path(dirpath)))
        return iter(sorted(found))

    def last_seq(self, partition: str) -> int:
        return self.tail(partition)[0]

    # ------------------------------------------------------------------ extras other layers rely on
    def start(self, partition: str) -> Head:
        """The head *before* the first stored record: ``(0, "")`` unless a prefix was pruned."""
        validate_partition(partition)
        path = self._file(partition)
        if not path.is_file():
            return EMPTY_HEAD
        with path.open("rb") as handle:
            first = handle.readline()
        if not first:
            return EMPTY_HEAD
        if not first.endswith(b"\n"):
            return EMPTY_HEAD  # the only line is a fragment: nothing complete is stored yet
        record = self._decode(path, 1, first)
        return record.seq - 1, record.prev

    def tail(self, partition: str) -> Head:
        """``(seq, digest)`` of the last complete record; lock-free, reads only the file's end.

        A trailing fragment (a writer mid-batch, or a crash) is ignored here: only the locked path
        (``append``, ``repair``) can tell the two apart, so only it judges a torn tail.
        """
        validate_partition(partition)
        path = self._file(partition)
        if not path.is_file():
            return EMPTY_HEAD
        line, _torn = _last_complete_line(path)
        if line is None:
            return EMPTY_HEAD
        record = self._decode(path, -1, line)
        return record.seq, record.digest()

    def _tail_locked(self, partition: str) -> Head:
        """Under the partition lock no writer is mid-batch, so a fragment is a crash: apply ``torn_tail``."""
        path = self._file(partition)
        if not path.is_file():
            return EMPTY_HEAD
        line, torn = _last_complete_line(path)
        if torn:
            if self.torn_tail == "raise":
                raise LogCorrupt(f"{path}: last line is torn ({torn} bytes without newline); run repair({partition!r})")
            self._truncate(path, torn)
        if line is None:
            return EMPTY_HEAD
        record = self._decode(path, -1, line)
        return record.seq, record.digest()

    def _truncate(self, path: Path, torn: int) -> None:
        size = path.stat().st_size
        with path.open("r+b") as handle:
            handle.truncate(size - torn)
            if self.fsync:
                handle.flush()
                os.fsync(handle.fileno())

    def verify_chain(self, partition: str, *, verifier: SignatureVerifier | None = None) -> Head:
        """Full scan from ``start``: linkage, validators and (with a verifier) signatures.  Returns the head."""
        return verify_chain(self.read(partition), head=self.start(partition), verifier=verifier, partition=partition)

    def repair(self, partition: str) -> dict[str, Any]:
        """Truncate a torn last line under the lock.  Explicit; never done on read or append."""
        validate_partition(partition)
        path = self._file(partition)
        report: dict[str, Any] = {"partition": partition, "dropped_bytes": 0, "tail": EMPTY_HEAD}
        if not path.is_file():
            return report
        directory = path.parent
        with exclusive_lock(directory / LOCK_FILE):
            _line, torn = _last_complete_line(path)
            if torn:
                self._truncate(path, torn)
                report["dropped_bytes"] = torn
            report["tail"] = self._tail_locked(partition)
        return report

    def prune(self, partition: str, keep_from_seq: int) -> int:
        """Drop stored records with ``seq < keep_from_seq``; returns how many were dropped.

        Pruning is the only destructive verb in this package and is never called by ``compact``;
        ``compaction.prune`` checks a checkpoint covers the prefix before calling this.
        """
        validate_partition(partition)
        path = self._file(partition)
        if not path.is_file():
            return 0
        directory = path.parent
        with exclusive_lock(directory / LOCK_FILE):
            start_seq = self.start(partition)[0]
            tail_seq = self._tail_locked(partition)[0]
            if keep_from_seq <= start_seq + 1:
                return 0
            if keep_from_seq > tail_seq + 1:
                raise PruneRefused(f"{partition!r}: keep_from_seq {keep_from_seq} is beyond the tail {tail_seq}")
            kept = bytearray()
            dropped = 0
            for record in self._iter(partition, path, 0):
                if record.seq >= keep_from_seq:
                    kept += encode_line(record)
                else:
                    dropped += 1
            write_atomic(path, bytes(kept), fsync=self.fsync)
            fsync_dir(directory)
        return dropped

    # ------------------------------------------------------------------ config as data
    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "required": ["root"], "properties": {
            "adapter": {"const": "local"},
            "root": {"type": "string", "description": "store root; records live under <root>/log/<partition>/records.jsonl"},
            "torn_tail": {"enum": ["raise", "truncate"], "default": "raise"},
            "fsync": {"type": "boolean", "default": True},
            "verify": {"enum": ["chain", "seq", "none"], "default": "chain", "description": "what read() checks per scanned line"},
        }}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "working", "requires": ["a writable directory"],
                "config_schema": cls.config_schema(), "ordering_authority": cls.ordering_authority,
                "semantics": "JSONL per partition; one locked, tail-checked write per batch; reads verify linkage"}

    @classmethod
    def from_config(cls, config: Any) -> LocalFileLog:
        return cls(str(config["root"]), torn_tail=str(config.get("torn_tail", "raise")),
                   fsync=bool(config.get("fsync", True)), verify=str(config.get("verify", "chain")))

    # ------------------------------------------------------------------ helpers
    def _decode(self, path: Path, line_no: int, line: bytes) -> Record:
        try:
            record = decode_line(line.rstrip(b"\n"))
            validate_record(record)
        except GridError as exc:
            where = "last line" if line_no < 0 else f"line {line_no}"
            raise LogCorrupt(f"{path}: {where}: {exc}") from exc
        return record


def _last_complete_line(path: Path) -> tuple[bytes | None, int]:
    """``(last newline-terminated line or None, bytes of torn trailing data)``, reading only the end."""
    size = path.stat().st_size
    if size == 0:
        return None, 0
    with path.open("rb") as handle:
        buf = b""
        pos = size
        while pos > 0 and buf.count(b"\n") < 2:
            step = min(_TAIL_BLOCK, pos)
            pos -= step
            handle.seek(pos)
            buf = handle.read(step) + buf
    last_nl = buf.rfind(b"\n")
    if last_nl < 0:
        return None, size  # nothing complete at all: the whole file is one torn line
    torn = len(buf) - last_nl - 1
    complete = buf[:last_nl]
    return complete[complete.rfind(b"\n") + 1:], torn


def is_prunable(log: LogStore) -> bool:
    return callable(getattr(log, "prune", None))


__all__ = ["ChainConflict", "LOCK_FILE", "LocalFileLog", "LogCorrupt", "PruneRefused", "RECORDS_FILE", "is_prunable"]
