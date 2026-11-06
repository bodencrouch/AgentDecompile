"""agentdecompile_grid — the shared contract every layer builds against.

This module is deliberately *all interface*: Protocols, frozen dataclasses, canonical encoding,
identifiers, and registries.  Concrete adapters live in their own packages (``objects``, ``log``,
``tasks``, ``worker``, ``verify``, ``view``, ``fleet``) and register themselves here.  The grid never
imports the recovery pipeline; pipeline task kinds live in ``agentdecompile_recovery.grid_lanes``
and import *this* package (import direction: recovery -> grid only), so the grid is reusable for
any CPU/IO-heavy work.

Design rules (recorded in the plan's program thesis and loop charter §6c):

* every result from every node is a *proposal* until a machine check by an independent key passes;
* the frontier is a pure function of the log and the object store — no scheduler state exists;
* leases are advisory: a lost or duplicated lease can waste compute, never produce a wrong commit;
* ``task_id = sha256(canonical(kind, kind_version, input hashes, params, basis_hash))`` so an
  identical-basis re-run is a cache hit and a basis change invalidates every id;
* every layer is an extension point with a registry and at least one working implementation
  (speculative generality is a goal here, not a smell).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator, Mapping, Protocol, Sequence, runtime_checkable

GRID_SCHEMA_VERSION = 1
HASH_ALGORITHM = "sha256"


# --------------------------------------------------------------------------- canonical encoding
def canonical_json(value: Any) -> bytes:
    """One byte-exact JSON encoding for everything that is hashed or signed."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_value(value: Any) -> str:
    return digest(canonical_json(value))


class ObjectRef(str):
    """A content address: ``sha256:<hex>``.  Plain ``str`` so it serializes as-is."""

    __slots__ = ()

    @classmethod
    def of_bytes(cls, data: bytes) -> "ObjectRef":
        return cls(f"{HASH_ALGORITHM}:{digest(data)}")

    @classmethod
    def of_value(cls, value: Any) -> "ObjectRef":
        return cls.of_bytes(canonical_json(value))

    @property
    def hex(self) -> str:
        return self.split(":", 1)[1]

    @property
    def prefix(self) -> str:
        """Two-hex-char shard prefix used for head sub-partitioning and directory fan-out."""
        return self.hex[:2]


# --------------------------------------------------------------------------- tasks
class BudgetClass(str, Enum):
    """Kill-deadline class a task kind declares.  The worker owns the deadline, not the task."""

    MICRO = "micro"        # <= 10 s   (hash, score, shard)
    SMALL = "small"        # <= 60 s   (one compile attempt, one parity check)
    MEDIUM = "medium"      # <= 10 min (a decompile chunk, a signature batch)
    LARGE = "large"        # <= 60 min (an analysis slice, a link) — fleet only by default
    UNBOUNDED = "unbounded"  # never offered; exists so a kind can be *refused*, not silently run


DEFAULT_DEADLINES_S: Mapping[BudgetClass, int] = {
    BudgetClass.MICRO: 10,
    BudgetClass.SMALL: 60,
    BudgetClass.MEDIUM: 600,
    BudgetClass.LARGE: 3600,
    BudgetClass.UNBOUNDED: 0,
}


@dataclass(frozen=True)
class TaskSpec:
    """A unit of work.  Immutable; its identity is a pure function of its content and the basis."""

    kind: str
    kind_version: int
    inputs: Mapping[str, ObjectRef]      # name -> content address of an input object
    params: Mapping[str, Any]            # canonical-JSON-able parameters
    basis_hash: str                      # determinism basis under which the result is valid
    capabilities: Sequence[str] = ()     # canary-proven capabilities a node needs, e.g. "toolchain:<hash>"
    budget: BudgetClass = BudgetClass.SMALL
    partition: str = ""                  # lane x subject partition key (empty = kind name)

    @property
    def task_id(self) -> str:
        return digest_value({
            "kind": self.kind,
            "kind_version": self.kind_version,
            "inputs": {k: str(v) for k, v in sorted(self.inputs.items())},
            "params": self.params,
            "basis_hash": self.basis_hash,
        })

    @property
    def partition_key(self) -> str:
        return self.partition or self.kind

    def to_record(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "kind_version": self.kind_version,
            "inputs": {k: str(v) for k, v in sorted(self.inputs.items())},
            "params": self.params,
            "basis_hash": self.basis_hash,
            "capabilities": list(self.capabilities),
            "budget": self.budget.value,
            "partition": self.partition_key,
        }

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> "TaskSpec":
        return cls(
            kind=rec["kind"], kind_version=int(rec["kind_version"]),
            inputs={k: ObjectRef(v) for k, v in rec.get("inputs", {}).items()},
            params=dict(rec.get("params", {})), basis_hash=rec["basis_hash"],
            capabilities=tuple(rec.get("capabilities", ())),
            budget=BudgetClass(rec.get("budget", BudgetClass.SMALL.value)),
            partition=rec.get("partition", ""),
        )


