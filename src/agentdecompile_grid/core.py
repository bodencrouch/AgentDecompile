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
* ``task_id = sha256(canonical(kind, kind_version, input hashes, params, basis_projection))`` where
  ``basis_projection`` is the slice of the determinism basis the *kind* declares it depends on
  (``TaskKind.basis_fields``, vocabulary ``BASIS_FIELDS``): an identical-basis re-run is a cache
  hit, a change to a basis field re-keys only the kinds that declare that field, and the full
  ``basis_hash`` still travels on every spec and record for audit (design §2.8: never redo
  completed work);
* every layer is an extension point with a registry and at least one working implementation
  (speculative generality is a goal here, not a smell).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol, Sequence, runtime_checkable

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


# --------------------------------------------------------------------------- determinism basis
BASIS_FIELDS: tuple[str, ...] = (
    "basis_version",
    "analyzer.version",
    "analyzer.options_hash",
    "analyzer.timeout_policy",
    "analyzer.loader_revision",
    "analyzer.compiler_spec_ids",
    "analyzer.processor_spec_hash",
    "algorithm_version",
    "masking_rule_version",
    "threshold_params.*",
    "seeds.*",
    "toolchain_identity_hash",
    "data_packs",
    "data_packs_root_declared",
    "filler_set",
    "decoder",
    "external_channels.*",
    "corpus_manifest_hash",
)
"""The vocabulary of determinism-basis field paths a task kind may declare in ``basis_fields``.

This tuple mirrors the *shape* of the corpus package's ``determinism_basis.package_basis`` object
(dotted paths into that mapping; ``<name>.*`` names a whole sub-mapping) WITHOUT importing it: the
grid never imports the recovery pipeline (import direction is recovery -> grid only), so the
vocabulary is declared once here and the pipeline's lanes declare their slices in this spelling.
A field that the pipeline lists as pending is still a legal name here; projecting it from a basis
that lacks it is a named ``Refused``, never a silent empty slot.
"""

BASIS_WILDCARD = "*"


def basis_field_known(path: str, vocabulary: Sequence[str] = BASIS_FIELDS) -> bool:
    """True when ``path`` is in the vocabulary or sits under one of its ``<name>.*`` entries."""
    if path in vocabulary:
        return True
    for entry in vocabulary:
        if entry.endswith("." + BASIS_WILDCARD) and path.startswith(entry[:-1]) and len(path) > len(entry) - 1:
            return True
    return False


