"""Shared helpers for the pipeline's grid lanes (import direction: recovery -> grid only).

Everything a lane kind needs that is not the kind itself: the named refusal classes the corpus
verbs already speak (basis, content hash, lock) as ``GridError`` subclasses; slug hashing; a
subprocess runner with a hard kill deadline; result construction; recompute-based verification;
the ``SubprocessVerb``-style parameter shape the grid's builtin runner understands; and the
**basis sources** (U158c) a planner projects a kind's ``basis_fields`` from: ``StoreBasisSource``
reads ``determinism_basis.basis(con)`` from a store snapshot (working); ``PackBasisSource`` and
``ExplicitBasisSource`` are declared slots.  ``lane_spec`` is the one builder every planner uses,
so a planned spec always carries the projection the grid's registry checks by name.

No absolute path and no plaintext slug ever reaches a receipt: ``scrub_paths`` and
``hashed_slug`` are applied before any text leaves a task.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping, Protocol, Sequence

from agentdecompile_grid.core import (
    BASIS_FIELDS,
    DEFAULT_DEADLINES_S,
    BudgetClass,
    GridError,
    NotConfigured,
    ObjectRef,
    ObjectStore,
    Refused,
    Registry,
    ResultStatus,
    TaskResult,
    TaskSpec,
    Verification,
    VerificationOutcome,
    basis_field_known,
    canonical_json,
    check_basis_projection,
    digest,
    kind_basis_fields,
    kind_basis_projection,
)
from agentdecompile_grid.tasks.spec import build_spec

# --------------------------------------------------------------------------- basis field sets
_ANALYZER_FIELDS = (
    "analyzer.version", "analyzer.options_hash", "analyzer.loader_revision", "analyzer.timeout_policy",
    "analyzer.processor_spec_hash",
)
_TOOLCHAIN_FIELDS = ("toolchain_identity_hash",)
_CASCADE_FIELDS = ("algorithm_version", "masking_rule_version", "threshold_params.*", "seeds.*")
_REPAIR_FIELDS = (
    "basis_version", "analyzer.version", "analyzer.options_hash", "analyzer.loader_revision",
    "analyzer.timeout_policy", "algorithm_version", "masking_rule_version", "threshold_params.*", "seeds.*",
    "toolchain_identity_hash", "data_packs", "data_packs_root_declared",
)

BASIS_FIELD_SETS: dict[str, tuple[str, ...]] = {
    "content_only": (),
    "analyzer": _ANALYZER_FIELDS,
    "toolchain": _TOOLCHAIN_FIELDS,
    "cascade": _CASCADE_FIELDS,
    "corpus_verb": _ANALYZER_FIELDS + _CASCADE_FIELDS + ("data_packs", "data_packs_root_declared", "basis_version"),
    "parity": _TOOLCHAIN_FIELDS + ("masking_rule_version",),
    "repair": _REPAIR_FIELDS,
}
"""The named slices of the determinism basis a lane kind may key its tasks on (design §2.8).

A lane declares one set by name (``PlannableKind.basis_field_set``) instead of retyping paths;
``basis_fields`` is derived from it.  Paths are spelled as ``agentdecompile_grid.core.BASIS_FIELDS``
spells them: ``threshold_params.*`` / ``seeds.*`` name the whole sub-mapping.  ``content_only`` is
``()``: the kind's output depends on its inputs alone.  A toolchain change re-keys ``toolchain`` and
``parity`` kinds only; an analyzer change re-keys ``analyzer`` and ``corpus_verb`` kinds only.
"""


def basis_fields_for(set_name: str) -> tuple[str, ...]:
    """The paths of the named set; ``Refused("basis-field-set-unknown:<name>")`` for a name not in
    ``BASIS_FIELD_SETS``.  Every path is checked against ``core.BASIS_FIELDS`` so a set never names a
    field the grid's vocabulary lacks."""
    if set_name not in BASIS_FIELD_SETS:
        raise Refused(f"basis-field-set-unknown:{set_name}:known {sorted(BASIS_FIELD_SETS)}")
    fields = BASIS_FIELD_SETS[set_name]
    unknown = [p for p in fields if not basis_field_known(p, BASIS_FIELDS)]
    if unknown:
        raise Refused(f"basis-field-set-outside-vocabulary:{set_name}:{unknown}")
    return tuple(fields)


