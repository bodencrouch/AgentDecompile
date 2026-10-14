"""How a big verb becomes micro-tasks: ``plan_tasks(kind, store_snapshot, basis_hash, shard_size)``.

A planner turns one *store snapshot* into a list of ``TaskSpec`` (§3: every task is a value:
inputs by content address, params canonical, ``basis_hash`` inside the id).  Planners live in
``PLANNERS`` (one per kind); ``plan_tasks`` is the single chokepoint that enforces the
**never-awaited rule**: every emitted task's budget is SMALL or below unless the kind is a
link/relink (``LINK_KINDS``) or the caller raised ``max_budget`` explicitly.  A refusal names
the shard kinds that would satisfy the rule (``SHARD_ALTERNATIVES``), so the integrator sees
what is missing rather than a silent MEDIUM task.

What a snapshot is, per kind:

* corpus verbs and the cascade read a **SQLite store**: the planner makes a ``VACUUM INTO`` copy
  (not ``.backup``: freelist pages and WAL residue make identical content hash differently),
<<<<<<< HEAD
  puts it as one ``restricted`` object per publish, and derives ``basis_hash`` from *that copy*
  with ``determinism_basis.basis_hash`` (never from the live store, never from the
  environment).  A caller-supplied ``basis_hash`` that differs from the copy's is refused: a task
  under a foreign basis is the hive's ``derive_unit_id`` collision (§1.5 graft a).  The exception
  is a repair kind such as ``corpus-backfill-pass``: an incomplete store is its input, so its task
  id combines the snapshot ref with a lane-specific current-package basis instead.
=======
  puts it as one ``restricted`` object per publish, and reads the basis *object* from *that copy*
  (``_common.StoreBasisSource``: ``determinism_basis.basis`` + ``basis_hash``; never from the
  live store, never from the environment).  A caller-supplied ``basis_hash`` that differs from
  the copy's is refused: a task under a foreign basis is the hive's ``derive_unit_id`` collision
  (§1.5 graft a).
>>>>>>> origin/nvme/feat/portable-signatures-codecaves-generic
* ``compile-attempt`` takes a directory of ``.c`` translation units or a JSONL manifest; each TU
  becomes one object and one task.  No store in the snapshot, so ``store=`` must point at a
  store to read the basis from (a bare ``basis_hash`` cannot be projected; the
  ``ExplicitBasisSource`` slot is the named alternative).
* ``parity-check`` takes a JSONL manifest of ``{target, candidate, symbol}`` rows (paths or
  object refs).
* ``match-score-shard`` slices one directed pair of the store into shards of ``shard_size``
  source addresses (``cascade.plan_match_shards``).
* the analyzer kinds are declared: their planners refuse by name (U137/U139/U141).

Basis rule (U158c): ``plan_tasks`` resolves one ``BasisSource`` per publish (``resolve_basis``:
the store snapshot, else ``store=``, else ``basis=`` -> the ``ExplicitBasisSource`` slot) and every
planner builds its specs through ``_common.lane_spec``, so each spec's ``basis_projection`` is the
kind's declared fields expanded against that basis object and its ``basis_hash`` is the source's
declared hash (``determinism_basis.basis_hash(con)`` for a store).  A kind whose fields include a
per-store path (``analyzer.processor_spec_hash``, ``corpus_manifest_hash``) refuses any source but
the store.  ``describe_planners()`` reports each planner's basis source.

Partitions are ``<kind>/<subject>/<task-id prefix>`` (§2.2): subject = the build's content hash
or the snapshot's hash, prefix width per kind (``PREFIX_HEX``) so hot lanes fan out over many
heads and a verb lane keeps one.

Acceptance tests (named, landed in the verification phase):

* ``test_plan_refuses_medium_by_name_with_candidates`` -- ``corpus-export-hookpack`` under the
  default ``max_budget`` refuses naming ``export-site-shard``; ``--allow-budget medium`` emits it;
* ``test_plan_basis_from_snapshot_only`` -- a differing caller basis is refused;
* ``test_plan_snapshot_is_vacuum_copy_not_live`` -- the live store's bytes and mtime are untouched;
* ``test_plan_task_ids_stable_across_nodes`` -- same snapshot + options give the same ids;
* ``test_plan_partition_prefix_width_per_kind``;
* ``test_plan_no_slug_in_any_spec`` -- grep of every spec/object for registered slugs is empty.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from agentdecompile_grid.core import (
    BudgetClass,
    NotConfigured,
    ObjectRef,
    ObjectStore,
    Refused,
    Registry,
    TaskSpec,
)

<<<<<<< HEAD
from . import analysis, cascade, compile as compile_lane, parity, parity_region, target, verbs
from ._common import Locked, hashed_slug, put_file, translate_refusal
=======
from . import analysis, cascade, compile as compile_lane, parity, verbs
from ._common import (
    BASIS_SOURCES, ExplicitBasisSource, Locked, ResolvedBasis, StoreBasisSource, hashed_slug, lane_spec, put_file,
    translate_refusal,
)
>>>>>>> origin/nvme/feat/portable-signatures-codecaves-generic

PLANNERS = Registry("task planner")
Planner = Callable[..., list[TaskSpec]]

#: Planner name -> the ``BASIS_SOURCES`` names it accepts, first = default (``describe_planners``).
PLANNER_BASIS_SOURCES: dict[str, tuple[str, ...]] = {}

#: Kinds exempt from the never-awaited rule (one process over all objects; < 1 % of work).
LINK_KINDS = frozenset({"link", "relink", "image-join", "corpus-link"})

#: Budget order for the chokepoint.
BUDGET_RANK: Mapping[BudgetClass, int] = {
    BudgetClass.MICRO: 0, BudgetClass.SMALL: 1, BudgetClass.MEDIUM: 2, BudgetClass.LARGE: 3, BudgetClass.UNBOUNDED: 4,
}

#: The sharded kinds (design §3) that would make a MEDIUM verb SMALL.
SHARD_ALTERNATIVES: Mapping[str, Sequence[Mapping[str, str]]] = {
    "corpus-export-hookpack": (
        {"kind": "site-key-table", "unit": "U148"}, {"kind": "export-slice", "unit": "U148"},
        {"kind": "export-site-shard", "unit": "U148"}, {"kind": "export-merge", "unit": "U148"},
    ),
    "corpus-verify-determinism": (
        {"kind": "verify-determinism gate (a): cache-hit check", "unit": "U151"},
        {"kind": "verify-determinism gate (b): k shards recomputed", "unit": "U151"},
    ),
    "analysis-slice": ({"kind": "analysis-slice (fleet, LARGE by design)", "unit": "U137"},),
    "decompile-chunk": ({"kind": "decompile-chunk (chunk class)", "unit": "U139"},),
    "bsim-sigs": ({"kind": "bsim-sigs range (micro once the per-node open is amortised)", "unit": "U141"},),
}

#: Hex chars of task-id prefix per kind's partition (§2.2: 6-bit for compile/parity, 4-bit for match).
PREFIX_HEX: Mapping[str, int] = {"compile-attempt": 2, "parity-check": 2, "match-score-shard": 1}

SQLITE_MAGIC = b"SQLite format 3\x00"

#: These kinds exist to make an incomplete store valid, so deriving their basis from that store
#: would reject exactly the input they repair.  The immutable snapshot ref is already a TaskSpec
#: input; ``repair_basis_hash`` adds current package-policy invalidation to that content identity.
REPAIR_KINDS = frozenset({verbs.CorpusBackfillPass.name})


def planner(kind: str, *, basis_sources: Sequence[str] = ("store",), replace: bool = False) -> Callable[[Planner], Planner]:
    """Register a planner for *kind*; ``basis_sources`` names the ``BASIS_SOURCES`` it may project
    from (first = default).  A name the registry lacks is refused at import."""
    unknown = [n for n in basis_sources if n not in BASIS_SOURCES]
    if unknown:
        raise Refused(f"planner-basis-source-unknown:{kind}:{unknown}:known {BASIS_SOURCES.names()}")

    def register(fn: Planner) -> Planner:
        PLANNERS.register(kind, fn, replace=replace)
        PLANNER_BASIS_SOURCES[kind] = tuple(basis_sources)
        return fn

    return register


# --------------------------------------------------------------------------- snapshots
@dataclasses.dataclass(frozen=True)
class Snapshot:
    """What ``plan_tasks`` was handed: a store copy (ref + local path), a manifest, or a bare ref."""

    ref: ObjectRef | None
    path: Path | None
    flavour: str          # "store" | "manifest" | "object"
    owned: bool = False   # the local copy was made by us and is removed after planning

    @property
    def subject(self) -> str:
        if self.ref is not None:
            return self.ref.hex[:12]
        return hashed_slug(str(self.path))


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def vacuum_copy(store: str | Path, dest: str | Path) -> Path:
    """A compact, WAL-free copy of *store* at *dest* via ``VACUUM INTO`` over a read-only handle."""
    src = Path(store).resolve()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=5)
    try:
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("VACUUM INTO ?", (str(dest),))
    except sqlite3.OperationalError as exc:
        err = translate_refusal(exc)
        if err is not None:
            raise err from exc
        raise Locked(f"snapshot-failed:{type(exc).__name__}") from exc
    finally:
        con.close()
    return dest


def snapshot_store(objects: ObjectStore, store: str | Path, scratch: str | Path | None = None) -> Snapshot:
    """``VACUUM INTO`` copy of *store*, put as one object; the copy stays on disk for planning."""
    scratch_dir = Path(scratch) if scratch else Path(tempfile.mkdtemp(prefix="adgrid-snapshot-"))
    copy = vacuum_copy(store, scratch_dir / f"snapshot-{os.getpid()}.sqlite")
    ref = put_file(objects, copy)
    return Snapshot(ref=ref, path=copy, flavour="store", owned=True)


def resolve_snapshot(objects: ObjectStore, store_snapshot: Any, scratch: str | Path | None = None) -> Snapshot:
    if isinstance(store_snapshot, Snapshot):
        return store_snapshot
    text = str(store_snapshot)
    if text.startswith("sha256:"):
        ref = ObjectRef(text)
        if not objects.exists(ref):
            raise Refused(f"snapshot-object-missing:{ref.hex[:12]}")
        return Snapshot(ref=ref, path=None, flavour="object")
    path = Path(text).expanduser()
    if path.is_dir() or path.suffix.lower() in (".jsonl", ".json"):
        return Snapshot(ref=None, path=path.resolve(), flavour="manifest")
    if path.is_file() and _is_sqlite(path):
        return snapshot_store(objects, path, scratch)
    raise Refused(f"snapshot-unrecognised:{hashed_slug(text)}")


def derive_basis_hash(store_path: str | Path) -> str:
    """The store's own declared basis hash (``determinism_basis.basis_hash``) over a read-only handle."""
    return StoreBasisSource(Path(store_path)).resolve().basis_hash