def _basis_lookup(basis: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    parts = path.split(".")
    if parts and parts[-1] == BASIS_WILDCARD:
        parts = parts[:-1]
        whole = True
    else:
        whole = False
    node: Any = basis
    for part in parts:
        if not isinstance(node, Mapping) or part not in node:
            return False, None
        node = node[part]
    if whole and not isinstance(node, Mapping):
        return False, None
    return True, node


def hashed_basis_projection(basis: Mapping[str, Any], fields: Sequence[str], *, kind: str = "") -> dict[str, Any]:
    """The second projection style: like ``project_basis`` but every ``<name>.*`` sub-mapping is
    replaced by its digest, so a kind that depends on a large table keeps its ids short and its
    TASK bodies small (the full basis is still reachable through ``basis_hash``)."""
    out = project_basis(basis, fields, kind=kind)
    for path, value in list(out.items()):
        if path.endswith("." + BASIS_WILDCARD):
            out[path] = digest_value(value)
    return out


def project_basis(basis: Mapping[str, Any], fields: Sequence[str], *, kind: str = "") -> dict[str, Any]:
    """The default ``TaskKind.basis_projection``: pick ``fields`` (dotted paths, ``x.*`` = the whole
    sub-mapping) out of a full basis mapping into a flat ``{path: value}`` dict, keys sorted.
    A path absent from the basis is ``Refused("basis projection: <path> absent for kind <name>")``;
    an empty ``fields`` is the content-only projection ``{}``."""
    if not isinstance(basis, Mapping):
        raise Refused(f"basis projection: basis must be a mapping for kind {kind or '?'}, got {type(basis).__name__}")
    out: dict[str, Any] = {}
    for path in sorted(set(fields)):
        present, value = _basis_lookup(basis, path)
        if not present:
            raise Refused(f"basis projection: {path} absent for kind {kind or '?'}")
        out[path] = value
    return out


BASIS_PROJECTIONS: dict[str, Callable[..., dict[str, Any]]] = {"plain": project_basis, "hashed": hashed_basis_projection}
"""Projection styles a kind may name in ``basis_projection_style`` (both working; ``plain`` is the default)."""


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
    basis_hash: str                      # full determinism basis under which the result is valid (audit only)
    capabilities: Sequence[str] = ()     # canary-proven capabilities a node needs, e.g. "toolchain:<hash>"
    budget: BudgetClass = BudgetClass.SMALL
    partition: str = ""                  # lane x subject partition key (empty = kind name)
    basis_projection: Mapping[str, Any] = field(default_factory=dict)   # {basis path: value} the kind declares (in the id)

    @property
    def task_id(self) -> str:
        """Content plus the kind's basis *projection*; ``basis_hash`` is deliberately not in here
        (design §2.8: a basis change re-keys only the kinds whose declared fields changed)."""
        return digest_value({
            "kind": self.kind,
            "kind_version": self.kind_version,
            "inputs": {k: str(v) for k, v in sorted(self.inputs.items())},
            "params": self.params,
            "basis_projection": dict(sorted(self.basis_projection.items())),
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
            "basis_projection": dict(sorted(self.basis_projection.items())),
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
            basis_projection=dict(rec.get("basis_projection", {})),
        )

    @classmethod
    def from_basis(cls, kind: "TaskKind | type", inputs: Mapping[str, ObjectRef], params: Mapping[str, Any],
                   basis: Mapping[str, Any], *, capabilities: Sequence[str] | None = None,
                   budget: "BudgetClass | str | None" = None, partition: str = "") -> "TaskSpec":
        """A spec whose ``basis_hash`` is the digest of the whole ``basis`` and whose
        ``basis_projection`` is the kind's declared slice of it (``kind_basis_projection``).
        ``tasks.spec.spec_from_basis`` is the canonicalising builder; this is the raw one."""
        projection = kind_basis_projection(kind, basis)
        caps = tuple(sorted({*(getattr(kind, "capabilities", ()) or ()), *(capabilities or ())}))
        chosen = BudgetClass(budget) if budget is not None else BudgetClass(getattr(kind, "budget", BudgetClass.SMALL))
        return cls(kind=str(kind.name), kind_version=int(kind.version), inputs=dict(inputs), params=dict(params),
                   basis_hash=digest_value(basis), capabilities=caps, budget=chosen, partition=partition,
                   basis_projection=projection)


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
    basis_fields: tuple[str, ...]        # the BASIS_FIELDS paths this kind's output depends on; () = content-only
    basis_projection_style: str          # optional: a BASIS_PROJECTIONS name (plain | hashed); absent = plain

    def run(self, spec: TaskSpec, objects: "ObjectStore", scratch: str) -> TaskResult: ...

    def verify(self, spec: TaskSpec, result: TaskResult, objects: "ObjectStore", scratch: str) -> Verification: ...

    @classmethod
    def basis_projection(cls, basis: Mapping[str, Any]) -> dict[str, Any]:
        """Default: the ``basis_projection_style`` entry of ``BASIS_PROJECTIONS`` over ``basis_fields``.
        A kind may override this *classmethod* (kinds are registered as classes) as long as the keys
        stay exactly ``basis_fields``; ``kind_basis_projection`` checks that."""
        style = str(getattr(cls, "basis_projection_style", "plain") or "plain")
        return BASIS_PROJECTIONS[style](basis, tuple(cls.basis_fields), kind=str(cls.name))


def kind_basis_fields(kind: Any) -> tuple[str, ...]:
    """``kind.basis_fields`` as a tuple; ``Refused("basis-fields-undeclared:<kind>")`` when the kind
    does not declare it (every kind must; the registry refuses registration without it)."""
    declared = getattr(kind, "basis_fields", None)
    if declared is None or isinstance(declared, str):
        raise Refused(f"basis-fields-undeclared:{getattr(kind, 'name', type(kind).__name__)}")
    return tuple(str(p) for p in declared)


def kind_basis_projection(kind: Any, basis: Mapping[str, Any]) -> dict[str, Any]:
    """``kind.basis_projection(basis)`` when the kind defines one, else the default projection;
    the result's keys must equal ``kind.basis_fields`` or the projection is ``Refused`` by name."""
    import inspect

    fields = kind_basis_fields(kind)
    cls = kind if inspect.isclass(kind) else type(kind)
    static = inspect.getattr_static(cls, "basis_projection", None)
    if isinstance(static, (classmethod, staticmethod)):
        projection = cls.basis_projection(basis)            # a class-level override or the Protocol default
    elif static is not None and not inspect.isclass(kind):
        projection = kind.basis_projection(basis)           # an instance-level override on an instance
    elif static is not None:
        raise Refused(f"basis projection: kind {cls.__name__} overrides basis_projection as an instance method; declare it a classmethod")
    else:
        style = str(getattr(cls, "basis_projection_style", "plain") or "plain")
        if style not in BASIS_PROJECTIONS:
            raise Refused(f"basis projection: kind {kind.name} names unknown style {style!r}; known {sorted(BASIS_PROJECTIONS)}")
        projection = BASIS_PROJECTIONS[style](basis, fields, kind=str(kind.name))
    if set(projection) != set(fields):
        raise Refused(f"basis projection: kind {kind.name} declares {sorted(fields)} but projected {sorted(projection)}")
    return dict(sorted(projection.items()))


def check_basis_projection(kind: Any, spec: TaskSpec) -> None:
    """The shape check publish, execute, verify and consume share: the spec's projection keys must
    be exactly the kind's ``basis_fields`` (a full basis is not available at run time, so this is a
    shape check, not a re-projection; ``task_id`` binds the values).  Refused by name otherwise."""
    fields = kind_basis_fields(kind)
    carried = tuple(sorted(spec.basis_projection))
    if carried != tuple(sorted(set(fields))):
        raise Refused(f"basis-projection-mismatch:{kind.name}:declares {sorted(set(fields))} spec carries {list(carried)}")


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
SIGNING_BACKENDS = Registry("signing backend")     # ed25519 implementations: first importable wins (log.signing)
KEY_SOURCES = Registry("keyring key source")       # where a Keyring learns public keys (log.keys)
RECORD_FILTERS = Registry("frontier record filter")  # what the frontier ignores: revoked keys, rate limits (log.frontier)
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
    KEY_ANNOUNCE = "key-announce"  # a node publishes its public key (and the keys it supersedes) for offline verification
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
    """Signs canonical bytes.  One hierarchy for operator and node signers (``log.signing``):
    ``Ed25519Signer`` is the default whenever a signing backend imports, ``NullSigner`` (hash-chain
    only, no authorship) is the explicit fallback by name, ``HMACSigner`` the shared-secret one;
    ``HsmSigner`` and ``SshAgentSigner`` are declared slots.  ``key_id`` is ``<algorithm>:<hex sha256
    of the raw public key>`` so a ``Keyring`` can find the public key from a record alone."""

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