# --------------------------------------------------------------------------- basis sources
#: Basis paths only a *store* basis carries (``determinism_basis.basis(con)``): the package basis
#: (``package_basis``) has neither, so a kind that keys on one must project from a store source.
STORE_ONLY_FIELDS: tuple[str, ...] = ("analyzer.processor_spec_hash", "corpus_manifest_hash")


@dataclasses.dataclass(frozen=True)
class ResolvedBasis:
    """What a ``BasisSource`` yields: the full basis object, the hash the source declares for it,
    and the source's name.  ``basis_hash`` is the *declared* hash (a store's own
    ``determinism_basis.basis_hash``, which leaves ``BASIS_HASH_EXCLUDED`` out), not
    ``digest_value(basis)``: it is the value ``binary.basis_hash`` rows, ``admitted_bases`` and
    the caller-supplied ``basis_hash`` of ``plan_tasks`` all speak."""

    basis: Mapping[str, Any]
    basis_hash: str
    source: str


class BasisSource(Protocol):
    """Where a planner's basis object comes from.  ``resolve()`` returns the object and its
    declared hash, or raises a named refusal (``BasisRefused`` when no single basis can be
    declared; ``NotConfigured`` for a declared slot)."""

    name: ClassVar[str]

    def resolve(self) -> ResolvedBasis: ...


@dataclasses.dataclass(frozen=True)
class StoreBasisSource:
    """The basis a store snapshot declares: ``determinism_basis.basis(con)`` over a read-only handle
    (``store.connect(path, read_only=True)``; never migrates, never writes).  A ``BasisError`` is
    the lane's ``BasisRefused`` by name; a locked or unopenable file is ``Locked``."""

    name: ClassVar[str] = "store"
    path: Path

    def resolve(self) -> ResolvedBasis:
        from ..corpus.determinism_basis import BasisError, basis, basis_hash
        from ..corpus.store import connect

        try:
            con = connect(Path(self.path).resolve(), read_only=True)
        except sqlite3.OperationalError as exc:
            err = translate_refusal(exc)
            raise (err if err is not None else Locked(f"store-open-failed:{type(exc).__name__}")) from exc
        try:
            obj = basis(con)
            declared = basis_hash(con)
        except (BasisError, sqlite3.OperationalError) as exc:
            err = translate_refusal(exc)
            if err is not None:
                raise err from exc
            raise
        finally:
            con.close()
        return ResolvedBasis(basis=obj, basis_hash=declared, source=self.name)


@dataclasses.dataclass(frozen=True)
class RepairBasisSource:
    """Current package-policy basis for repair lanes over intentionally incomplete stores.

    The immutable input snapshot keys the pre-repair database contents. This projection separately
    keys the current package policy so a policy change re-plans the repair without asking an
    incomplete database to declare the very basis it is meant to restore.
    """

    name: ClassVar[str] = "repair"
    kind: str

    def resolve(self) -> ResolvedBasis:
        from ..corpus.determinism_basis import basis_hash_for, package_basis

        version = f"repair:{self.kind}"
        return ResolvedBasis(basis=package_basis(version), basis_hash=basis_hash_for(version), source=self.name)


@dataclasses.dataclass(frozen=True)
class PackBasisSource:
    """Slot: the ``basis`` block at a hook pack's root (``export_hookpack`` writes it).  Declared so
    a planner over an exported pack has a named source; refuses by name until it lands."""

    name: ClassVar[str] = "pack"
    pack: Any

    def resolve(self) -> ResolvedBasis:
        raise not_present("PackBasisSource (a hook pack's root basis block)")


@dataclasses.dataclass(frozen=True)
class ExplicitBasisSource:
    """Slot: a basis object handed in by the caller (``plan_tasks(..., basis=<mapping>)``) for the
    lanes that plan from a manifest and have no store to read.  Refuses by name until it lands."""

    name: ClassVar[str] = "explicit"
    basis: Mapping[str, Any]

    def resolve(self) -> ResolvedBasis:
        raise not_present("ExplicitBasisSource (a basis object passed in params)")


