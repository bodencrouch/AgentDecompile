"""agentdecompile_grid.config — ``GridConfig``: every knob of every layer, as data.

Configuration is data, never constants: each layer reads its numbers from here (the object
store its shard width and fsync policy, the worker its kill deadlines, the log its batch
size and backoff, the verifier its proposal cap).  The file is deliberately small and stable
because every other package under ``agentdecompile_grid`` imports it.

Precedence (lowest to highest)::

    dataclass defaults  <  TOML file  <  environment (``ADGRID_<SECTION>__<FIELD>``)

* The TOML file is ``load(path)``, else ``$ADGRID_CONFIG``, else ``<root>/config.toml`` when
  that file exists.  TOML sections mirror the nested dataclasses exactly: ``[objects]``,
  ``[objects.s3]``, ``[budgets]``, ``[tasks]`` ...
* Environment overrides name the field path with ``__`` between levels, upper-cased:
  ``ADGRID_OBJECTS__SHARD_WIDTH=3``, ``ADGRID_OBJECTS__S3__BUCKET=grid``,
  ``ADGRID_BUDGETS__PER_KIND_S='{"link": 7200}'`` (mappings are JSON, sequences are
  comma-separated).  ``ADGRID_HOME`` sets ``paths.root`` and ``ADGRID_CONFIG`` the file.
* ``describe(config)`` returns the dict the CLI prints: every field with its value, type,
  documentation and provenance (``default`` / ``file:<path>`` / ``env:<VAR>``).

Every field carries ``metadata={"doc": ...}``; ``describe()`` is generated from those docs so
the documentation cannot drift from the schema.

Acceptance tests (named here, landed in the verification phase):

* ``test_config_defaults_validate`` — ``GridConfig()`` validates and ``describe()`` lists every
  field with source ``default``.
* ``test_config_toml_then_env_precedence`` — a TOML value is overridden by the matching env var
  and the provenance says so.
* ``test_config_rejects_unknown_key_by_name`` — an unknown TOML key raises ``ConfigError``
  naming the key and the section.
* ``test_config_roundtrip_toml`` — ``load(write(to_toml(cfg)))`` equals ``cfg``.
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, MutableMapping

from .core import HASH_ALGORITHM, BudgetClass, GridError, NotConfigured

CONFIG_SCHEMA_VERSION = 1
ENV_PREFIX = "ADGRID_"
ENV_CONFIG_FILE = "ADGRID_CONFIG"
ENV_HOME = "ADGRID_HOME"
CONFIG_FILE_NAME = "config.toml"

FSYNC_POLICIES = ("none", "data", "full")
WRITE_ONCE_STRATEGIES = ("link", "replace")
WRITE_POLICIES = ("first", "all", "all-strict")
LAYER_FAILURE_POLICIES = ("record", "raise")
FLOAT_POLICIES = ("repr", "refuse")
PORTABILITY_POLICIES = ("strict", "off")
CAPTURE_POLICIES = ("digest", "object", "none")


class ConfigError(GridError):
    """A configuration value is unusable; the message names the field path and the rule."""


def _doc(text: str, **extra: Any) -> dict[str, Any]:
    meta = {"doc": text}
    meta.update(extra)
    return meta


# --------------------------------------------------------------------------- sections
@dataclass(frozen=True)
class PathsConfig:
    """Where the grid keeps its state.  Empty sub-paths resolve under ``root`` (``resolved()``)."""

    root: str = field(default="", metadata=_doc(
        "Grid home. Empty = $ADGRID_HOME, else $XDG_DATA_HOME/adgrid, else ~/.local/share/adgrid."))
    objects: str = field(default="", metadata=_doc("Local object store root. Empty = <root>/objects."))
    scratch: str = field(default="", metadata=_doc("Per-task scratch directories. Empty = <root>/scratch."))
    log: str = field(default="", metadata=_doc("Local log partitions. Empty = <root>/log."))
    heads: str = field(default="", metadata=_doc("Local head pointers. Empty = <root>/heads."))
    outbox: str = field(default="", metadata=_doc("Records and objects awaiting flush. Empty = <root>/outbox."))
    keys: str = field(default="", metadata=_doc("Node keys and invites. Empty = <root>/keys."))
    views: str = field(default="", metadata=_doc("Materialized views. Empty = <root>/views."))
    toolchains: str = field(default="", metadata=_doc("Unpacked toolchain objects. Empty = <root>/toolchains."))

    def resolved(self, env: Mapping[str, str] | None = None) -> "PathsConfig":
        env = os.environ if env is None else env
        root = self.root or env.get(ENV_HOME) or ""
        if not root:
            xdg = env.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
            root = os.path.join(xdg, "adgrid")
        root = os.path.abspath(os.path.expanduser(root))
        values: dict[str, str] = {"root": root}
        for f in fields(self):
            if f.name == "root":
                continue
            current = getattr(self, f.name)
            values[f.name] = os.path.abspath(os.path.expanduser(current)) if current else os.path.join(root, f.name)
        return PathsConfig(**values)


@dataclass(frozen=True)
class AdaptersConfig:
    """Which registered adapter each layer uses, by registry name."""

    objects: str = field(default="local", metadata=_doc(
        "Object store adapter (OBJECT_STORES): local | s3 | static-mirror | peer | layered."))
    log: str = field(default="local", metadata=_doc("Log adapter (LOG_STORES)."))
    heads: str = field(default="local", metadata=_doc("Head store adapter (HEAD_STORES)."))
    signer: str = field(default="null", metadata=_doc("Signer (SIGNERS); 'null' = hash chain only, no keys."))
    transport: str = field(default="local", metadata=_doc("Transport adapter (TRANSPORTS)."))
    provider: str = field(default="manual", metadata=_doc("Fleet provider adapter (PROVIDERS)."))


@dataclass(frozen=True)
class LocalStoreConfig:
    root: str = field(default="", metadata=_doc("Override of paths.objects for the local adapter. Empty = paths.objects."))


@dataclass(frozen=True)
class S3StoreConfig:
    bucket: str = field(default="", metadata=_doc("Bucket name. Required to use the s3 adapter."))
    prefix: str = field(default="", metadata=_doc("Key prefix inside the bucket (no leading slash)."))
    endpoint_url: str = field(default="", metadata=_doc("Custom endpoint for S3-compatible services. Empty = AWS."))
    region: str = field(default="", metadata=_doc("Region name. Empty = the SDK default chain."))
    profile: str = field(default="", metadata=_doc("Named credential profile. Empty = the SDK default chain."))
    presign_ttl_s: int = field(default=3600, metadata=_doc("Lifetime of presigned read/write URLs in seconds."))
    conditional_put: bool = field(default=True, metadata=_doc(
        "Send If-None-Match: * on PUT so an existing key is never overwritten (412 = no-op)."))


@dataclass(frozen=True)
class MirrorStoreConfig:
    base_url: str = field(default="", metadata=_doc("Read-only HTTP(S) mirror root serving objects/ named/ index/."))
    timeout_s: float = field(default=30.0, metadata=_doc("Per-request timeout in seconds."))
    retries: int = field(default=2, metadata=_doc("Retries on transient HTTP failures (5xx, connection errors)."))
    index_path: str = field(default="index", metadata=_doc(
        "Directory under base_url holding listing indexes (<shard>.txt, all.txt) published by write_mirror_index()."))


@dataclass(frozen=True)
class PeerStoreConfig:
    base_url: str = field(default="", metadata=_doc("Another node's read endpoint root (outbound-only HTTP)."))
    token_env: str = field(default="ADGRID_PEER_TOKEN", metadata=_doc(
        "Name of the environment variable holding the bearer token. Never the token itself."))
    timeout_s: float = field(default=30.0, metadata=_doc("Per-request timeout in seconds."))
    allow_put: bool = field(default=False, metadata=_doc(
        "Permit PUT to the peer's write endpoint. Off = the peer is read-only from here."))


@dataclass(frozen=True)
class LayeredStoreConfig:
    layers: tuple[str, ...] = field(default=("local",), metadata=_doc(
        "Adapter names in read order; the first is the cache and always receives writes first."))
    write_policy: str = field(default="all", metadata=_doc(
        "all = the first layer, then every other writable layer (read-only layers skipped, failures recorded "
        "for flush_pending); first = the first layer only (an outbox must propagate); all-strict = every layer must accept."))
    promote_on_read: bool = field(default=True, metadata=_doc(
        "Copy an object found in a later layer into the earlier writable layers (cache fill)."))
    named_authority: str = field(default="first", metadata=_doc(
        "Which layer answers get_named first: first | last | <index>. Others are fallbacks."))
    on_layer_failure: str = field(default="record", metadata=_doc(
        "When a later layer fails a write: record = keep it in the pending list for flush_pending(); raise = error."))


@dataclass(frozen=True)
class ObjectsConfig:
    """Content-addressed store behaviour shared by every adapter."""

    hash_algorithm: str = field(default=HASH_ALGORITHM, metadata=_doc(
        "Digest algorithm for object refs. core pins sha256; anything else is refused by name."))
    shard_width: int = field(default=2, metadata=_doc(
        "Hex characters per directory level under objects/ (0-4). Frozen per store in layout.json."))
    shard_depth: int = field(default=1, metadata=_doc("Directory levels of sharding (0-2). Frozen per store in layout.json."))
    fsync: str = field(default="data", metadata=_doc(
        "none = no fsync; data = fsync the object file; full = also fsync the directory entry."))
    write_once_strategy: str = field(default="link", metadata=_doc(
        "link = hard-link temp into place (EEXIST = already present, true write-once); "
        "replace = os.replace (last-writer-wins, for filesystems without hard links)."))
    verify_on_read: bool = field(default=True, metadata=_doc("Re-hash every object on get() and refuse a mismatch."))
    touch_on_read: bool = field(default=False, metadata=_doc(
        "Update the object's mtime on get() so eviction is LRU; off = eviction is FIFO by write time."))
    size_cap_bytes: int = field(default=0, metadata=_doc(
        "Local store size cap in bytes; 0 = unlimited. At the cap, GC runs; if it cannot free enough, put() raises StoreFull."))
    gc_policy: str = field(default="lru", metadata=_doc("Eviction policy (GC_POLICIES): lru | fifo | largest-first."))
    gc_low_water: float = field(default=0.9, metadata=_doc("GC frees until usage <= cap * gc_low_water."))
    gc_grace_s: int = field(default=300, metadata=_doc("Objects younger than this are never evicted."))
    gc_max_scan_bytes: int = field(default=1_048_576, metadata=_doc(
        "Largest referent document GC will parse when walking pins (bigger ones are leaves)."))
    gc_walk_depth: int = field(default=2, metadata=_doc(
        "Pin walk depth: 1 = named pointer referents; 2 = also the outputs of result records they point at."))
    local: LocalStoreConfig = field(default_factory=LocalStoreConfig, metadata=_doc("local adapter"))
    s3: S3StoreConfig = field(default_factory=S3StoreConfig, metadata=_doc("s3 adapter"))
    mirror: MirrorStoreConfig = field(default_factory=MirrorStoreConfig, metadata=_doc("static-mirror adapter"))
    peer: PeerStoreConfig = field(default_factory=PeerStoreConfig, metadata=_doc("peer adapter"))
    layered: LayeredStoreConfig = field(default_factory=LayeredStoreConfig, metadata=_doc("layered adapter"))


@dataclass(frozen=True)
class BudgetsConfig:
    """Kill deadlines per budget class; the worker enforces them, task kinds only declare a class."""

    micro_s: int = field(default=10, metadata=_doc("Deadline for BudgetClass.MICRO in seconds."))
    small_s: int = field(default=60, metadata=_doc("Deadline for BudgetClass.SMALL in seconds."))
    medium_s: int = field(default=600, metadata=_doc("Deadline for BudgetClass.MEDIUM in seconds."))
    large_s: int = field(default=3600, metadata=_doc("Deadline for BudgetClass.LARGE in seconds."))
    kill_grace_s: int = field(default=5, metadata=_doc("Seconds between SIGTERM and SIGKILL at the deadline."))
    allow_unbounded: bool = field(default=False, metadata=_doc(
        "Offer BudgetClass.UNBOUNDED kinds at all. Off = they are refused by name."))
    allow_large: bool = field(default=True, metadata=_doc("Offer BudgetClass.LARGE kinds on this node (fleet only by default)."))
    per_kind_s: Mapping[str, int] = field(default_factory=dict, metadata=_doc(
        "Per-kind deadline overrides in seconds, keyed by kind name; recorded in the basis timeout policy."))
    verify_class: str = field(default="small", metadata=_doc("Budget class used for verification tasks."))


@dataclass(frozen=True)
class TasksConfig:
    """Task-kind discovery, canonical parameters and the proposal cap."""

    proposal_cap: int = field(default=4, metadata=_doc(
        "Maximum proposals per task_id; a further result is refused by name (design 2.6)."))
    entry_point_group: str = field(default="agentdecompile_grid.task_kinds", metadata=_doc(
        "importlib.metadata entry-point group scanned for task kinds."))
    auto_discover: bool = field(default=True, metadata=_doc("Scan entry points on first registry use."))
    float_policy: str = field(default="repr", metadata=_doc(
        "repr = floats become their repr string in params (no float tokens in canonical JSON); refuse = floats are an error."))
    portability: str = field(default="strict", metadata=_doc(
        "strict = string params that look like absolute paths are refused; off = allowed."))
    max_param_bytes: int = field(default=65_536, metadata=_doc("Largest canonical params document accepted."))
    max_candidates: int = field(default=16, metadata=_doc("Largest ordered candidate list a refusal may carry."))
    env_allowlist: tuple[str, ...] = field(default=(), metadata=_doc(
        "Host environment variables subprocess-verb passes through unless the spec narrows them."))
    capture_stdout: str = field(default="digest", metadata=_doc(
        "subprocess-verb default for stdout: digest | object | none."))
    capture_stderr: str = field(default="digest", metadata=_doc(
        "subprocess-verb default for stderr: digest | object | none (never the text in a log record)."))


@dataclass(frozen=True)
class LogConfig:
    """Append batching, CAS backoff and checkpoint cadence (design 2.2)."""

    flush_interval_s: float = field(default=5.0, metadata=_doc("Outbox flush interval in seconds."))
    batch_max: int = field(default=64, metadata=_doc("Records per batch append."))
    backoff_base_ms: int = field(default=100, metadata=_doc("Full-jitter exponential backoff base on CAS failure."))
    backoff_cap_ms: int = field(default=5000, metadata=_doc("Backoff cap."))
    rotate_after_failures: int = field(default=8, metadata=_doc(
        "Consecutive CAS failures on one head before the writer rotates to another partition."))
    checkpoint_index_max_age_s: int = field(default=60, metadata=_doc(
        "A checkpoint-index older than this is rewritten by whichever node appended last."))
    rate_limit_per_minute: int = field(default=64, metadata=_doc("Records accepted per key per minute."))
    partition_prefix_bits: int = field(default=0, metadata=_doc(
        "Task-id prefix bits for head sub-partitioning; 0 = one head per partition."))


@dataclass(frozen=True)
class WorkerConfig:
    """Donor knobs and the poison rule (design 2.7)."""

    cores: int = field(default=0, metadata=_doc("Concurrent tasks; 0 = auto (os.cpu_count())."))
    idle_only: bool = field(default=False, metadata=_doc("Only take work when the machine is idle."))
    poison_threshold: int = field(default=3, metadata=_doc(
        "Timeouts/errors from independent keys before a task is poisoned and not re-offered."))
    intent_ttl_s: int = field(default=120, metadata=_doc("Advisory lease lifetime in seconds."))
    key_ttl_days: int = field(default=7, metadata=_doc("Node key lifetime; renewal needs a canary re-run."))
    keep_scratch: bool = field(default=False, metadata=_doc("Keep per-task scratch directories after completion."))
    attach_url: str = field(default="http://127.0.0.1:7473/adgrid", metadata=_doc(
        "Well-known local agent URL; join attaches here first and never starts a second owner."))


@dataclass(frozen=True)
class GridConfig:
    """The whole configuration.  Immutable; derive variants with ``dataclasses.replace``."""

    schema: int = field(default=CONFIG_SCHEMA_VERSION, metadata=_doc("Config schema version."))
    paths: PathsConfig = field(default_factory=PathsConfig, metadata=_doc("paths"))
    adapters: AdaptersConfig = field(default_factory=AdaptersConfig, metadata=_doc("adapters"))
    objects: ObjectsConfig = field(default_factory=ObjectsConfig, metadata=_doc("objects"))
    budgets: BudgetsConfig = field(default_factory=BudgetsConfig, metadata=_doc("budgets"))
    tasks: TasksConfig = field(default_factory=TasksConfig, metadata=_doc("tasks"))
    log: LogConfig = field(default_factory=LogConfig, metadata=_doc("log"))
    worker: WorkerConfig = field(default_factory=WorkerConfig, metadata=_doc("worker"))
    sources: Mapping[str, str] = field(default_factory=dict, compare=False, repr=False,
                                       metadata={"doc": "provenance per field path", "internal": True})

    # ---- derived views -------------------------------------------------------------------
    def deadline_s(self, budget: BudgetClass, kind: str = "") -> int:
        """Seconds a task of ``budget`` (or the override for ``kind``) may run before the worker kills it."""
        if kind and kind in self.budgets.per_kind_s:
            return int(self.budgets.per_kind_s[kind])
        table = {
            BudgetClass.MICRO: self.budgets.micro_s, BudgetClass.SMALL: self.budgets.small_s,
            BudgetClass.MEDIUM: self.budgets.medium_s, BudgetClass.LARGE: self.budgets.large_s,
            BudgetClass.UNBOUNDED: 0,
        }
        return int(table[BudgetClass(budget)])

    def resolved_paths(self, env: Mapping[str, str] | None = None) -> PathsConfig:
        return self.paths.resolved(env)

    def validate(self) -> "GridConfig":
        """Raise ``ConfigError`` naming the first unusable field; return self when everything is usable."""
        o, b, t, lg, w = self.objects, self.budgets, self.tasks, self.log, self.worker
        _require(o.hash_algorithm == HASH_ALGORITHM, "objects.hash_algorithm",
                 f"core pins {HASH_ALGORITHM!r}; got {o.hash_algorithm!r}")
        _require(0 <= o.shard_width <= 4, "objects.shard_width", "must be 0..4")
        _require(0 <= o.shard_depth <= 2, "objects.shard_depth", "must be 0..2")
        _require(o.shard_width * o.shard_depth <= 8, "objects.shard_depth", "width*depth must be <= 8")
        _require(o.fsync in FSYNC_POLICIES, "objects.fsync", f"must be one of {FSYNC_POLICIES}")
        _require(o.write_once_strategy in WRITE_ONCE_STRATEGIES, "objects.write_once_strategy",
                 f"must be one of {WRITE_ONCE_STRATEGIES}")
        _require(o.size_cap_bytes >= 0, "objects.size_cap_bytes", "must be >= 0 (0 = unlimited)")
        _require(0 < o.gc_low_water <= 1.0, "objects.gc_low_water", "must be in (0, 1]")
        _require(o.gc_grace_s >= 0, "objects.gc_grace_s", "must be >= 0")
        _require(o.gc_walk_depth in (0, 1, 2), "objects.gc_walk_depth", "must be 0, 1 or 2")
        _require(o.layered.write_policy in WRITE_POLICIES, "objects.layered.write_policy", f"must be one of {WRITE_POLICIES}")
        _require(o.layered.on_layer_failure in LAYER_FAILURE_POLICIES, "objects.layered.on_layer_failure",
                 f"must be one of {LAYER_FAILURE_POLICIES}")
        _require(len(o.layered.layers) >= 1, "objects.layered.layers", "needs at least one layer")
        _require(o.layered.named_authority in ("first", "last") or o.layered.named_authority.isdigit(),
                 "objects.layered.named_authority", "must be first | last | <index>")
        _require(o.s3.presign_ttl_s > 0, "objects.s3.presign_ttl_s", "must be > 0")
        for name in ("micro_s", "small_s", "medium_s", "large_s"):
            _require(getattr(b, name) > 0, f"budgets.{name}", "must be > 0")
        _require(b.micro_s <= b.small_s <= b.medium_s <= b.large_s, "budgets", "classes must be non-decreasing")
        _require(b.kill_grace_s >= 0, "budgets.kill_grace_s", "must be >= 0")
        for kind, secs in b.per_kind_s.items():
            _require(isinstance(secs, int) and secs > 0, f"budgets.per_kind_s.{kind}", "must be a positive int")
        _require(b.verify_class in {c.value for c in BudgetClass} - {BudgetClass.UNBOUNDED.value},
                 "budgets.verify_class", "must be a bounded budget class")
        _require(t.proposal_cap >= 1, "tasks.proposal_cap", "must be >= 1")
        _require(t.float_policy in FLOAT_POLICIES, "tasks.float_policy", f"must be one of {FLOAT_POLICIES}")
        _require(t.portability in PORTABILITY_POLICIES, "tasks.portability", f"must be one of {PORTABILITY_POLICIES}")
        _require(t.capture_stdout in CAPTURE_POLICIES, "tasks.capture_stdout", f"must be one of {CAPTURE_POLICIES}")
        _require(t.capture_stderr in CAPTURE_POLICIES, "tasks.capture_stderr", f"must be one of {CAPTURE_POLICIES}")
        _require(t.max_param_bytes > 0, "tasks.max_param_bytes", "must be > 0")
        _require(lg.batch_max >= 1, "log.batch_max", "must be >= 1")
        _require(lg.backoff_base_ms > 0 and lg.backoff_cap_ms >= lg.backoff_base_ms, "log.backoff_cap_ms",
                 "must be >= backoff_base_ms > 0")
        _require(0 <= lg.partition_prefix_bits <= 16, "log.partition_prefix_bits", "must be 0..16")
        _require(w.cores >= 0, "worker.cores", "must be >= 0 (0 = auto)")
        _require(w.poison_threshold >= 1, "worker.poison_threshold", "must be >= 1")
        return self


def _require(ok: bool, path: str, rule: str) -> None:
    if not ok:
        raise ConfigError(f"config {path}: {rule}")


# --------------------------------------------------------------------------- dict <-> dataclass
def to_dict(cfg: Any) -> dict[str, Any]:
    """Nested plain dict (tuples become lists), omitting internal fields."""
    out: dict[str, Any] = {}
    for f in fields(cfg):
        if f.metadata.get("internal"):
            continue
        value = getattr(cfg, f.name)
        if is_dataclass(value):
            out[f.name] = to_dict(value)
        elif isinstance(value, tuple):
            out[f.name] = list(value)
        elif isinstance(value, Mapping):
            out[f.name] = dict(value)
        else:
            out[f.name] = value
    return out


def from_dict(data: Mapping[str, Any], *, sources: Mapping[str, str] | None = None) -> GridConfig:
    """Build a validated ``GridConfig`` from a nested mapping; unknown keys are refused by name."""
    cfg = _build(GridConfig, data, "")
    if sources is not None:
        cfg = dataclasses.replace(cfg, sources=dict(sources))
    return cfg.validate()


def _build(cls: type, data: Mapping[str, Any], path: str) -> Any:
    known = {f.name: f for f in fields(cls) if not f.metadata.get("internal")}
    unknown = sorted(set(data) - set(known))
    if unknown:
        where = path or "top level"
        raise ConfigError(f"config {where}: unknown key(s) {unknown}; known: {sorted(known)}")
    kwargs: dict[str, Any] = {}
    for name, f in known.items():
        if name not in data:
            continue
        sub = f"{path}.{name}" if path else name
        kwargs[name] = _coerce(f, data[name], sub)
    return cls(**kwargs)


def _field_kind(f: dataclasses.Field) -> str:
    """One of: dataclass | bool | int | float | str | tuple | mapping."""
    default = f.default if f.default is not dataclasses.MISSING else (
        f.default_factory() if f.default_factory is not dataclasses.MISSING else None)  # type: ignore[misc]
    if is_dataclass(default):
        return "dataclass"
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, float):
        return "float"
    if isinstance(default, tuple):
        return "tuple"
    if isinstance(default, Mapping):
        return "mapping"
    return "str"


def _coerce(f: dataclasses.Field, value: Any, path: str) -> Any:
    kind = _field_kind(f)
    try:
        if kind == "dataclass":
            cls = type(f.default_factory())  # type: ignore[misc]
            if is_dataclass(value):
                return value
            if not isinstance(value, Mapping):
                raise ConfigError(f"config {path}: expected a table")
            return _build(cls, value, path)
        if kind == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                low = value.strip().lower()
                if low in ("1", "true", "yes", "on"):
                    return True
                if low in ("0", "false", "no", "off", ""):
                    return False
            raise ConfigError(f"config {path}: expected a boolean, got {value!r}")
        if kind == "int":
            if isinstance(value, bool):
                raise ConfigError(f"config {path}: expected an integer, got a boolean")
            return int(value)
        if kind == "float":
            return float(value)
        if kind == "tuple":
            if isinstance(value, str):
                return tuple(part.strip() for part in value.split(",") if part.strip())
            if isinstance(value, (list, tuple)):
                return tuple(str(v) for v in value)
            raise ConfigError(f"config {path}: expected a list of strings, got {value!r}")
        if kind == "mapping":
            if isinstance(value, str):
                value = json.loads(value) if value.strip() else {}
            if not isinstance(value, Mapping):
                raise ConfigError(f"config {path}: expected a table or JSON object")
            return dict(value)
        if value is None:
            return ""
        if isinstance(value, (list, tuple, Mapping)):
            raise ConfigError(f"config {path}: expected a string, got {type(value).__name__}")
        return str(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"config {path}: {exc}") from None


# --------------------------------------------------------------------------- loading
def _read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # Python >= 3.11
    except ImportError:  # pragma: no cover - depends on the interpreter
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            raise NotConfigured(
                f"reading {path} needs Python >= 3.11 (tomllib) or the 'tomli' package on older interpreters"
            ) from None
    with open(path, "rb") as fh:
        try:
            return tomllib.load(fh)
        except (ValueError, OSError) as exc:  # tomllib.TOMLDecodeError subclasses ValueError
            raise ConfigError(f"config file {path}: {exc}") from None


def _env_overrides(env: Mapping[str, str]) -> dict[str, Any]:
    """``ADGRID_A__B=value`` -> ``{"a": {"b": "value"}}`` (strings; coerced later by field type)."""
    tree: dict[str, Any] = {}
    reserved = {ENV_CONFIG_FILE, ENV_HOME}
    for key in sorted(env):
        if not key.startswith(ENV_PREFIX) or key in reserved:
            continue
        parts = [p.lower() for p in key[len(ENV_PREFIX):].split("__") if p]
        if len(parts) < 2:
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ConfigError(f"env {key}: {part} is a value, not a section")
        node[parts[-1]] = env[key]
    return tree


def _merge(base: MutableMapping[str, Any], over: Mapping[str, Any], path: str, source: str,
           sources: dict[str, str]) -> None:
    for key, value in over.items():
        sub = f"{path}.{key}" if path else key
        if isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            _merge(base[key], value, sub, source, sources)
        elif isinstance(value, Mapping) and key not in base:
            base[key] = {}
            _merge(base[key], value, sub, source, sources)
        else:
            base[key] = value
            sources[sub] = source


def _leaf_paths(cls: type, prefix: str = "") -> Iterator[str]:
    for f in fields(cls):
        if f.metadata.get("internal"):
            continue
        sub = f"{prefix}.{f.name}" if prefix else f.name
        if _field_kind(f) == "dataclass":
            yield from _leaf_paths(type(f.default_factory()), sub)  # type: ignore[misc]
        else:
            yield sub


def config_file_path(path: str | os.PathLike[str] | None = None, env: Mapping[str, str] | None = None) -> Path | None:
    """The TOML file ``load`` would read: explicit path, else $ADGRID_CONFIG, else <root>/config.toml if present."""
    env = os.environ if env is None else env
    if path is not None:
        return Path(path)
    if env.get(ENV_CONFIG_FILE):
        return Path(env[ENV_CONFIG_FILE])
    candidate = Path(PathsConfig().resolved(env).root) / CONFIG_FILE_NAME
    return candidate if candidate.is_file() else None


def load(path: str | os.PathLike[str] | None = None, env: Mapping[str, str] | None = None) -> GridConfig:
    """Defaults, then the TOML file, then ``ADGRID_*`` environment overrides; validated."""
    env = os.environ if env is None else env
    data: dict[str, Any] = {}
    sources: dict[str, str] = {p: "default" for p in _leaf_paths(GridConfig)}
    file_path = config_file_path(path, env)
    if file_path is not None:
        if not file_path.is_file():
            raise ConfigError(f"config file {file_path}: not found")
        _merge(data, _read_toml(file_path), "", f"file:{file_path}", sources)
    overrides = _env_overrides(env)
    if env.get(ENV_HOME):
        overrides.setdefault("paths", {}).setdefault("root", env[ENV_HOME])
    if overrides:
        _merge(data, overrides, "", "env", sources)
        for key in env:
            if key.startswith(ENV_PREFIX) and "__" in key:
                sources[".".join(p.lower() for p in key[len(ENV_PREFIX):].split("__") if p)] = f"env:{key}"
        if env.get(ENV_HOME):
            sources["paths.root"] = f"env:{ENV_HOME}"
    return from_dict(data, sources=sources)


def default() -> GridConfig:
    """The built-in defaults, validated, with no file or environment applied."""
    return GridConfig(sources={p: "default" for p in _leaf_paths(GridConfig)}).validate()


# --------------------------------------------------------------------------- describe / emit
def describe(cfg: GridConfig, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The dict the CLI prints: every field with value, type, doc and provenance, plus resolved paths."""
    entries: dict[str, dict[str, Any]] = {}

    def walk(obj: Any, prefix: str) -> None:
        for f in fields(obj):
            if f.metadata.get("internal"):
                continue
            sub = f"{prefix}.{f.name}" if prefix else f.name
            value = getattr(obj, f.name)
            kind = _field_kind(f)
            if kind == "dataclass":
                walk(value, sub)
                continue
            entries[sub] = {
                "value": list(value) if isinstance(value, tuple) else (dict(value) if isinstance(value, Mapping) else value),
                "type": kind,
                "doc": f.metadata.get("doc", ""),
                "source": cfg.sources.get(sub, "default"),
            }

    walk(cfg, "")
    return {
        "schema": cfg.schema,
        "config_file": str(config_file_path(None, env) or ""),
        "resolved_paths": to_dict(cfg.resolved_paths(env)),
        "fields": entries,
    }


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{json.dumps(str(k))} = {_toml_scalar(v)}" for k, v in sorted(value.items())) + "}"
    return json.dumps(str(value), ensure_ascii=False)


