"""Bound one reference-free PE function to a reproducible target COFF object.

The receipt is a proposal about raw bytes, never source/parity acceptance. The
owned Python/grid runtime and its admitted object adapter remain trusted. This
fixed loaded-source check is deliberately limited to this lane's dependency
closure; it does not attest the interpreter or native SQLite implementation.
"""
from __future__ import annotations

import ast
import hashlib
import math
import os
import sqlite3
import stat
import struct
import sys
import tempfile
import time
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentdecompile_grid import core
from agentdecompile_grid.core import (
    BudgetClass, ObjectRef, ObjectStore, Refused, ResultStatus, TaskResult,
    TaskSpec, Verification, VerificationOutcome, canonical_json, digest, task_kind,
)
from agentdecompile_grid.objects.local import LocalDirStore

from ..corpus import (
    bsim_eval, cfg_signature, channel_confidence, determinism_basis as corpus_basis,
    export_hookpack, match_engine, mkobj, policy_tables,
    verify_recovered_byteexact as mapper,
)
from .. import symbol_map
from . import _common
from ._common import PlannableKind, verify_by_recompute

KIND = "mkobj-target"
VERSION = 1
MODE = "reference-free-only-v1"
SELECTION_SCHEMA = "agentdecompile.mkobj-target-selection/v1"
RECEIPT_SCHEMA = "agentdecompile.mkobj-target/v1"
IMPLEMENTATION_SCHEMA = "agentdecompile.mkobj-target-implementation/v1"
SNAPSHOT_LIMIT = 256 * 1024 * 1024
IMAGE_LIMIT = 128 * 1024 * 1024
FUNCTION_LIMIT = 64 * 1024
RECEIPT_LIMIT = 32 * 1024
TARGET_LIMIT = FUNCTION_LIMIT + 1024
SOURCE_LIMIT = 2 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
MAX_TIMEOUT = 60
PARAM_FIELDS = frozenset({"selection", "selection_sha256", "implementation_basis",
                          "implementation_sha256", "decoder_mode", "timeout_s"})
SELECTION_FIELDS = frozenset({"schema", "store_ref", "image_ref", "corpus_scope_sha256",
    "generation_sha256", "binary_id", "func_id", "addr", "size", "ranges",
    "report_version", "image_sha256"})


def _refuse(reason: str) -> None:
    raise Refused("mkobj_target_" + reason)


def _tick(deadline: float) -> None:
    if time.monotonic() >= deadline:
        _refuse("deadline_exceeded")