BASIS_SOURCES = Registry("basis source")
for _source in (StoreBasisSource, RepairBasisSource, PackBasisSource, ExplicitBasisSource):
    BASIS_SOURCES.register(_source.name, _source)


def project_for(kind_cls: Any, basis_obj: Mapping[str, Any]) -> dict[str, Any]:
    """The kind's declared slice of *basis_obj*: ``core.kind_basis_projection`` (the same helper
    ``TaskSpec.from_basis`` uses), so the keys are exactly ``kind.basis_fields`` or it is
    ``Refused`` by name (a path absent from the basis, a style the grid does not know)."""
    return kind_basis_projection(kind_cls, basis_obj)


def require_source_for(kind_cls: Any, resolved: ResolvedBasis) -> None:
    """A kind whose fields include a ``STORE_ONLY_FIELDS`` path must project from a store basis;
    ``Refused("basis-source-store-required:<kind>:[fields]")`` for any other source."""
    needs = sorted(set(kind_basis_fields(kind_cls)) & set(STORE_ONLY_FIELDS))
    if needs and resolved.source != StoreBasisSource.name:
        raise Refused(f"basis-source-store-required:{kind_cls.name}:{needs}:got {resolved.source}")


def lane_spec(
    kind_cls: Any, inputs: Mapping[str, Any], params: Mapping[str, Any], resolved: ResolvedBasis, *,
    capabilities: Iterable[str] | None = None, budget: BudgetClass | None = None,
) -> TaskSpec:
    """The one spec builder for every lane planner (U158c).

    ``basis_projection = project_for(kind, resolved.basis)`` keys the id; ``basis_hash`` is the
    source's *declared* hash (``ResolvedBasis``).  Params and projection values go through
    ``tasks.spec.build_spec`` so they are canonical (floats become repr strings: read them back
    with ``deadline_for`` / ``param_float``).  Capabilities and budget are the planner's
    (``kind.capabilities`` / ``kind.budget`` when not given): compile and parity kinds carry
    template capabilities and the cascade sizes its budget per shard, so ``spec_for_kind``'s
    kind-level validation is not applied here; the projection check the registry, publish,
    execute and verify share (``core.check_basis_projection``) is.
    """
    require_source_for(kind_cls, resolved)
    caps = tuple(kind_cls.capabilities) if capabilities is None else tuple(capabilities)
    spec = build_spec(
        kind_cls.name, inputs, params, resolved.basis_hash, kind_version=int(kind_cls.version), capabilities=caps,
        budget=budget if budget is not None else BudgetClass(kind_cls.budget),
        basis_projection=project_for(kind_cls, resolved.basis),
    )
    check_basis_projection(kind_cls, spec)
    return spec


# --------------------------------------------------------------------------- named refusals
class BasisRefused(Refused):
    """The store cannot declare one basis (``determinism_basis.BasisError``)."""

    exit_code = 10


class ContentHashRefused(Refused):
    """A build the cascade keys on lacks a usable ``content_sha256`` (``logical.ContentHashError``)."""

    exit_code = 11


class Locked(GridError):
    """The store's write lock was held past ``busy_timeout``; reported by name, never waited on."""

    exit_code = 12


class Infra(GridError):
    """Infrastructure failure inside a task (timeout, no object, no diagnostic): writes nothing."""

    exit_code = 13


def hashed_slug(slug: object) -> str:
    """A build name for a message or receipt: ``sha256(slug)[:12]``, never the slug."""
    return digest(str(slug).encode("utf-8"))[:12]


_LOCK_MARKERS = ("locked", "busy", "readonly", "read-only", "unable to open")


def translate_refusal(exc: BaseException) -> GridError | None:
    """The ``GridError`` for a recovery-side refusal, or ``None`` when *exc* is not one.

    Mirrors ``corpus.cli._refusal_line`` without importing it: the three classes the keyed
    verbs share are mapped to named grid errors with hashed build names.
    """
    from ..corpus.determinism_basis import BasisError
    from ..corpus.logical import ContentHashError

    if isinstance(exc, ContentHashError):
        names = ",".join(hashed_slug(s) for s in getattr(exc, "slugs", ()))
        detail = "shared-by" if getattr(exc, "kind", "") == "duplicate" else "missing-for"
        return ContentHashRefused(f"content-hash:{detail}:{len(getattr(exc, 'slugs', ()))}:[{names}]")
    if isinstance(exc, BasisError):
        return BasisRefused(f"basis:{scrub_paths(str(exc))}")
    if isinstance(exc, sqlite3.OperationalError) and any(m in str(exc).lower() for m in _LOCK_MARKERS):
        return Locked(f"locked:{scrub_paths(str(exc))}")
    return None


