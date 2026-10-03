"""Authenticate a persisted native observation under an explicit current owner pin.

This read-only consumer has no checker, key loader, store writer, database or dashboard
adapter. Callers must supply freshly reloaded owner configuration on every request;
a stale GridConfig cannot establish currentness. No positive result is cached.
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

from agentdecompile_grid.config import GridConfig, to_dict
from agentdecompile_grid.core import GridError, ObjectRef, RecordType, TaskSpec, canonical_json
from agentdecompile_grid.log.records import validate_partition, record_from_dict, unsigned_bytes, validate_record, verify_chain
from agentdecompile_grid.log.signing import HAVE_CRYPTOGRAPHY, Keyring, refusal_reason
from agentdecompile_grid.objects.base import Layout, validate_ref
from agentdecompile_grid.verify.policy import RevocationList
from agentdecompile_grid.worker.records import task_result_from_record
from agentdecompile_recovery.objdiff_verification import parse_objdiff_report

SCHEMA = "agentdecompile.current-observation-admission.v1"
PREDICATE = "current-signed-observation-v1"
KIB, MIB = 1024, 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ObservationSelection:
    partition: str
    task_digest: str
    result_digest: str
    verified_digest: str
    result_ref: str


@dataclass(frozen=True)
class AdmissionRead:
    status: str
    reason: str
    admission_identity: str | None = None
    snapshot_bytes: bytes | None = None


@dataclass(frozen=True)
class ObservationRead:
    status: str
    reason: str
    admission_identity: str | None = None
    observation_identity: str | None = None
    selection: ObservationSelection | None = None
    record_bytes: tuple[bytes, ...] = ()
    task_bytes: bytes | None = None
    result_bytes: bytes | None = None
    evidence_bytes: bytes | None = None
    consumed_refs: tuple[str, ...] = ()
    grade: str | None = None
    implementation_source_closure: str = "not_evaluated"
    implementation_runtime_closure: str = "not_evaluated"
    source_acceptance: str = "not_evaluated"


class _Refusal(Exception):
    def __init__(self, status: str, reason: str):
        self.status, self.reason = status, reason
        super().__init__(reason)


def _need(ok: bool, reason: str, status: str = "failed") -> None:
    if not ok:
        raise _Refusal(status, reason)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fields(value: Any, names: str, reason: str) -> None:
    _need(type(value) is dict and set(value) == set(names.split()), reason)


def _string(value: Any) -> bool:
    return type(value) is str and bool(value) and "\0" not in value


def _strings(value: Any, *, empty: bool = False) -> bool:
    return (type(value) is list and (empty or bool(value)) and all(_string(v) for v in value)
            and len(set(value)) == len(value))


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _hex(value: Any) -> bool:
    return type(value) is str and HEX.fullmatch(value) is not None


def _ref(value: Any) -> ObjectRef:
    _need(isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and _hex(value[7:]), "invalid_ref")
    return validate_ref(value)


def _json(raw: bytes, *, canonical: bool = True) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            _need(key not in out, "duplicate_json_key")
            out[key] = value
        return out

    def constant(_):
        raise _Refusal("failed", "nonfinite_json_number")

    def finite_float(value):
        result = float(value)
        _need(math.isfinite(result), "nonfinite_json_number")
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant, parse_float=finite_float)
        _need(type(value) is dict, "invalid_json_object")
        if canonical:
            _need(canonical_json(value) == raw, "noncanonical_encoding")
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise _Refusal("failed", "invalid_json") from exc


def _parts(path: str, *, absolute: bool = False) -> tuple[str, ...]:
    _need(_string(path) and (path.startswith("/") == absolute) and "\\" not in path,
          "unsafe_path")
    pieces = path.split("/")[1:] if absolute else path.split("/")
    _need(bool(pieces) and all(p not in ("", ".", "..") and not any(ord(c) < 32 or ord(c) == 127 for c in p)
                              for p in pieces), "unsafe_path")
    return tuple(pieces)


def _identity(info) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


class _Reader:
    """All opens are descriptor-relative, no-follow and read-only, including root ancestry."""

    def __init__(self):
        self.deadline = time.monotonic() + 10.0
        self.files: dict[tuple[str, str], tuple[int, str, tuple, str]] = {}
        self.refs: dict[str, bytes] = {}
        self.cas_total = 0

    def tick(self):
        _need(time.monotonic() < self.deadline, "deadline_exceeded", "unavailable")

    def read(self, root: str, name: str, cap: int, missing: str, *, remember: bool = True, metadata_only: bool = False) -> bytes:
        self.tick()
        root_parts = () if root == "/" else _parts(root, absolute=True)
        names = _parts(name)
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in (*root_parts, *names[:-1]):
                self.tick()
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            fd = os.open(names[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                before = os.fstat(fd)
                _need(stat.S_ISREG(before.st_mode), "nonregular_file", "unavailable")
                _need(before.st_size <= cap, "limit_exceeded", "unavailable")
                if metadata_only:
                    previous = self.files[(root, name)]
                    if previous[2] == _identity(before):
                        return b""
                    # A persistent CAS mutation never retains authority. Rehash the retained
                    # bytes and reject; an altered path must be authenticated by a new read.
                    ref = next((r for r in self.refs if r[7:] == name.rsplit("/", 1)[-1]), None)
                    _need(ref is not None and _sha(self.refs[ref]) == ref[7:], "object_hash_mismatch")
                    raise _Refusal("unavailable", "files_unstable")
                chunks, size, hasher = [], 0, hashlib.sha256()
                while True:
                    self.tick()
                    chunk = os.read(fd, min(64 * KIB, cap + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    _need(size <= cap, "limit_exceeded", "unavailable")
                    hasher.update(chunk)
                    chunks.append(chunk)
                after = os.fstat(fd)
                unstable = "log_snapshot_unstable" if name.endswith("records.jsonl") else "files_unstable"
                _need(_identity(before) == _identity(after), unstable, "unavailable")
                identity = (cap, hasher.hexdigest(), _identity(after), missing)
                if remember:
                    previous = self.files.setdefault((root, name), identity)
                    _need(previous == identity, unstable, "unavailable")
                self.tick()
                return b"".join(chunks)
            finally:
                os.close(fd)
        except OSError as exc:
            raise _Refusal("unavailable", missing) from exc
        finally:
            os.close(directory)

    def revalidate(self):
        for (root, name), (cap, digest, _, missing) in tuple(self.files.items()):
            if missing == "evidence_unavailable":
                self.read(root, name, cap, missing, metadata_only=True)
                continue
            _need(_sha(self.read(root, name, cap, missing)) == digest,
                  "log_snapshot_unstable" if name.endswith("records.jsonl") else "files_unstable", "unavailable")
        self.tick()

    def cas(self, root: str, layout: Layout, value: str, cap: int) -> bytes:
        ref = _ref(value)
        if value in self.refs:
            _need(len(self.refs[value]) <= cap, "limit_exceeded", "unavailable")
            return self.refs[value]
        _need(len(self.refs) < 16, "limit_exceeded", "unavailable")
        raw = self.read(root, layout.relpath(ref), min(cap, 160 * MIB - self.cas_total), "evidence_unavailable")
        self.cas_total += len(raw)
        _need(_sha(raw) == ref.hex, "object_hash_mismatch")
        self.refs[value] = raw
        return raw


def _config_identity(cfg: GridConfig) -> bytes:
    # Include effective roots as well as every public configuration field; never read a secret.
    return canonical_json({"config": to_dict(cfg), "objects": cfg.objects_locator(),
                           "log": cfg.log_locator(), "keyring": cfg.keyring_locator(), "predicate": PREDICATE})


def _policy(cfg: GridConfig, reader: _Reader):
    a = cfg.admission
    _need(bool(a.snapshot_path and a.snapshot_sha256 and a.policy_id) and type(a.generation) is int and a.generation >= 0
          and bool(cfg.keyring.key_dir) and bool(cfg.paths.root or (cfg.paths.objects and cfg.paths.log)),
          "admission_not_configured", "unavailable")
    _need(HAVE_CRYPTOGRAPHY, "crypto_unavailable", "unavailable")
    _need(type(a.snapshot_path) is str and _hex(a.snapshot_sha256) and _string(a.policy_id), "invalid_admission_configuration")
    _need(not cfg.keyring.allow_null and not cfg.keyring.trust_local_nodes,
          "development_trust_unsupported", "unavailable")
    _need(cfg.adapters.objects == "local" and cfg.adapters.log == "local" and os.name == "posix",
          "transport_unsupported", "unavailable")
    _need(cfg.objects.hash_algorithm == "sha256" and cfg.objects.write_once_strategy == "link",
          "unsupported_layout", "unavailable")
    _need(all(hasattr(os, key) for key in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")), "transport_unsupported", "unavailable")
    config_bytes = _config_identity(cfg)
    parts = _parts(a.snapshot_path, absolute=True)
    raw = reader.read("/", "/".join(parts), 256 * KIB, "admission_snapshot_unavailable")
    _need(_sha(raw) == a.snapshot_sha256, "admission_snapshot_mismatch")
    policy = _json(raw)
    _fields(policy, "schema policy_id generation public_keys revocations independence_policy observations corpus_scope execution_profiles", "invalid_admission_snapshot")
    _need(policy["schema"] == SCHEMA and _string(policy["policy_id"]) and type(policy["generation"]) is int
          and policy["generation"] >= 0, "invalid_admission_snapshot")
    _need(policy["policy_id"] == a.policy_id and policy["generation"] == a.generation, "admission_snapshot_mismatch")
    _need(policy["independence_policy"] == "disjoint-lineage" and policy["execution_profiles"] == [], "unsupported_admission_profile", "unavailable")
    ring, keys = Keyring(allow_null=False), {}
    entries = policy["public_keys"]
    _need(type(entries) is list and 0 < len(entries) <= 64, "invalid_public_keys")
    filenames = set()
    public_materials: set[bytes] = set()
    for entry in entries:
        reader.tick()
        _fields(entry, "filename sha256 key_id algorithm role lineage", "invalid_public_key")
        key = entry["key_id"]
        _need(_string(key) and key not in keys and entry["algorithm"] == "ed25519"
              and entry["role"] in ("operator", "fleet", "donor") and _strings(entry["lineage"], empty=True), "invalid_public_key")
        name = entry["filename"]
        # Only the public trust directory's flat *.pub / *.json contract is supported.
        _need(type(name) is str and len(_parts(name)) == 1 and name.endswith((".pub", ".json"))
              and name not in filenames and _hex(entry["sha256"]), "invalid_public_key")
        filenames.add(name)
        public = reader.read(cfg.keyring.key_dir, name, 16 * KIB, "signer_not_available")
        _need(_sha(public) == entry["sha256"], "public_key_hash_mismatch")
        if name.endswith(".pub"):
            _need(entry["role"] == "operator" and entry["lineage"] == [], "invalid_public_key")
            actual = ring.add_ed25519_public(public, role="operator")
            material = public
        else:
            data = _json(public, canonical=False)
            required = {"key_id", "algorithm", "public", "role", "lineage"}
            # Existing Keyring intentionally does not use lifecycle timestamps or
            # previous IDs as authorization. The owner pin covers these bytes, while
            # only the explicit role/lineage fields supply current trust metadata.
            lifecycle = {"created_at", "expires_at", "previous_key_ids"}
            _need(required <= set(data) and set(data) <= required | lifecycle, "invalid_public_key")
            for name in ("created_at", "expires_at"):
                _need(name not in data or _number(data[name]), "invalid_public_key")
            _need("previous_key_ids" not in data or _strings(data["previous_key_ids"], empty=True), "invalid_public_key")
            _need(all(data[k] == entry[k] for k in ("key_id", "algorithm", "role", "lineage"))
                  and type(data["public"]) is str and _hex(data["public"]), "public_key_metadata_mismatch")
            material = bytes.fromhex(data["public"])
            actual = ring.add_node_public(key, "ed25519", material,
                                          role=entry["role"], lineage=entry["lineage"])
        _need(actual == key, "public_key_identity_mismatch")
        # The raw operator and node formats assign different IDs to the same key.
        # Include every selected entry so aliases of ancestors cannot split lineage.
        _need(material not in public_materials, "duplicate_public_key_material")
        public_materials.add(material)
        keys[key] = entry
    for key, entry in keys.items():
        lineage = entry["lineage"]
        _need(key not in lineage and all(parent in keys for parent in lineage), "invalid_lineage")
        for parent in lineage:
            _need(key not in keys[parent]["lineage"] and set(keys[parent]["lineage"]).issubset(lineage), "invalid_lineage")
    revocations = policy["revocations"]
    _need(type(revocations) is dict and len(revocations) <= 4096, "invalid_revocations")
    for key, item in revocations.items():
        _fields(item, "at by reason", "invalid_revocations")
        _need(_string(key) and _number(item["at"]) and _string(item["reason"]) and _string(item["by"])
              and item["by"] in keys and keys[item["by"]]["role"] in ("operator", "fleet"), "invalid_revocations")
    observations = policy["observations"]
    _need(type(observations) is list and 0 < len(observations) <= 16, "invalid_observation_policy")
    seen = set()
    for entry in observations:
        _fields(entry, "kind kind_version method verifier_id basis_hashes task_operator_keys producer_keys verifier_keys profile_id", "invalid_observation_policy")
        _need(entry["kind"] == "parity-check" and type(entry["kind_version"]) is int and entry["kind_version"] == 1
              and entry["method"] == "parity-binding-v1" and entry["profile_id"] == "native-objdiff-observation-v1"
              and type(entry["verifier_id"]) is str and re.fullmatch(r"parity:[0-9a-f]{64}", entry["verifier_id"]) is not None,
              "invalid_observation_policy")
        for name in ("basis_hashes", "task_operator_keys", "producer_keys", "verifier_keys"):
            _need(_strings(entry[name]) and "*" not in entry[name], "invalid_observation_policy")
            if name != "basis_hashes":
                _need(all(key in keys for key in entry[name]), "invalid_observation_policy")
        identity = canonical_json(entry)
        _need(identity not in seen, "duplicate_observation_policy")
        seen.add(identity)
    scope = policy["corpus_scope"]
    if scope is not None:
        _fields(scope, "scope_id generation snapshot_ref", "invalid_corpus_scope")
        _need(_string(scope["scope_id"]) and type(scope["generation"]) is int and scope["generation"] >= 0, "invalid_corpus_scope")
        _ref(scope["snapshot_ref"])
    identity = _sha(canonical_json({"predicate": PREDICATE, "config_sha256": _sha(config_bytes), "snapshot": policy}))
    return policy, ring, RevocationList(revocations), identity, raw, config_bytes


def load_current_admission(cfg: GridConfig) -> AdmissionRead:
    """Read the owner pin and selected public bytes without granting a reusable capability."""
    try:
        reader = _Reader()
        _, _, _, identity, raw, config_bytes = _policy(cfg, reader)
        reader.revalidate()
        _need(config_bytes == _config_identity(cfg), "config_unstable", "unavailable")
        return AdmissionRead("authenticated", "current_admission", identity, raw)
    except _Refusal as exc:
        return AdmissionRead(exc.status, exc.reason)
    except (GridError, ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError, OverflowError):
        return AdmissionRead("failed", "invalid_admission_snapshot")


def _log(reader: _Reader, cfg: GridConfig, partition: str):
    _parts(partition)
    validate_partition(partition)
    raw = reader.read(cfg.log_locator()["log_dir"], partition + "/records.jsonl", 16 * MIB, "raw_history_unavailable")
    _need(bool(raw) and raw.endswith(b"\n"), "log_snapshot_unstable", "unavailable")
    lines = raw.splitlines(keepends=True)
    _need(len(lines) <= 4096, "limit_exceeded", "unavailable")
    records = []
    for line in lines:
        reader.tick()
        _need(len(line) <= 128 * KIB, "limit_exceeded", "unavailable")
        data = _json(line[:-1])
        _fields(data, "schema partition seq type body prev signer_key signature basis_hash", "invalid_record")
        _need(type(data["schema"]) is int and type(data["seq"]) is int and type(data["body"]) is dict,
              "invalid_record")
        _need(all(type(data[k]) is str for k in ("partition", "type", "prev", "signer_key", "signature", "basis_hash")), "invalid_record")
        try:
            record = record_from_dict(data)
            validate_record(record)
        except GridError as exc:
            raise _Refusal("failed", "invalid_record") from exc
        records.append(record)
    _need(records[0].seq == 1 and records[0].prev == "", "raw_history_unavailable", "unavailable")
    try:
        tail = verify_chain(records, partition=partition)
    except GridError as exc:
        raise _Refusal("failed", "chain_mismatch") from exc
    return records, lines, _sha(raw), tail


def _tuple(records, lines, selection):
    selected, encoded = [], []
    for digest, kind in ((selection.task_digest, RecordType.TASK), (selection.result_digest, RecordType.RESULT),
                         (selection.verified_digest, RecordType.VERIFIED)):
        _need(_hex(digest), "invalid_selection")
        matches = [(r, line[:-1]) for r, line in zip(records, lines) if r.digest() == digest]
        _need(len(matches) == 1, "selected_record_unavailable" if not matches else "duplicate_selected_tuple",
              "unavailable" if not matches else "failed")
        r, raw = matches[0]
        _need(r.type == kind, "record_type_mismatch")
        selected.append(r)
        encoded.append(raw)
    task, result, verdict = selected
    _need(task.seq < result.seq < verdict.seq, "causal_order_mismatch")
    task_id = task.body.get("task_id")
    # Re-flushed duplicate statements cannot silently choose an ambiguous causal tuple.
    for kind in (RecordType.TASK, RecordType.RESULT, RecordType.VERIFIED):
        count = sum(r.type == kind and r.body.get("task_id") == task_id
                    and (kind == RecordType.TASK or r.body.get("result_ref") == selection.result_ref) for r in records)
        _need(count == 1, "duplicate_selected_tuple")
    return selected, tuple(encoded)


def _spec(task, partition):
    body = task.body
    _fields(body, "task_id kind kind_version inputs params basis_hash capabilities budget partition", "invalid_task")
    _need(len(canonical_json(body)) <= 64 * KIB, "limit_exceeded", "unavailable")
    _need(body["kind"] == "parity-check" and type(body["kind_version"]) is int and body["kind_version"] == 1
          and body["budget"] == "small" and _strings(body["capabilities"], empty=True)
          and _string(body["basis_hash"]) and body["partition"] == partition, "invalid_task")
    _fields(body["inputs"], "target candidate", "invalid_task")
    for value in body["inputs"].values():
        _ref(value)
    params = body["params"]
    _need(type(params) is dict and not set(params) - {"verifier_id", "symbol", "timeout_s"}, "invalid_task")
    verifier = params.get("verifier_id")
    _need(type(verifier) is str and re.fullmatch(r"parity:[0-9a-f]{64}", verifier) is not None, "unsupported_checker", "unavailable")
    symbol = params.get("symbol")
    _need(symbol is None or (type(symbol) is str and "\0" not in symbol and len(symbol.encode()) <= 4096), "invalid_task")
    _need(params.get("timeout_s") is None or _number(params["timeout_s"]), "invalid_task")
    spec = TaskSpec.from_record(body)
    _need(spec.task_id == body["task_id"], "task_identity_mismatch")
    return spec


def _result_body(body):
    _fields(body, "task_id kind status result_ref outputs producer_key producer_lineage elapsed_s deadline_s reason nonce", "invalid_result_body")
    _need(_strings(body["producer_lineage"], empty=True) and _number(body["elapsed_s"]) and body["elapsed_s"] >= 0
          and _number(body["deadline_s"]) and body["deadline_s"] >= 0 and type(body["reason"]) is str
          and _string(body["nonce"]), "invalid_result_body")


def _verdict_body(body):
    _need(type(body) is dict and (("evidence" in body) != ("evidence_ref" in body)), "invalid_evidence_association")
    field = "evidence" if "evidence" in body else "evidence_ref"
    _fields(body, "task_id result_ref outcome verifier_key method producer_key verifier_lineage nonce " + field, "invalid_verdict_body")
    _need(_strings(body["verifier_lineage"], empty=True) and _string(body["nonce"]), "invalid_verdict_body")
    return field


def _outputs(value):
    _fields(value, "receipt raw", "invalid_outputs")
    for ref in value.values():
        _ref(ref)


def _receipt(raw, spec):
    receipt = _json(raw)
    required = set("schema status differences message objdiffExit kind kind_version verifier_id verifier sides symbol grade basis_hash".split())
    optional = {"detailLevel", "mismatchHistogram", "instructionMismatchCount", "alignedDiff"}
    _need(required <= set(receipt) <= required | optional, "invalid_receipt")
    grade, code, differences = receipt["grade"], receipt["objdiffExit"], receipt["differences"]
    _need(receipt["schema"] == "agentdecompile.verify-objdiff.v1" and receipt["kind"] == spec.kind
          and type(receipt["kind_version"]) is int and receipt["kind_version"] == 1
          and receipt["verifier_id"] == spec.params["verifier_id"] and receipt["verifier"] == "native"
          and receipt["basis_hash"] == spec.basis_hash and receipt["symbol"] == (spec.params.get("symbol") or "")
          and receipt["sides"] == {k: _ref(v).hex for k, v in spec.inputs.items()}
          and type(receipt["message"]) is str and type(code) is int and type(differences) is int
          and grade == receipt["status"] and grade in ("matched", "mismatched", "error"), "receipt_binding_mismatch")
    _need((grade == "matched" and code == 0 and differences == 0)
          or (grade == "mismatched" and code == 0 and differences >= 1)
          or (grade == "error" and differences == -1), "invalid_receipt_grade")
    return receipt


def _revoked(key, keys, revoked):
    return any(revoked.is_revoked(k) for k in (key, *keys[key]["lineage"]))


def authenticate_native_observation(cfg: GridConfig, selection: ObservationSelection) -> ObservationRead:
    """Authenticate an exact existing tuple; never execute a checker or accept source."""
    admission_identity = None
    try:
        reader = _Reader()
        policy, ring, revoked, admission_identity, _, config_bytes = _policy(cfg, reader)
        _need(type(selection) is ObservationSelection, "invalid_selection")
        _ref(selection.result_ref)
        records, lines, log_digest, tail = _log(reader, cfg, selection.partition)
        selected, encoded = _tuple(records, lines, selection)
        task, result, verdict = selected
        # Cryptographic authenticity precedes any stale-policy classification.
        for record in selected:
            _need(ring.knows(record.signer_key), "signer_not_available", "unavailable")
            _need(ring.verify(record.signer_key, unsigned_bytes(record), record.signature), "bad_signature")
        _need(all(len(raw) <= 64 * KIB for raw in encoded[:2]), "limit_exceeded", "unavailable")
        spec = _spec(task, selection.partition)
        _result_body(result.body)
        evidence_field = _verdict_body(verdict.body)
        _need(all(r.basis_hash == spec.basis_hash for r in selected), "basis_mismatch")
        _need(result.body["task_id"] == verdict.body["task_id"] == spec.task_id
              and result.body["result_ref"] == verdict.body["result_ref"] == selection.result_ref
              and result.body["kind"] == spec.kind and verdict.body["producer_key"] == result.signer_key,
              "tuple_association_mismatch")
        _need(result.body["status"] == "ok" and verdict.body["outcome"] == "verified", "invalid_observation_outcome")
        root = cfg.objects_locator()["root"]
        layout_data = _json(reader.read(root, "layout.json", 4096, "layout_unavailable"))
        _fields(layout_data, "schema hash_algorithm shard_width shard_depth", "unsupported_layout")
        _need(type(layout_data["schema"]) is int and layout_data["schema"] == 1
              and layout_data["hash_algorithm"] == "sha256"
              and type(layout_data["shard_width"]) is int and 0 <= layout_data["shard_width"] <= 4
              and type(layout_data["shard_depth"]) is int and 0 <= layout_data["shard_depth"] <= 2
              and layout_data["shard_width"] == cfg.objects.shard_width
              and layout_data["shard_depth"] == cfg.objects.shard_depth, "unsupported_layout", "unavailable")
        layout = Layout(**layout_data)
        result_bytes = reader.cas(root, layout, selection.result_ref, 64 * KIB)
        data = _json(result_bytes)
        if "schema" in data:
            raise _Refusal("unavailable", "unsupported_result_encoding")
        _fields(data, "task_id status outputs producer_key basis_hash elapsed_s reason candidates metrics", "invalid_result")
        _need(_number(data["elapsed_s"]) and data["elapsed_s"] >= 0 and type(data["candidates"]) is list
              and all(type(v) is dict for v in data["candidates"]) and type(data["metrics"]) is dict
              and data["reason"] == "", "invalid_result")
        _outputs(data["outputs"])
        _need(data["task_id"] == spec.task_id and data["basis_hash"] == spec.basis_hash
              and data["producer_key"] == result.signer_key and data["status"] == "ok"
              and data["outputs"] == result.body["outputs"] and result.body["reason"] == data["reason"], "result_binding_mismatch")
        _need(canonical_json(task_result_from_record(data).to_record()) == result_bytes, "unsupported_result_encoding", "unavailable")
        evidence_bytes = (reader.cas(root, layout, verdict.body["evidence_ref"], MIB) if evidence_field == "evidence_ref"
                          else canonical_json(verdict.body["evidence"]))
        _need(len(evidence_bytes) <= MIB, "limit_exceeded", "unavailable")
        evidence = _json(evidence_bytes)
        _fields(evidence, "reason compared predicate comparison_scope checker_identity_scope target_region_complete runtime_admission grade proposal_outputs recomputed_outputs", "invalid_evidence")
        _need(evidence["reason"] == "receipt_equal" and evidence["compared"] == ["receipt"]
              and evidence["predicate"] == "authenticated-checker-observation-v1"
              and evidence["comparison_scope"] == "native-reported-code"
              and evidence["checker_identity_scope"] == "registered-artifacts-v1"
              and evidence["target_region_complete"] is False and evidence["runtime_admission"] == "not_evaluated",
              "evidence_binding_mismatch")
        _need(evidence["proposal_outputs"] == data["outputs"], "output_ref_substitution")
        receipts = []
        for outputs in (evidence["proposal_outputs"], evidence["recomputed_outputs"]):
            _outputs(outputs)
            receipt_bytes = reader.cas(root, layout, outputs["receipt"], MIB)
            raw_report = reader.cas(root, layout, outputs["raw"], 4 * MIB)
            receipt = _receipt(receipt_bytes, spec)
            # Use the existing pure legacy parser, never ParityCheck.verify/run or a
            # locally installed checker. This preserves its observation-only semantics.
            parsed = parse_objdiff_report(receipt["objdiffExit"], raw_report.decode("utf-8", "replace"))
            normalized = {k: v for k, v in parsed.items() if k != "output"}
            normalized.update({"kind": spec.kind, "kind_version": 1, "verifier_id": spec.params["verifier_id"],
                               "verifier": "native", "sides": {k: _ref(v).hex for k, v in spec.inputs.items()},
                               "symbol": spec.params.get("symbol") or "", "grade": parsed["status"], "basis_hash": spec.basis_hash})
            _need(canonical_json(normalized) == receipt_bytes, "raw_receipt_mismatch")
            reader.tick()
            _need(evidence["grade"] == receipt["grade"], "evidence_grade_mismatch")
            receipts.append(receipt_bytes)
        _need(receipts[0] == receipts[1], "recomputed_receipt_mismatch")
        for ref in spec.inputs.values():
            reader.cas(root, layout, str(ref), 64 * MIB)
        keys = {key["key_id"]: key for key in policy["public_keys"]}
        stale = []
        for record in selected:
            if refusal_reason(record, ring) is not None:
                stale.append("role_disallowed")
            if _revoked(record.signer_key, keys, revoked):
                stale.append("key_revoked")
        if not ring.independent(result.signer_key, verdict.signer_key):
            stale.append("lineage_disallowed")
        if ring.role_of(verdict.signer_key) not in ("operator", "fleet"):
            stale.append("role_disallowed")
        if verdict.body["method"] != "parity-binding-v1":
            stale.append("method_disallowed")
        if cfg.verifier.methods_by_kind.get(spec.kind, cfg.verifier.default_method or "kind") != "kind":
            stale.append("method_disallowed")
        if cfg.admitted_bases and spec.basis_hash not in cfg.admitted_bases:
            stale.append("basis_disallowed")
        entries = [e for e in policy["observations"] if e["verifier_id"] == spec.params["verifier_id"]]
        if not entries:
            stale.append("checker_disallowed")
        allowed = [e for e in entries if spec.basis_hash in e["basis_hashes"]]
        if entries and not allowed:
            stale.append("basis_disallowed")
        allowed = [e for e in allowed if task.signer_key in e["task_operator_keys"]
                   and result.signer_key in e["producer_keys"] and verdict.signer_key in e["verifier_keys"]]
        if entries and not allowed and "basis_disallowed" not in stale:
            stale.append("key_disallowed")
        if allowed and cfg.admitted_bases and not any(set(e["basis_hashes"]).issubset(cfg.admitted_bases) for e in allowed):
            stale.append("basis_disallowed")
        if result.body["producer_lineage"] != keys[result.signer_key]["lineage"] or verdict.body["verifier_lineage"] != keys[verdict.signer_key]["lineage"]:
            stale.append("lineage_disallowed")
        # Complete current trusted negative scan. Old/unavailable keys do not gain authority.
        for record in records:
            reader.tick()
            body = record.body
            if record.type != RecordType.REFUTED or body.get("task_id") != spec.task_id or body.get("result_ref") != selection.result_ref:
                continue
            key = record.signer_key
            if (key not in keys or refusal_reason(record, ring) is not None or _revoked(key, keys, revoked)
                    or ring.role_of(key) not in ("operator", "fleet") or not ring.independent(result.signer_key, key)):
                continue
            negative_allowed = any(spec.basis_hash in e["basis_hashes"] and task.signer_key in e["task_operator_keys"]
                                   and result.signer_key in e["producer_keys"] and key in e["verifier_keys"] for e in entries)
            if negative_allowed:
                _verdict_body(body)
                _need(body["producer_key"] == result.signer_key and record.basis_hash == spec.basis_hash
                      and body["method"] == "parity-binding-v1", "negative_verdict_association_mismatch")
                raise _Refusal("failed", "conflicting_verdict")
        reader.revalidate()
        _need(config_bytes == _config_identity(cfg), "config_unstable", "unavailable")
        if stale:
            raise _Refusal("stale", stale[0])
        observation_identity = _sha(canonical_json({"admission": admission_identity, "records": [_sha(r) for r in encoded],
                                                   "log": log_digest, "tail": list(tail), "refs": sorted(reader.refs)}))
        return ObservationRead("authenticated", "current_observation", admission_identity, observation_identity,
                               selection, encoded, canonical_json(task.body), result_bytes, evidence_bytes,
                               tuple(sorted(reader.refs)), evidence["grade"])
    except _Refusal as exc:
        return ObservationRead(exc.status, exc.reason, admission_identity)
    except (GridError, ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError, OverflowError):
        return ObservationRead("failed", "invalid_observation", admission_identity)