def to_toml(cfg: GridConfig, *, with_docs: bool = True) -> str:
    """A TOML rendering ``load`` reads back; one section per nested dataclass, docs as comments."""
    lines: list[str] = [f"# agentdecompile_grid configuration (schema {cfg.schema})", ""]

    def emit(obj: Any, prefix: str) -> None:
        scalars = [f for f in fields(obj) if not f.metadata.get("internal") and _field_kind(f) != "dataclass"]
        tables = [f for f in fields(obj) if not f.metadata.get("internal") and _field_kind(f) == "dataclass"]
        if prefix:
            lines.append(f"[{prefix}]")
        for f in scalars:
            if with_docs and f.metadata.get("doc"):
                lines.append(f"# {f.metadata['doc']}")
            lines.append(f"{f.name} = {_toml_scalar(getattr(obj, f.name))}")
        lines.append("")
        for f in tables:
            emit(getattr(obj, f.name), f"{prefix}.{f.name}" if prefix else f.name)

    emit(cfg, "")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "CONFIG_SCHEMA_VERSION", "ENV_PREFIX", "ENV_CONFIG_FILE", "ENV_HOME", "CONFIG_FILE_NAME",
    "FSYNC_POLICIES", "WRITE_ONCE_STRATEGIES", "WRITE_POLICIES", "LAYER_FAILURE_POLICIES",
    "FLOAT_POLICIES", "PORTABILITY_POLICIES", "CAPTURE_POLICIES",
    "ConfigError", "PathsConfig", "AdaptersConfig", "LocalStoreConfig", "S3StoreConfig",
    "MirrorStoreConfig", "PeerStoreConfig", "LayeredStoreConfig", "ObjectsConfig", "BudgetsConfig",
    "TasksConfig", "LogConfig", "WorkerConfig", "GridConfig",
    "to_dict", "from_dict", "load", "default", "describe", "to_toml", "config_file_path",
]