# --------------------------------------------------------------------------- scrubbing
_ABS_POSIX = re.compile(r"(?<![\w./])/(?:[^/\s'\"()]+/)+[^/\s'\"()]*")
_ABS_WIN = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"()]*")


def scrub_paths(text: str) -> str:
    """Replace absolute path spellings with ``<path>`` so no host layout leaks into a receipt."""
    text = _ABS_WIN.sub("<path>", text)
    return _ABS_POSIX.sub("<path>", text)


def assert_portable(payload: Any) -> None:
    """Refuse a receipt that carries an absolute path (the landed exchange rule, R1)."""
    from ..exchange.store import assert_portable_payload

    try:
        assert_portable_payload(payload)
    except ValueError as exc:
        raise Refused(f"non-portable-receipt:{scrub_paths(str(exc))}") from exc


# --------------------------------------------------------------------------- subprocesses
@dataclasses.dataclass(frozen=True)
class RunOutcome:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float
    timed_out: bool

    @property
    def stdout_sha256(self) -> str:
        return digest(self.stdout.encode("utf-8", "replace"))

    @property
    def stderr_sha256(self) -> str:
        return digest(self.stderr.encode("utf-8", "replace"))


def deadline_for(budget: BudgetClass, requested_s: float | str | None = None) -> float:
    """The kill deadline a task may use: never more than its class allows.  *requested_s* may be
    the repr string a canonical spec stores a float as (``tasks.spec.normalize_params``)."""
    cap = DEFAULT_DEADLINES_S[budget]
    if isinstance(requested_s, str):
        try:
            requested_s = float(requested_s)
        except ValueError:
            raise Refused(f"deadline-not-a-number:{requested_s[:32]!r}") from None
    if requested_s is None or requested_s <= 0:
        return float(cap)
    return float(min(requested_s, cap)) if cap else float(requested_s)


def run_argv(
    argv: Sequence[str],
    *,
    cwd: str | Path,
    timeout_s: float,
    env: Mapping[str, str] | None = None,
    stdin_bytes: bytes | None = None,
) -> RunOutcome:
    """Run *argv* in its own process group; SIGTERM at the deadline, SIGKILL 5 s later.

    The worker owns the class deadline (design §2.7); this runner is the kind's own guard so a
    kind never outlives its budget even when driven outside the worker (the CLI's ``--once``).
    """
    started = time.monotonic()
    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd), "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
        "env": dict(env) if env is not None else None,
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen([str(a) for a in argv], **popen_kwargs)
    timed_out = False
    try:
        out, err = proc.communicate(input=stdin_bytes, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc, signal.SIGTERM if os.name != "nt" else None)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_group(proc, signal.SIGKILL if os.name != "nt" else None)
            out, err = proc.communicate()
    elapsed = time.monotonic() - started
    return RunOutcome(
        argv=tuple(str(a) for a in argv), returncode=int(proc.returncode if proc.returncode is not None else -1),
        stdout=(out or b"").decode("utf-8", "replace"), stderr=(err or b"").decode("utf-8", "replace"),
        elapsed_s=elapsed, timed_out=timed_out,
    )


def _kill_group(proc: subprocess.Popen, sig) -> None:
    try:
        if sig is None:
            proc.kill()
        else:
            os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def corpus_cli_argv(verb: str, *args: str) -> list[str]:
    """``python -m agentdecompile_recovery.corpus.cli <verb> ...`` under the running interpreter."""
    return [sys.executable, "-m", "agentdecompile_recovery.corpus.cli", verb, *args]