class ResultStatus(str, Enum):
    OK = "ok"                # a value was produced (still a proposal until verified)
    REFUSED = "refused"      # the kind refused deterministically (named reason, ordered candidates allowed)
    TIMEOUT = "timeout"      # killed at the budget deadline by the worker
    ERROR = "error"          # the kind raised; stderr digest recorded, never the text
    POISON = "poison"        # repeated timeouts/errors across independent nodes; not re-offered


@dataclass(frozen=True)
class TaskResult:
    """What a node claims for a task.  Stored at ``objects/results/<task_id>/<producer_key>``."""

    task_id: str
    status: ResultStatus
    outputs: Mapping[str, ObjectRef]     # name -> content address of a produced object
    producer_key: str                    # public key id of the node that produced it
    basis_hash: str
    elapsed_s: float
    reason: str = ""                     # refusal/error class, never free text with secrets or slugs
    candidates: Sequence[Mapping[str, Any]] = ()   # ordered alternatives when the kind cannot decide
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "status": self.status.value,
            "outputs": {k: str(v) for k, v in sorted(self.outputs.items())},
            "producer_key": self.producer_key, "basis_hash": self.basis_hash,
            "elapsed_s": round(float(self.elapsed_s), 3), "reason": self.reason,
            "candidates": list(self.candidates), "metrics": dict(self.metrics),
        }


class VerificationOutcome(str, Enum):
    VERIFIED = "verified"     # independent check passed; the result enters the verified stream
    REFUTED = "refuted"       # check failed; producer key is penalised, task re-offered
    UNVERIFIABLE = "unverifiable"  # no verifier capability available yet; stays a proposal


@dataclass(frozen=True)
class Verification:
    task_id: str
    result_ref: ObjectRef
    outcome: VerificationOutcome
    verifier_key: str
    method: str                          # "hash-lookup" | "recompute" | "parity" | ...
    evidence: Mapping[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- task kinds
@runtime_checkable
class TaskKind(Protocol):
    """A kind of work.  Pure: same inputs + basis -> same outputs, or a deterministic refusal."""

    name: str
    version: int
    budget: BudgetClass
    capabilities: Sequence[str]

    def run(self, spec: TaskSpec, objects: "ObjectStore", scratch: str) -> TaskResult: ...

    def verify(self, spec: TaskSpec, result: TaskResult, objects: "ObjectStore", scratch: str) -> Verification: ...


class Registry:
    """A named registry with a stable, sorted view — every extension point has one."""

    def __init__(self, what: str) -> None:
        self.what = what
        self._items: dict[str, Any] = {}

    def register(self, name: str, item: Any, *, replace: bool = False) -> Any:
        if name in self._items and not replace:
            raise ValueError(f"{self.what} {name!r} is already registered")
        self._items[name] = item
        return item

    def get(self, name: str) -> Any:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"no {self.what} named {name!r}; known: {sorted(self._items)}") from None

    def names(self) -> list[str]:
        return sorted(self._items)

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def items(self) -> Iterator[tuple[str, Any]]:
        return iter(sorted(self._items.items()))


TASK_KINDS = Registry("task kind")
OBJECT_STORES = Registry("object store adapter")
LOG_STORES = Registry("log adapter")
HEAD_STORES = Registry("head store adapter")
SIGNERS = Registry("signer")
CANARIES = Registry("capability canary")
VERIFIERS = Registry("verification method")
APPLIERS = Registry("view applier")
PROVIDERS = Registry("fleet provider adapter")
TRANSPORTS = Registry("transport adapter")


def task_kind(cls: type) -> type:
    """Class decorator: register a TaskKind by its ``name``."""
    TASK_KINDS.register(cls.name, cls)
    return cls


# --------------------------------------------------------------------------- object store
@runtime_checkable
class ObjectStore(Protocol):
    """Content-addressed, write-once, immutable blobs.  ``put`` of an existing ref is a no-op."""

    name: str

    def put(self, data: bytes) -> ObjectRef: ...
    def get(self, ref: ObjectRef) -> bytes: ...
    def exists(self, ref: ObjectRef) -> bool: ...
    def list(self, prefix: str = "") -> Iterator[ObjectRef]: ...
    def size(self, ref: ObjectRef) -> int: ...

    # named, mutable pointers *into* the immutable space (results index, heads, manifests)
    def put_named(self, name: str, data: bytes) -> None: ...
    def get_named(self, name: str) -> bytes | None: ...


# --------------------------------------------------------------------------- log
class RecordType(str, Enum):
    TASK = "task"              # a TaskSpec was published
    INTENT = "intent"          # advisory lease: key intends to run task_id until ttl
    RESULT = "result"          # a proposal exists at result_ref
    VERIFIED = "verified"      # a Verification with outcome=verified
    REFUTED = "refuted"
    POISON = "poison"
    CHECKPOINT = "checkpoint"  # compaction snapshot: everything before this record is summarised
    NOTE = "note"              # free-form, never load-bearing


