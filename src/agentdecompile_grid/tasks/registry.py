"""agentdecompile_grid.tasks.registry — task kinds: explicit registration, entry-point discovery, execution.

Kinds are classes (or instances) meeting ``core.TaskKind``: class attributes ``name``, ``version``,
``budget``, ``capabilities`` and methods ``run``/``verify``.  ``core.TASK_KINDS`` is the registry;
this module adds:

* ``register_kind`` — validates the shape (name pattern, positive version, a ``BudgetClass``,
  string capabilities, callable ``run``/``verify``, a ``basis_fields`` tuple drawn from
  ``core.BASIS_FIELDS``) and records where the kind came from.  A kind without ``basis_fields`` is
  refused by name: its task ids could not say which basis fields they depend on (U158).
* ``discover_entry_points`` — loads the ``agentdecompile_grid.task_kinds`` entry-point group
  (``tasks.entry_point_group``).  An entry point may resolve to a kind, a list of kinds, or a
  zero-argument callable returning either.  Failures are collected per entry point in the
  ``DiscoveryReport``, never raised, so one broken plugin cannot take the grid down; the CLI prints
  them.  Works with zero entry points and when this distribution is not installed at all.
* ``get_kind`` — an *instance* ready to ``run``; ``kind_class`` the raw registration.
* ``execute`` — runs a kind under the discipline the worker expects: a deterministic ``Refused``
  becomes ``REFUSED``, ``core.Deadline`` becomes ``TIMEOUT``, any other exception becomes ``ERROR``
  carrying the exception class as ``reason`` and the digest of the traceback in ``metrics``
  (never the text).  The producer key is stamped on the result here because ``TaskKind.run``
  does not receive it.
* ``describe_kinds`` — the dict the CLI prints (``adgrid tasks kinds``).
* ``projection_table`` — ``{kind: basis_fields}`` for ``describe`` plus the kinds that declare none.
* ``check_projection`` — the shape check ``execute``/``stamp`` and the publish/verify/consume paths
  share (``core.check_basis_projection``): a spec whose projection keys are not the kind's
  ``basis_fields`` is refused by name; ``core.task_kind`` registers raw (a lane module must stay
  importable), so the refusal lands at use, not at import.

Acceptance tests (named here, landed in the verification phase):

* ``test_register_kind_validates_shape_by_name`` — a class without ``version`` is refused naming ``version``.
* ``test_discovery_collects_failures_and_works_with_no_entry_points``.
* ``test_execute_maps_refused_deadline_and_exceptions_to_statuses``.
* ``test_describe_kinds_lists_builtins_with_deadlines``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..core import (
    BASIS_FIELDS, TASK_KINDS, BudgetClass, Deadline as DeadlineError, GridError, ObjectStore, Refused, ResultStatus, TaskKind,
    TaskResult, TaskSpec, basis_field_known, check_basis_projection, kind_basis_fields,
)
from .spec import KIND_NAME_RE, SpecError, validate_spec

DEFAULT_ENTRY_POINT_GROUP = "agentdecompile_grid.task_kinds"

_SOURCES: dict[str, str] = {}
_DISCOVERY_LOCK = threading.Lock()
_DISCOVERED: dict[str, "DiscoveryReport"] = {}


class KindError(GridError):
    """A task kind is malformed or unknown; the message names the kind and the missing piece."""


# --------------------------------------------------------------------------- registration
def validate_kind(kind: Any) -> Any:
    """Raise ``KindError`` naming the first missing/invalid attribute; return ``kind``."""
    what = getattr(kind, "__name__", type(kind).__name__)
    name = getattr(kind, "name", None)
    if not isinstance(name, str) or not KIND_NAME_RE.match(name):
        raise KindError(f"task kind {what}: 'name' must be a class attribute matching {KIND_NAME_RE.pattern}, got {name!r}")
    version = getattr(kind, "version", None)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise KindError(f"task kind {name}: 'version' must be a positive int class attribute, got {version!r}")
    budget = getattr(kind, "budget", None)
    try:
        BudgetClass(budget)
    except ValueError:
        raise KindError(f"task kind {name}: 'budget' must be a BudgetClass, got {budget!r}") from None
    caps = getattr(kind, "capabilities", None)
    if caps is None or isinstance(caps, str) or not all(isinstance(c, str) and c for c in caps):
        raise KindError(f"task kind {name}: 'capabilities' must be a sequence of non-empty strings, got {caps!r}")
    for method in ("run", "verify"):
        if not callable(getattr(kind, method, None)):
            raise KindError(f"task kind {name}: missing callable {method}(spec, objects, scratch)")
    validate_basis_fields(kind)
    for extra in getattr(kind, "allowed_budgets", ()) or ():
        try:
            BudgetClass(extra)
        except ValueError:
            raise KindError(f"task kind {name}: allowed_budgets entry {extra!r} is not a BudgetClass") from None
    return kind


def validate_basis_fields(kind: Any) -> tuple[str, ...]:
    """``basis_fields`` must be a tuple/list of ``core.BASIS_FIELDS`` paths (``()`` = content-only);
    refused by name when absent, a bare string, or naming a path outside the vocabulary."""
    name = getattr(kind, "name", getattr(kind, "__name__", type(kind).__name__))
    try:
        fields = kind_basis_fields(kind)
    except Refused as exc:
        raise KindError(f"task kind {name}: 'basis_fields' must be a tuple of core.BASIS_FIELDS paths (() = content-only); {exc.reason}") from None
    declared = getattr(kind, "basis_fields")
    if not isinstance(declared, (tuple, list)):
        raise KindError(f"task kind {name}: 'basis_fields' must be a tuple, got {type(declared).__name__}")
    unknown = [p for p in fields if not basis_field_known(p)]
    if unknown:
        raise KindError(f"task kind {name}: basis_fields {unknown} are not in core.BASIS_FIELDS {list(BASIS_FIELDS)}")
    if len(set(fields)) != len(fields):
        raise KindError(f"task kind {name}: basis_fields repeats a path: {list(fields)}")
    return fields


def check_projection(kind: Any, spec: TaskSpec) -> None:
    """``core.check_basis_projection`` for a registered kind name or class (Refused by name)."""
    if isinstance(kind, str):
        kind = kind_class(kind)
    check_basis_projection(kind, spec)


def projection_table(*, include_undeclared: bool = True) -> dict[str, Any]:
    """``{kind: [basis_fields...]}`` for ``describe``; kinds registered raw without ``basis_fields``
    are listed under ``undeclared`` (they are refused at publish/execute/verify, not hidden)."""
    table: dict[str, list[str]] = {}
    undeclared: list[str] = []
    for name in kind_names():
        try:
            table[name] = list(kind_basis_fields(kind_class(name)))
        except Refused:
            undeclared.append(name)
    out: dict[str, Any] = {"kinds": table}
    if include_undeclared:
        out["undeclared"] = undeclared
    return out


def register_kind(kind: Any, *, replace: bool = False, source: str = "explicit") -> Any:
    validate_kind(kind)
    TASK_KINDS.register(kind.name, kind, replace=replace)
    _SOURCES[kind.name] = source
    return kind


def unregister_kind(name: str) -> bool:
    if name not in TASK_KINDS:
        return False
    del TASK_KINDS._items[name]
    _SOURCES.pop(name, None)
    return True


def kind_class(name: str) -> Any:
    try:
        return TASK_KINDS.get(name)
    except KeyError as exc:
        raise KindError(str(exc)) from None


def get_kind(name: str, *, config: Any = None) -> TaskKind:
    """A ready instance: classes are instantiated (``cls(config=...)`` if accepted, else ``cls()``)."""
    if config is not None and config.tasks.auto_discover:
        ensure_discovered(config)
    kind = kind_class(name)
    if inspect.isclass(kind):
        try:
            params = inspect.signature(kind).parameters
        except (TypeError, ValueError):
            params = {}
        return kind(config=config) if "config" in params else kind()
    return kind


def kind_names() -> list[str]:
    return TASK_KINDS.names()


def kind_source(name: str) -> str:
    return _SOURCES.get(name, "unknown")


# --------------------------------------------------------------------------- discovery
@dataclass(frozen=True)
class DiscoveryReport:
    group: str
    loaded: tuple[str, ...]                          # kind names registered by this discovery
    skipped: tuple[str, ...]                         # already registered (not replaced)
    failed: Mapping[str, str] = field(default_factory=dict)   # entry point name -> error class: message

    def to_dict(self) -> dict[str, Any]:
        return {"group": self.group, "loaded": list(self.loaded), "skipped": list(self.skipped), "failed": dict(self.failed)}


def _iter_entry_points(group: str) -> Iterable[Any]:
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return []
    try:
        eps = entry_points()
        if hasattr(eps, "select"):
            return list(eps.select(group=group))
        return list(eps.get(group, []))  # type: ignore[union-attr]
    except Exception:  # a broken distribution metadata must not take the grid down
        return []


def _kinds_from(obj: Any) -> list[Any]:
    if callable(obj) and not inspect.isclass(obj) and not hasattr(obj, "run"):
        obj = obj()
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return [obj]


def discover_entry_points(group: str = DEFAULT_ENTRY_POINT_GROUP, *, replace: bool = False) -> DiscoveryReport:
    loaded: list[str] = []
    skipped: list[str] = []
    failed: dict[str, str] = {}
    for ep in sorted(_iter_entry_points(group), key=lambda e: (e.name, getattr(e, "value", ""))):
        dist = getattr(getattr(ep, "dist", None), "name", "") or ""
        try:
            for kind in _kinds_from(ep.load()):
                validate_kind(kind)
                if kind.name in TASK_KINDS and not replace:
                    skipped.append(kind.name)
                    continue
                register_kind(kind, replace=replace, source=f"entry-point:{dist or ep.name}")
                loaded.append(kind.name)
        except Exception as exc:  # noqa: BLE001 - collected, reported by name
            failed[ep.name] = f"{type(exc).__name__}: {exc}"
    return DiscoveryReport(group=group, loaded=tuple(loaded), skipped=tuple(skipped), failed=dict(sorted(failed.items())))


def ensure_discovered(config: Any = None, *, group: str | None = None) -> DiscoveryReport:
    """Run discovery once per process per group (idempotent); returns the cached report."""
    group = group or (config.tasks.entry_point_group if config is not None else DEFAULT_ENTRY_POINT_GROUP)
    with _DISCOVERY_LOCK:
        if group not in _DISCOVERED:
            _DISCOVERED[group] = discover_entry_points(group)
        return _DISCOVERED[group]


def reset_discovery() -> None:
    with _DISCOVERY_LOCK:
        _DISCOVERED.clear()


# --------------------------------------------------------------------------- execution
def stamp(result: TaskResult, *, producer_key: str, basis_hash: str | None = None, spec: TaskSpec | None = None,
          kind: Any = None) -> TaskResult:
    """Fill the producer key (and basis when the kind left it empty) on a result a kind returned.
    With ``spec`` and ``kind`` given the projection shape is checked first (Refused by name) and the
    result's ``basis_hash`` must be the spec's: a result stamped under another basis is refused."""
    if spec is not None and kind is not None:
        check_projection(kind, spec)
    if spec is not None and result.basis_hash and result.basis_hash != spec.basis_hash:
        raise Refused(f"basis-mismatch:{result.basis_hash[:12]}!={spec.basis_hash[:12]}")
    changes: dict[str, Any] = {"producer_key": producer_key}
    if basis_hash and not result.basis_hash:
        changes["basis_hash"] = basis_hash
    return dataclasses.replace(result, **changes)


def execute(kind: TaskKind | str, spec: TaskSpec, objects: ObjectStore, scratch: str, *, producer_key: str,
            config: Any = None, validate: bool = True) -> TaskResult:
    """Run ``kind`` on ``spec`` and always return a ``TaskResult`` (never raise for task-level failures)."""
    if isinstance(kind, str):
        kind = get_kind(kind, config=config)
    started = time.perf_counter()
    try:
        check_projection(kind, spec)                     # publish/verify/consume share this; here it is a REFUSED result by name
        if validate:
            validate_spec(spec, kind=kind, config=config)
        result = kind.run(spec, objects, scratch)
    except Refused as exc:
        result = TaskResult(task_id=spec.task_id, status=ResultStatus.REFUSED, outputs={}, producer_key="",
                            basis_hash=spec.basis_hash, elapsed_s=time.perf_counter() - started, reason=exc.reason,
                            candidates=tuple(exc.candidates))
    except DeadlineError as exc:
        result = TaskResult(task_id=spec.task_id, status=ResultStatus.TIMEOUT, outputs={}, producer_key="",
                            basis_hash=spec.basis_hash, elapsed_s=time.perf_counter() - started, reason=str(exc)[:200])
    except SpecError as exc:
        result = TaskResult(task_id=spec.task_id, status=ResultStatus.REFUSED, outputs={}, producer_key="",
                            basis_hash=spec.basis_hash, elapsed_s=time.perf_counter() - started, reason=f"spec-error:{exc}"[:200])
    except Exception as exc:  # noqa: BLE001 - recorded as ERROR, never the text
        tb = traceback.format_exc().encode("utf-8", "replace")
        result = TaskResult(task_id=spec.task_id, status=ResultStatus.ERROR, outputs={}, producer_key="",
                            basis_hash=spec.basis_hash, elapsed_s=time.perf_counter() - started,
                            reason=f"exception:{type(exc).__name__}",
                            metrics={"traceback_sha256": hashlib.sha256(tb).hexdigest(), "traceback_bytes": len(tb)})
    if result.task_id != spec.task_id:
        raise KindError(f"task kind {kind.name} returned a result for {result.task_id}, expected {spec.task_id}")
    return stamp(result, producer_key=producer_key, basis_hash=spec.basis_hash, spec=spec)


# --------------------------------------------------------------------------- describe
def describe_kind(name: str, *, config: Any = None) -> dict[str, Any]:
    kind = kind_class(name)
    cls = kind if inspect.isclass(kind) else type(kind)
    budget = BudgetClass(kind.budget)
    info: dict[str, Any] = {
        "name": kind.name, "version": int(kind.version), "budget": budget.value,
        "allowed_budgets": [BudgetClass(b).value for b in (getattr(kind, "allowed_budgets", ()) or (budget,))],
        "capabilities": sorted(kind.capabilities), "class": f"{cls.__module__}.{cls.__qualname__}",
        "source": kind_source(name), "doc": (inspect.getdoc(cls) or "").splitlines()[0] if inspect.getdoc(cls) else "",
        "params_schema": getattr(kind, "params_schema", {}),
        "inputs": list(getattr(kind, "input_names", ()) or ()), "outputs": list(getattr(kind, "output_names", ()) or ()),
        "verify_method": getattr(kind, "verify_method", ""),
        "basis_fields": list(getattr(kind, "basis_fields", ()) or ()) if getattr(kind, "basis_fields", None) is not None else None,
    }
    if config is not None:
        info["deadline_s"] = config.deadline_s(budget, kind.name)
    return info


def describe_kinds(config: Any = None, *, discover: bool | None = None) -> dict[str, Any]:
    """Every registered kind (after discovery when enabled) plus the discovery report."""
    do_discover = discover if discover is not None else (config.tasks.auto_discover if config is not None else True)
    report = ensure_discovered(config) if do_discover else None
    return {"kinds": {name: describe_kind(name, config=config) for name in kind_names()},
            "discovery": report.to_dict() if report else {"group": "", "loaded": [], "skipped": [], "failed": {}},
            "projections": projection_table()}


def kinds_for_capabilities(capabilities: Iterable[str], *, config: Any = None) -> list[str]:
    """Kinds a node holding ``capabilities`` may be offered (kind capabilities subset; budget offerable)."""
    have = set(capabilities)
    out: list[str] = []
    for name in kind_names():
        kind = kind_class(name)
        if not set(kind.capabilities) <= have:
            continue
        if config is not None:
            from .budget import offerable
            if not offerable(kind.budget, config)[0]:
                continue
        out.append(name)
    return out


__all__ = [
    "DEFAULT_ENTRY_POINT_GROUP", "KindError", "DiscoveryReport",
    "validate_kind", "validate_basis_fields", "check_projection", "projection_table", "register_kind", "unregister_kind",
    "kind_class", "get_kind", "kind_names", "kind_source",
    "discover_entry_points", "ensure_discovered", "reset_discovery",
    "stamp", "execute", "describe_kind", "describe_kinds", "kinds_for_capabilities",
]