def resolve_basis(kind: str, snapshot: Snapshot, options: Mapping[str, Any]) -> ResolvedBasis:
    """The one basis object a publish of *kind* projects from, in this order: the store snapshot
    itself; ``store=`` (a store path, for manifest-flavoured lanes); ``basis=`` (a mapping: the
    ``ExplicitBasisSource`` slot).  A source the planner does not accept, or none at all, is
    ``Refused`` by name -- a bare ``basis_hash`` cannot be projected, so it never stands in."""
    accepted = PLANNER_BASIS_SOURCES.get(kind, ("store",))
    source: Any
    if snapshot.flavour == "store" and snapshot.path is not None:
        source = StoreBasisSource(snapshot.path)
    elif options.get("store"):
        source = StoreBasisSource(Path(str(options["store"])).expanduser())
    elif isinstance(options.get("basis"), Mapping):
        source = ExplicitBasisSource(dict(options["basis"]))
    else:
        raise Refused(
            f"basis-required:{kind}:no basis source (snapshot is {snapshot.flavour}); "
            f"pass a store snapshot, store=<path> or basis=<mapping>; accepted {list(accepted)}"
        )
    if source.name not in accepted:
        raise Refused(f"basis-source-not-accepted:{kind}:{source.name}:accepted {list(accepted)}")
    return source.resolve()