@dataclass(frozen=True)
class Record:
    """One hash-chained, signed log entry.  ``prev`` links the chain within a partition."""

    partition: str
    seq: int
    type: RecordType
    body: Mapping[str, Any]
    prev: str                     # digest of the previous record in this partition ("" for the first)
    signer_key: str
    signature: str
    basis_hash: str = ""

    def digest(self) -> str:
        return digest_value(self.to_record(include_signature=False))

    def to_record(self, *, include_signature: bool = True) -> dict[str, Any]:
        rec = {
            "schema": GRID_SCHEMA_VERSION, "partition": self.partition, "seq": self.seq,
            "type": self.type.value, "body": self.body, "prev": self.prev,
            "signer_key": self.signer_key, "basis_hash": self.basis_hash,
        }
        if include_signature:
            rec["signature"] = self.signature
        return rec


@runtime_checkable
class Signer(Protocol):
    """Signs canonical bytes.  ``NullSigner`` (hash-chain only) must exist so a laptop grid needs no keys."""

    key_id: str

    def sign(self, data: bytes) -> str: ...
    def verify(self, key_id: str, data: bytes, signature: str) -> bool: ...


@runtime_checkable
class LogStore(Protocol):
    """Per-partition append-only records.  Appends are batched; ordering within a partition is total."""

    name: str

    def append(self, records: Sequence[Record]) -> None: ...
    def read(self, partition: str, since_seq: int = 0) -> Iterator[Record]: ...
    def partitions(self) -> Iterator[str]: ...
    def last_seq(self, partition: str) -> int: ...


@runtime_checkable
class HeadStore(Protocol):
    """Compare-and-swap head pointer per partition (sub-partitioned by task-id prefix when hot)."""

    name: str

    def get(self, partition: str) -> tuple[int, str]: ...            # (seq, digest of the last record)
    def cas(self, partition: str, expected: tuple[int, str], new: tuple[int, str]) -> bool: ...


@dataclass(frozen=True)
class Frontier:
    """What may be worked on now.  A pure function of (log, objects, now); never persisted as state."""

    ready: Sequence[TaskSpec]          # published, no verified result, no live intent, under the proposal cap
    awaiting_verification: Sequence[str]   # task_ids with proposals and no verification
    poisoned: Sequence[str]
    done: Sequence[str]


# --------------------------------------------------------------------------- worker side
@runtime_checkable
class Canary(Protocol):
    """Proves a capability by doing a fixed piece of work whose result hash is pinned."""

    capability: str

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]: ...


@dataclass(frozen=True)
class NodeIdentity:
    key_id: str
    capabilities: Sequence[str]
    invite_lineage: Sequence[str]        # chain of invite key ids; independence = disjoint lineage
    role: str = "donor"                  # "donor" | "fleet" | "operator" — affects which objects are mirrored, nothing else


@runtime_checkable
class Transport(Protocol):
    """How a node reaches objects/log/heads: local, HTTP(S) outbound-only, static mirror, peer."""

    name: str

    def objects(self) -> ObjectStore: ...
    def log(self) -> LogStore: ...
    def heads(self) -> HeadStore: ...


@runtime_checkable
class Applier(Protocol):
    """Replays the verified stream of one partition into a materialized view (e.g. the SQLite store)."""

    name: str

    def apply(self, records: Iterable[Record], objects: ObjectStore) -> int: ...
    def position(self) -> Mapping[str, int]: ...


@runtime_checkable
class ProviderAdapter(Protocol):
    """A fleet provider: renders join user-data and creates/destroys nodes.  ``manual`` must exist."""

    name: str

    def up(self, count: int, user_data: str, labels: Mapping[str, str]) -> Sequence[str]: ...
    def down(self, node_ids: Sequence[str]) -> None: ...
    def status(self) -> Sequence[Mapping[str, Any]]: ...


# --------------------------------------------------------------------------- errors
class GridError(Exception):
    """Base: every grid error names a class the CLI maps to an exit code; never a bare traceback."""

    exit_code = 2


class NotConfigured(GridError):
    """A declared adapter exists but is not usable here; the message names what would make it so."""


class AlreadyOwned(GridError):
    """An exclusive resource (socket, lock) is held by a live owner: attach, never restart."""

    exit_code = 3


class Refused(GridError):
    """A deterministic refusal with a named reason; candidates may be attached."""

    def __init__(self, reason: str, candidates: Sequence[Mapping[str, Any]] = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.candidates = tuple(candidates)


class Deadline(GridError):
    """A task exceeded its budget; the worker killed it and recorded a TIMEOUT."""

    exit_code = 4


__all__ = [name for name in dir() if not name.startswith("_")]