def subprocess_verb_params(
    *, argv: Sequence[str], outputs: Mapping[str, str], timeout_s: float,
    env: Mapping[str, str] | None = None, cwd: str = "{scratch}",
) -> dict[str, Any]:
    """The ``SubprocessVerb``-style parameter shape (``agentdecompile_grid.tasks.builtin``).

    ``{store}`` / ``{scratch}`` / ``{out}`` placeholders name the materialised input object, the
    scratch directory and the output directory; ``outputs`` maps output names to files under
    ``{out}`` that become objects.  A lane renders this so the grid's builtin runner can execute
    the verb identically to the lane's own ``run``.
    """
    return {
        "argv": [str(a) for a in argv], "cwd": cwd, "timeout_s": float(timeout_s),
        "env": dict(env or {}), "outputs": dict(outputs),
    }


# --------------------------------------------------------------------------- objects / results
def materialize_object(objects: ObjectStore, ref: ObjectRef, path: Path) -> Path:
    """Write the object at *ref* to *path* (a task's scratch copy of an input).

    Uses the store's streaming ``get_path(ref, path)`` when it has one (a store snapshot is
    GB-sized); the Protocol's ``get`` -> bytes otherwise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    get_path = getattr(objects, "get_path", None)
    if callable(get_path):
        get_path(ref, path)
        return path
    path.write_bytes(objects.get(ref))
    return path


def put_file(objects: ObjectStore, path: Path) -> ObjectRef:
    """Put a file's bytes; streams through ``put_path(path)`` when the store offers it."""
    put_path = getattr(objects, "put_path", None)
    if callable(put_path):
        return ObjectRef(put_path(path))
    return objects.put(path.read_bytes())


def put_json(objects: ObjectStore, value: Any) -> ObjectRef:
    return objects.put(canonical_json(value))


def get_json(objects: ObjectStore, ref: ObjectRef) -> Any:
    return json.loads(objects.get(ref).decode("utf-8"))


def make_result(
    spec: TaskSpec,
    outputs: Mapping[str, ObjectRef],
    *,
    elapsed_s: float,
    status: ResultStatus = ResultStatus.OK,
    reason: str = "",
    candidates: Sequence[Mapping[str, Any]] = (),
    metrics: Mapping[str, Any] | None = None,
    producer_key: str = "",
) -> TaskResult:
    """A ``TaskResult`` for *spec*.  ``producer_key`` is stamped by the worker (it holds the key)."""
    return TaskResult(
        task_id=spec.task_id, status=status, outputs=dict(outputs), producer_key=producer_key,
        basis_hash=spec.basis_hash, elapsed_s=elapsed_s, reason=reason,
        candidates=tuple(candidates), metrics=dict(metrics or {}),
    )


def require_param(spec: TaskSpec, name: str, *, kind: str) -> Any:
    if name not in spec.params:
        raise Refused(f"missing-param:{kind}:{name}")
    return spec.params[name]


def require_input(spec: TaskSpec, name: str, *, kind: str) -> ObjectRef:
    if name not in spec.inputs:
        raise Refused(f"missing-input:{kind}:{name}")
    return ObjectRef(spec.inputs[name])


def check_kind(spec: TaskSpec, kind_name: str, kind_version: int) -> None:
    """Refusal first, at 1 ms: a spec of another kind or version never fetches an input."""
    if spec.kind != kind_name:
        raise Refused(f"kind-mismatch:{spec.kind}!={kind_name}")
    if spec.kind_version != kind_version:
        raise Refused(f"kind-version-mismatch:{spec.kind}:{spec.kind_version}!={kind_version}")
    if not spec.basis_hash:
        raise Refused(f"basis-required:{kind_name}")