def repair_basis_hash(kind: str) -> str:
    """Current package basis for a lane that repairs an incomplete store.

    The analyzer-version value is a namespaced sentinel, not a claim about any binary row.  It
    lets the existing package-basis serializer cover policy/constants while the snapshot object
    itself covers the exact pre-repair database bytes.
    """
    if kind not in REPAIR_KINDS:
        raise ValueError(f"not a repair kind: {kind}")
    from ..corpus.determinism_basis import basis_hash_for

    return basis_hash_for(f"repair:{kind}")


# --------------------------------------------------------------------------- chokepoint
def assign_partition(spec: TaskSpec, subject: str) -> TaskSpec:
    width = PREFIX_HEX.get(spec.kind, 0)
    parts = [spec.kind, subject]
    if width:
        parts.append(spec.task_id[:width])
    return dataclasses.replace(spec, partition="/".join(parts))


def plan_tasks(
    kind: str,
    store_snapshot: Any,
    basis_hash: str | None,
    shard_size: int,
    *,
    objects: ObjectStore,
    max_budget: BudgetClass = BudgetClass.SMALL,
    scratch: str | Path | None = None,
    **options: Any,
) -> list[TaskSpec]:
    """Plan *kind* over *store_snapshot* into tasks whose budget is at most *max_budget*.

<<<<<<< HEAD
    ``basis_hash=None`` derives it from the snapshot (stores only), except that repair kinds use
    :func:`repair_basis_hash` because an incomplete store cannot yet declare its own basis.  A
    given value must equal the derived basis.  Returns specs with partitions assigned.  Raises
    ``Refused`` (no planner, budget above the cap, basis mismatch) or the named refusals of the
    store.
=======
    The basis object comes from ``resolve_basis`` (the snapshot, ``store=`` or ``basis=``); a
    given ``basis_hash`` must equal the source's declared hash.  Every planner receives the
    ``ResolvedBasis`` and builds through ``lane_spec``, so each spec carries the kind's projection.
    Returns specs with partitions assigned.  Raises ``Refused`` (no planner, budget above the cap,
    basis mismatch, no basis source) or the named refusals of the store.
>>>>>>> origin/nvme/feat/portable-signatures-codecaves-generic
    """
    if kind not in PLANNERS:
        raise Refused(f"no-planner:{kind}", candidates=[{"kind": name} for name in PLANNERS.names()])
    snapshot = resolve_snapshot(objects, store_snapshot, scratch)
    try:
<<<<<<< HEAD
        if snapshot.flavour == "store" and snapshot.path is not None:
            derived = repair_basis_hash(kind) if kind in REPAIR_KINDS else derive_basis_hash(snapshot.path)
            if basis_hash and basis_hash != derived:
                raise Refused(f"basis-mismatch:given-{basis_hash[:12]}!=snapshot-{derived[:12]}")
            basis_hash = derived
        elif not basis_hash and options.get("store"):
            basis_hash = derive_basis_hash(options["store"])
        if not basis_hash:
            raise Refused(f"basis-required:{kind}:pass basis_hash or a store to derive it from")
        specs = PLANNERS.get(kind)(objects, snapshot, basis_hash, int(shard_size), **options)
=======
        resolved = resolve_basis(kind, snapshot, options)
        if basis_hash and basis_hash != resolved.basis_hash:
            raise Refused(f"basis-mismatch:given-{basis_hash[:12]}!={resolved.source}-{resolved.basis_hash[:12]}")
        specs = PLANNERS.get(kind)(objects, snapshot, resolved, int(shard_size), **options)
>>>>>>> origin/nvme/feat/portable-signatures-codecaves-generic
    finally:
        if snapshot.owned and snapshot.path is not None:
            snapshot.path.unlink(missing_ok=True)   # the object store holds the bytes; the copy was for planning
    over = [s for s in specs if BUDGET_RANK[s.budget] > BUDGET_RANK[max_budget] and s.kind not in LINK_KINDS]
    if over:
        raise Refused(
            f"budget-above-{max_budget.value}:{kind}:{len(over)}-of-{len(specs)}:{over[0].budget.value}",
            candidates=list(SHARD_ALTERNATIVES.get(kind, ())),
        )
    subject = str(options.get("subject") or snapshot.subject)
    return [assign_partition(s, subject) for s in specs]


# --------------------------------------------------------------------------- planners: corpus verbs
def _store_ref(snapshot: Snapshot) -> ObjectRef:
    if snapshot.ref is None:
        raise Refused("snapshot-store-required")
    return snapshot.ref


def _verb_spec(cls: type, snapshot: Snapshot, basis: ResolvedBasis, params: Mapping[str, Any]) -> TaskSpec:
    return lane_spec(cls, {"store": _store_ref(snapshot)}, params, basis)


