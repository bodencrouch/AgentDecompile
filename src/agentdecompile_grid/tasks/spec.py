"""agentdecompile_grid.tasks.spec — builders and validators for ``TaskSpec``; canonical parameters.

``task_id = sha256(canonical(kind, kind_version, inputs, params, basis_projection))`` is only stable
if ``params`` (and the projection's values) are canonical *before* the ``TaskSpec`` exists.  ``core.TaskSpec.from_record`` does a
plain ``dict()`` and ``canonical_json`` only sorts keys, so normalisation lives here and every
builder in the grid goes through ``normalize_params``:

* **Floats become their ``repr`` string** (``tasks.float_policy = repr``): the canonical JSON then
  contains no float tokens, so ``1`` and ``1.0`` never collide, ``0.1`` is byte-identical from any
  language's encoder, and ``-0.0`` survives.  ``NaN``/``Infinity`` are refused by name.  Kinds
  read floats back with ``param_float``.  ``float_policy = refuse`` makes any float an error.
* **Keys are strings, sorted**; tuples become lists; ``Enum`` values are unwrapped; ``bytes`` are
  refused (make them an input object); anything else non-JSON is refused naming its type and path.
* **Portability** (``tasks.portability = strict``): a string that looks like an absolute path
  (``/...``, ``C:\\...``, ``\\\\...``, ``~/...``) is refused — a spec must mean the same thing on
  every node (the landed ``assert_portable_payload`` rule, applied at build time).
* Normalisation is idempotent: normalising a normalised document returns an equal document, so
  a spec read back from a record re-validates without changing its id.
* **Basis projection** (U158): ``spec_from_basis(kind, inputs, params, basis)`` is the canonical
  builder: ``basis_hash = digest(basis)`` (audit, on the spec and every record) and
  ``basis_projection = kind.basis_projection(basis)`` (in the id), values normalised like params.
  ``validate_spec(spec, kind=...)`` runs ``core.check_basis_projection``: the projection's keys must
  be exactly the kind's ``basis_fields``, refused by name otherwise — publish, execute, verify and
  the view applier all go through it.

Acceptance tests (named here, landed in the verification phase):

* ``test_normalize_params_floats_become_repr_strings_and_nan_refused``.
* ``test_normalize_params_is_idempotent_and_sorted``.
* ``test_build_spec_refuses_absolute_paths_by_name``.
* ``test_task_id_stable_across_param_key_order_and_input_order``.
* ``test_validate_spec_checks_budget_against_kind``.
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from ..core import (
    BudgetClass, GridError, ObjectRef, ObjectStore, TaskKind, TaskSpec, canonical_json, check_basis_projection, digest_value,
    kind_basis_projection,
)
from ..objects.base import InvalidRef, validate_ref

BASIS_RE = re.compile(r"^[A-Za-z0-9:._-]{1,128}$")
KIND_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
INPUT_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
PARTITION_RE = re.compile(r"^[A-Za-z0-9:._/-]{0,256}$")
ABSOLUTE_PATH_RE = re.compile(r"^(?:/|\\\\|[A-Za-z]:[\\/]|~[/\\]|~$)")
MAX_DEPTH = 32
SPEC_SCHEMA_VERSION = 1


class SpecError(GridError):
    """A spec or its parameters cannot be canonical; the message names the path and the rule."""


# --------------------------------------------------------------------------- canonical params
def normalize_value(value: Any, *, path: str = "params", float_policy: str = "repr", portability: str = "strict",
                    depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise SpecError(f"{path}: nesting deeper than {MAX_DEPTH}")
    if isinstance(value, Enum):
        value = value.value
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise SpecError(f"{path}: {value!r} is not a canonical number (NaN/Infinity refused)")
        if float_policy == "refuse":
            raise SpecError(f"{path}: floats are refused by tasks.float_policy=refuse; pass {value!r} as a string")
        if float_policy != "repr":
            raise SpecError(f"tasks.float_policy must be repr | refuse, got {float_policy!r}")
        return repr(float(value))
    if isinstance(value, str):
        if "\x00" in value:
            raise SpecError(f"{path}: NUL byte in string")
        if portability == "strict" and ABSOLUTE_PATH_RE.match(value):
            raise SpecError(f"{path}: {value[:60]!r} looks like an absolute path; specs must be portable "
                            f"(use a scratch-relative path or an input object; tasks.portability=off to allow)")
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise SpecError(f"{path}: bytes are not parameters; store them as an input object and pass its ref")
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key in value:
            if not isinstance(key, str):
                raise SpecError(f"{path}: key {key!r} is not a string")
            if "\x00" in key:
                raise SpecError(f"{path}: NUL byte in key")
        for key in sorted(value):
            out[key] = normalize_value(value[key], path=f"{path}.{key}", float_policy=float_policy,
                                       portability=portability, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=_sort_key) if isinstance(value, (set, frozenset)) else list(value)
        return [normalize_value(v, path=f"{path}[{i}]", float_policy=float_policy, portability=portability, depth=depth + 1)
                for i, v in enumerate(items)]
    raise SpecError(f"{path}: {type(value).__name__} is not a canonical parameter type "
                    f"(use null, bool, int, float, str, list or mapping)")


def _sort_key(value: Any) -> tuple[str, str]:
    return (type(value).__name__, json.dumps(value, sort_keys=True, default=str))


def normalize_params(params: Mapping[str, Any] | None, *, float_policy: str = "repr", portability: str = "strict",
                     max_bytes: int = 65_536, config: Any = None) -> dict[str, Any]:
    """Canonical parameter mapping (see module docstring).  Settings come from ``config.tasks`` when given."""
    if config is not None:
        float_policy = config.tasks.float_policy
        portability = config.tasks.portability
        max_bytes = config.tasks.max_param_bytes
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise SpecError(f"params must be a mapping, got {type(params).__name__}")
    out = normalize_value(params, float_policy=float_policy, portability=portability)
    encoded = canonical_json(out)
    if len(encoded) > max_bytes:
        raise SpecError(f"params canonical form is {len(encoded)} bytes; tasks.max_param_bytes is {max_bytes}")
    return out


def is_canonical(params: Mapping[str, Any], **kw: Any) -> bool:
    """True when ``normalize_params`` would return an equal document."""
    try:
        return normalize_params(params, **kw) == dict(params) and canonical_json(normalize_params(params, **kw)) == canonical_json(params)
    except SpecError:
        return False


# --------------------------------------------------------------------------- reading params back
def param_float(params: Mapping[str, Any], key: str, default: float | None = None) -> float:
    """Read a float that ``normalize_params`` stored as a repr string (ints and floats accepted too)."""
    if key not in params:
        if default is None:
            raise SpecError(f"params.{key}: missing")
        return float(default)
    value = params[key]
    if isinstance(value, bool):
        raise SpecError(f"params.{key}: expected a number, got a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            raise SpecError(f"params.{key}: {value!r} is not a number") from None
        if math.isnan(result) or math.isinf(result):
            raise SpecError(f"params.{key}: {value!r} is not finite")
        return result
    raise SpecError(f"params.{key}: expected a number, got {type(value).__name__}")


def param_int(params: Mapping[str, Any], key: str, default: int | None = None) -> int:
    if key not in params:
        if default is None:
            raise SpecError(f"params.{key}: missing")
        return int(default)
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpecError(f"params.{key}: expected an integer, got {type(value).__name__}")
    return value


def param_str(params: Mapping[str, Any], key: str, default: str | None = None, *, choices: Sequence[str] = ()) -> str:
    if key not in params:
        if default is None:
            raise SpecError(f"params.{key}: missing")
        value = default
    else:
        value = params[key]
    if not isinstance(value, str):
        raise SpecError(f"params.{key}: expected a string, got {type(value).__name__}")
    if choices and value not in choices:
        raise SpecError(f"params.{key}: {value!r} is not one of {list(choices)}")
    return value


def param_bool(params: Mapping[str, Any], key: str, default: bool | None = None) -> bool:
    if key not in params:
        if default is None:
            raise SpecError(f"params.{key}: missing")
        return bool(default)
    value = params[key]
    if not isinstance(value, bool):
        raise SpecError(f"params.{key}: expected a boolean, got {type(value).__name__}")
    return value


def param_list(params: Mapping[str, Any], key: str, default: Sequence[Any] | None = None, *, item_type: type = str) -> list[Any]:
    if key not in params:
        if default is None:
            raise SpecError(f"params.{key}: missing")
        return list(default)
    value = params[key]
    if not isinstance(value, list) or any(not isinstance(v, item_type) or isinstance(v, bool) and item_type is not bool for v in value):
        raise SpecError(f"params.{key}: expected a list of {item_type.__name__}")
    return list(value)


def param_mapping(params: Mapping[str, Any], key: str, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if key not in params:
        if default is None:
            raise SpecError(f"params.{key}: missing")
        return dict(default)
    value = params[key]
    if not isinstance(value, Mapping):
        raise SpecError(f"params.{key}: expected a mapping, got {type(value).__name__}")
    return dict(value)


# --------------------------------------------------------------------------- building
def validate_inputs(inputs: Mapping[str, Any] | None) -> dict[str, ObjectRef]:
    out: dict[str, ObjectRef] = {}
    for name in sorted(inputs or {}):
        if not isinstance(name, str) or not INPUT_NAME_RE.match(name):
            raise SpecError(f"inputs: name {name!r} must match {INPUT_NAME_RE.pattern}")
        try:
            out[name] = validate_ref(str((inputs or {})[name]))
        except InvalidRef as exc:
            raise SpecError(f"inputs.{name}: {exc}") from None
    return out


def validate_basis_hash(basis_hash: str) -> str:
    if not isinstance(basis_hash, str) or not BASIS_RE.match(basis_hash):
        raise SpecError(f"basis_hash must match {BASIS_RE.pattern}, got {basis_hash!r}")
    return basis_hash


def validate_kind_name(name: str) -> str:
    if not isinstance(name, str) or not KIND_NAME_RE.match(name):
        raise SpecError(f"kind name must match {KIND_NAME_RE.pattern}, got {name!r}")
    return name


def normalize_projection(projection: Mapping[str, Any] | None, *, config: Any = None) -> dict[str, Any]:
    """The basis projection with its values canonical like params (floats as repr strings, sorted keys)."""
    if projection is None:
        return {}
    if not isinstance(projection, Mapping):
        raise SpecError(f"basis_projection must be a mapping, got {type(projection).__name__}")
    float_policy = config.tasks.float_policy if config is not None else "repr"
    out: dict[str, Any] = {}
    for path in sorted(projection):
        if not isinstance(path, str) or not path:
            raise SpecError(f"basis_projection: key {path!r} is not a basis field path")
        out[path] = normalize_value(projection[path], path=f"basis_projection.{path}", float_policy=float_policy, portability="off")
    return out


def build_spec(kind: str, inputs: Mapping[str, Any] | None, params: Mapping[str, Any] | None, basis_hash: str, *,
               kind_version: int = 1, capabilities: Iterable[str] = (), budget: BudgetClass | str = BudgetClass.SMALL,
               partition: str = "", config: Any = None, basis_projection: Mapping[str, Any] | None = None) -> TaskSpec:
    """A canonical ``TaskSpec``: params normalised, inputs validated, capabilities sorted and deduplicated.
    ``basis_projection`` is the kind's declared slice of the basis (``spec_from_basis`` computes it);
    absent = the content-only projection ``{}`` that builtin kinds use."""
    validate_kind_name(kind)
    if isinstance(kind_version, bool) or not isinstance(kind_version, int) or kind_version < 1:
        raise SpecError(f"kind_version must be a positive int, got {kind_version!r}")
    caps = tuple(sorted({str(c) for c in capabilities}))
    for cap in caps:
        if not cap or any(ch.isspace() for ch in cap):
            raise SpecError(f"capabilities: {cap!r} is not a capability token")
    if not isinstance(partition, str) or not PARTITION_RE.match(partition):
        raise SpecError(f"partition must match {PARTITION_RE.pattern}")
    spec = TaskSpec(
        kind=kind, kind_version=int(kind_version), inputs=validate_inputs(inputs),
        params=normalize_params(params, config=config), basis_hash=validate_basis_hash(basis_hash),
        capabilities=caps, budget=BudgetClass(budget), partition=partition,
        basis_projection=normalize_projection(basis_projection, config=config),
    )
    return spec


def spec_for_kind(kind: TaskKind | type, inputs: Mapping[str, Any] | None, params: Mapping[str, Any] | None,
                  basis_hash: str, *, capabilities: Iterable[str] = (), budget: BudgetClass | str | None = None,
                  partition: str = "", config: Any = None, basis_projection: Mapping[str, Any] | None = None) -> TaskSpec:
    """``build_spec`` with version/budget/capabilities taken from the kind (extra capabilities merged in).
    Without ``basis_projection`` the kind must declare ``basis_fields == ()`` (content-only); a kind
    that declares fields needs ``spec_from_basis`` (or an explicit projection) or is refused by name."""
    caps = set(getattr(kind, "capabilities", ()) or ()) | set(capabilities)
    chosen = BudgetClass(budget) if budget is not None else BudgetClass(getattr(kind, "budget", BudgetClass.SMALL))
    spec = build_spec(kind.name, inputs, params, basis_hash, kind_version=int(kind.version), capabilities=caps,
                      budget=chosen, partition=partition, config=config, basis_projection=basis_projection)
    return validate_spec(spec, kind=kind, config=config)


def spec_from_basis(kind: TaskKind | type, inputs: Mapping[str, Any] | None, params: Mapping[str, Any] | None,
                    basis: Mapping[str, Any], *, capabilities: Iterable[str] = (), budget: BudgetClass | str | None = None,
                    partition: str = "", config: Any = None) -> TaskSpec:
    """The canonical builder from a *full* basis mapping (U158): ``basis_hash = digest(basis)`` for
    audit, ``basis_projection = kind.basis_projection(basis)`` for the id.  ``core.TaskSpec.from_basis``
    is the raw equivalent; this one canonicalises params and projection values and validates."""
    if not isinstance(basis, Mapping):
        raise SpecError(f"basis must be a mapping, got {type(basis).__name__}")
    projection = kind_basis_projection(kind, basis)
    return spec_for_kind(kind, inputs, params, digest_value(basis), capabilities=capabilities, budget=budget,
                         partition=partition, config=config, basis_projection=projection)


def allowed_budgets(kind: TaskKind | type) -> tuple[BudgetClass, ...]:
    """The classes a spec of this kind may declare: ``kind.allowed_budgets`` if present, else ``(kind.budget,)``."""
    declared = getattr(kind, "allowed_budgets", None)
    if declared:
        return tuple(BudgetClass(b) for b in declared)
    return (BudgetClass(getattr(kind, "budget", BudgetClass.SMALL)),)


def validate_spec(spec: TaskSpec, *, kind: TaskKind | type | None = None, config: Any = None) -> TaskSpec:
    """Re-check a spec (e.g. one read from a record): refs, canonical params, basis, budget vs kind."""
    validate_kind_name(spec.kind)
    validate_inputs(spec.inputs)
    validate_basis_hash(spec.basis_hash)
    canonical = normalize_params(spec.params, config=config)
    if canonical_json(canonical) != canonical_json(spec.params):
        raise SpecError(f"spec {spec.kind}: params are not canonical (floats as repr strings, sorted keys); rebuild with build_spec")
    projection = normalize_projection(spec.basis_projection, config=config)
    if canonical_json(projection) != canonical_json(dict(spec.basis_projection)):
        raise SpecError(f"spec {spec.kind}: basis_projection is not canonical; rebuild with spec_from_basis")
    budget = BudgetClass(spec.budget)
    if budget is BudgetClass.UNBOUNDED and not (config is not None and config.budgets.allow_unbounded):
        raise SpecError(f"spec {spec.kind}: budget 'unbounded' is never offered (budgets.allow_unbounded is off)")
    if kind is not None:
        if kind.name != spec.kind:
            raise SpecError(f"spec kind {spec.kind!r} does not match kind {kind.name!r}")
        if int(kind.version) != int(spec.kind_version):
            raise SpecError(f"spec {spec.kind}: kind_version {spec.kind_version} but the registered kind is version {kind.version}")
        if budget not in allowed_budgets(kind):
            raise SpecError(f"spec {spec.kind}: budget {budget.value!r} not in the kind's allowed budgets "
                            f"{[b.value for b in allowed_budgets(kind)]}")
        needed = set(getattr(kind, "capabilities", ()) or ())
        missing = sorted(needed - set(spec.capabilities))
        if missing:
            raise SpecError(f"spec {spec.kind}: kind requires capabilities {missing} which the spec does not declare")
        check_basis_projection(kind, spec)          # Refused by name: the projection keys must be the kind's basis_fields
        validator = getattr(kind, "validate_params", None)
        if callable(validator):
            validator(spec.params)
    return spec


# --------------------------------------------------------------------------- records and objects
def spec_to_record(spec: TaskSpec) -> dict[str, Any]:
    rec = spec.to_record()
    rec["schema"] = SPEC_SCHEMA_VERSION
    rec["record"] = "task"
    return rec


def spec_from_record(rec: Mapping[str, Any], *, config: Any = None) -> TaskSpec:
    """``TaskSpec.from_record`` followed by ``validate_spec`` and an id check when the record carries one.

    ``to_record`` writes ``partition_key`` (the kind name when ``partition`` is empty); an explicit
    partition equal to the kind name means the same thing, so it is folded back to ``""`` here and a
    written-then-read spec compares equal to the original.
    """
    spec = TaskSpec.from_record(rec)
    if spec.partition == spec.kind:
        spec = dataclasses.replace(spec, partition="")
    spec = validate_spec(spec, config=config)
    recorded = rec.get("task_id")
    if recorded and recorded != spec.task_id:
        raise SpecError(f"record task_id {recorded} does not match the spec's derived id {spec.task_id}")
    return spec


def write_spec(store: ObjectStore, spec: TaskSpec) -> ObjectRef:
    """Store the spec record as an object; returns its ref (deterministic for equal specs)."""
    return store.put(canonical_json(spec_to_record(spec)))


def read_spec(store: ObjectStore, ref: ObjectRef, *, config: Any = None) -> TaskSpec:
    return spec_from_record(json.loads(store.get(ref).decode("utf-8")), config=config)


def describe_spec(spec: TaskSpec) -> dict[str, Any]:
    rec = spec_to_record(spec)
    rec["partition_key"] = spec.partition_key
    rec["params_bytes"] = len(canonical_json(spec.params))
    return rec


__all__ = [
    "SpecError", "SPEC_SCHEMA_VERSION", "BASIS_RE", "KIND_NAME_RE", "INPUT_NAME_RE", "ABSOLUTE_PATH_RE",
    "normalize_value", "normalize_params", "is_canonical",
    "param_float", "param_int", "param_str", "param_bool", "param_list", "param_mapping",
    "validate_inputs", "validate_basis_hash", "validate_kind_name", "normalize_projection", "build_spec", "spec_for_kind",
    "spec_from_basis", "allowed_budgets",
    "validate_spec", "spec_to_record", "spec_from_record", "write_spec", "read_spec", "describe_spec",
]
