"""Head stores: one compare-and-swap ``(seq, digest)`` pointer per partition.

``LocalFileHeads`` is the working adapter: the pointer is a small JSON file replaced atomically
(temp file + ``os.replace``) while an exclusive ``fcntl``/``msvcrt`` lock on a sibling lock file makes
read-compare-write one step.  ``S3ConditionalHeads`` and ``HttpHeads`` are declared with their
config schema and the exact protocol they would run; constructing or using them raises
``NotConfigured`` naming what would make them usable.

Sub-partitioning.  A hot base partition is split by task-id prefix: the effective partition of a
record about ``task_id`` is ``sub_partition(base, task_id, width)`` = ``f"{base}/{task_id[:width]}"``
(``width`` hex chars; ``0`` = no split).  The head key *is* the partition name, so log and head
agree by construction and the frontier reads a base partition as the family ``base`` + ``base/*``.

CAS rules.  ``get`` of an absent head is ``(0, "")``.  ``cas(key, expected, new)`` succeeds iff the
stored value equals ``expected`` exactly.  ``publish_head`` only ever moves a head *forward* along
the same chain and raises ``HeadDiverged`` when two different digests claim one seq: that is a fork,
never something to paper over.  ``rebuild_heads`` recomputes every head from a chain scan of the
log (the recovery path when the head store is lost) and publishes them.

Acceptance tests (named here, written in the verification phase):
  U122 (a) two writers on one head under 50 % induced CAS failure: no writer starved beyond 30 s;
  U122 (b) a head-store outage leaves writers appending to the local log; ``rebuild_heads`` after
  the outage yields heads equal to the log tails;
  U122 (c) heads rebuilt by chain scan equal the live heads;
  heads-cas: concurrent ``cas`` from 8 processes on one key admits exactly one winner per round;
  heads-fork: ``publish_head`` with a different digest at the same seq raises ``HeadDiverged``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from collections.abc import Iterator, Mapping, Sequence

from agentdecompile_grid.core import GridError, HeadStore, LogStore, NotConfigured
from agentdecompile_grid.log._fs import InvalidPartition, exclusive_lock, partition_dir, partition_name, validate_partition, write_atomic
from agentdecompile_grid.log.records import EMPTY_HEAD, Head, SignatureVerifier, verify_chain

HEAD_SUFFIX = ".head"
LOCK_SUFFIX = ".head.lock"


class HeadDiverged(GridError):
    """Two different record digests claim the same seq on one partition: a fork, reported by name."""

    def __init__(self, partition: str, seq: int, stored: str, offered: str) -> None:
        super().__init__(f"head {partition!r} at seq {seq}: stored digest {stored!r} != offered {offered!r}")
        self.partition, self.seq, self.stored, self.offered = partition, seq, stored, offered


class HeadPublishFailed(GridError):
    """``publish_head`` lost the CAS more times than ``attempts`` allows."""


def sub_partition(partition: str, task_id: str, width: int) -> str:
    """Effective partition (and head key) for ``task_id`` under a base partition."""
    validate_partition(partition)
    if width <= 0:
        return partition
    if not task_id or len(task_id) < width:
        raise InvalidPartition(f"task_id {task_id!r} shorter than prefix width {width}")
    return validate_partition(f"{partition}/{task_id[:width]}")


def partition_family(partitions: Sequence[str], base: str) -> list[str]:
    """``base`` and every ``base/<prefix>`` among ``partitions``, sorted."""
    return sorted(p for p in partitions if p == base or p.startswith(base + "/"))


def prefix_width(config: Mapping[str, Any], lane: str) -> int:
    """Configuration is data: ``{"default": 0, "<lane>": <hex chars>}``."""
    return int(config.get(lane, config.get("default", 0)))


# --------------------------------------------------------------------------- local
class LocalFileHeads:
    """CAS by ``os.replace`` of a temp file under an exclusive file lock; key = partition name."""

    name = "local"

    def __init__(self, root: str | os.PathLike[str], *, fsync: bool = True) -> None:
        self.root = Path(root)
        self.fsync = fsync

    @property
    def heads_root(self) -> Path:
        return self.root / "heads"

    def _paths(self, key: str) -> tuple[Path, Path]:
        base = partition_dir(self.heads_root, key)
        return base.with_name(base.name + HEAD_SUFFIX), base.with_name(base.name + LOCK_SUFFIX)

    @staticmethod
    def _read(path: Path) -> Head:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return EMPTY_HEAD
        except ValueError as exc:
            raise GridError(f"head file {path} is not JSON: {exc}") from exc
        return int(data["seq"]), str(data["digest"])

    def get(self, partition: str) -> Head:
        head_path, _lock = self._paths(partition)
        return self._read(head_path)

    def cas(self, partition: str, expected: Head, new: Head) -> bool:
        head_path, lock_path = self._paths(partition)
        expected = (int(expected[0]), str(expected[1]))
        new = (int(new[0]), str(new[1]))
        with exclusive_lock(lock_path):
            if self._read(head_path) != expected:
                return False
            write_atomic(head_path, json.dumps({"seq": new[0], "digest": new[1]}).encode("utf-8"), fsync=self.fsync)
            return True

    def keys(self) -> Iterator[str]:
        if not self.heads_root.is_dir():
            return iter(())
        found = []
        for dirpath, _dirnames, filenames in os.walk(self.heads_root):
            for filename in filenames:
                if filename.endswith(HEAD_SUFFIX) and not filename.endswith(LOCK_SUFFIX):
                    found.append(partition_name(self.heads_root, Path(dirpath) / filename[: -len(HEAD_SUFFIX)]))
        return iter(sorted(found))

    def snapshot(self) -> dict[str, Head]:
        return {key: self.get(key) for key in self.keys()}

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "required": ["root"], "properties": {
            "adapter": {"const": "local"},
            "root": {"type": "string", "description": "store root; heads live under <root>/heads/<partition>.head"},
            "fsync": {"type": "boolean", "default": True},
        }}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "working", "requires": ["a writable directory", "fcntl or msvcrt"],
                "config_schema": cls.config_schema(),
                "semantics": "read-compare-replace under an exclusive file lock; (0, '') when absent"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> LocalFileHeads:
        return cls(str(config["root"]), fsync=bool(config.get("fsync", True)))


# --------------------------------------------------------------------------- declared adapters
class S3ConditionalHeads:
    """Declared: one small object per partition, CAS by ETag ``If-Match`` / ``If-None-Match: *``.

    Protocol it would run: ``get`` = GET ``<prefix>/heads/<partition>`` and remember the ETag
    (absent -> ``(0, "")`` with a "must not exist" precondition); ``cas`` = PUT the new JSON with
    ``If-Match: <etag>`` (or ``If-None-Match: *`` for the first write); a 412 is ``False``.  Needs a
    bucket whose conditional writes are enabled and a client library; until then every call raises
    ``NotConfigured`` naming the requirement.
    """

    name = "s3"
    REQUIRES = ("python package 'boto3'", "heads.s3.bucket", "heads.s3.prefix",
                "credentials with s3:GetObject and s3:PutObject", "a bucket with conditional writes (If-Match) enabled")

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self._unavailable()

    def _unavailable(self) -> None:
        missing = [k for k in ("bucket", "prefix") if not self.config.get(k)]
        raise NotConfigured(f"S3ConditionalHeads is declared, not wired: needs {list(self.REQUIRES)}; missing config keys {missing}")

    def get(self, partition: str) -> Head:
        self._unavailable()
        return EMPTY_HEAD  # pragma: no cover

    def cas(self, partition: str, expected: Head, new: Head) -> bool:
        self._unavailable()
        return False  # pragma: no cover

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "required": ["bucket", "prefix"], "properties": {
            "adapter": {"const": "s3"}, "bucket": {"type": "string"}, "prefix": {"type": "string"},
            "endpoint_url": {"type": "string"}, "region": {"type": "string"},
            "profile": {"type": "string", "description": "credentials profile; never inline keys in config"},
        }}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "declared", "requires": list(cls.REQUIRES), "config_schema": cls.config_schema(),
                "semantics": "conditional PUT with If-Match on the head object; 412 = CAS failure"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> S3ConditionalHeads:
        return cls(config)


class HttpHeads:
    """Declared: a head table behind an outbound-only HTTP gateway (``GET/PUT /heads/<partition>``
    with ``If-Match``).  Same CAS semantics as S3; needs ``heads.http.base_url`` and a bearer token
    source before it does anything."""

    name = "http"
    REQUIRES = ("heads.http.base_url", "heads.http.token_env (bearer token variable)", "a gateway implementing GET/PUT /heads/<partition> with If-Match")

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self._unavailable()

    def _unavailable(self) -> None:
        raise NotConfigured(f"HttpHeads is declared, not wired: needs {list(self.REQUIRES)}")

    def get(self, partition: str) -> Head:
        self._unavailable()
        return EMPTY_HEAD  # pragma: no cover

    def cas(self, partition: str, expected: Head, new: Head) -> bool:
        self._unavailable()
        return False  # pragma: no cover

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "required": ["base_url"], "properties": {
            "adapter": {"const": "http"}, "base_url": {"type": "string"}, "token_env": {"type": "string"},
            "timeout_s": {"type": "number", "default": 10}}}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "declared", "requires": list(cls.REQUIRES), "config_schema": cls.config_schema(),
                "semantics": "PUT with If-Match against a gateway; 412 = CAS failure"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> HttpHeads:
        return cls(config)


# --------------------------------------------------------------------------- protocol helpers
def publish_head(heads: HeadStore, partition: str, new: Head, *, attempts: int = 64) -> bool:
    """Move ``partition``'s head forward to ``new`` (never backward); ``True`` when the store holds it.

    Returns ``False`` when the stored head is already *ahead* (a later batch published first); raises
    ``HeadDiverged`` when the stored head sits at the same seq with another digest.
    """
    for _ in range(attempts):
        current = heads.get(partition)
        if current == new:
            return True
        if current[0] > new[0]:
            return False
        if current[0] == new[0] and current[1] != new[1]:
            raise HeadDiverged(partition, new[0], current[1], new[1])
        if heads.cas(partition, current, new):
            return True
    raise HeadPublishFailed(f"could not publish head {new!r} for {partition!r} in {attempts} attempts")


def rebuild_heads(log: LogStore, heads: HeadStore, partitions: Sequence[str] | None = None, *,
                  verifier: SignatureVerifier | None = None) -> dict[str, Head]:
    """Recompute every head from a chain scan of the log and publish it; returns what was published."""
    names = sorted(partitions) if partitions is not None else sorted(log.partitions())
    rebuilt: dict[str, Head] = {}
    for partition in names:
        start = getattr(log, "start", None)
        origin: Head = start(partition) if callable(start) else EMPTY_HEAD
        head = verify_chain(log.read(partition), head=origin, verifier=verifier, partition=partition)
        if head != EMPTY_HEAD:
            publish_head(heads, partition, head)
        rebuilt[partition] = head
    return rebuilt


def heads_match_log(log: LogStore, heads: HeadStore, partitions: Sequence[str] | None = None) -> dict[str, tuple[Head, Head]]:
    """``{partition: (head_store_value, log_tail)}`` for every partition where they differ."""
    names = sorted(partitions) if partitions is not None else sorted(log.partitions())
    tail = getattr(log, "tail", None)
    mismatches: dict[str, tuple[Head, Head]] = {}
    for partition in names:
        if callable(tail):
            log_head = tail(partition)
        else:
            start = getattr(log, "start", None)
            log_head = verify_chain(log.read(partition), head=start(partition) if callable(start) else EMPTY_HEAD, validate=False)
        stored = heads.get(partition)
        if stored != log_head:
            mismatches[partition] = (stored, log_head)
    return mismatches


__all__ = [
    "HEAD_SUFFIX", "HeadDiverged", "HeadPublishFailed", "HttpHeads", "LocalFileHeads", "S3ConditionalHeads",
    "heads_match_log", "partition_family", "prefix_width", "publish_head", "rebuild_heads", "sub_partition",
]