def _verb_params(options: Mapping[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if options.get("timeout_s"):
        params["timeout_s"] = float(options["timeout_s"])
    return params


@planner(verbs.CorpusExportHookpack.name)
def plan_export_hookpack(objects, snapshot, basis, shard_size, **options):
    return [_verb_spec(verbs.CorpusExportHookpack, snapshot, basis, _verb_params(options))]


@planner(verbs.CorpusVerifyDeterminism.name)
def plan_verify_determinism(objects, snapshot, basis, shard_size, **options):
    return [_verb_spec(verbs.CorpusVerifyDeterminism, snapshot, basis, _verb_params(options))]


@planner(verbs.CorpusLogicalBuild.name)
def plan_logical_build(objects, snapshot, basis, shard_size, **options):
    return [_verb_spec(verbs.CorpusLogicalBuild, snapshot, basis, _verb_params(options))]


@planner(verbs.CorpusBackfillPass.name)
def plan_backfill_passes(objects, snapshot, basis, shard_size, **options):
    """One task per pass: the verb's ``--pass`` loop is the split."""
    from ..corpus.backfill import PASSES

    names = list(options.get("passes") or PASSES)
    unknown = sorted(set(names) - set(PASSES))
    if unknown:
        raise Refused("backfill-pass-unknown:" + ",".join(unknown), candidates=[{"pass": p} for p in sorted(PASSES)])
    return [
        _verb_spec(verbs.CorpusBackfillPass, snapshot, basis,
                   {**_verb_params(options), "pass": name, "resume": bool(options.get("resume", True))})
        for name in names
    ]


@planner(verbs.CorpusAttest.name)
def plan_attest(objects, snapshot, basis, shard_size, **options):
    """One declared ``corpus-attest`` task per verb; running them refuses by name until U28x."""
    names = list(options.get("verbs") or ("logical-build", "backfill", "export-hookpack", "verify-determinism"))
    return [
        _verb_spec(verbs.CorpusAttest, snapshot, basis,
                   {"verb": verb, "verb_params": dict(options.get("verb_params") or {}), "deadline_s": float(options.get("deadline_s") or 60.0)})
        for verb in names
    ]


# --------------------------------------------------------------------------- planners: compile
def _iter_manifest(path: Path) -> Iterable[dict[str, Any]]:
    if path.is_dir():
        for tu in sorted(p for p in path.rglob("*.c") if not p.name.startswith("_")):
            yield {"path": str(tu)}
        return
    with path.open("r", encoding="utf-8") as fh:
        if path.suffix.lower() == ".json":
            data = json.load(fh)
            rows = data if isinstance(data, list) else data.get("rows", [])
            for row in rows:
                yield dict(row)
            return
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _object_of(objects: ObjectStore, row: Mapping[str, Any], key: str, base: Path) -> ObjectRef:
    value = row.get(key)
    if isinstance(value, str) and value.startswith("sha256:"):
        ref = ObjectRef(value)
        if not objects.exists(ref):
            raise Refused(f"manifest-object-missing:{key}:{ref.hex[:12]}")
        return ref
    path_value = row.get(f"{key}_path") or (row.get("path") if key == "tu" else None) or value
    if not path_value:
        raise Refused(f"manifest-row-missing:{key}")
    path = Path(str(path_value))
    if not path.is_absolute():
        path = (base if base.is_dir() else base.parent) / path
    if not path.is_file():
        raise Refused(f"manifest-file-missing:{key}:{hashed_slug(str(path))}")
    return objects.put(path.read_bytes())


@planner(compile_lane.CompileAttempt.name, basis_sources=("store", "explicit"))
def plan_compile_attempts(objects, snapshot, basis, shard_size, **options):
    """One ``compile-attempt`` per translation unit of a directory or manifest."""
    if snapshot.flavour != "manifest" or snapshot.path is None:
        raise Refused("compile-attempt:snapshot-must-be-tu-dir-or-manifest")
    identity = str(options.get("toolchain_identity_hash") or "")
    if not identity:
        raise Refused("compile-attempt:toolchain_identity_hash-required")
    flags = [str(f) for f in (options.get("flags") or ())]
    profile = str(options.get("profile") or "default")
    opt = str(options.get("opt") or compile_lane.DEFAULT_OPT)
    specs: list[TaskSpec] = []
    for row in _iter_manifest(snapshot.path):
        tu_ref = _object_of(objects, row, "tu", snapshot.path)
        params = {"toolchain_identity_hash": identity, "profile": profile, "opt": opt, "flags": flags}
        specs.append(lane_spec(
            compile_lane.CompileAttempt, {"tu": tu_ref}, params, basis,
            capabilities=(compile_lane.CAPABILITY_PREFIX + identity,),
        ))
    return specs


@planner(parity.ParityCheck.name, basis_sources=("store", "explicit"))
def plan_parity_checks(objects, snapshot, basis, shard_size, **options):
    """One ``parity-check`` per ``{target, candidate, symbol}`` manifest row."""
    if snapshot.flavour != "manifest" or snapshot.path is None or snapshot.path.is_dir():
        raise Refused("parity-check:snapshot-must-be-pairs-manifest")
    verifier_id = str(options.get("verifier_id") or "")
    if not verifier_id:
        raise Refused("parity-check:verifier_id-required")
    specs: list[TaskSpec] = []
    for row in _iter_manifest(snapshot.path):
        params = {"verifier_id": verifier_id, "symbol": str(row.get("symbol") or "")}
        specs.append(lane_spec(
            parity.ParityCheck,
            {"target": _object_of(objects, row, "target", snapshot.path), "candidate": _object_of(objects, row, "candidate", snapshot.path)},
            params, basis, capabilities=(verifier_id,),
        ))
    return specs


@planner(parity_region.ParityRegionCheck.name)
def plan_parity_regions(objects, snapshot, basis_hash, shard_size, **options):
    return parity_region.plan_parity_regions(objects, snapshot, basis_hash, shard_size, **options)


# --------------------------------------------------------------------------- planners: bounded target object
@planner(target.MkobjTarget.name)
def plan_mkobj_target(objects, snapshot, basis_hash, shard_size, **options):
    return target.plan_mkobj_target(objects, snapshot, basis_hash, shard_size, **options)


# --------------------------------------------------------------------------- planners: cascade
@planner(cascade.MatchScoreShard.name)
def plan_match_score_shards(objects, snapshot, basis, shard_size, **options):
    if snapshot.flavour != "store" or snapshot.path is None:
        raise Refused("match-score-shard:snapshot-must-be-store")
    src, dst = options.get("src"), options.get("dst")
    if not src or not dst:
        raise Refused("match-score-shard:src-and-dst-required")
    mapping = options.get("mapping") or {}
    if isinstance(mapping, str):
        text = mapping
        if text.startswith("sha256:"):
            mapping = json.loads(objects.get(ObjectRef(text)).decode("utf-8")).get("mapping", {})
        else:
            mapping = json.loads(Path(text).read_text("utf-8"))
            mapping = mapping.get("mapping", mapping)
    return cascade.plan_match_shards(
        objects, snapshot.path, basis, shard_size or 512, src=str(src), dst=str(dst),
        mapping={int(k): int(v) for k, v in dict(mapping).items()}, round_index=int(options.get("round", 0)),
        use_name_features=bool(options.get("use_name_features", True)),
    )


# --------------------------------------------------------------------------- planners: analyzer (declared)
def _declared_planner(cls: type):
    def plan(objects, snapshot, basis, shard_size, **options):
        raise NotConfigured(f"{cls.name}: analyzer lane planner not present in this checkout yet ({cls.UNIT})")

    return plan


for _cls in analysis.ANALYSIS_KINDS:
    planner(_cls.name)(_declared_planner(_cls))   # analyzer fields include processor_spec_hash: store source only


def describe_planners() -> dict[str, Any]:
    """The planner catalogue plus, per planner, the basis sources it accepts (first = default)."""
    return {
        "planners": PLANNERS.names(), "max_budget_default": BudgetClass.SMALL.value, "link_kinds": sorted(LINK_KINDS),
        "prefix_hex": dict(PREFIX_HEX), "shard_alternatives": {k: list(v) for k, v in SHARD_ALTERNATIVES.items()},
        "basis_sources": {
            name: {"default": PLANNER_BASIS_SOURCES[name][0], "accepted": list(PLANNER_BASIS_SOURCES[name])}
            for name in PLANNERS.names()
        },
        "basis_source_kinds": BASIS_SOURCES.names(),
    }


__all__ = [
    "BUDGET_RANK", "LINK_KINDS", "PLANNERS", "PLANNER_BASIS_SOURCES", "PREFIX_HEX", "SHARD_ALTERNATIVES", "Snapshot",
    "assign_partition", "derive_basis_hash", "describe_planners", "plan_tasks", "planner", "resolve_basis", "resolve_snapshot",
    "snapshot_store", "vacuum_copy",
]