def _sha(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _ref(value: Any) -> ObjectRef:
    if not isinstance(value, str) or not value.startswith("sha256:") or not _sha(value[7:]):
        _refuse("invalid_spec")
    return ObjectRef(value)


def _integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= (1 << 63) - 1


def _timeout(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= MAX_TIMEOUT:
        _refuse("invalid_spec")
    return float(value)


def _stream(source: Any, limit: int, deadline: float, dest: Path | None = None) -> tuple[str, int]:
    """Read at most limit+1 bytes, optionally copying into a fresh independent file."""
    _tick(deadline)
    total = 0
    hasher = hashlib.sha256()
    info = os.fstat(source.fileno())
    if not stat.S_ISREG(info.st_mode):
        _refuse("input_unavailable")
    if info.st_size > limit:
        _refuse("input_limit_exceeded")
    output = dest.open("xb") if dest is not None else None
    try:
        while True:
            _tick(deadline)
            block = source.read(min(CHUNK_SIZE, limit + 1 - total))
            if not block:
                break
            total += len(block)
            if total > limit:
                _refuse("input_limit_exceeded")
            hasher.update(block)
            if output is not None:
                output.write(block)
    finally:
        if output is not None:
            output.close()
    _tick(deadline)
    return hasher.hexdigest(), total


def _read_file(path: Path, limit: int, deadline: float) -> tuple[str, int]:
    with path.open("rb") as source:
        return _stream(source, limit, deadline)


def _local_copy(objects: LocalDirStore, ref: ObjectRef, dest: Path, limit: int, deadline: float) -> tuple[str, int]:
    """Walk below the local store root without following object/shard symlinks."""
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        _refuse("input_unavailable")
    root = Path(objects.root).absolute()
    path = Path(objects.path_for(ref)).absolute()
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise Refused("mkobj_target_input_unavailable") from exc
    if ".." in relative.parts or not relative.parts:
        _refuse("input_unavailable")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            _tick(deadline)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as source:
            return _stream(source, limit, deadline, dest)
    finally:
        os.close(directory)


def _materialize(objects: ObjectStore, ref: ObjectRef, dest: Path, limit: int, deadline: float) -> Path:
    """v1 has one bounded adapter route; never call arbitrary unbounded get()."""
    _tick(deadline)
    if not isinstance(objects, LocalDirStore):
        _refuse("input_unavailable")
    try:
        declared = objects.size(ref)
        if type(declared) is not int or declared < 0:
            _refuse("input_unavailable")
        if declared > limit:
            _refuse("input_limit_exceeded")
        actual, size = _local_copy(objects, ref, dest, limit, deadline)
        if actual != ref.hex or size != declared:
            _refuse("input_integrity_failed")
    except Refused:
        raise
    except Exception as exc:
        raise Refused("mkobj_target_input_unavailable") from exc
    return dest


def _selection_shape(selection: Any) -> None:
    if type(selection) is not dict or set(selection) != SELECTION_FIELDS:
        _refuse("invalid_spec")
    if selection["schema"] != SELECTION_SCHEMA:
        _refuse("invalid_spec")
    for key in ("binary_id", "func_id", "size", "ranges"):
        if not _integer(selection[key], 1):
            _refuse("invalid_spec")
    if not _integer(selection["addr"]):
        _refuse("invalid_spec")
    if selection["ranges"] != 1:
        _refuse("extent_unsupported")
    if selection["size"] > FUNCTION_LIMIT:
        _refuse("input_limit_exceeded")
    for key in ("image_sha256", "report_version", "corpus_scope_sha256", "generation_sha256"):
        if not _sha(selection[key]):
            _refuse("invalid_spec")
    _ref(selection["store_ref"])
    _ref(selection["image_ref"])


def _validate_spec(spec: TaskSpec) -> None:
    if (not isinstance(spec.inputs, Mapping) or not isinstance(spec.params, Mapping)
            or not isinstance(spec.capabilities, (tuple, list))
            or spec.kind != KIND or type(spec.kind_version) is not int or spec.kind_version != VERSION
            or spec.budget != BudgetClass.SMALL or not _sha(spec.basis_hash)
            or set(spec.inputs) != {"store", "image"} or set(spec.params) != PARAM_FIELDS):
        _refuse("invalid_spec")
    params = spec.params
    if params["decoder_mode"] != MODE:
        _refuse("decoder_unsupported")
    _timeout(params["timeout_s"])
    for key in ("selection_sha256", "implementation_sha256"):
        if not _sha(params[key]):
            _refuse("invalid_spec")
    if type(params["implementation_basis"]) is not dict:
        _refuse("invalid_spec")
    _selection_shape(params["selection"])
    if digest(canonical_json(params["selection"])) != params["selection_sha256"]:
        _refuse("selection_mismatch")
    if digest(canonical_json(params["implementation_basis"])) != params["implementation_sha256"]:
        _refuse("implementation_mismatch")
    if tuple(spec.capabilities) != MkobjTarget.required_capabilities(spec):
        _refuse("invalid_spec")
    for name in ("store", "image"):
        if _ref(spec.inputs[name]) != params["selection"][name + "_ref"]:
            _refuse("selection_mismatch")


def _snapshot_selection(path: Path, store_ref: ObjectRef, image_ref: ObjectRef,
                        requested: dict, basis_hash: str, deadline: float) -> dict:
    """Only this verified, immutable SQLite file supplies physical membership."""
    _tick(deadline)
    try:
        con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)
        try:
            con.enable_load_extension(False)
            con.execute("PRAGMA trusted_schema=OFF")
            con.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            required = {
                "binary": {"id", "content_sha256", "slug", "md5", "analyzer_version", "processor_spec_hash", "basis_hash"},
                "func": {"id", "binary_id", "addr", "size", "ranges"},
            }
            for table, columns in required.items():
                schema = con.execute("SELECT type, sql FROM sqlite_master WHERE name=? LIMIT 2", (table,)).fetchall()
                if (len(schema) != 1 or schema[0][0] != "table" or not schema[0][1]
                        or not " ".join(schema[0][1].upper().split()).startswith("CREATE TABLE ")):
                    _refuse("snapshot_unsupported")
                if not columns <= {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}:
                    _refuse("snapshot_unsupported")
            binaries = con.execute("SELECT id, content_sha256 FROM binary WHERE id=? LIMIT 2",
                                   (requested["binary_id"],)).fetchall()
            functions = con.execute("SELECT id, binary_id, addr, size, ranges FROM func WHERE binary_id=? AND addr=? LIMIT 2",
                                    (requested["binary_id"], requested["addr"])).fetchall()
            if not binaries or not functions:
                _refuse("selection_missing")
            if len(binaries) != 1 or len(functions) != 1:
                _refuse("selection_ambiguous")
            binary_id, image_hash = binaries[0]
            func_id, owner_id, addr, size, ranges = functions[0]
            if (not _integer(binary_id, 1) or not _integer(func_id, 1) or not _integer(owner_id, 1)
                    or not _integer(addr) or not _integer(size, 1) or type(ranges) is not int or ranges != 1):
                _refuse("extent_unsupported")
            if size > FUNCTION_LIMIT:
                _refuse("input_limit_exceeded")
            if binary_id != requested["binary_id"] or owner_id != binary_id or addr != requested["addr"]:
                _refuse("selection_mismatch")
            if not _sha(image_hash) or image_hash != image_ref.hex or image_hash != requested["report_version"]:
                _refuse("image_mismatch")
            try:
                actual_basis = corpus_basis.basis_hash(con)
            except corpus_basis.BasisError as exc:
                raise Refused("mkobj_target_basis_mismatch") from exc
            if actual_basis != basis_hash:
                _refuse("basis_mismatch")
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        _tick(deadline)
        raise Refused("mkobj_target_execution_unavailable") from exc
    except sqlite3.DatabaseError as exc:
        _tick(deadline)
        raise Refused("mkobj_target_snapshot_unsupported") from exc
    _tick(deadline)
    return {"schema": SELECTION_SCHEMA, "store_ref": str(store_ref), "image_ref": str(image_ref),
            "corpus_scope_sha256": requested["corpus_scope_sha256"], "generation_sha256": requested["generation_sha256"],
            "binary_id": binary_id, "func_id": func_id, "addr": addr, "size": size, "ranges": ranges,
            "report_version": image_hash, "image_sha256": image_hash}


def _mapping(raw: bytes, selection: dict) -> dict:
    try:
        if raw[:2] != b"MZ":
            _refuse("format_unsupported")
        pe = struct.unpack_from("<I", raw, 0x3c)[0]
        if raw[pe:pe + 4] != b"PE\0\0":
            _refuse("format_unsupported")
        machine = struct.unpack_from("<H", raw, pe + 4)[0]
        magic = struct.unpack_from("<H", raw, pe + 24)[0]
    except struct.error as exc:
        raise Refused("mkobj_target_format_unsupported") from exc
    formats = {(0x14c, 0x10b): ("coff-i386", 32), (0x8664, 0x20b): ("coff-x86-64", 64)}
    if (machine, magic) not in formats:
        _refuse("format_unsupported")
    fmt, width = formats[(machine, magic)]
    if selection["addr"] + selection["size"] > 1 << width:
        _refuse("extent_unsupported")
    offset = mapper.file_region_offset(raw, selection["addr"], selection["size"])
    if offset is None:
        _refuse("mapping_unsupported")
    return {"file_offset": offset, "machine": machine, "optional_magic": magic, "format": fmt}


def _typed(value: Any) -> Any:
    """Deterministic typed code constants; never marshal filenames/line tables."""
    if isinstance(value, types.CodeType):
        return ["code", _code_value(value)]
    if value is None or value is Ellipsis:
        return ["none" if value is None else "ellipsis"]
    if type(value) in (str, int, bool):
        return [type(value).__name__, value]
    if type(value) is float:
        return ["float", value.hex()]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [_typed(v) for v in value]
        if isinstance(value, (set, frozenset)):
            items.sort(key=canonical_json)
        return [type(value).__name__, items]
    if isinstance(value, dict):
        return ["dict", sorted([[_typed(k), _typed(v)] for k, v in value.items()], key=canonical_json)]
    _refuse("implementation_unavailable")


def _code_value(code: types.CodeType) -> dict:
    return {name: _typed(getattr(code, name, b"")) for name in (
        "co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals", "co_stacksize",
        "co_flags", "co_code", "co_consts", "co_names", "co_varnames", "co_freevars", "co_cellvars",
        "co_exceptiontable",
    )}


def _function(owner: Any, name: str) -> Any:
    value = owner
    for part in name.split("."):
        value = getattr(value, part)
    return value.fget if isinstance(value, property) else getattr(value, "__func__", value)


def _source_codes(code: types.CodeType, prefix: str = "") -> dict:
    result = {}
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            name = prefix + item.co_name
            result[name] = item
            result.update(_source_codes(item, name + "."))
    return result


def _source_defaults(tree: Any, prefix: str = "") -> dict:
    """The fixed closure uses literal defaults; never evaluate source expressions."""
    result = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            result.update(_source_defaults(node, prefix + node.name + "."))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Only inspect defaults for functions actually in the fixed closure.
            # Unrelated module helpers may use nonliteral defaults.
            result[prefix + node.name] = node.args
    return result


def _implementation(deadline: float) -> dict:
    """Reconcile captured source with fixed loaded helpers; no source execution."""
    _tick(deadline)
    source_hashes, code_hashes, constants = {}, {}, {}
    for module, names, constant_names in _CLOSURE:
        _tick(deadline)
        if sys.modules.get(module.__name__) is not module:
            _refuse("loaded_source_mismatch")
        parent_name, _, child_name = module.__name__.rpartition(".")
        if parent_name and getattr(sys.modules[parent_name], child_name, None) is not module:
            _refuse("loaded_source_mismatch")
        path = Path(module.__file__)
        try:
            with path.open("rb") as source:
                captured = source.read(SOURCE_LIMIT + 1)
            if len(captured) > SOURCE_LIMIT:
                _refuse("implementation_unavailable")
            compiled = compile(captured, "<mkobj-target-source>", "exec", dont_inherit=True, optimize=sys.flags.optimize)
            expected = _source_codes(compiled)
            defaults = _source_defaults(ast.parse(captured))
        except (OSError, SyntaxError, ValueError) as exc:
            raise Refused("mkobj_target_implementation_unavailable") from exc
        relative = module.__name__.replace(".", "/") + ".py"
        source_hashes[relative] = digest(captured)
        for name in names:
            loaded = _function(module, name)
            key = module.__name__ + "." + name
            if loaded is not _BINDINGS[key] or not isinstance(loaded, types.FunctionType):
                _refuse("loaded_source_mismatch")
            actual_code = _code_value(loaded.__code__)
            if name not in expected or actual_code != _code_value(expected[name]):
                _refuse("loaded_source_mismatch")
            try:
                args = defaults[name]
                positional = tuple(ast.literal_eval(value) for value in args.defaults) or None
                keywords = {arg.arg: ast.literal_eval(value) for arg, value in zip(args.kwonlyargs, args.kw_defaults)
                            if value is not None} or None
            except (KeyError, ValueError, TypeError) as exc:
                raise Refused("mkobj_target_implementation_unavailable") from exc
            if _typed(positional) != _typed(loaded.__defaults__) or _typed(keywords) != _typed(loaded.__kwdefaults__):
                _refuse("loaded_source_mismatch")
            code_hashes[key] = digest(canonical_json({"code": actual_code,
                "defaults": _typed(loaded.__defaults__), "kwdefaults": _typed(loaded.__kwdefaults__)}))
        for name in constant_names:
            constants[module.__name__ + "." + name] = _typed(getattr(module, name))
    # Imported aliases must still reference the checked grid/shared functions.
    if (canonical_json is not core.canonical_json or digest is not core.digest
            or verify_by_recompute is not _common.verify_by_recompute
            or ObjectRef is not core.ObjectRef or TaskSpec is not core.TaskSpec or TaskResult is not core.TaskResult
            or _common.ObjectRef is not core.ObjectRef or _common.canonical_json is not core.canonical_json
            or _common.digest is not core.digest
            or any(globals()[name] is not module for name, module in _MODULE_BINDINGS.items())):
        _refuse("loaded_source_mismatch")
    _tick(deadline)
    return {"schema": IMPLEMENTATION_SCHEMA, "kind": KIND, "kind_version": VERSION,
            "decoder_mode": MODE, "selection_schema": SELECTION_SCHEMA, "receipt_schema": RECEIPT_SCHEMA,
            "sources": source_hashes, "functions": code_hashes, "constants": constants,
            "python": {"implementation": sys.implementation.name, "cache_tag": sys.implementation.cache_tag,
                       "version": list(sys.version_info), "optimization": sys.flags.optimize},
            "sqlite_version": sqlite3.sqlite_version, "external_decoder": None, "external_decoder_dependencies": []}


def _unchanged(before: dict, deadline: float) -> None:
    try:
        after = _implementation(deadline)
    except Refused as exc:
        if exc.reason == "mkobj_target_deadline_exceeded":
            raise
        raise Refused("mkobj_target_implementation_changed") from exc
    if after != before:
        _refuse("implementation_changed")


def _receipt(spec: TaskSpec, mapping: dict, target_ref: ObjectRef, target_size: int, region_hash: str) -> dict:
    return {"schema": RECEIPT_SCHEMA, "claim": "raw_image_function_target_object", "status": "produced",
            "kind": KIND, "kind_version": VERSION, "task_id": spec.task_id, "basis_hash": spec.basis_hash,
            **{key: spec.params[key] for key in ("selection", "selection_sha256", "implementation_basis",
                                                "implementation_sha256", "decoder_mode")},
            "mapping": mapping, "symbol": f'F_{spec.params["selection"]["addr"]:x}',
            "target_ref": str(target_ref), "target_sha256": target_ref.hex, "target_size": target_size,
            "region_sha256": region_hash, "relocation_count": 0}


def _publish(objects: ObjectStore, data: bytes, deadline: float) -> ObjectRef:
    _tick(deadline)
    expected = ObjectRef.of_bytes(data)
    returned = objects.put(data)
    if returned != expected:
        _refuse("input_integrity_failed")
    _tick(deadline)
    return expected


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _verification(spec: TaskSpec, result: TaskResult, outcome: VerificationOutcome, reason: str) -> Verification:
    return Verification(task_id=spec.task_id, result_ref=ObjectRef.of_value(result.to_record()),
                        outcome=outcome, verifier_key="", method="mkobj-target-reference-free-v1",
                        evidence={"reason": "mkobj_target_" + reason})


@task_kind
class MkobjTarget(PlannableKind):
    name = KIND
    version = VERSION
    budget = BudgetClass.SMALL
    capabilities = ("mkobj-target-reference-free:<implementation_sha256>",)
    INPUTS = {"store": "immutable SQLite snapshot", "image": "immutable raw PE image"}
    INPUT_ROLES = {"store": "restricted", "image": "restricted"}
    OUTPUTS = {"target": "reference-free COFF object", "receipt": "raw image/function binding proposal"}
    OUTPUT_ROLES = {"target": "restricted", "receipt": "restricted"}

    @staticmethod
    def required_capabilities(spec: TaskSpec) -> tuple[str, ...]:
        return ("mkobj-target-reference-free:" + str(spec.params.get("implementation_sha256", "")),)

    @classmethod
    def describe(cls) -> dict:
        return {"kind": cls.name, "version": cls.version, "budget": cls.budget.value,
                "capabilities": list(cls.capabilities), "inputs": dict(cls.INPUTS),
                "input_roles": dict(cls.INPUT_ROLES), "outputs": dict(cls.OUTPUTS),
                "output_roles": dict(cls.OUTPUT_ROLES), "params": sorted(PARAM_FIELDS),
                "status": "working", "verify": "recompute exact target and canonical receipt"}

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        _validate_spec(spec)
        started = time.monotonic()
        deadline = started + _timeout(spec.params["timeout_s"])
        try:
            implementation = _implementation(deadline)
            if implementation != spec.params["implementation_basis"]:
                _refuse("implementation_mismatch")
            Path(scratch).mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="mkobj-target-", dir=scratch) as owned:
                root = Path(owned)
                store = _materialize(objects, _ref(spec.inputs["store"]), root / "store.sqlite", SNAPSHOT_LIMIT, deadline)
                image = _materialize(objects, _ref(spec.inputs["image"]), root / "image.bin", IMAGE_LIMIT, deadline)
                selection = _snapshot_selection(store, _ref(spec.inputs["store"]), _ref(spec.inputs["image"]),
                                                spec.params["selection"], spec.basis_hash, deadline)
                if selection != spec.params["selection"]:
                    _refuse("selection_mismatch")
                raw = image.read_bytes()  # independently owned, already bounded and authenticated
                mapping = _mapping(raw, selection)
                offset = mapping["file_offset"]
                region_hash = digest(raw[offset:offset + selection["size"]])
                _unchanged(implementation, deadline)
                try:
                    mkobj.write_object(binary=image, offset=offset, size=selection["size"],
                        name=f'F_{selection["addr"]:x}', output=root / "target.obj", symbol_prefix="",
                        format=mapping["format"], reference_free_only=True)
                except mkobj.MkobjRefusal as exc:
                    raise Refused("mkobj_target_" + exc.reason) from exc
                _tick(deadline)
                for path, key, limit in ((store, "store", SNAPSHOT_LIMIT), (image, "image", IMAGE_LIMIT)):
                    if _read_file(path, limit, deadline)[0] != _ref(spec.inputs[key]).hex:
                        _refuse("input_integrity_failed")
                output_hash, output_size = _read_file(root / "target.obj", TARGET_LIMIT, deadline)
                output = (root / "target.obj").read_bytes()
                if digest(output) != output_hash:
                    _refuse("input_integrity_failed")
                target_ref = ObjectRef("sha256:" + output_hash)
                receipt = canonical_json(_receipt(spec, mapping, target_ref, output_size, region_hash))
                if len(receipt) > RECEIPT_LIMIT:
                    _refuse("input_limit_exceeded")
                _unchanged(implementation, deadline)
                outputs = {"target": _publish(objects, output, deadline), "receipt": _publish(objects, receipt, deadline)}
                _unchanged(implementation, deadline)
                return TaskResult(spec.task_id, ResultStatus.OK, outputs, "", spec.basis_hash,
                                  time.monotonic() - started, reason="")
        except Refused:
            raise
        except Exception as exc:
            raise Refused("mkobj_target_execution_unavailable") from exc

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        try:
            _validate_spec(spec)
        except Refused as exc:
            return _verification(spec, result, VerificationOutcome.UNVERIFIABLE, exc.reason.removeprefix("mkobj_target_"))
        except (TypeError, ValueError, KeyError):
            return _verification(spec, result, VerificationOutcome.UNVERIFIABLE, "invalid_spec")
        if (result.task_id != spec.task_id or result.basis_hash != spec.basis_hash
                or result.status != ResultStatus.OK or result.reason != "" or set(result.outputs) != {"target", "receipt"}):
            return _verification(spec, result, VerificationOutcome.REFUTED, "proposal_binding_invalid")
        deadline = time.monotonic() + _timeout(spec.params["timeout_s"])
        try:
            Path(scratch).mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="mkobj-proposal-", dir=scratch) as owned:
                root = Path(owned)
                try:
                    target_ref, receipt_ref = _ref(result.outputs["target"]), _ref(result.outputs["receipt"])
                except Refused:
                    return _verification(spec, result, VerificationOutcome.REFUTED, "proposal_binding_invalid")
                try:
                    target_path = _materialize(objects, target_ref, root / "target.obj", TARGET_LIMIT, deadline)
                    receipt_path = _materialize(objects, receipt_ref, root / "receipt.json", RECEIPT_LIMIT, deadline)
                except Refused as exc:
                    corrupt = exc.reason in {"mkobj_target_input_integrity_failed", "mkobj_target_input_limit_exceeded"}
                    return _verification(spec, result, VerificationOutcome.REFUTED if corrupt else VerificationOutcome.UNVERIFIABLE,
                                         "proposal_binding_invalid" if corrupt else "proposal_unavailable")
                try:
                    encoded = receipt_path.read_bytes()
                    receipt = json_loads(encoded)
                    if type(receipt) is not dict or canonical_json(receipt) != encoded:
                        raise ValueError("noncanonical")
                    mapping = receipt["mapping"]
                    if (type(mapping) is not dict or set(mapping) != {"file_offset", "machine", "optional_magic", "format"}
                            or any(type(mapping[k]) is not int for k in ("file_offset", "machine", "optional_magic"))
                            or mapping["file_offset"] < 0 or type(mapping["format"]) is not str
                            or not _sha(receipt["region_sha256"])):
                        raise ValueError("mapping")
                    expected = _receipt(spec, mapping, target_ref, target_path.stat().st_size, receipt["region_sha256"])
                    if encoded != canonical_json(expected):
                        raise ValueError("binding")
                except (KeyError, TypeError, ValueError, UnicodeError):
                    return _verification(spec, result, VerificationOutcome.REFUTED, "proposal_binding_invalid")
            _tick(deadline)
            return verify_by_recompute(self, spec, result, objects, scratch, compare=("target", "receipt"),
                                       method="mkobj-target-reference-free-v1")
        except Exception as exc:
            reason = exc.reason.removeprefix("mkobj_target_") if isinstance(exc, Refused) else "execution_unavailable"
            return _verification(spec, result, VerificationOutcome.UNVERIFIABLE, reason)


