"""LocalTransport: objects, log and heads from one root directory — the working transport.

Dependency injection first: ``LocalTransport(objects, log, heads)`` takes the three stores.
``LocalTransport.from_root(root)`` builds them through the registries (``OBJECT_STORES["local"]``
→ ``LocalDirStore(root/objects)``, ``LOG_STORES["local"]`` → ``LocalFileLog(root/log)``,
``HEAD_STORES["local"]`` → ``LocalFileHeads(root/heads)``) and raises ``NotConfigured`` naming
the adapter that is not registered in this process.  Nothing here imports ``objects/`` or ``log/``.

``ChainAppender`` is the fallback ``RecordWriter`` so a single-host grid works end to end today:
head CAS first (reserve ``seq``), then chain, sign and append.  A crash between the two leaves a
head pointing at records that do not exist — detectable (the head digest matches no record) and
repaired by the log layer's chain-scan rebuild (design §2.1).  The log layer's own append path
replaces this writer when it lands.

Acceptance tests named for the final verification phase (U122 (b), (c)):
  * ``test_chain_appender_links``: records appended in two batches form one chain (``prev`` of
    the first record of batch 2 is the digest of the last of batch 1) and the head matches.
  * ``test_from_root_names_missing_adapter``: with an empty registry ``from_root`` raises
    ``NotConfigured`` naming ``LocalDirStore(root)``.
  * ``test_cas_contention_backoff``: an injected CAS failure rate of 50 % still lands every
    record with no writer deferred beyond the stated cap.
"""
from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..core import HEAD_STORES, LOG_STORES, OBJECT_STORES, TRANSPORTS, GridError, HeadStore, LogStore, NotConfigured, ObjectStore, Record, Signer
from ..verify.policy import full_jitter_backoff
from ..worker.outbox import PendingRecord

OBJECTS_SUBDIR = "objects"
LOG_SUBDIR = "log"
HEADS_SUBDIR = "heads"


class HeadContention(GridError):
    """The head CAS kept failing past ``max_attempts``; the outbox defers and rotates partitions."""


def _construct(registry: Any, name: str, path: Path, expected: str) -> Any:
    try:
        cls = registry.get(name)
    except KeyError as exc:
        raise NotConfigured(f"{registry.what} {name!r} is not registered in this process; expected {expected} from agentdecompile_grid.{'objects' if 'object' in registry.what else 'log'}") from exc
    if hasattr(cls, "from_locator"):
        return cls.from_locator({"adapter": name, "root": str(path)})
    return cls(str(path))


class LocalTransport:
    name = "local"

    def __init__(self, objects: ObjectStore, log: LogStore, heads: HeadStore, *, root: str | os.PathLike[str] | None = None) -> None:
        self._objects = objects
        self._log = log
        self._heads = heads
        self.root = Path(root) if root is not None else None

    @classmethod
    def from_root(cls, root: str | os.PathLike[str], *, objects: ObjectStore | None = None, log: LogStore | None = None, heads: HeadStore | None = None) -> "LocalTransport":
        root_path = Path(root)
        objects = objects if objects is not None else _construct(OBJECT_STORES, "local", root_path / OBJECTS_SUBDIR, "LocalDirStore(root)")
        log = log if log is not None else _construct(LOG_STORES, "local", root_path / LOG_SUBDIR, "LocalFileLog(root)")
        heads = heads if heads is not None else _construct(HEAD_STORES, "local", root_path / HEADS_SUBDIR, "LocalFileHeads(root)")
        return cls(objects, log, heads, root=root_path)

    @classmethod
    def from_locator(cls, locator: Mapping[str, Any]) -> "LocalTransport":
        return cls.from_root(str(locator["root"]))

    def objects(self) -> ObjectStore:
        return self._objects

    def log(self) -> LogStore:
        return self._log

    def heads(self) -> HeadStore:
        return self._heads

    def locator(self) -> dict[str, Any]:
        """The serialisable store locator a sandbox child resolves (``sandbox.resolve_store``)."""
        if self.root is None:
            raise NotConfigured("LocalTransport built from injected stores has no root; pass root= to make it locatable by a sandbox child")
        return {"adapter": "local", "root": str(self.root / OBJECTS_SUBDIR)}

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "root": str(self.root) if self.root else None, "objects": getattr(self._objects, "name", "?"), "log": getattr(self._log, "name", "?"), "heads": getattr(self._heads, "name", "?")}


class ChainAppender:
    """Fallback ``RecordWriter``: CAS the head to reserve, then chain + sign + append."""

    def __init__(self, log: LogStore, heads: HeadStore, signer: Signer, *, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 rng: random.Random | None = None, max_attempts: int = 8, backoff_base_s: float = 0.1, backoff_cap_s: float = 5.0) -> None:
        self.log = log
        self.heads = heads
        self.signer = signer
        self.clock = clock
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self.backoff_cap_s = backoff_cap_s
        self.retries = 0
        self.repairs = 0

    def _tail(self, partition: str) -> tuple[int, str]:
        seq = self.log.last_seq(partition)
        prev = ""
        if seq > 0:
            for rec in self.log.read(partition, seq - 1):
                if rec.seq == seq:
                    prev = rec.digest()
        return seq, prev

    def _head(self, partition: str) -> tuple[tuple[int, str], tuple[int, str]]:
        """(stored head to CAS from, chain tail to build on).  They differ only after a crash between
        CAS and append left the head pointing past the log; then the tail wins (chain-scan repair)."""
        tail = self._tail(partition)
        try:
            seq, digest = self.heads.get(partition)
            stored = (int(seq), str(digest))
        except (KeyError, TypeError, ValueError):
            stored = tail
        if stored[0] > tail[0]:
            self.repairs += 1
            return stored, tail
        return stored, tail if stored[0] < tail[0] else stored

    def build(self, partition: str, entries: Sequence[PendingRecord], head: tuple[int, str]) -> list[Record]:
        seq, prev = head
        out: list[Record] = []
        for pending in entries:
            seq += 1
            unsigned = Record(partition, seq, pending.type, dict(pending.body), prev, self.signer.key_id, "", pending.basis_hash)
            signature = self.signer.sign(unsigned.digest().encode("ascii"))
            record = Record(partition, seq, pending.type, dict(pending.body), prev, self.signer.key_id, signature, pending.basis_hash)
            prev = record.digest()
            out.append(record)
        return out

    def write_batch(self, partition: str, entries: Sequence[PendingRecord]) -> Sequence[Record]:
        if not entries:
            return ()
        for attempt in range(self.max_attempts):
            stored, tail = self._head(partition)
            records = self.build(partition, entries, tail)
            new_head = (records[-1].seq, records[-1].digest())
            if self.heads.cas(partition, stored, new_head):
                self.log.append(records)
                return records
            self.retries += 1
            self.sleep(full_jitter_backoff(attempt, base_s=self.backoff_base_s, cap_s=self.backoff_cap_s, rng=self.rng))
        raise HeadContention(f"head CAS on partition {partition!r} failed {self.max_attempts} times; rotating")


TRANSPORTS.register("local", LocalTransport)

__all__ = ["ChainAppender", "HEADS_SUBDIR", "HeadContention", "LOG_SUBDIR", "LocalTransport", "OBJECTS_SUBDIR"]
