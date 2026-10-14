"""Bounded, read-only planning of the fixed native-region verification inputs.

This module authenticates a proposed P2 execution tuple; it neither runs the
checker nor qualifies a result.  Copying into the private job store is owned by
the later stage helper.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
from dataclasses import dataclass
from typing import Any

from agentdecompile_grid.core import NotConfigured, RecordType, canonical_json
from agentdecompile_grid.log.records import (
    BadSignature, InvalidPartition, SignerNotAuthorized, UnknownSigner, record_from_dict, record_to_dict,
    validate_partition, validate_record, verify_chain,
)
from agentdecompile_grid.log.signing import Keyring, authorize_record
from agentdecompile_grid.objects.base import validate_ref
from agentdecompile_recovery.corpus.current_native_region_admission import (
    NativeRegionAuthority, NativeRegionAuthorityError, NativeRegionReaderConfig,
    load_native_region_authority,
)

SEED_SCHEMA = "agentdecompile.native-region-verify-seed.v1"
PLAN_SCHEMA = "agentdecompile.native-region-verify-plan.v1"
KIB, MIB = 1024, 1024 * 1024
MAX_NS = (1 << 63) - 1
STAGE_NS = 100_000_000_000
TOTAL_NS = 600_000_000_000
RESERVE_NS = 410_000_000_000
LOADER_NS = 5_000_000_000
ROLES = (
    ("p2_task", 64 * KIB), ("p2_result", 64 * KIB),
    ("p2_proposed_receipt", MIB), ("p2_proposed_target_inventory", MIB),
    ("p2_proposed_candidate_inventory", MIB), ("target_task", 64 * KIB),
    ("target_result", 64 * KIB), ("parity_task", 64 * KIB),
    ("parity_result", 64 * KIB), ("target", 66_560), ("candidate", 64 * MIB),
    ("target_snapshot", 256 * MIB), ("target_image", 128 * MIB),
    ("target_proposed_receipt", 32 * KIB), ("parity_proposed_receipt", MIB),
    ("parity_proposed_raw", 4 * MIB),
)
ROLE_CAPS = dict(ROLES)
HEX = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[^\x00-\x1f\x7f]{1,256}\Z")
REASONS = frozenset({
    "invalid_selection", "invalid_seed", "unsupported_profile", "ambiguous_profile",
    "invalid_log", "ambiguous_selection", "signature_invalid", "signer_ineligible",
    "authority_changed", "log_changed", "object_changed", "schema_invalid",
    "tuple_mismatch", "object_hash_mismatch", "limit_exceeded", "deadline_exceeded",
    "input_unavailable", "authority_unavailable", "authority_invalid",
})


@dataclass(frozen=True)
class NativeRegionVerifySelection:
    partition: str
    task_record_ref: str
    result_record_ref: str
    result_ref: str


@dataclass(frozen=True)
class NativeRegionVerifySeed:
    schema: str
    selection: NativeRegionVerifySelection
    profile_id: str
    verifier_key: str
    admitted_at_ns: int
    absolute_deadline_ns: int

    def to_record(self) -> dict[str, Any]:
        return {"schema": self.schema, "selection": _selection_record(self.selection),
                "profile_id": self.profile_id, "verifier_key": self.verifier_key,
                "admitted_at_ns": self.admitted_at_ns,
                "absolute_deadline_ns": self.absolute_deadline_ns}


@dataclass(frozen=True)
class NativeRegionRole:
    role: str
    ref: str
    cap: int


@dataclass(frozen=True)
class NativeRegionVerifyPlan:
    schema: str
    selection: NativeRegionVerifySelection
    task_ref: str
    task_id: str
    basis_hash: str
    producer_key: str
    verifier_key: str
    profile_id: str
    profile_sha256: str
    profile_row_sha256: str
    admission_identity: str
    admission_generation: int
    admitted_at_ns: int
    absolute_deadline_ns: int
    stage_started_at_ns: int
    stage_deadline_ns: int
    roles: tuple[NativeRegionRole, ...]

    def to_record(self) -> dict[str, Any]:
        return {"schema": self.schema, "selection": _selection_record(self.selection),
                "task_ref": self.task_ref, "task_id": self.task_id,
                "basis_hash": self.basis_hash, "producer_key": self.producer_key,
                "verifier_key": self.verifier_key, "profile_id": self.profile_id,
                "profile_sha256": self.profile_sha256,
                "profile_row_sha256": self.profile_row_sha256,
                "admission_identity": self.admission_identity,
                "admission_generation": self.admission_generation,
                "admitted_at_ns": self.admitted_at_ns,
                "absolute_deadline_ns": self.absolute_deadline_ns,
                "stage_started_at_ns": self.stage_started_at_ns,
                "stage_deadline_ns": self.stage_deadline_ns,
                "roles": [{"role": row.role, "ref": row.ref, "cap": row.cap}
                          for row in self.roles]}


@dataclass(frozen=True)
class NativeRegionSourceObservation:
    ref: str
    size: int
    cap: int
    identity: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class NativeRegionLogObservation:
    sha256: str
    size: int
    identity: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class NativeRegionPlanRead:
    plan: NativeRegionVerifyPlan
    plan_bytes: bytes
    plan_sha256: str
    inline_task_bytes: bytes
    authority: NativeRegionAuthority
    source_objects: tuple[NativeRegionSourceObservation, ...]
    log_observation: NativeRegionLogObservation


class NativeRegionPlanError(ValueError):
    """Closed, path-free refusal returned by the planner."""

    def __init__(self, status: str, reason: str):
        self.status = status if status in ("failed", "unavailable") else "failed"
        self.reason = reason if reason in REASONS else "schema_invalid"
        super().__init__(self.reason)


class _Refusal(Exception):
    def __init__(self, status: str, reason: str):
        self.status, self.reason = status, reason


def _need(ok: bool, reason: str, status: str = "failed") -> None:
    if not ok:
        raise _Refusal(status, reason)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(st: os.stat_result) -> tuple[int, int, int, int, int]:
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def _id(value: Any) -> bool:
    if type(value) is not str or ID.fullmatch(value) is None:
        return False
    try:
        return len(value.encode("utf-8")) <= 256
    except UnicodeEncodeError:
        return False


def _hash(value: Any) -> bool:
    return type(value) is str and HEX.fullmatch(value) is not None


def _ref(value: Any) -> str:
    _need(type(value) is str and len(value) == 71 and value.startswith("sha256:")
          and _hash(value[7:]), "invalid_selection")
    return value


def _selection_record(value: NativeRegionVerifySelection) -> dict[str, str]:
    return {"partition": value.partition, "task_record_ref": value.task_record_ref,
            "result_record_ref": value.result_record_ref, "result_ref": value.result_ref}


def _validate_selection(value: Any) -> None:
    _need(type(value) is NativeRegionVerifySelection, "invalid_selection")
    try:
        size = len(value.partition.encode("utf-8")) if type(value.partition) is str else 0
    except UnicodeEncodeError:
        size = 0
    _need(0 < size <= 512 and "\\" not in value.partition and "\x00" not in value.partition,
          "invalid_selection")
    try:
        validate_partition(value.partition)
    except (InvalidPartition, ValueError, TypeError):
        raise _Refusal("failed", "invalid_selection")
    for field in ("task_record_ref", "result_record_ref", "result_ref"):
        _ref(getattr(value, field))


def _canonical_load(raw: bytes, cap: int, deadline_ns: int | None = None) -> Any:
    _need(type(raw) is bytes and len(raw) <= cap, "limit_exceeded", "unavailable")
    if deadline_ns is not None:
        _tick(deadline_ns)
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate")
            out[key] = value
        return out
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
        _depth(value, 0)
        _need(canonical_json(value) == raw, "schema_invalid")
        if deadline_ns is not None:
            _tick(deadline_ns)
        return value
    except _Refusal:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise _Refusal("failed", "schema_invalid")


def _depth(value: Any, depth: int) -> None:
    _need(depth <= 32, "limit_exceeded", "unavailable")
    if type(value) is dict:
        for key, item in value.items():
            _need(type(key) is str, "schema_invalid")
            _depth(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _depth(item, depth + 1)
    elif type(value) is float:
        _need(math.isfinite(value), "schema_invalid")


def _parts(path: str) -> tuple[str, ...]:
    _need(type(path) is str and path.startswith("/") and len(path.encode("utf-8")) <= 512
          and "\\" not in path and "~" not in path, "input_unavailable", "unavailable")
    parts = tuple(path.split("/")[1:])
    _need(bool(parts) and all(p not in ("", ".", "..") and not any(ord(c) < 32 or ord(c) == 127 for c in p)
                              for p in parts), "input_unavailable", "unavailable")
    return parts


def _read_path(path: str, cap: int, deadline_ns: int, *, chunk: int = 64 * KIB,
               aggregate: list[int] | None = None) -> tuple[bytes, tuple[int, int, int, int, int]]:
    _tick(deadline_ns)
    parts = _parts(path)
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        for part in parts[:-1]:
            _tick(deadline_ns)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode), "input_unavailable", "unavailable")
        _need(before.st_size <= cap, "limit_exceeded", "unavailable")
        if aggregate is not None:
            _need(aggregate[0] + before.st_size <= 512 * MIB,
                  "limit_exceeded", "unavailable")
        out, size = [], 0
        while True:
            _tick(deadline_ns)
            if size == cap:
                break
            read_size = min(chunk, cap - size)
            if aggregate is not None:
                remaining = 512 * MIB - aggregate[0]
                _need(remaining > 0, "limit_exceeded", "unavailable")
                read_size = min(read_size, remaining)
            block = os.read(fd, read_size)
            if not block:
                break
            size += len(block)
            _need(size <= cap, "limit_exceeded", "unavailable")
            if aggregate is not None:
                aggregate[0] += len(block)
                _need(aggregate[0] <= 512 * MIB, "limit_exceeded", "unavailable")
            out.append(block)
        after = os.fstat(fd)
        path_after = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        _need(_identity(before) == _identity(after) == _identity(path_after) and size == before.st_size,
              "input_unavailable", "unavailable")
        _tick(deadline_ns)
        return b"".join(out), _identity(after)
    except _Refusal:
        raise
    except OSError:
        raise _Refusal("unavailable", "input_unavailable")
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def _tick(deadline_ns: int, reserve_ns: int = 0) -> None:
    now = time.monotonic_ns()
    _need(now <= MAX_NS and now + reserve_ns < deadline_ns,
          "deadline_exceeded", "unavailable")


def begin_native_region_verify(selection: NativeRegionVerifySelection, *,
                               profile_id: str, verifier_key: str) -> NativeRegionVerifySeed:
    try:
        _validate_selection(selection)
        _need(_id(profile_id) and _id(verifier_key), "invalid_selection")
        admitted = time.monotonic_ns()
        _need(type(admitted) is int and 0 <= admitted <= MAX_NS - TOTAL_NS,
              "deadline_exceeded", "unavailable")
        copied = NativeRegionVerifySelection(selection.partition, selection.task_record_ref,
                                             selection.result_record_ref, selection.result_ref)
        return NativeRegionVerifySeed(SEED_SCHEMA, copied, profile_id, verifier_key,
                                      admitted, admitted + TOTAL_NS)
    except _Refusal as exc:
        raise NativeRegionPlanError(exc.status, exc.reason) from None


def _validate_seed(seed: Any) -> None:
    try:
        _need(type(seed) is NativeRegionVerifySeed and seed.schema == SEED_SCHEMA
              and type(seed.profile_id) is str and _id(seed.profile_id)
              and type(seed.verifier_key) is str and _id(seed.verifier_key), "invalid_seed")
        _validate_selection(seed.selection)
        for value in (seed.admitted_at_ns, seed.absolute_deadline_ns):
            _need(type(value) is int and 0 <= value <= MAX_NS, "invalid_seed")
        _need(seed.absolute_deadline_ns - seed.admitted_at_ns == TOTAL_NS, "invalid_seed")
        _need(len(canonical_json(seed.to_record())) <= 2 * KIB, "invalid_seed")
    except _Refusal as exc:
        raise NativeRegionPlanError(exc.status, exc.reason) from None


def _authority(cfg: NativeRegionReaderConfig, deadline_ns: int) -> NativeRegionAuthority:
    _tick(deadline_ns, LOADER_NS)
    try:
        value = load_native_region_authority(cfg)
    except NativeRegionAuthorityError as exc:
        raise _Refusal("failed" if exc.status == "failed" else "unavailable",
                       "authority_invalid" if exc.status == "failed" else "authority_unavailable")
    _tick(deadline_ns)
    _need(type(value) is NativeRegionAuthority, "authority_invalid")
    return value


def _profile(authority: NativeRegionAuthority, profile_id: str,
             deadline_ns: int) -> tuple[dict[str, Any], Any]:
    selected = []
    for entry in authority.profiles:
        row = _canonical_load(entry.profile_bytes, 64 * KIB, deadline_ns)
        _need(type(row) is dict, "unsupported_profile")
        if row.get("profile_id") == profile_id:
            selected.append((row, entry))
    _need(len(selected) == 1, "unsupported_profile" if not selected else "ambiguous_profile")
    row, evidence = selected[0]
    _need(type(evidence.profile_row_sha256) is str
          and evidence.profile_row_sha256 == _sha(canonical_json(row)), "unsupported_profile")
    _need(_hash(row.get("profile_sha256")) and _hash(row.get("implementation_source_sha256"))
          and _hash(row.get("launcher_sha256")) and _hash(row.get("filter_sha256"))
          and _hash(row.get("environment_sha256")) and _hash(row.get("entrypoint_sha256"))
          and _ref(row.get("root_inventory_ref")) == row.get("root_inventory_ref"), "unsupported_profile")
    return row, evidence


def _ring(authority: NativeRegionAuthority) -> Keyring:
    ring = Keyring(allow_null=False)
    for key in authority.public_keys:
        try:
            if key.filename.endswith(".pub"):
                actual = ring.add_ed25519_public(key.public_material, role=key.role)
            else:
                actual = ring.add_node_public(key.key_id, key.algorithm, key.public_material,
                                              role=key.role, lineage=key.lineage)
            _need(actual == key.key_id, "signer_ineligible")
        except _Refusal:
            raise
        except Exception:
            raise _Refusal("failed", "signer_ineligible")
    return ring


def _log(authority: NativeRegionAuthority, selection: NativeRegionVerifySelection,
         deadline_ns: int):
    path = authority.roots.log_root.rstrip("/") + "/" + selection.partition + "/records.jsonl"
    raw, identity = _read_path(path, 16 * MIB, deadline_ns)
    _need(raw.endswith(b"\n") and raw, "invalid_log", "unavailable")
    lines = raw.splitlines(keepends=True)
    _need(len(lines) <= 4096, "limit_exceeded", "unavailable")
    records, values = [], []
    for line in lines:
        _tick(deadline_ns)
        _need(len(line) <= 128 * KIB, "limit_exceeded", "unavailable")
        _need(line.endswith(b"\n"), "invalid_log", "unavailable")
        value = _canonical_load(line[:-1], 128 * KIB, deadline_ns)
        _need(type(value) is dict and set(value) == {
            "schema", "partition", "seq", "type", "body", "prev", "signer_key", "basis_hash", "signature"
        }, "invalid_log")
        _need(type(value["schema"]) is int and type(value["seq"]) is int and value["seq"] > 0
              and all(type(value[key]) is str for key in ("partition", "type", "prev", "signer_key",
                                                           "basis_hash", "signature"))
              and type(value["body"]) is dict and value["partition"] == selection.partition,
              "invalid_log")
        try:
            record = record_from_dict(value)
            validate_record(record)
        except Exception:
            raise _Refusal("failed", "invalid_log")
        _need(record_to_dict(record) == value and canonical_json(record_to_dict(record)) == line[:-1],
              "invalid_log")
        records.append(record)
        values.append(value)
    _need(records[0].seq == 1 and records[0].prev == "", "invalid_log", "unavailable")
    try:
        verify_chain(records, partition=selection.partition)
    except Exception:
        raise _Refusal("failed", "invalid_log")
    wanted = ((selection.task_record_ref, RecordType.TASK),
              (selection.result_record_ref, RecordType.RESULT))
    selected = []
    for ref, record_type in wanted:
        matches = [(record, value, line[:-1]) for record, value, line in zip(records, values, lines)
                   if _sha(line[:-1]) == ref[7:]]
        _need(len(matches) == 1, "ambiguous_selection" if matches else "input_unavailable",
              "failed" if matches else "unavailable")
        _need(matches[0][0].type == record_type, "invalid_log")
        selected.append(matches[0])
    task, result = selected
    _need(task[0].seq < result[0].seq, "ambiguous_selection")
    task_id = task[0].body.get("task_id")
    result_body = result[0].body
    _need(_id(task_id), "schema_invalid")
    _need(not any(r is not task[0] and r.type == RecordType.TASK and r.body.get("task_id") == task_id for r in records),
          "ambiguous_selection")
    _need(not any(r is not result[0] and r.type == RecordType.RESULT
                  and r.body.get("task_id") == task_id and r.body.get("result_ref") == selection.result_ref
                  for r in records), "ambiguous_selection")
    try:
        ring = _ring(authority)
        authorize_record(task[0], ring)
        authorize_record(result[0], ring)
    except UnknownSigner as exc:
        raise _Refusal("unavailable", "input_unavailable") from exc
    except NotConfigured as exc:
        raise _Refusal("unavailable", "input_unavailable") from exc
    except SignerNotAuthorized as exc:
        raise _Refusal("failed", "signer_ineligible") from exc
    except BadSignature as exc:
        raise _Refusal("failed", "signature_invalid") from exc
    except Exception as exc:
        raise _Refusal("failed", "signature_invalid") from exc
    _need(result_body.get("result_ref") == selection.result_ref, "tuple_mismatch")
    return raw, identity, records, task, result, ring


def _object_path(authority: NativeRegionAuthority, ref: str) -> str:
    hexdigest = ref[7:]
    layout = authority.layout
    parts = [hexdigest[i * layout.shard_width:(i + 1) * layout.shard_width]
             for i in range(layout.shard_depth)]
    return authority.roots.objects_root.rstrip("/") + "/objects/" + "/".join((*parts, hexdigest))


def _exact(value: Any, fields: set[str] | frozenset[str], reason: str = "schema_invalid") -> None:
    _need(type(value) is dict and set(value) == set(fields), reason)


def _task_doc(value: Any, *, kind: str, input_names: set[str], basis: str,
              param_names: set[str], budget: str, caps: list[str],
              optional_params: set[str] | None = None) -> dict[str, Any]:
    optional_params = optional_params or set()
    fields = {"task_id", "kind", "kind_version", "inputs", "params", "basis_hash",
              "capabilities", "budget", "partition"}
    _exact(value, fields)
    _need(all(type(value[name]) is str for name in ("task_id", "kind", "basis_hash", "budget", "partition"))
          and _hash(value["task_id"]) and type(value["kind_version"]) is int
          and value["kind_version"] == 1 and value["kind"] == kind
          and value["basis_hash"] == basis and type(value["inputs"]) is dict
          and set(value["inputs"]) == input_names and type(value["params"]) is dict
          and param_names <= set(value["params"]) <= param_names | optional_params
          and type(value["capabilities"]) is list
          and value["capabilities"] == caps and value["budget"] == budget,
          "tuple_mismatch")
    for ref in value["inputs"].values():
        _ref(ref)
    projection = {key: value[key] for key in ("kind", "kind_version", "inputs", "params", "basis_hash")}
    _need(_sha(canonical_json(projection)) == value["task_id"], "tuple_mismatch")
    return value


def _result_doc(value: Any, task: dict[str, Any], expected_outputs: set[str]) -> dict[str, Any]:
    _exact(value, {"task_id", "status", "outputs", "producer_key", "basis_hash", "elapsed_s",
                   "reason", "candidates", "metrics"})
    elapsed = value["elapsed_s"]
    _need(value["task_id"] == task["task_id"] and value["basis_hash"] == task["basis_hash"]
          and value["status"] == "ok" and value["reason"] == ""
          and _id(value["producer_key"]) and type(elapsed) in (int, float)
          and math.isfinite(elapsed) and 0 <= elapsed <= 600
          and type(value["outputs"]) is dict and set(value["outputs"]) == expected_outputs
          and type(value["candidates"]) is list and all(type(row) is dict for row in value["candidates"])
          and type(value["metrics"]) is dict, "tuple_mismatch")
    for ref in value["outputs"].values():
        _ref(ref)
    return value


def _target_receipt(value: Any, target_task: dict[str, Any], target_ref: str,
                    basis: str, task_id: str) -> dict[str, Any]:
    fields = {"schema", "claim", "status", "kind", "kind_version", "task_id", "basis_hash",
              "selection", "selection_sha256", "implementation_basis", "implementation_sha256",
              "decoder_mode", "mapping", "symbol", "target_ref", "target_sha256", "target_size",
              "region_sha256", "relocation_count"}
    _exact(value, fields)
    params = target_task["params"]
    selection = value["selection"]
    _need(value["schema"] == "agentdecompile.mkobj-target/v1"
          and value["claim"] == "raw_image_function_target_object" and value["status"] == "produced"
          and value["kind"] == "mkobj-target" and type(value["kind_version"]) is int
          and value["kind_version"] == 1 and value["task_id"] == task_id
          and value["basis_hash"] == basis and selection == params["selection"]
          and value["selection_sha256"] == params["selection_sha256"]
          and value["implementation_basis"] == params["implementation_basis"]
          and value["implementation_sha256"] == params["implementation_sha256"]
          and value["decoder_mode"] == "reference-free-only-v1"
          and type(value["mapping"]) is dict
          and set(value["mapping"]) == {"file_offset", "machine", "optional_magic", "format"}
          and all(type(value["mapping"][k]) is int and value["mapping"][k] >= 0
                  for k in ("file_offset", "machine", "optional_magic"))
          and value["mapping"]["machine"] == 0x14C
          and value["mapping"]["optional_magic"] == 0x10B
          and value["mapping"]["format"] == "coff-i386"
          and value["symbol"] == f'F_{selection["addr"]:x}'
          and value["target_ref"] == target_ref and value["target_sha256"] == target_ref[7:]
          and type(value["target_size"]) is int and 0 < value["target_size"] <= 66_560
          and _hash(value["region_sha256"]) and type(value["relocation_count"]) is int
          and value["relocation_count"] == 0, "tuple_mismatch")
    return value


def _p1_receipt(value: Any, parity_task: dict[str, Any], target_ref: str,
                candidate_ref: str, symbol: str, basis: str) -> dict[str, Any]:
    required = {"schema", "status", "differences", "message", "objdiffExit", "detailLevel",
                "kind", "kind_version", "verifier_id", "verifier", "sides", "symbol", "grade", "basis_hash"}
    allowed = required | {"mismatchHistogram", "instructionMismatchCount", "alignedDiff"}
    _need(type(value) is dict and required <= set(value) <= allowed, "schema_invalid")
    grade = value["grade"]
    _need(value["schema"] == "agentdecompile.verify-objdiff.v1"
          and value["kind"] == "parity-check" and type(value["kind_version"]) is int
          and value["kind_version"] == 1 and value["verifier_id"] == "parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81"
          and value["verifier"] == "native" and value["sides"] == {
              "target": target_ref[7:], "candidate": candidate_ref[7:]}
          and value["symbol"] == symbol and value["basis_hash"] == basis
          and grade in ("matched", "mismatched") and value["status"] == grade
          and type(value["differences"]) is int and type(value["objdiffExit"]) is int
          and value["objdiffExit"] == 0 and not value.get("fallback")
          and ((grade == "matched" and value["differences"] == 0)
               or (grade == "mismatched" and value["differences"] > 0))
          and value["message"] == ("Object files match" if grade == "matched" else "Object files do not match")
          and value["detailLevel"] in ("instruction", "scalar-only"),
          "tuple_mismatch")
    if "mismatchHistogram" in value:
        _need(type(value["mismatchHistogram"]) is dict
              and all(k in {"INSERTION", "DELETION", "REPLACEMENT", "OPCODE_MISMATCH", "ARGUMENT_MISMATCH"}
                      and type(v) is int and v > 0
                      for k, v in value["mismatchHistogram"].items()), "schema_invalid")
    if "instructionMismatchCount" in value:
        _need(type(value["instructionMismatchCount"]) is int and value["instructionMismatchCount"] >= 0,
              "schema_invalid")
        _need("mismatchHistogram" in value
              and value["instructionMismatchCount"] == sum(value["mismatchHistogram"].values()),
              "tuple_mismatch")
    if "alignedDiff" in value:
        _need(type(value["alignedDiff"]) is list and len(value["alignedDiff"]) <= 200,
              "schema_invalid")
        for row in value["alignedDiff"]:
            _exact(row, {"index", "target", "candidate", "diffKind", "differs"})
            _need(type(row["index"]) is int and row["index"] >= 0
                  and (row["target"] is None or type(row["target"]) is str)
                  and (row["candidate"] is None or type(row["candidate"]) is str)
                  and (row["diffKind"] is None or type(row["diffKind"]) is str)
                  and type(row["differs"]) is bool, "schema_invalid")
    _need(value["detailLevel"] == ("instruction" if value.get("mismatchHistogram") else "scalar-only"),
          "schema_invalid")
    return value


def _inventory(value: Any, ref: str, cap: int) -> dict[str, Any]:
    fields = {"schema", "policy", "object_ref", "object_sha256", "object_size", "header", "section",
              "symbols", "strings", "string_table", "intervals", "region", "relocations", "line_numbers",
              "dependencies", "file_metadata", "coverage_bytes", "unclassified_bytes", "metadata_differences"}
    _exact(value, fields)
    _need(type(value["region"]) is dict, "schema_invalid")
    _exact(value["region"], {"name", "section", "offset", "file_offset", "length", "sha256"})
    _need(type(value["region"]["name"]) is str, "schema_invalid")
    _need(value["schema"] == "agentdecompile.parity-region-inventory.v1"
          and value["policy"] == "coff-i386-register-leaf-v1"
          and value["object_ref"] == ref and value["object_sha256"] == ref[7:]
          and type(value["object_size"]) is int and 0 < value["object_size"] <= cap
          and type(value["header"]) is dict
          and set(value["header"]) == {"machine", "sections", "timestamp", "symbol_pointer", "symbol_slots",
                                       "optional_header_size", "characteristics"}
          and type(value["section"]) is dict
          and set(value["section"]) == {"name", "physical_address", "virtual_address", "size", "raw_pointer",
                                        "relocation_pointer", "relocation_count", "line_pointer", "line_count", "characteristics"}
          and type(value["symbols"]) is list and type(value["strings"]) is list
          and type(value["string_table"]) is dict and set(value["string_table"]) == {"offset", "size"}
          and type(value["intervals"]) is list and type(value["region"]) is dict
          and set(value["region"]) == {"name", "section", "offset", "file_offset", "length", "sha256"}
          and value["relocations"] == [] and value["line_numbers"] == [] and value["dependencies"] == []
          and (value["file_metadata"] is None or (type(value["file_metadata"]) is dict
               and set(value["file_metadata"]) == {"length", "sha256", "class"}
               and type(value["file_metadata"]["length"]) is int
               and 0 < value["file_metadata"]["length"] <= 4096
               and _hash(value["file_metadata"]["sha256"])
               and value["file_metadata"]["class"] == "file_metadata"))
          and type(value["coverage_bytes"]) is int and value["coverage_bytes"] == value["object_size"]
          and type(value["unclassified_bytes"]) is int and value["unclassified_bytes"] == 0
          and type(value["metadata_differences"]) is list
          and all(x in {"timestamp", "redundant_i386_characteristic", "file_offsets", "zero_alignment",
                        "symbol_order", "function_name_representation", "string_table_layout", "optional_file_metadata"}
                  for x in value["metadata_differences"])
          and value["metadata_differences"] == sorted(set(value["metadata_differences"])), "schema_invalid")
    _need(value["header"]["machine"] == 0x14C and value["header"]["sections"] == 1
          and value["header"]["optional_header_size"] == 0
          and value["header"]["characteristics"] in (0, 0x100)
          and 0 < value["header"]["symbol_slots"] <= 256
          and value["header"]["symbol_pointer"] > 0
          and value["section"]["name"] == ".text"
          and value["section"]["physical_address"] == value["section"]["virtual_address"] == 0
          and value["section"]["relocation_pointer"] == value["section"]["relocation_count"] == 0
          and value["section"]["line_pointer"] == value["section"]["line_count"] == 0
          and value["section"]["characteristics"] == 0x60500020
          and value["section"]["size"] == value["region"]["length"]
          and value["region"]["section"] == ".text" and value["region"]["offset"] == 0
          and value["region"]["file_offset"] == value["section"]["raw_pointer"]
          and value["section"]["raw_pointer"] >= 60
          and value["header"]["symbol_pointer"] >= value["section"]["raw_pointer"] + value["section"]["size"]
          and value["string_table"]["offset"] == value["header"]["symbol_pointer"]
              + value["header"]["symbol_slots"] * 18
          and 4 <= value["string_table"]["size"] <= 16 * KIB
          and value["string_table"]["offset"] + value["string_table"]["size"] == value["object_size"]
          and _hash(value["region"]["sha256"]), "tuple_mismatch")
    cursor = 0
    interval_classes = []
    for row in value["intervals"]:
        _exact(row, {"start", "end", "class", "sha256"})
        _need(type(row["start"]) is int and type(row["end"]) is int
              and row["start"] == cursor and row["start"] < row["end"] <= value["object_size"]
              and row["class"] in {"file_header", "section_table", "zero_alignment", "region",
                                    "symbol_table", "string_table"} and _hash(row["sha256"]), "schema_invalid")
        if row["class"] == "file_header":
            _need(row["start"] == 0 and row["end"] == 20, "tuple_mismatch")
        elif row["class"] == "section_table":
            _need(row["start"] == 20 and row["end"] == 60, "tuple_mismatch")
        elif row["class"] == "region":
            _need(row["start"] == value["region"]["file_offset"]
                  and row["end"] == row["start"] + value["region"]["length"], "tuple_mismatch")
        elif row["class"] == "symbol_table":
            symbol_end = value["header"]["symbol_pointer"] + value["header"]["symbol_slots"] * 18
            _need(row["start"] == value["header"]["symbol_pointer"]
                  and row["end"] == symbol_end, "tuple_mismatch")
        elif row["class"] == "string_table":
            _need(row["start"] == value["string_table"]["offset"]
                  and row["end"] == value["object_size"], "tuple_mismatch")
        elif row["class"] == "zero_alignment":
            _need(0 < row["end"] - row["start"] <= 3 and row["end"] % 4 == 0,
                  "schema_invalid")
        cursor = row["end"]
        interval_classes.append(row["class"])
    expected_intervals = ["file_header", "section_table"]
    if len(interval_classes) > 2 and interval_classes[2] == "zero_alignment":
        expected_intervals.append("zero_alignment")
    expected_intervals.append("region")
    region_index = interval_classes.index("region")
    if region_index + 1 < len(interval_classes) - 2:
        expected_intervals.append("zero_alignment")
    expected_intervals.extend(("symbol_table", "string_table"))
    _need(cursor == value["object_size"] and interval_classes == expected_intervals,
          "schema_invalid")
    for field in ("machine", "sections", "timestamp", "symbol_pointer", "symbol_slots",
                  "optional_header_size", "characteristics"):
        _need(type(value["header"][field]) is int and value["header"][field] >= 0, "schema_invalid")
    for field in ("physical_address", "virtual_address", "size", "raw_pointer", "relocation_pointer",
                  "relocation_count", "line_pointer", "line_count", "characteristics"):
        _need(type(value["section"][field]) is int and value["section"][field] >= 0, "schema_invalid")
    symbol_cursor = 0
    for symbol in value["symbols"]:
        _need(type(symbol) is dict, "schema_invalid")
        common = {"slot", "end_slot", "name", "name_field_hex", "string_offset", "value", "section",
                  "type", "storage_class", "aux_count", "class", "auxiliary_hex"}
        if symbol.get("class") == "file":
            common |= {"filename"}
        _exact(symbol, common)
        _need(type(symbol["slot"]) is int and type(symbol["end_slot"]) is int
              and 0 <= symbol["slot"] < symbol["end_slot"] <= value["header"]["symbol_slots"]
              and type(symbol["name"]) is str
              and type(symbol["name_field_hex"]) is str and len(symbol["name_field_hex"]) == 16
              and re.fullmatch(r"[0-9a-f]{16}", symbol["name_field_hex"]) is not None
              and (symbol["string_offset"] is None or (type(symbol["string_offset"]) is int
                   and 4 <= symbol["string_offset"] < value["string_table"]["size"]))
              and all(type(symbol[k]) is int for k in ("value", "section", "type", "storage_class", "aux_count"))
              and type(symbol["auxiliary_hex"]) is list
              and all(type(x) is str and len(x) % 2 == 0 and re.fullmatch(r"[0-9a-f]*", x) is not None
                      for x in symbol["auxiliary_hex"])
              and symbol["slot"] == symbol_cursor
              and symbol["end_slot"] == symbol["slot"] + symbol["aux_count"] + 1,
              "schema_invalid")
        symbol_cursor = symbol["end_slot"]
        if symbol["class"] == "file":
            _exact(symbol["filename"], {"length", "sha256", "class"})
            _need(type(symbol["filename"]["length"]) is int and _hash(symbol["filename"]["sha256"])
                  and symbol["filename"]["class"] == "file_metadata", "schema_invalid")
        else:
            _need(symbol["class"] in ("function", "section_definition"), "schema_invalid")
            if symbol["class"] == "function":
                _need(symbol["value"] == 0 and symbol["section"] == 1 and symbol["type"] == 0x20
                      and symbol["storage_class"] == 2 and symbol["aux_count"] == 0
                      and symbol["auxiliary_hex"] == [], "schema_invalid")
            else:
                _need(symbol["name"] == ".text" and symbol["value"] == 0 and symbol["section"] == 1
                      and symbol["type"] == 0 and symbol["storage_class"] == 3 and symbol["aux_count"] == 1
                      and len(symbol["auxiliary_hex"]) == 1 and len(symbol["auxiliary_hex"][0]) == 36,
                      "schema_invalid")
    string_refs = {}
    for string in value["strings"]:
        _exact(string, {"offset", "size", "name", "references"})
        _need(type(string["offset"]) is int and type(string["size"]) is int
              and type(string["name"]) is str and type(string["references"]) is list
              and all(type(slot) is int for slot in string["references"]), "schema_invalid")
        referenced_symbols = [symbol for symbol in value["symbols"]
                              if symbol["string_offset"] == string["offset"]]
        expected_slots = [symbol["slot"] for symbol in referenced_symbols]
        _need(len(expected_slots) == 1 and string["references"] == expected_slots
              and referenced_symbols[0]["name"] == string["name"], "tuple_mismatch")
        string_refs[string["offset"]] = string
    _need(all(symbol["string_offset"] is None or
              (symbol["string_offset"] in string_refs
               and string_refs[symbol["string_offset"]]["name"] == symbol["name"])
              for symbol in value["symbols"]), "tuple_mismatch")
    _need(all(type(value["string_table"][k]) is int and value["string_table"][k] >= 0
              for k in ("offset", "size"))
          and all(type(value["region"][k]) is int and value["region"][k] >= 0
                  for k in ("offset", "file_offset", "length"))
          and value["region"]["name"].startswith("F_")
          and value["region"]["length"] == value["section"]["size"], "schema_invalid")
    _need([row["offset"] for row in value["strings"]]
          == sorted({row["offset"] for row in value["strings"]})
          and all(4 <= row["offset"] < value["string_table"]["size"]
                  and 1 <= row["size"] <= 4097
                  and row["offset"] + row["size"] <= value["string_table"]["size"]
                  and row["name"].isascii() and 0 < len(row["name"]) <= 4096
                  and row["references"] for row in value["strings"]), "schema_invalid")
    _need(symbol_cursor == value["header"]["symbol_slots"], "schema_invalid")
    names = {item["name"] for item in value["symbols"]}
    _need(names in ({value["region"]["name"], ".text"},
                    {value["region"]["name"], ".text", ".file"})
          and value["region"]["name"].startswith("F_")
          and len([item for item in value["symbols"] if item["class"] == "function"]) == 1
          and len([item for item in value["symbols"] if item["class"] == "section_definition"]) == 1
          and len([item for item in value["symbols"] if item["class"] == "file"]) <= 1,
          "schema_invalid")
    file_symbols = [item["filename"] for item in value["symbols"] if item["class"] == "file"]
    if value["file_metadata"] is None:
        _need(not file_symbols, "schema_invalid")
    else:
        _need(len(file_symbols) == 1 and file_symbols[0] == value["file_metadata"], "schema_invalid")
    _need(all(entry["name"] == value["region"]["name"] and len(entry["references"]) == 1
              for entry in value["strings"]), "schema_invalid")
    return value


def _p2_receipt(value: Any, task_id: str, basis: str, inputs: dict[str, str],
                target_receipt_ref: str, p1_receipt_ref: str, p1_raw_ref: str,
                inventory_refs: dict[str, str]) -> dict[str, Any]:
    fields = set("schema kind kind_version task_id basis_hash checker_profile comparison_policy verifier_id upstream_commit upstream_asset_sha256 inputs prerequisites target_receipt_ref proposed_parity_receipt_ref proposed_parity_raw_ref objects target_selection selection_sha256 inventory_refs strict_report_sha256 section symbol region_length region_sha256 grade checker_grade byte_difference_count instruction_count relocation_count coverage_bytes unclassified_bytes metadata_differences comparison_scope reference_policy target_producer_scope runtime_admission source_binding linked_image_metadata".split())
    _exact(value, fields)
    _need(value["schema"] == "agentdecompile.parity-region.v1"
          and value["kind"] == "parity-region-check" and type(value["kind_version"]) is int
          and value["kind_version"] == 1 and value["task_id"] == task_id and value["basis_hash"] == basis
          and value["checker_profile"] == "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1"
          and value["comparison_policy"] == "coff-i386-register-leaf-v1"
          and value["verifier_id"] == "parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81"
          and value["inputs"] == inputs and value["target_receipt_ref"] == target_receipt_ref
          and value["proposed_parity_receipt_ref"] == p1_receipt_ref
          and value["proposed_parity_raw_ref"] == p1_raw_ref and value["inventory_refs"] == inventory_refs
          and value["upstream_commit"] == "784a16740a8a67b835b752ab867e76347d8a9691"
          and value["upstream_asset_sha256"] == "bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81",
          "tuple_mismatch")
    _exact(value["prerequisites"], {"target", "parity"})
    _exact(value["prerequisites"]["target"], {"task_id", "result_ref", "method"})
    _exact(value["prerequisites"]["parity"], {"task_id", "result_ref", "method"})
    _need(value["prerequisites"]["target"]["method"] == "mkobj-target-reference-free-v1"
          and value["prerequisites"]["parity"]["method"] == "parity-binding-v1"
          and value["prerequisites"]["target"]["result_ref"] == inputs["target_result"]
          and value["prerequisites"]["parity"]["result_ref"] == inputs["parity_result"], "tuple_mismatch")
    _exact(value["objects"], {"target", "candidate"})
    for side in ("target", "candidate"):
        _exact(value["objects"][side], {"sha256", "size"})
        _need(_hash(value["objects"][side]["sha256"]) and type(value["objects"][side]["size"]) is int
              and value["objects"][side]["size"] >= 0, "schema_invalid")
    selection_fields = {"image_sha256", "report_version", "binary_id", "func_id", "addr", "size"}
    _exact(value["target_selection"], selection_fields)
    _need(_hash(value["selection_sha256"]) and _hash(value["strict_report_sha256"])
          and all(_hash(value["target_selection"][x]) for x in ("image_sha256", "report_version"))
          and all(type(value["target_selection"][x]) is int and value["target_selection"][x] >= 0
                  for x in ("binary_id", "func_id", "addr", "size"))
          and value["section"] == ".text" and type(value["symbol"]) is str
          and re.fullmatch(r"F_[0-9a-f]+", value["symbol"]) is not None
          and type(value["region_length"]) is int and value["region_length"] > 0
          and type(value["region_sha256"]) is dict and set(value["region_sha256"]) == {"target", "candidate"}
          and all(_hash(x) for x in value["region_sha256"].values()), "schema_invalid")
    _need(value["grade"] in ("matched", "mismatched") and value["checker_grade"] in ("matched", "mismatched")
          and type(value["byte_difference_count"]) is int and value["byte_difference_count"] >= 0
          and ((value["grade"] == "matched" and value["byte_difference_count"] == 0)
               or (value["grade"] == "mismatched" and value["byte_difference_count"] > 0))
          and all(type(value[k]) is int and value[k] >= 0 for k in
                  ("relocation_count", "coverage_bytes", "unclassified_bytes"))
          and value["relocation_count"] == 0 and value["coverage_bytes"] == value["region_length"]
          and value["unclassified_bytes"] == 0 and type(value["metadata_differences"]) is list
          and value["comparison_scope"] == "complete-emitted-reference-free-region"
          and value["reference_policy"] == "coff-i386-register-leaf-v1"
          and value["target_producer_scope"] == "conservative-pc-relative-byte-screen"
          and value["runtime_admission"] == value["source_binding"] == value["linked_image_metadata"] == "not_evaluated",
          "tuple_mismatch")
    _exact(value["region_sha256"], {"target", "candidate"})
    _exact(value["instruction_count"], {"target", "candidate"})
    _need(all(type(v) is int and v > 0 for v in value["instruction_count"].values())
          and ((value["grade"] == "matched"
                and value["region_sha256"]["target"] == value["region_sha256"]["candidate"])
               or (value["grade"] == "mismatched"
                   and value["region_sha256"]["target"] != value["region_sha256"]["candidate"])),
          "tuple_mismatch")
    return value


def _cas(authority: NativeRegionAuthority, ref: str, cap: int, deadline_ns: int,
         budget: list[int]) -> tuple[int, tuple[int, int, int, int, int]]:
    _ref(ref)
    path = _object_path(authority, ref)
    parts = _parts(path)
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        for part in parts[:-1]:
            _tick(deadline_ns)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode), "input_unavailable", "unavailable")
        _need(before.st_size <= cap, "limit_exceeded", "unavailable")
        _need(budget[0] + before.st_size <= 512 * MIB, "limit_exceeded", "unavailable")
        size, h = 0, hashlib.sha256()
        while True:
            _tick(deadline_ns)
            if size == cap:
                break
            block = os.read(fd, min(64 * KIB, cap - size, 512 * MIB - budget[0]))
            if not block:
                break
            size += len(block)
            budget[0] += len(block)
            _need(size <= cap and budget[0] <= 512 * MIB, "limit_exceeded", "unavailable")
            h.update(block)
        after = os.fstat(fd)
        try:
            path_after = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except OSError:
            raise _Refusal("unavailable", "object_changed")
        _need(_identity(before) == _identity(after) == _identity(path_after) and size == before.st_size,
              "object_changed", "unavailable")
        _need(h.hexdigest() == ref[7:], "object_hash_mismatch")
        return size, _identity(after)
    except _Refusal:
        raise
    except OSError:
        raise _Refusal("unavailable", "input_unavailable")
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def _build_native_region_verify_plan(seed: NativeRegionVerifySeed, *,
                                     cfg: NativeRegionReaderConfig,
                                     stage_started_at_ns: int) -> NativeRegionPlanRead:
    _validate_seed(seed)
    _need(type(cfg) is NativeRegionReaderConfig, "authority_unavailable", "unavailable")
    now = time.monotonic_ns()
    _need(type(stage_started_at_ns) is int and 0 <= stage_started_at_ns <= MAX_NS
          and seed.admitted_at_ns <= stage_started_at_ns <= now < seed.absolute_deadline_ns,
          "invalid_seed")
    stage_deadline = min(stage_started_at_ns + STAGE_NS,
                         seed.absolute_deadline_ns - RESERVE_NS)
    _need(stage_deadline <= MAX_NS and now < stage_deadline, "deadline_exceeded", "unavailable")
    try:
        authority = _authority(cfg, stage_deadline)
        selected_log = _log(authority, seed.selection, stage_deadline)
        raw_log, log_identity, records, task_pair, result_pair, ring = selected_log
        task_record, task_json, task_envelope = task_pair
        result_record, result_json, result_envelope = result_pair
        _need(task_record.partition == seed.selection.partition and result_record.partition == seed.selection.partition,
              "tuple_mismatch")
        task_body = task_record.body
        result_body = result_record.body
        _need(type(task_body) is dict and type(result_body) is dict, "schema_invalid")
        _need(set(task_body) == {"task_id", "kind", "kind_version", "inputs", "params",
                                 "basis_hash", "capabilities", "budget", "partition"}
              and type(task_body["partition"]) is str
              and task_body["partition"] == seed.selection.partition, "tuple_mismatch")
        _need(set(result_body) == {"task_id", "kind", "status", "result_ref", "outputs",
                                   "producer_key", "producer_lineage", "elapsed_s", "deadline_s",
                                   "reason", "nonce"}, "schema_invalid")
        inline_task = canonical_json(task_body)
        _need(len(inline_task) <= 64 * KIB, "limit_exceeded", "unavailable")
        task_ref = "sha256:" + _sha(inline_task)
        task_id = task_body.get("task_id")
        _need(type(task_id) is str and _hash(task_id), "schema_invalid")
        projection = {key: task_body[key] for key in ("kind", "kind_version", "inputs", "params", "basis_hash")}
        _need(_sha(canonical_json(projection)) == task_id, "tuple_mismatch")
        _need(result_body.get("task_id") == task_id and result_body.get("result_ref") == seed.selection.result_ref,
              "tuple_mismatch")
        _need(result_body.get("status") == "ok" and result_body.get("reason") == ""
              and type(result_body.get("outputs")) is dict
              and result_body.get("kind") == "parity-region-check"
              and result_body.get("deadline_s") == 600
              and _id(result_body.get("nonce"))
              and type(result_body.get("producer_lineage")) is list
              and all(_id(key) for key in result_body["producer_lineage"])
              and type(result_body.get("elapsed_s")) in (int, float)
              and math.isfinite(result_body["elapsed_s"])
              and type(result_body.get("deadline_s")) in (int, float)
              and math.isfinite(result_body["deadline_s"])
              and 0 <= result_body["elapsed_s"] <= result_body["deadline_s"], "schema_invalid")
        result_ref = seed.selection.result_ref
        document_io = [0]
        cas_io = [0]
        basis = task_body.get("basis_hash")
        _need(_hash(basis), "schema_invalid")
        _need(task_record.basis_hash == basis and result_record.basis_hash == basis,
              "tuple_mismatch")
        producer = result_body.get("producer_key")
        _need(_id(producer) and result_record.signer_key == producer, "signer_ineligible")
        _need(task_body.get("kind") == "parity-region-check"
              and type(task_body.get("kind_version")) is int and task_body["kind_version"] == 1
              and task_body.get("budget") == "medium"
              and task_body.get("capabilities") == [
                  "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1",
                  "parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81"]
              and task_body.get("params") == {
                  "checker_profile": "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1",
                  "comparison_policy": "coff-i386-register-leaf-v1"}, "unsupported_profile")
        doc_identities: dict[str, tuple[int, int, int, int, int]] = {}
        p2_result_raw, doc_identities[result_ref] = _read_path(
            _object_path(authority, result_ref), ROLE_CAPS["p2_result"], stage_deadline,
            aggregate=document_io)
        p2_result = _canonical_load(p2_result_raw, ROLE_CAPS["p2_result"], stage_deadline)
        _need(type(p2_result) is dict and set(p2_result) == {
            "task_id", "status", "outputs", "producer_key", "basis_hash", "elapsed_s",
            "reason", "candidates", "metrics"
        }, "schema_invalid")
        _need(p2_result["task_id"] == task_id and p2_result["status"] == "ok"
              and p2_result["outputs"] == result_body["outputs"]
              and p2_result["producer_key"] == producer and p2_result["basis_hash"] == basis
              and type(p2_result["elapsed_s"]) in (int, float)
              and type(result_body.get("elapsed_s")) in (int, float)
              and type(p2_result["elapsed_s"]) is type(result_body["elapsed_s"])
              and p2_result["elapsed_s"] == result_body["elapsed_s"]
              and p2_result["reason"] == "" and type(p2_result["candidates"]) is list
              and all(type(item) is dict for item in p2_result["candidates"])
              and type(p2_result["metrics"]) is dict, "tuple_mismatch")
        profile, profile_auth = _profile(authority, seed.profile_id, stage_deadline)
        _need(profile["profile_id"] == seed.profile_id
              and profile["kind"] == "parity-region-check" and profile["kind_version"] == 1
              and profile["dispatch"] == "kind" and profile["method"] == "parity-region-coff-i386-leaf-v1"
              and profile["checker_profile"] == "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1"
              and profile["comparison_policy"] == "coff-i386-register-leaf-v1"
              and profile["verifier_id"] == "parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81",
              "unsupported_profile")
        _need(basis in profile["basis_hashes"] and producer in profile["producer_keys"]
              and seed.verifier_key in profile["verifier_keys"], "unsupported_profile")
        keys = {key.key_id: key for key in authority.public_keys}
        _need(producer in keys and seed.verifier_key in keys and task_record.signer_key in keys,
              "signer_ineligible")
        producer_meta, verifier_meta = keys[producer], keys[seed.verifier_key]
        task_meta = keys[task_record.signer_key]
        _need(producer_meta.role in ("node", "donor", "operator", "fleet"), "signer_ineligible")
        _need(task_record.signer_key in profile["task_operator_keys"]
              and task_meta.role in ("operator", "fleet"), "signer_ineligible")
        _need(result_body["producer_lineage"] == list(producer_meta.lineage), "tuple_mismatch")
        _need(verifier_meta.role in ("operator", "fleet") and producer != seed.verifier_key
              and producer_meta.public_material != verifier_meta.public_material
              and set(producer_meta.lineage).isdisjoint((seed.verifier_key, *verifier_meta.lineage)),
              "signer_ineligible")
        revocations = _canonical_load(authority.revocations_bytes, MIB, stage_deadline)
        checked_keys = {producer, seed.verifier_key, task_record.signer_key,
                        *producer_meta.lineage, *verifier_meta.lineage, *task_meta.lineage}
        _need(not any(key in revocations for key in checked_keys), "signer_ineligible")

        # Only the frozen P2 dependency graph is traversed. Every role survives aliasing;
        # the narrowest cap is used for the shared source observation.
        role_refs: dict[str, str] = {"p2_task": task_ref, "p2_result": result_ref}
        p2_inputs = task_body.get("inputs")
        _need(type(p2_inputs) is dict and set(p2_inputs) == {
            "target_task", "target_result", "parity_task", "parity_result", "target", "candidate"}, "schema_invalid")
        role_refs.update({k: _ref(v) for k, v in p2_inputs.items()})
        result_outputs = result_body["outputs"]
        _need(set(result_outputs) == {"receipt", "target_inventory", "candidate_inventory"}, "schema_invalid")
        role_refs["p2_proposed_receipt"] = _ref(result_outputs["receipt"])
        role_refs["p2_proposed_target_inventory"] = _ref(result_outputs["target_inventory"])
        role_refs["p2_proposed_candidate_inventory"] = _ref(result_outputs["candidate_inventory"])

        specs, results = {}, {}
        for name in ("target_task", "parity_task"):
            obj, doc_identities[role_refs[name]] = _read_path(
                _object_path(authority, role_refs[name]), ROLE_CAPS[name], stage_deadline,
                aggregate=document_io)
            specs[name] = _canonical_load(obj, ROLE_CAPS[name], stage_deadline)
        for name in ("target_result", "parity_result"):
            obj, doc_identities[role_refs[name]] = _read_path(
                _object_path(authority, role_refs[name]), ROLE_CAPS[name], stage_deadline,
                aggregate=document_io)
            results[name] = _canonical_load(obj, ROLE_CAPS[name], stage_deadline)
        _need(type(specs["target_task"].get("inputs")) is dict
              and set(specs["target_task"]["inputs"]) == {"store", "image"}, "schema_invalid")
        role_refs["target_snapshot"] = _ref(specs["target_task"]["inputs"]["store"])
        role_refs["target_image"] = _ref(specs["target_task"]["inputs"]["image"])
        target_params = specs["target_task"].get("params")
        _need(type(target_params) is dict and type(target_params.get("implementation_basis")) is dict,
              "schema_invalid")
        target_caps = ["mkobj-target-reference-free:" + str(target_params.get("implementation_sha256", ""))]
        target_task = _task_doc(specs["target_task"], kind="mkobj-target",
            input_names={"store", "image"}, basis=basis,
            param_names={"selection", "selection_sha256", "implementation_basis",
                         "implementation_sha256", "decoder_mode", "timeout_s"},
            budget="small", caps=target_caps)
        selection = target_task["params"]["selection"]
        _exact(selection, {"schema", "store_ref", "image_ref", "corpus_scope_sha256", "generation_sha256",
                           "binary_id", "func_id", "addr", "size", "ranges", "report_version", "image_sha256"})
        _need(selection["schema"] == "agentdecompile.mkobj-target-selection/v1"
              and all(type(selection[x]) is int and selection[x] >= 0 for x in ("addr", "size", "ranges"))
              and type(selection["binary_id"]) is int and selection["binary_id"] > 0
              and type(selection["func_id"]) is int and selection["func_id"] > 0
              and selection["size"] > 0 and selection["size"] <= 64 * KIB and selection["ranges"] == 1
              and all(_hash(selection[x]) for x in ("corpus_scope_sha256", "generation_sha256",
                                                     "report_version", "image_sha256"))
              and target_task["params"]["decoder_mode"] == "reference-free-only-v1"
              and type(target_task["params"]["timeout_s"]) in (int, float)
              and math.isfinite(target_task["params"]["timeout_s"])
              and 0 < target_task["params"]["timeout_s"] <= 60
              and target_task["params"]["selection_sha256"] == _sha(canonical_json(selection))
              and target_task["params"]["implementation_sha256"] == _sha(
                  canonical_json(target_task["params"]["implementation_basis"]))
              and selection["store_ref"] == target_task["inputs"]["store"]
              and selection["image_ref"] == target_task["inputs"]["image"], "tuple_mismatch")
        implementation = target_task["params"]["implementation_basis"]
        _exact(implementation, {"schema", "kind", "kind_version", "decoder_mode", "selection_schema",
                                "receipt_schema", "sources", "functions", "constants", "python",
                                "sqlite_version", "external_decoder", "external_decoder_dependencies"})
        _need(implementation["schema"] == "agentdecompile.mkobj-target-implementation/v1"
              and implementation["kind"] == "mkobj-target" and type(implementation["kind_version"]) is int
              and implementation["kind_version"] == 1
              and implementation["decoder_mode"] == "reference-free-only-v1"
              and implementation["selection_schema"] == "agentdecompile.mkobj-target-selection/v1"
              and implementation["receipt_schema"] == "agentdecompile.mkobj-target/v1"
              and type(implementation["sources"]) is dict and type(implementation["functions"]) is dict
              and type(implementation["constants"]) is dict and type(implementation["python"]) is dict
              and all(type(name) is str and _hash(digest) for name, digest in implementation["sources"].items())
              and all(type(name) is str and _hash(digest) for name, digest in implementation["functions"].items())
              and set(implementation["python"]) == {"implementation", "cache_tag", "version", "optimization"}
              and all(type(implementation["python"][key]) is str
                      for key in ("implementation", "cache_tag"))
              and type(implementation["python"]["version"]) is list
              and len(implementation["python"]["version"]) == 5
              and all(type(piece) is int for piece in implementation["python"]["version"][:3])
              and type(implementation["python"]["optimization"]) is int
              and type(implementation["sqlite_version"]) is str
              and implementation["external_decoder"] is None
              and implementation["external_decoder_dependencies"] == [], "schema_invalid")
        parity_task = _task_doc(specs["parity_task"], kind="parity-check",
            input_names={"target", "candidate"}, basis=basis,
            param_names={"verifier_id", "symbol"}, budget="small",
            caps=["parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81"],
            optional_params={"timeout_s"})
        symbol = f'F_{selection["addr"]:x}'
        _need({key: parity_task["params"][key] for key in ("verifier_id", "symbol")} == {
                  "verifier_id": "parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81",
                  "symbol": symbol}, "tuple_mismatch")
        if "timeout_s" in parity_task["params"]:
            _need(type(parity_task["params"]["timeout_s"]) in (int, float)
                  and math.isfinite(parity_task["params"]["timeout_s"])
                  and 0 < parity_task["params"]["timeout_s"] <= 60, "schema_invalid")
        target_result = _result_doc(results["target_result"], target_task, {"target", "receipt"})
        parity_result = _result_doc(results["parity_result"], parity_task, {"raw", "receipt"})
        _need(target_task["basis_hash"] == parity_task["basis_hash"] == basis
              and target_result["producer_key"] == parity_result["producer_key"] == producer
              and target_task["inputs"]["store"] == role_refs["target_snapshot"]
              and target_task["inputs"]["image"] == role_refs["target_image"]
              and target_result["outputs"]["target"] == role_refs["target"]
              and parity_task["inputs"] == {"target": role_refs["target"], "candidate": role_refs["candidate"]},
              "tuple_mismatch")
        target_outputs = target_result.get("outputs")
        parity_outputs = parity_result.get("outputs")
        _need(type(target_outputs) is dict and set(target_outputs) == {"target", "receipt"}
              and type(parity_outputs) is dict and set(parity_outputs) == {"raw", "receipt"}, "schema_invalid")
        role_refs["target_proposed_receipt"] = _ref(target_outputs["receipt"])
        role_refs["parity_proposed_receipt"] = _ref(parity_outputs["receipt"])
        role_refs["parity_proposed_raw"] = _ref(parity_outputs["raw"])
        _need(role_refs["target"] == _ref(target_outputs["target"]), "tuple_mismatch")

        # P2 receipt and inventory metadata are bounded canonical documents. Their
        # exact joins are checked before a plan can escape.
        receipt_raw, doc_identities[role_refs["p2_proposed_receipt"]] = _read_path(
            _object_path(authority, role_refs["p2_proposed_receipt"]), MIB, stage_deadline,
            aggregate=document_io)
        receipt = _canonical_load(receipt_raw, MIB, stage_deadline)
        target_receipt_raw, doc_identities[role_refs["target_proposed_receipt"]] = _read_path(
            _object_path(authority, role_refs["target_proposed_receipt"]), ROLE_CAPS["target_proposed_receipt"],
            stage_deadline, aggregate=document_io)
        target_receipt = _target_receipt(_canonical_load(target_receipt_raw, ROLE_CAPS["target_proposed_receipt"], stage_deadline),
                                         target_task, role_refs["target"], basis,
                                         target_task["task_id"])
        p1_receipt_raw, doc_identities[role_refs["parity_proposed_receipt"]] = _read_path(
            _object_path(authority, role_refs["parity_proposed_receipt"]), ROLE_CAPS["parity_proposed_receipt"],
            stage_deadline, aggregate=document_io)
        p1_receipt = _p1_receipt(_canonical_load(p1_receipt_raw, ROLE_CAPS["parity_proposed_receipt"], stage_deadline),
                                 parity_task, role_refs["target"], role_refs["candidate"], symbol, basis)
        inventory_refs = {"target": role_refs["p2_proposed_target_inventory"],
                          "candidate": role_refs["p2_proposed_candidate_inventory"]}
        inventory_values = {}
        for side, role in (("target", "p2_proposed_target_inventory"),
                           ("candidate", "p2_proposed_candidate_inventory")):
            inventory_raw, doc_identities[role_refs[role]] = _read_path(
                _object_path(authority, role_refs[role]), ROLE_CAPS[role], stage_deadline,
                aggregate=document_io)
            inventory_values[side] = _inventory(_canonical_load(inventory_raw, ROLE_CAPS[role], stage_deadline),
                                                 role_refs["target" if side == "target" else "candidate"],
                                                 ROLE_CAPS["target" if side == "target" else "candidate"])
        receipt = _p2_receipt(receipt, task_id, basis, p2_inputs,
                              role_refs["target_proposed_receipt"],
                              role_refs["parity_proposed_receipt"], role_refs["parity_proposed_raw"],
                              inventory_refs)
        target_selection = {key: selection[key] for key in
                            ("image_sha256", "report_version", "binary_id", "func_id", "addr", "size")}
        _need(receipt["prerequisites"]["target"]["task_id"] == target_task["task_id"]
              and receipt["prerequisites"]["parity"]["task_id"] == parity_task["task_id"]
              and receipt["target_selection"] == target_selection
              and receipt["selection_sha256"] == target_task["params"]["selection_sha256"]
              and receipt["symbol"] == symbol and receipt["region_length"] == selection["size"]
              and receipt["coverage_bytes"] == selection["size"]
              and receipt["metadata_differences"] == inventory_values["target"]["metadata_differences"]
              and receipt["metadata_differences"] == inventory_values["candidate"]["metadata_differences"]
              and inventory_values["target"]["region"]["name"] == symbol
              and inventory_values["candidate"]["region"]["name"] == symbol
              and receipt["region_sha256"] == {side: inventory_values[side]["region"]["sha256"]
                                                for side in ("target", "candidate")}
              and receipt["objects"] == {side: {"sha256": inventory_values[side]["object_sha256"],
                                                 "size": inventory_values[side]["object_size"]}
                                         for side in ("target", "candidate")}
              and target_receipt["target_size"] == inventory_values["target"]["object_size"]
              and target_receipt["region_sha256"] == inventory_values["target"]["region"]["sha256"]
              and receipt["checker_grade"] == p1_receipt["grade"], "tuple_mismatch")

        # Min-cap accounting is computed over all rows before reading the final set.
        caps_by_ref: dict[str, int] = {task_ref: ROLE_CAPS["p2_task"]}
        for role, ref in role_refs.items():
            cap = ROLE_CAPS[role]
            caps_by_ref[ref] = min(cap, caps_by_ref.get(ref, cap))
        _need(len(inline_task) <= caps_by_ref[task_ref], "limit_exceeded", "unavailable")
        _need(len(caps_by_ref) <= 128, "limit_exceeded", "unavailable")
        sizes: dict[str, tuple[int, tuple[int, int, int, int, int]]] = {}
        for ref, cap in sorted(caps_by_ref.items()):
            if ref == task_ref:
                # Inline TASK is the one CAS-free role. Other aliases remain ordinary CAS reads.
                if all(role_refs.get(role) != ref for role in ROLE_CAPS if role != "p2_task"):
                    sizes[ref] = (len(inline_task), (0, 0, len(inline_task), 0, 0))
                    continue
            sizes[ref] = _cas(authority, ref, cap, stage_deadline, cas_io)
            _need(ref not in doc_identities or sizes[ref][1] == doc_identities[ref],
                  "object_changed", "unavailable")
        if task_ref in sizes:
            _need(sizes[task_ref][0] == len(inline_task), "tuple_mismatch")
        unique_sizes = {ref: size for ref, (size, _) in sizes.items()}
        unique_sizes.setdefault(task_ref, len(inline_task))
        _need(sum(unique_sizes.values()) <= 512 * MIB,
              "limit_exceeded", "unavailable")
        role_rows = tuple(NativeRegionRole(role, role_refs[role], ROLE_CAPS[role])
                          for role, _ in sorted(ROLES))
        _need(set(role_refs) == set(ROLE_CAPS), "schema_invalid")
        plan = NativeRegionVerifyPlan(
            PLAN_SCHEMA, seed.selection, task_ref, task_id, basis, producer, seed.verifier_key,
            seed.profile_id, profile["profile_sha256"], profile_auth.profile_row_sha256,
            profile_auth.effective_authority_digest, authority.generation, seed.admitted_at_ns,
            seed.absolute_deadline_ns, stage_started_at_ns, stage_deadline, role_rows)
        plan_bytes = canonical_json(plan.to_record())
        _need(len(plan_bytes) <= 16 * KIB, "limit_exceeded", "unavailable")
        # Re-read log and authority after all source reads; never return a partial handoff.
        _tick(stage_deadline)
        try:
            new_log, new_identity = _read_path(authority.roots.log_root.rstrip("/") + "/" +
                                               seed.selection.partition + "/records.jsonl", 16 * MIB, stage_deadline)
        except _Refusal as exc:
            if exc.reason == "input_unavailable":
                raise _Refusal("unavailable", "log_changed") from None
            raise
        _need(new_log == raw_log and new_identity == log_identity, "log_changed", "unavailable")
        final_authority = _authority(cfg, stage_deadline)
        _need(final_authority == authority, "authority_changed", "unavailable")
        _tick(stage_deadline)
        observations = tuple(NativeRegionSourceObservation(ref, sizes[ref][0], caps_by_ref[ref], sizes[ref][1])
                             for ref in sorted(sizes) if ref != task_ref or any(
                                 role_refs.get(role) == task_ref for role in ROLE_CAPS if role != "p2_task"))
        log_obs = NativeRegionLogObservation(_sha(raw_log), len(raw_log), log_identity)
        return NativeRegionPlanRead(plan, plan_bytes, _sha(plan_bytes), inline_task, authority,
                                    observations, log_obs)
    except NativeRegionPlanError:
        raise
    except _Refusal as exc:
        raise NativeRegionPlanError(exc.status, exc.reason) from None
    except NotConfigured:
        raise NativeRegionPlanError("unavailable", "input_unavailable") from None
    except OSError:
        raise NativeRegionPlanError("unavailable", "input_unavailable") from None
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise NativeRegionPlanError("failed", "schema_invalid") from None


def build_native_region_verify_plan(seed: NativeRegionVerifySeed, *,
                                    cfg: NativeRegionReaderConfig,
                                    stage_started_at_ns: int) -> NativeRegionPlanRead:
    try:
        return _build_native_region_verify_plan(seed, cfg=cfg,
                                                stage_started_at_ns=stage_started_at_ns)
    except NativeRegionPlanError:
        raise
    except _Refusal as exc:
        raise NativeRegionPlanError(exc.status, exc.reason) from None
    except NotConfigured:
        raise NativeRegionPlanError("unavailable", "input_unavailable") from None
    except OSError:
        raise NativeRegionPlanError("unavailable", "input_unavailable") from None
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise NativeRegionPlanError("failed", "schema_invalid") from None