def verify_by_recompute(
    kind: Any, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str,
    *, compare: Sequence[str] | None = None, method: str = "recompute",
) -> Verification:
    """Re-run *kind* on this node and compare the content addresses of its outputs.

    Outputs are content-addressed, so equality of refs is equality of bytes.  A kind whose
    outputs carry per-run noise must keep that noise in ``metrics`` (not in an output) or pass
    *compare* to name the load-bearing outputs.  Refusals during recompute are UNVERIFIABLE with
    the reason in evidence; a capability this node lacks is likewise UNVERIFIABLE, never REFUTED.
    """
    result_refs = {k: str(v) for k, v in result.outputs.items()}
    try:
        recomputed = kind.run(spec, objects, scratch)
    except Refused as exc:
        return Verification(
            task_id=spec.task_id, result_ref=ObjectRef.of_value(result.to_record()),
            outcome=VerificationOutcome.UNVERIFIABLE, verifier_key="", method=method,
            evidence={"reason": exc.reason},
        )
    names = list(compare) if compare else sorted(set(result_refs) | set(recomputed.outputs))
    mismatched = [
        n for n in names if result_refs.get(n) != (str(recomputed.outputs[n]) if n in recomputed.outputs else None)
    ]
    status_same = recomputed.status == result.status and recomputed.reason == result.reason
    outcome = VerificationOutcome.VERIFIED if not mismatched and status_same else VerificationOutcome.REFUTED
    return Verification(
        task_id=spec.task_id, result_ref=ObjectRef.of_value(result.to_record()), outcome=outcome,
        verifier_key="", method=method,
        evidence={
            "compared": names, "mismatched": mismatched,
            "status": {"proposal": result.status.value, "recomputed": recomputed.status.value},
            "recomputed_outputs": {k: str(v) for k, v in sorted(recomputed.outputs.items())},
        },
    )


def not_present(module: str) -> NotConfigured:
    return NotConfigured(f"{module} not present in this checkout yet")


class PlannableKind:
    """Mixin: ``Kind.plan(...)`` is how the grid CLI reaches a lane's planner without importing it.

    ``adgrid publish <kind>`` duck-types ``TASK_KINDS.get(kind).plan`` (the grid never imports
    ``agentdecompile_recovery``); the call goes through ``splitter.plan_tasks``, the one
    chokepoint for the never-awaited rule.  Returns the specs; every spec carries its basis.

    A lane declares one basis field set by name (``basis_field_set``, a ``BASIS_FIELD_SETS`` key);
    ``basis_fields`` -- what the grid's registry, publish, execute and verify read (U158) -- is
    derived from it at class creation, plus ``basis_fields_extra`` for a kind that keys on one path
    beyond its set.  A subclass that names no set stays undeclared: the grid refuses it by name
    rather than keying it on nothing.
    """

    name = ""
    basis_field_set: str = ""
    basis_fields_extra: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.basis_field_set:
            declared = basis_fields_for(cls.basis_field_set)
            extra = tuple(p for p in cls.basis_fields_extra if p not in declared)
            unknown = [p for p in extra if not basis_field_known(p, BASIS_FIELDS)]
            if unknown:
                raise Refused(f"basis-fields-extra-outside-vocabulary:{cls.name or cls.__name__}:{unknown}")
            cls.basis_fields = declared + extra

    @classmethod
    def describe_basis(cls) -> dict[str, Any]:
        """``{set, fields}``: the set name and the derived paths (``describe_lanes`` reports it)."""
        return {
            "set": cls.basis_field_set or None,
            "fields": list(getattr(cls, "basis_fields", ())) if cls.basis_field_set else None,
        }

    @classmethod
    def plan(
        cls, objects: ObjectStore, store_snapshot: Any, *, basis_hash: str | None = None, shard_size: int = 512,
        max_budget: BudgetClass = BudgetClass.SMALL, scratch: str | None = None, **options: Any,
    ) -> list[TaskSpec]:
        from .splitter import plan_tasks

        return plan_tasks(
            cls.name, store_snapshot, basis_hash, shard_size, objects=objects, max_budget=max_budget,
            scratch=scratch, **options,
        )


__all__ = [
    "BASIS_FIELD_SETS", "BASIS_SOURCES", "STORE_ONLY_FIELDS", "BasisRefused", "BasisSource", "ContentHashRefused",
    "ExplicitBasisSource", "Infra", "Locked", "PackBasisSource", "PlannableKind", "RepairBasisSource", "ResolvedBasis",
    "RunOutcome", "StoreBasisSource", "assert_portable", "basis_fields_for", "check_kind", "corpus_cli_argv",
    "deadline_for", "get_json",
    "hashed_slug", "lane_spec", "make_result", "materialize_object", "not_present", "project_for", "put_file", "put_json",
    "require_input", "require_param", "require_source_for", "run_argv", "scrub_paths", "subprocess_verb_params",
    "translate_refusal", "verify_by_recompute",
]
