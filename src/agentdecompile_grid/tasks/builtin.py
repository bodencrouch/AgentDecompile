"""agentdecompile_grid.tasks.builtin — the three task kinds the skeleton and the canaries use.

===================  =======  ==============  ==========================================================
kind                 budget   capabilities    what
===================  =======  ==============  ==========================================================
``hash-object``      MICRO    ``python``      digest of input ``data`` -> output ``digest`` object
``python-canary``    MICRO    (none)          fixed fixture computation whose output ref is pinned
``subprocess-verb``  SMALL    (per spec)      run a declared argv over materialised inputs, collect outputs
                     /MEDIUM
===================  =======  ==============  ==========================================================

Every kind is pure: same inputs + basis -> same outputs, or a deterministic ``Refused``.  Kinds
return results with an empty ``producer_key``; ``tasks.registry.execute`` stamps it.

``hash-object`` and ``python-canary`` also carry a planner (``Kind.plan(objects, snapshot, *,
basis_hash, shard_size, max_budget, scratch, **options)``), the duck-typed contract ``adgrid
publish <kind>`` reaches without importing any lane: the snapshot is a file path (put into the
store, streamed) or a ``sha256:`` ref, and the plan is one task.  ``builtin_basis(kind)`` is the
basis a builtin kind gets when the caller names none: the kind and its version, nothing else
(these kinds depend on the interpreter only, which the ``python`` canary pins).

``subprocess-verb`` is the generic adapter the recovery pipeline's verbs (compile, parity check,
mkobj, link ...) will wrap.  Its parameter schema (``SubprocessVerbKind.params_schema``)::

    argv            [str]            required. Placeholders expanded at run time:
                                     {scratch} {cwd} {inputs_dir} {outputs_dir} {input:<name>} {output:<name>}
    inputs_layout   {name: relpath}  where each input object is materialised, relative to scratch
                                     (default "in/<name>"); no "..", no absolute paths
    outputs         {name: relpath | {"path": relpath, "required": bool}}
                                     files to collect after the run, relative to scratch (default required)
    env             {NAME: value}    fixed environment entries (deterministic; win over the allowlist)
    env_allowlist   [NAME]           host variables passed through (the builder fills it from tasks.env_allowlist)
    cwd             relpath          working directory relative to scratch (default "work")
    deadline_s      number           the verb's own timeout; must not exceed the class deadline
    stdin           name | null      input whose bytes feed stdin
    expected_exit   [int]            exit codes that mean OK (default [0]); others -> status ERROR "exit:<n>"
    capture_stdout  digest|object|none  (the builder fills it from tasks.capture_stdout)
    capture_stderr  digest|object|none  (from tasks.capture_stderr; never the text in a log record)
    verify          recompute|outputs-exist|none   (default recompute)

The base environment is deterministic (``LANG=C``, ``LC_ALL=C``, ``TZ=UTC``, ``PYTHONHASHSEED=0``,
``SOURCE_DATE_EPOCH=0``, ``HOME``/``TMPDIR`` inside scratch); ``PATH`` is only present when allowlisted
or fixed, and ``argv[0]`` is resolved with the host ``PATH`` when it is not absolute — the
*capability* the spec declares (``toolchain:<hash>`` ...) is what pins which binary that is.
Metrics: ``exit_code``, ``stdout_sha256``/``stdout_bytes``, ``stderr_sha256``/``stderr_bytes``,
``timed_out``.  Nothing in a result carries a scratch path.

Acceptance tests (named here, landed in the verification phase):

* ``test_hash_object_run_and_verify_recompute``.
* ``test_python_canary_output_matches_pinned_digest_on_this_interpreter``.
* ``test_subprocess_verb_materialises_inputs_collects_outputs_and_digests_streams``.
* ``test_subprocess_verb_timeout_is_status_timeout_and_kills_process_group``.
* ``test_subprocess_verb_missing_required_output_is_error_by_name``.
* ``test_subprocess_verb_refuses_traversal_in_layout``.
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import signal
import subprocess
import time
from typing import Any, Mapping, Sequence

from ..core import (
    BudgetClass, ObjectRef, ObjectStore, Refused, ResultStatus, TaskResult, TaskSpec, Verification, VerificationOutcome,
    canonical_json, digest, digest_value, task_kind,
)
from ..objects.base import ObjectMissing, validate_name
from .spec import (
    SpecError, build_spec, param_list, param_mapping, param_str, spec_for_kind, validate_spec,
)

PYTHON_CAPABILITY = "python"


def _result(spec: TaskSpec, status: ResultStatus, outputs: Mapping[str, ObjectRef], started: float, *,
            reason: str = "", metrics: Mapping[str, Any] | None = None,
            candidates: Sequence[Mapping[str, Any]] = ()) -> TaskResult:
    return TaskResult(task_id=spec.task_id, status=status, outputs=dict(sorted(outputs.items())), producer_key="",
                      basis_hash=spec.basis_hash, elapsed_s=time.perf_counter() - started, reason=reason,
                      candidates=tuple(candidates), metrics=dict(sorted((metrics or {}).items())))


def _verification(spec: TaskSpec, result_ref: ObjectRef, outcome: VerificationOutcome, method: str,
                  evidence: Mapping[str, Any]) -> Verification:
    return Verification(task_id=spec.task_id, result_ref=result_ref, outcome=outcome, verifier_key="", method=method,
                        evidence=dict(sorted(evidence.items())))


def _result_ref(result: TaskResult) -> ObjectRef:
    """The ref the result record has when written by ``tasks.results.write_result`` (for evidence)."""
    from .results import result_to_record
    return ObjectRef.of_bytes(canonical_json(result_to_record(result)))


def builtin_basis(kind: type) -> str:
    """The default basis of a builtin kind: its name and version (design 2.8: a basis names what
    the result depends on; these kinds depend on the pinned interpreter only)."""
    return digest_value({"basis": "builtin", "kind": kind.name, "kind_version": int(kind.version)})


def snapshot_ref(objects: ObjectStore, snapshot: Any) -> ObjectRef:
    """A planner's snapshot argument as an object: a ``sha256:`` ref that must exist, or a file path
    that is put (streamed when the store can)."""
    text = os.fspath(snapshot) if isinstance(snapshot, os.PathLike) else str(snapshot)
    if text.startswith("sha256:"):
        ref = ObjectRef(text)
        if not objects.exists(ref):
            raise Refused(f"snapshot-missing:{ref.hex[:12]}")
        return ref
    if not os.path.isfile(text):
        raise Refused("snapshot-not-a-file")
    put_path = getattr(objects, "put_path", None)
    if callable(put_path):
        return ObjectRef(put_path(text))
    with open(text, "rb") as fh:
        return objects.put(fh.read())


def _check_budget(kind: type, max_budget: BudgetClass | str) -> None:
    order = [BudgetClass.MICRO, BudgetClass.SMALL, BudgetClass.MEDIUM, BudgetClass.LARGE, BudgetClass.UNBOUNDED]
    if order.index(BudgetClass(kind.budget)) > order.index(BudgetClass(max_budget)):
        raise Refused(f"budget-exceeds-allowed:{kind.budget.value}>{BudgetClass(max_budget).value}")


# --------------------------------------------------------------------------- hash-object
@task_kind
class HashObjectKind:
    """Digest one input object; the output is a small JSON object naming algorithm, hex and size."""

    name = "hash-object"
    version = 1
    budget = BudgetClass.MICRO
    capabilities: Sequence[str] = (PYTHON_CAPABILITY,)
    input_names = ("data",)
    output_names = ("digest",)
    verify_method = "recompute"
    params_schema = {"type": "object", "properties": {
        "algorithm": {"type": "string", "default": "sha256", "enum": sorted(hashlib.algorithms_guaranteed)}},
        "additionalProperties": False}

    @staticmethod
    def validate_params(params: Mapping[str, Any]) -> None:
        extra = sorted(set(params) - {"algorithm"})
        if extra:
            raise SpecError(f"hash-object: unknown params {extra}")
        param_str(params, "algorithm", "sha256", choices=sorted(hashlib.algorithms_guaranteed))

    @classmethod
    def spec(cls, data: ObjectRef, basis_hash: str, *, algorithm: str = "sha256", config: Any = None,
             partition: str = "") -> TaskSpec:
        return spec_for_kind(cls, {"data": data}, {"algorithm": algorithm}, basis_hash, config=config, partition=partition)

    @classmethod
    def plan(cls, objects: ObjectStore, snapshot: Any, *, basis_hash: str | None = None, shard_size: int = 512,
             max_budget: BudgetClass | str = BudgetClass.SMALL, scratch: str | None = None, algorithm: str = "sha256",
             subject: str = "", config: Any = None, **options: Any) -> list[TaskSpec]:
        """One task: digest the snapshot object.  ``subject`` names the partition (default: the kind)."""
        extra = sorted(set(options))
        if extra:
            raise Refused(f"unknown-options:{','.join(extra)}")
        _check_budget(cls, max_budget)
        ref = snapshot_ref(objects, snapshot)
        return [cls.spec(ref, basis_hash or builtin_basis(cls), algorithm=algorithm, config=config, partition=subject)]

    def _compute(self, spec: TaskSpec, objects: ObjectStore) -> bytes:
        algorithm = param_str(spec.params, "algorithm", "sha256")
        if algorithm not in hashlib.algorithms_guaranteed:
            raise Refused(f"unknown-algorithm:{algorithm}")
        if "data" not in spec.inputs:
            raise Refused("input-missing:data")
        data = objects.get(spec.inputs["data"])
        h = hashlib.new(algorithm)
        h.update(data)
        hexdigest = h.hexdigest() if not algorithm.startswith("shake") else h.hexdigest(32)  # type: ignore[call-arg]
        return canonical_json({"algorithm": algorithm, "hex": hexdigest, "size": len(data)})

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        started = time.perf_counter()
        out = objects.put(self._compute(spec, objects))
        return _result(spec, ResultStatus.OK, {"digest": out}, started, metrics={"input_bytes": objects.size(spec.inputs["data"])})

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        expected = ObjectRef.of_bytes(self._compute(spec, objects))
        actual = result.outputs.get("digest")
        outcome = VerificationOutcome.VERIFIED if result.status is ResultStatus.OK and actual == expected else VerificationOutcome.REFUTED
        return _verification(spec, _result_ref(result), outcome, "recompute",
                             {"expected": str(expected), "actual": str(actual or ""), "status": result.status.value})


# --------------------------------------------------------------------------- python-canary
CANARY_FIXTURES: Mapping[str, str] = {
    # fixture name -> pinned ref of the output object on a conforming interpreter (filled below)
    "v1": "sha256:c9e352713c4926d9c21aec9ee5030ce295521e7d2f33b9227cacdffed902f05c",
}


def canary_fixture(name: str) -> bytes:
    """Deterministic computation exercising ints, IEEE doubles, hashing, unicode and canonical JSON.

    ``v1`` is arithmetic-only by design: every float operation is an IEEE-754 *basic* operation
    (add, divide, sqrt, ldexp — correctly rounded on every conforming platform) or CPython-native
    (``fsum``, shortest ``repr``), never a libm transcendental (no ``pow``/``exp``/``log``), so the
    pin proves the interpreter's arithmetic, not the host's libm.  A platform whose doubles differ
    (x87 double rounding, non-IEEE floats) fails the canary — which is the point.
    """
    if name != "v1":
        raise Refused(f"unknown-fixture:{name}")
    modulus = (1 << 61) - 1
    acc = 0
    for i in range(10_000):
        acc = (acc * 1_000_003 + i * i) % modulus
    chain = b"agentdecompile-grid-canary-v1"
    for _ in range(256):
        chain = hashlib.sha256(chain).digest()
    harmonic = 0.0
    for i in range(1, 1001):
        harmonic += 1.0 / i
    floats = [repr(harmonic), repr(math.sqrt(2.0)), repr(0.1 + 0.2), repr(1e16 + 1.0), repr(-0.0), repr(math.ldexp(1.0, -1074)),
              repr(math.fsum(0.1 for _ in range(10))), repr(1.0 / 3.0), repr(0.1 * 3.0)]
    text = canonical_json({"ü": "ß", "z": [3, 1, 2], "a": {"b": None, "c": True}, "é": "\U0001F600"})
    words = sorted({"pear", "Apple", "apple", "banana", "Äpfel", "zebra", "10", "9", "" }, key=lambda w: (w.casefold(), w))
    payload = {
        "fixture": name, "int_chain": acc, "sha_chain": chain.hex(), "floats": floats,
        "canonical_text_sha256": hashlib.sha256(text).hexdigest(), "sorted_words": words,
        "int_pow": pow(7, 4093, modulus), "bigint": str(2 ** 200), "divmod": list(divmod(-7, 3)),
        "round_half_even": [round(0.5), round(1.5), round(2.5)],
    }
    return canonical_json(payload)


@task_kind
class PythonCanaryKind:
    """Prove the ``python`` capability: compute a pinned fixture and compare its ref with the pin."""

    name = "python-canary"
    version = 1
    budget = BudgetClass.MICRO
    capabilities: Sequence[str] = ()
    input_names = ()
    output_names = ("fixture",)
    verify_method = "hash-lookup"
    params_schema = {"type": "object", "properties": {"fixture": {"type": "string", "default": "v1", "enum": sorted(CANARY_FIXTURES)}},
                     "additionalProperties": False}

    @staticmethod
    def validate_params(params: Mapping[str, Any]) -> None:
        extra = sorted(set(params) - {"fixture"})
        if extra:
            raise SpecError(f"python-canary: unknown params {extra}")
        param_str(params, "fixture", "v1")

    @classmethod
    def spec(cls, basis_hash: str, *, fixture: str = "v1", config: Any = None, partition: str = "") -> TaskSpec:
        return spec_for_kind(cls, {}, {"fixture": fixture}, basis_hash, config=config, partition=partition)

    @classmethod
    def plan(cls, objects: ObjectStore, snapshot: Any = None, *, basis_hash: str | None = None, shard_size: int = 512,
             max_budget: BudgetClass | str = BudgetClass.SMALL, scratch: str | None = None, fixture: str = "v1",
             subject: str = "", config: Any = None, **options: Any) -> list[TaskSpec]:
        """One task per call; the snapshot is ignored (the fixture is the input)."""
        extra = sorted(set(options))
        if extra:
            raise Refused(f"unknown-options:{','.join(extra)}")
        _check_budget(cls, max_budget)
        return [cls.spec(basis_hash or builtin_basis(cls), fixture=fixture, config=config, partition=subject)]

    @staticmethod
    def pinned_ref(fixture: str = "v1") -> ObjectRef:
        pinned = CANARY_FIXTURES.get(fixture, "")
        if not pinned:
            raise Refused(f"unknown-fixture:{fixture}")
        return ObjectRef(pinned)

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        started = time.perf_counter()
        fixture = param_str(spec.params, "fixture", "v1")
        out = objects.put(canary_fixture(fixture))
        matches = out == self.pinned_ref(fixture)
        return _result(spec, ResultStatus.OK, {"fixture": out}, started,
                       metrics={"matches_pinned": matches, "pinned": str(self.pinned_ref(fixture))})

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        fixture = param_str(spec.params, "fixture", "v1")
        pinned = self.pinned_ref(fixture)
        actual = result.outputs.get("fixture")
        outcome = VerificationOutcome.VERIFIED if result.status is ResultStatus.OK and actual == pinned else VerificationOutcome.REFUTED
        return _verification(spec, _result_ref(result), outcome, "hash-lookup", {"pinned": str(pinned), "actual": str(actual or "")})


class PythonCanary:
    """``core.Canary`` for the ``python`` capability: run the kind and compare with the pin (no key needed)."""

    capability = PYTHON_CAPABILITY

    def __init__(self, basis_hash: str = "canary", fixture: str = "v1") -> None:
        self.basis_hash = basis_hash
        self.fixture = fixture

    def prove(self, objects: ObjectStore, scratch: str) -> tuple[bool, Mapping[str, Any]]:
        spec = PythonCanaryKind.spec(self.basis_hash, fixture=self.fixture)
        result = PythonCanaryKind().run(spec, objects, scratch)
        pinned = PythonCanaryKind.pinned_ref(self.fixture)
        actual = result.outputs["fixture"]
        return actual == pinned, {"capability": self.capability, "fixture": self.fixture, "pinned": str(pinned),
                                  "actual": str(actual), "task_id": spec.task_id}


# --------------------------------------------------------------------------- subprocess-verb
BASE_ENV: Mapping[str, str] = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC", "PYTHONHASHSEED": "0", "SOURCE_DATE_EPOCH": "0",
                               "PYTHONDONTWRITEBYTECODE": "1"}
CAPTURE_CHOICES = ("digest", "object", "none")
VERIFY_CHOICES = ("recompute", "outputs-exist", "none")
PLACEHOLDER_KEYS = ("scratch", "cwd", "inputs_dir", "outputs_dir")


def safe_relpath(value: str, what: str) -> str:
    """A scratch-relative path: no absolute, no ``..``, no empty segment, normalised with ``/``."""
    if not isinstance(value, str) or not value:
        raise SpecError(f"{what}: must be a non-empty relative path")
    if value.startswith(("/", "\\")) or "\x00" in value or (len(value) > 1 and value[1] == ":"):
        raise SpecError(f"{what}: {value!r} must be relative to scratch")
    parts = value.replace("\\", "/").split("/")
    if any(p in ("", "..") for p in parts):
        raise SpecError(f"{what}: {value!r} has an empty or '..' segment")
    return "/".join(p for p in parts if p != ".") or "."


@task_kind
class SubprocessVerbKind:
    """Run a declared argv over materialised input objects and collect declared output files."""

    name = "subprocess-verb"
    version = 1
    budget = BudgetClass.SMALL
    allowed_budgets = (BudgetClass.MICRO, BudgetClass.SMALL, BudgetClass.MEDIUM)
    capabilities: Sequence[str] = ()
    input_names = ()          # declared per spec
    output_names = ()         # declared per spec (params.outputs)
    verify_method = "recompute"
    params_schema = {
        "type": "object",
        "required": ["argv", "outputs"],
        "additionalProperties": False,
        "properties": {
            "argv": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                     "description": "Command; placeholders {scratch} {cwd} {inputs_dir} {outputs_dir} {input:<name>} {output:<name>}"},
            "inputs_layout": {"type": "object", "additionalProperties": {"type": "string"},
                              "description": "input name -> scratch-relative path (default in/<name>)"},
            "outputs": {"type": "object", "additionalProperties": {"oneOf": [
                {"type": "string"}, {"type": "object", "properties": {"path": {"type": "string"}, "required": {"type": "boolean"}},
                                     "required": ["path"], "additionalProperties": False}]},
                        "description": "output name -> scratch-relative file to collect"},
            "env": {"type": "object", "additionalProperties": {"type": "string"}, "description": "fixed environment"},
            "env_allowlist": {"type": "array", "items": {"type": "string"}, "description": "host variables passed through"},
            "cwd": {"type": "string", "default": "work"},
            "deadline_s": {"type": "number", "description": "verb timeout; <= the class deadline"},
            "stdin": {"type": ["string", "null"], "description": "input name fed to stdin"},
            "expected_exit": {"type": "array", "items": {"type": "integer"}, "default": [0]},
            "capture_stdout": {"type": "string", "enum": list(CAPTURE_CHOICES)},
            "capture_stderr": {"type": "string", "enum": list(CAPTURE_CHOICES)},
            "verify": {"type": "string", "enum": list(VERIFY_CHOICES), "default": "recompute"},
        },
    }

    def __init__(self, config: Any = None) -> None:
        self.config = config

    # ---- params ------------------------------------------------------------------------------
    @classmethod
    def validate_params(cls, params: Mapping[str, Any]) -> None:
        extra = sorted(set(params) - set(cls.params_schema["properties"]))
        if extra:
            raise SpecError(f"subprocess-verb: unknown params {extra}")
        argv = param_list(params, "argv")
        if not argv or not all(isinstance(a, str) and a for a in argv):
            raise SpecError("subprocess-verb: argv must be a non-empty list of non-empty strings")
        for name, rel in param_mapping(params, "inputs_layout", {}).items():
            safe_relpath(rel if isinstance(rel, str) else "", f"inputs_layout.{name}")
        outputs = param_mapping(params, "outputs")
        for name, entry in outputs.items():
            validate_name(name)
            if isinstance(entry, str):
                safe_relpath(entry, f"outputs.{name}")
            elif isinstance(entry, Mapping):
                safe_relpath(str(entry.get("path", "")), f"outputs.{name}.path")
                if "required" in entry and not isinstance(entry["required"], bool):
                    raise SpecError(f"outputs.{name}.required must be a boolean")
                unknown = sorted(set(entry) - {"path", "required"})
                if unknown:
                    raise SpecError(f"outputs.{name}: unknown keys {unknown}")
            else:
                raise SpecError(f"outputs.{name}: expected a path or {{path, required}}")
        for key, value in param_mapping(params, "env", {}).items():
            if not isinstance(value, str) or "=" in key or not key:
                raise SpecError(f"env.{key}: values must be strings and names must not contain '='")
        param_list(params, "env_allowlist", [])
        safe_relpath(param_str(params, "cwd", "work"), "cwd")
        if "deadline_s" in params:
            from .spec import param_float
            if param_float(params, "deadline_s") <= 0:
                raise SpecError("deadline_s must be > 0")
        if params.get("stdin") is not None and not isinstance(params.get("stdin"), str):
            raise SpecError("stdin must be an input name or null")
        param_list(params, "expected_exit", [0], item_type=int)
        param_str(params, "capture_stdout", "digest", choices=CAPTURE_CHOICES)
        param_str(params, "capture_stderr", "digest", choices=CAPTURE_CHOICES)
        param_str(params, "verify", "recompute", choices=VERIFY_CHOICES)

    @classmethod
    def spec(cls, argv: Sequence[str], *, inputs: Mapping[str, ObjectRef] | None, outputs: Mapping[str, Any],
             basis_hash: str, budget: BudgetClass | str = BudgetClass.SMALL, capabilities: Sequence[str] = (),
             inputs_layout: Mapping[str, str] | None = None, env: Mapping[str, str] | None = None,
             env_allowlist: Sequence[str] | None = None, cwd: str = "work", deadline_s: float | None = None,
             stdin: str | None = None, expected_exit: Sequence[int] = (0,), capture_stdout: str | None = None,
             capture_stderr: str | None = None, verify: str = "recompute", partition: str = "",
             config: Any = None) -> TaskSpec:
        """Build a canonical spec for this kind.

        Every parameter that changes what runs or what is captured is written into ``params`` —
        node-config defaults (``tasks.env_allowlist``, ``tasks.capture_*``) are resolved *here*, at
        build time, so the task id covers them and two nodes never run one id differently.
        Optional parameters that do not affect execution when absent (``inputs_layout``, ``env``,
        ``deadline_s``, ``stdin``) are left out when not given, so ids stay stable.
        """
        tasks_cfg = config.tasks if config is not None else None
        params: dict[str, Any] = {
            "argv": list(argv), "outputs": dict(outputs), "cwd": cwd, "expected_exit": list(expected_exit), "verify": verify,
            "env_allowlist": sorted(env_allowlist if env_allowlist is not None else (tasks_cfg.env_allowlist if tasks_cfg else ())),
            "capture_stdout": capture_stdout or (tasks_cfg.capture_stdout if tasks_cfg else "digest"),
            "capture_stderr": capture_stderr or (tasks_cfg.capture_stderr if tasks_cfg else "digest"),
        }
        if inputs_layout:
            params["inputs_layout"] = dict(inputs_layout)
        if env:
            params["env"] = dict(env)
        if deadline_s is not None:
            params["deadline_s"] = float(deadline_s)
        if stdin is not None:
            params["stdin"] = stdin
        spec = build_spec(cls.name, inputs, params, basis_hash, kind_version=cls.version, capabilities=capabilities,
                          budget=budget, partition=partition, config=config)
        return validate_spec(spec, kind=cls, config=config)

    # ---- run ---------------------------------------------------------------------------------
    def _deadline(self, spec: TaskSpec) -> float | None:
        from .spec import param_float
        own = param_float(spec.params, "deadline_s") if "deadline_s" in spec.params else None
        class_limit = float(self.config.deadline_s(spec.budget, spec.kind)) if self.config is not None else None
        if own is not None and class_limit and own > class_limit:
            raise Refused(f"deadline-exceeds-class:{own}>{class_limit}")
        return own if own is not None else class_limit

    def _materialize(self, spec: TaskSpec, objects: ObjectStore, scratch: str, layout: Mapping[str, str]) -> dict[str, str]:
        paths: dict[str, str] = {}
        inputs_dir = os.path.join(scratch, "in")
        os.makedirs(inputs_dir, exist_ok=True)
        for name, ref in sorted(spec.inputs.items()):
            rel = safe_relpath(layout.get(name, f"in/{name}"), f"inputs_layout.{name}")
            dest = os.path.join(scratch, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            materialize = getattr(objects, "materialize", None)
            if callable(materialize):
                try:
                    materialize(ref, dest)
                except (ObjectMissing, KeyError):
                    raise
                except OSError:
                    with open(dest, "wb") as fh:
                        fh.write(objects.get(ref))
            else:
                with open(dest, "wb") as fh:
                    fh.write(objects.get(ref))
            paths[name] = dest
        return paths

    @staticmethod
    def _expand(template: str, table: Mapping[str, str]) -> str:
        out = template
        for key, value in table.items():
            out = out.replace("{" + key + "}", value)
        return out

    def _environment(self, spec: TaskSpec, scratch: str) -> dict[str, str]:
        allow = param_list(spec.params, "env_allowlist", [])   # params only: node config never changes what one id runs
        env = dict(BASE_ENV)
        env["HOME"] = os.path.join(scratch, "home")
        env["TMPDIR"] = os.path.join(scratch, "tmp")
        for key in sorted(allow):
            if key in os.environ:
                env[key] = os.environ[key]
        env.update(param_mapping(spec.params, "env", {}))
        return env

    def _execute(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> tuple[dict[str, Any], dict[str, ObjectRef], str]:
        """(metrics, outputs, failure_reason) — the shared body of run() and a recompute verify()."""
        params = spec.params
        layout = param_mapping(params, "inputs_layout", {})
        outputs_decl = param_mapping(params, "outputs")
        cwd_rel = safe_relpath(param_str(params, "cwd", "work"), "cwd")
        scratch = os.path.abspath(scratch)
        for sub in ("home", "tmp", "out", cwd_rel):
            os.makedirs(os.path.join(scratch, *sub.split("/")), exist_ok=True)
        input_paths = self._materialize(spec, objects, scratch, layout)
        cwd = os.path.join(scratch, *cwd_rel.split("/"))
        table: dict[str, str] = {"scratch": scratch, "cwd": cwd, "inputs_dir": os.path.join(scratch, "in"),
                                 "outputs_dir": os.path.join(scratch, "out")}
        for name, path in input_paths.items():
            table[f"input:{name}"] = path
        output_paths: dict[str, tuple[str, bool]] = {}
        for name, entry in sorted(outputs_decl.items()):
            rel = entry if isinstance(entry, str) else str(entry["path"])
            required = True if isinstance(entry, str) else bool(entry.get("required", True))
            path = os.path.join(scratch, *safe_relpath(rel, f"outputs.{name}").split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            output_paths[name] = (path, required)
            table[f"output:{name}"] = path
        argv = [self._expand(a, table) for a in param_list(params, "argv")]
        env = {k: self._expand(v, table) for k, v in self._environment(spec, scratch).items()}
        if not os.path.isabs(argv[0]) and os.sep not in argv[0]:
            resolved = shutil.which(argv[0], path=env.get("PATH") or os.environ.get("PATH"))
            if resolved is None:
                raise Refused(f"executable-not-found:{argv[0]}")
            argv[0] = resolved
        elif not os.path.isabs(argv[0]):
            argv[0] = os.path.join(cwd, argv[0])
        stdin_name = params.get("stdin")
        stdin_data = None
        if stdin_name is not None:
            if stdin_name not in input_paths:
                raise Refused(f"stdin-input-missing:{stdin_name}")
            with open(input_paths[stdin_name], "rb") as fh:
                stdin_data = fh.read()
        deadline = self._deadline(spec)
        capture_out = param_str(params, "capture_stdout", "digest")
        capture_err = param_str(params, "capture_stderr", "digest")
        started = time.perf_counter()
        timed_out = False
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = proc.communicate(input=stdin_data, timeout=deadline)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout, stderr = b"", b""
        elapsed = time.perf_counter() - started
        metrics: dict[str, Any] = {
            "exit_code": proc.returncode, "timed_out": timed_out, "wall_s": round(elapsed, 3),
            "stdout_sha256": digest(stdout), "stdout_bytes": len(stdout),
            "stderr_sha256": digest(stderr), "stderr_bytes": len(stderr),
        }
        outputs: dict[str, ObjectRef] = {}
        if capture_out == "object":
            outputs["stdout"] = objects.put(stdout)
        if capture_err == "object":
            outputs["stderr"] = objects.put(stderr)
        failure = ""
        if timed_out:
            failure = "timeout"
        missing_required: list[str] = []
        for name, (path, required) in sorted(output_paths.items()):
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    outputs[name] = objects.put(fh.read())
            elif required:
                missing_required.append(name)
        expected = param_list(params, "expected_exit", [0], item_type=int)
        if not failure and proc.returncode not in expected:
            failure = f"exit:{proc.returncode}"
        if not failure and missing_required:
            failure = f"output-missing:{','.join(missing_required)}"
        metrics["missing_outputs"] = missing_required
        return metrics, outputs, failure

    @staticmethod
    def _kill_group(proc: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, AttributeError):
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, AttributeError):
                proc.kill()

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        started = time.perf_counter()
        metrics, outputs, failure = self._execute(spec, objects, scratch)
        if failure == "timeout":
            return _result(spec, ResultStatus.TIMEOUT, outputs, started, reason="timeout", metrics=metrics)
        if failure:
            return _result(spec, ResultStatus.ERROR, outputs, started, reason=failure, metrics=metrics)
        return _result(spec, ResultStatus.OK, outputs, started, metrics=metrics)

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        mode = param_str(spec.params, "verify", "recompute", choices=VERIFY_CHOICES)
        ref = _result_ref(result)
        if mode == "none":
            return _verification(spec, ref, VerificationOutcome.UNVERIFIABLE, "none", {"reason": "verify=none"})
        if mode == "outputs-exist":
            missing = sorted(name for name, out in result.outputs.items() if not objects.exists(out))
            outcome = VerificationOutcome.VERIFIED if not missing and result.status is ResultStatus.OK else VerificationOutcome.REFUTED
            return _verification(spec, ref, outcome, "outputs-exist", {"missing": missing, "status": result.status.value})
        redo = os.path.join(scratch, "verify")
        os.makedirs(redo, exist_ok=True)
        metrics, outputs, failure = self._execute(spec, objects, redo)
        expected_status = ResultStatus.TIMEOUT if failure == "timeout" else (ResultStatus.ERROR if failure else ResultStatus.OK)
        same = (expected_status is result.status and dict(outputs) == dict(result.outputs)
                and (result.status is not ResultStatus.OK or metrics["exit_code"] == result.metrics.get("exit_code", 0)))
        return _verification(spec, ref, VerificationOutcome.VERIFIED if same else VerificationOutcome.REFUTED, "recompute",
                             {"expected_outputs": {k: str(v) for k, v in sorted(outputs.items())},
                              "claimed_outputs": {k: str(v) for k, v in sorted(result.outputs.items())},
                              "expected_status": expected_status.value, "claimed_status": result.status.value,
                              "exit_code": metrics["exit_code"]})


BUILTIN_KINDS: tuple[type, ...] = (HashObjectKind, PythonCanaryKind, SubprocessVerbKind)

__all__ = ["HashObjectKind", "PythonCanaryKind", "PythonCanary", "SubprocessVerbKind", "BUILTIN_KINDS",
           "CANARY_FIXTURES", "canary_fixture", "BASE_ENV", "safe_relpath", "PYTHON_CAPABILITY", "builtin_basis", "snapshot_ref"]