def json_loads(encoded: bytes) -> Any:
    # A separate fixed helper keeps duplicate-key handling visible in the closure.
    import json
    return json.loads(encoded, object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def plan_mkobj_target(objects: ObjectStore, snapshot: Any, basis_hash: str, shard_size: int, **options: Any) -> list[TaskSpec]:
    required = {"binary_id", "addr", "image_ref", "corpus_scope_sha256", "generation_sha256", "report_version"}
    if (not required <= set(options) or set(options) - required - {"timeout_s"}
            or snapshot.flavour not in ("store", "object") or snapshot.ref is None
            or not _integer(options["binary_id"], 1) or not _integer(options["addr"]) or not _sha(basis_hash)):
        _refuse("invalid_spec")
    for key in ("corpus_scope_sha256", "generation_sha256", "report_version"):
        if not _sha(options[key]):
            _refuse("invalid_spec")
    timeout = _timeout(options.get("timeout_s", MAX_TIMEOUT))
    deadline = time.monotonic() + timeout
    store_ref, image_ref = _ref(snapshot.ref), _ref(options["image_ref"])
    try:
        implementation = _implementation(deadline)
        with tempfile.TemporaryDirectory(prefix="mkobj-plan-") as owned:
            root = Path(owned)
            store = _materialize(objects, store_ref, root / "store.sqlite", SNAPSHOT_LIMIT, deadline)
            image = _materialize(objects, image_ref, root / "image.bin", IMAGE_LIMIT, deadline)
            selection = _snapshot_selection(store, store_ref, image_ref, options, basis_hash, deadline)
            _selection_shape(selection)
            _mapping(image.read_bytes(), selection)
            _unchanged(implementation, deadline)
        implementation_hash = digest(canonical_json(implementation))
        params = {"selection": selection, "selection_sha256": digest(canonical_json(selection)),
                  "implementation_basis": implementation, "implementation_sha256": implementation_hash,
                  "decoder_mode": MODE, "timeout_s": timeout}
        spec = TaskSpec(KIND, VERSION, {"store": store_ref, "image": image_ref}, params, basis_hash,
                        capabilities=("mkobj-target-reference-free:" + implementation_hash,), budget=BudgetClass.SMALL)
        _validate_spec(spec)
        return [spec]
    except Refused:
        raise
    except Exception as exc:
        raise Refused("mkobj_target_execution_unavailable") from exc


# Fixed, reviewed closure. Function names are qualified within the named module;
# no caller supplies a resolver, callback, code list, or acceptance predicate.
_CLOSURE = (
    (sys.modules[__name__], (
        "_refuse", "_tick", "_sha", "_ref", "_integer", "_timeout", "_stream", "_read_file", "_local_copy", "_materialize",
        "_selection_shape", "_validate_spec", "_snapshot_selection", "_mapping", "_typed", "_code_value",
        "_function", "_source_codes", "_source_defaults", "_implementation", "_unchanged", "_receipt", "_publish", "_pairs",
        "_verification", "json_loads", "plan_mkobj_target", "MkobjTarget.required_capabilities",
        "MkobjTarget.run", "MkobjTarget.verify",
    ), ("KIND", "VERSION", "MODE", "SELECTION_SCHEMA", "RECEIPT_SCHEMA", "IMPLEMENTATION_SCHEMA",
        "SNAPSHOT_LIMIT", "IMAGE_LIMIT", "FUNCTION_LIMIT", "RECEIPT_LIMIT", "TARGET_LIMIT", "SOURCE_LIMIT",
        "CHUNK_SIZE", "MAX_TIMEOUT", "PARAM_FIELDS", "SELECTION_FIELDS")),
    (mkobj, ("_pc_relative_impossible", "find_call_targets", "write_object", "build_object", "symbol_name_field"),
        ("MACHINE", "_BRANCH_BYTES", "REL32_TYPE", "TEXT_CHARACTERISTICS", "SYMBOL_SIZE", "FILE_HEADER_SIZE",
         "SECTION_HEADER_SIZE", "IMAGE_SYM_CLASS_EXTERNAL", "IMAGE_SYM_CLASS_STATIC", "IMAGE_SYM_DTYPE_FUNCTION",
         "IMAGE_REL_I386_REL32", "IMAGE_REL_AMD64_REL32", "RELOCATION_ENTRY_SIZE")),
    (mapper, ("file_region_offset",), ()),
    (corpus_basis, ("basis_hash", "basis", "_identity_rows", "_group", "_fmt_groups", "basis_hash_for",
        "package_basis", "_check_present", "_without", "corpus_manifest_hash", "seeds"),
        ("BASIS_VERSION", "ALGORITHM_VERSION", "MASKING_RULE_VERSION", "ANALYZER_OPTIONS_HASH",
         "ANALYZER_TIMEOUT_POLICY", "ANALYZER_LOADER_REVISION", "TOOLCHAIN_IDENTITY_HASH", "PENDING_FIELDS",
         "BASIS_HASH_EXCLUDED", "_ABSENT")),
    (policy_tables, ("threshold_params", "_freeze"), ("BSIM_MARGIN", "BSIM_TINY_N_INSTR", "BSIM_TINY_SIM")),
    (bsim_eval, ("evaluate_pairs",), ("THRESH", "SIGNIF")),
    (export_hookpack, ("unique_window",), ()),
    (cfg_signature, (), ("_GOLDEN", "_SEED", "DEFAULT_SLACK")),
    (match_engine, (), ("PAIR_POLICY", "CONTENT_FLOOR", "CONTENT_FLOORS", "WEIGHTS", "MAX_STRING_DF", "MAX_CONST_DF")),
    (channel_confidence, (), ("BASE", "TINY_INSTR", "TINY_PENALTY", "NONUNIQUE_PENALTY", "TIGHT_MARGIN_PENALTY", "CHANNEL_BONUS")),
    (symbol_map, (), ("BSIM_TRUSTED_SIGNIFICANCE",)),
    (core, ("canonical_json", "digest", "digest_value", "ObjectRef.of_bytes", "ObjectRef.of_value",
            "TaskSpec.task_id", "TaskResult.to_record"), ("HASH_ALGORITHM",)),
    (_common, ("verify_by_recompute",), ()),
)
_BINDINGS = {module.__name__ + "." + name: _function(module, name)
             for module, names, _ in _CLOSURE for name in names}
_MODULE_BINDINGS = {name: globals()[name] for name in (
    "mkobj", "mapper", "corpus_basis", "policy_tables", "bsim_eval", "export_hookpack",
    "cfg_signature", "match_engine", "channel_confidence", "symbol_map", "core", "_common",
)}
