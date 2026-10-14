"""Read-only authentication of a current, qualified native-region execution.

This is deliberately a separate P3.2 consumer.  It does not extend or alter the
P3.1 observation admission API.  No result from this module means source or
whole-image acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import struct
import time
from dataclasses import dataclass
from typing import Any

from agentdecompile_grid.core import GridError, RecordType, TaskSpec, canonical_json
from agentdecompile_grid.log.records import (record_from_dict, unsigned_bytes, validate_partition,
                                             validate_record, verify_chain, verify_record, record_to_dict)
from agentdecompile_grid.log.signing import HAVE_CRYPTOGRAPHY, Keyring, refusal_reason
from agentdecompile_grid.objects.base import Layout, ObjectRef, validate_ref
from agentdecompile_grid.worker.records import task_result_from_record

PREDICATE = "current-qualified-native-region-v1"
OWNER_SCHEMA = "agentdecompile.current-native-region-reader-config.v1"
SNAPSHOT_SCHEMA = "agentdecompile.current-native-region-admission.v1"
READER_RESULT_SCHEMA = "agentdecompile.native-region-verification-evidence.v1"
EXECUTION_SCHEMA = "agentdecompile.native-region-execution.v1"
KIB, MIB = 1024, 1024 * 1024
REGION_LIMIT, OBJECT_LIMIT = 64*KIB, 64*MIB
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[^\x00-\x1f\x7f]{1,256}\Z")
_PROFILE_FIELDS = frozenset("profile_id profile_sha256 kind kind_version dispatch method checker_profile comparison_policy verifier_id root_inventory_ref implementation_source_sha256 launcher_sha256 filter_sha256 environment_sha256 entrypoint_sha256 basis_hashes task_operator_keys producer_keys verifier_keys".split())
_C_FIELDS = frozenset("schema profile_id profile_sha256 admission_identity admission_generation root_inventory_ref implementation_source_sha256 launcher_sha256 filter_sha256 environment_sha256 entrypoint_sha256 job_id nonce op kind kind_version dispatch method task_ref task_id result_ref basis_hash producer_key verifier_key task_record_sha256 result_record_sha256 v0_ref processes namespaces enforcement_ref module_diagnostics_ref ipc_transcript_sha256 elapsed_ms stage_ms staged exported measurement_scope tree_gone collection_status".split())
_VERIFIER = "parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81"
_METHOD = "parity-region-coff-i386-leaf-v1"
_EVIDENCE_FIELDS = frozenset("prerequisites parity_raw_evidence reason proposal_outputs recomputed_outputs grade target_region_complete region_inventory_complete checker_profile comparison_policy verifier_id implementation_source_closure implementation_runtime_closure source_binding runtime_admission".split())
_ROLE_CAPS = {
    "p2_result": 64*KIB, "p2_proposed_receipt": MIB,
    "p2_proposed_target_inventory": MIB, "p2_proposed_candidate_inventory": MIB,
    "target_task": 64*KIB, "target_result": 64*KIB, "parity_task": 64*KIB, "parity_result": 64*KIB,
    "target": 64*MIB, "candidate": 64*MIB, "target_snapshot": 256*MIB, "target_image": 128*MIB,
    "target_proposed_receipt": 32*KIB, "parity_proposed_receipt": MIB, "parity_proposed_raw": 4*MIB,
}
_INLINE_ROLES = frozenset(("p2_task",))
_CAS_LIMIT = 640*MIB


@dataclass(frozen=True)
class NativeRegionReaderConfig:
    owner_config_path: str = ""


@dataclass(frozen=True)
class NativeRegionPublicKey:
    filename: str
    raw_bytes: bytes
    sha256: str
    key_id: str
    algorithm: str
    role: str
    lineage: tuple[str, ...]
    public_material: bytes


@dataclass(frozen=True)
class NativeRegionProfileAuthority:
    profile_id: str
    profile_bytes: bytes
    profile_row_sha256: str
    effective_authority_digest: str


@dataclass(frozen=True)
class NativeRegionAuthorityRoots:
    owner_config_path: str
    snapshot_path: str
    objects_root: str
    log_root: str
    public_key_root: str


@dataclass(frozen=True)
class NativeRegionAuthorityLayout:
    schema: int
    hash_algorithm: str
    shard_width: int
    shard_depth: int
    raw_bytes: bytes
    sha256: str


@dataclass(frozen=True)
class NativeRegionAuthorityFile:
    role: str
    path: str
    sha256: str
    identity: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class NativeRegionAuthority:
    owner_config_bytes: bytes
    owner_config_sha256: str
    configuration_revision: int
    snapshot_bytes: bytes
    snapshot_sha256: str
    policy_id: str
    generation: int
    revocations_bytes: bytes
    revocations_sha256: str
    public_keys: tuple[NativeRegionPublicKey, ...]
    profiles: tuple[NativeRegionProfileAuthority, ...]
    roots: NativeRegionAuthorityRoots
    layout: NativeRegionAuthorityLayout
    files: tuple[NativeRegionAuthorityFile, ...]


class NativeRegionAuthorityError(Exception):
    """A bounded owner-authority load failure; no partial authority escapes."""

    def __init__(self, status: str, reason: str):
        self.status = status if status in ("unavailable", "failed") else "failed"
        self.reason = reason[:96]
        super().__init__(self.reason)


@dataclass(frozen=True)
class NativeRegionSelection:
    partition: str
    task_record_ref: str
    result_record_ref: str
    verified_record_ref: str


@dataclass(frozen=True)
class NativeRegionRecordRefs:
    task: str
    result: str
    verified: str


@dataclass(frozen=True)
class NativeRegionAdmissionRead:
    status: str
    reason: str
    admission_identity: str | None = None
    record_refs: NativeRegionRecordRefs | None = None
    closure_ref: str | None = None
    verifier_execution_qualified: bool = False
    producer_execution_qualified: bool = False
    region_equal: bool = False
    source_acceptance: str = "not_evaluated"


class _Refusal(Exception):
    def __init__(self, status: str, reason: str):
        self.status, self.reason = status, reason
        super().__init__(reason)


def _need(ok: bool, reason: str, status: str = "failed") -> None:
    if not ok:
        raise _Refusal(status, reason)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(info) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _id(value: Any) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None and len(value.encode("utf-8")) <= 256


def _hash(value: Any) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None


def _ref(value: Any) -> str:
    _need(type(value) is str and len(value) == 71 and value.startswith("sha256:") and _hash(value[7:]), "invalid_ref")
    return value


def _fields(value: Any, fields: set[str] | frozenset[str], reason: str) -> None:
    _need(type(value) is dict and set(value) == set(fields), reason)


def _json(raw: bytes, *, canonical: bool = True) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    try:
        def finite_float(raw_number: str) -> float:
            number = float(raw_number)
            if not math.isfinite(number):
                raise ValueError("nonfinite")
            return number
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_float=finite_float,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
        stack = [(value, 0)]
        while stack:
            node, depth = stack.pop()
            _need(depth <= 64, "json_depth_exceeded")
            if type(node) is dict:
                stack.extend((child, depth + 1) for child in node.values())
            elif type(node) is list:
                stack.extend((child, depth + 1) for child in node)
        if canonical:
            _need(canonical_json(value) == raw, "noncanonical_encoding")
        return value
    except _Refusal:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise _Refusal("failed", "invalid_json") from exc


def _path_parts(path: str, *, absolute: bool) -> tuple[str, ...]:
    _need(type(path) is str and len(path.encode("utf-8")) <= 512 and "\\" not in path
          and (path.startswith("/") is absolute) and "~" not in path, "unsafe_path")
    parts = path.split("/")[1:] if absolute else path.split("/")
    _need(bool(parts) and all(part not in ("", ".", "..") and not any(ord(c) < 32 or ord(c) == 127 for c in part)
                              for part in parts), "unsafe_path")
    return tuple(parts)


class _BoundedFiles:
    """Descriptor-relative, no-follow regular-file reads with cooperative budgets."""
    def __init__(self, deadline: float, *, aggregate_cap: int, chunk: int = 64 * KIB):
        self.deadline = deadline
        self.aggregate_cap = aggregate_cap
        self.chunk = chunk
        self.actual = 0
        self.observations: dict[tuple[str, str], tuple[str, tuple[int, int, int, int, int]]] = {}

    def tick(self, reserve: float = 0) -> None:
        _need(time.monotonic() + reserve < self.deadline, "deadline_exceeded", "unavailable")

    def read(self, path: str, cap: int, role: str, *, count_aggregate: bool = True) -> tuple[bytes, NativeRegionAuthorityFile]:
        self.tick()
        parts = _path_parts(path, absolute=True)
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = None
        try:
            for part in parts[:-1]:
                self.tick()
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            before = os.fstat(fd)
            _need(stat.S_ISREG(before.st_mode) and before.st_size <= cap, "file_unavailable", "unavailable")
            chunks, size, hasher = [], 0, hashlib.sha256()
            while True:
                self.tick()
                room = cap + 1 - size
                block = os.read(fd, min(self.chunk, room))
                if not block:
                    break
                size += len(block)
                if count_aggregate:
                    self.actual += len(block)
                    _need(self.actual <= self.aggregate_cap, "limit_exceeded", "unavailable")
                _need(size <= cap, "limit_exceeded", "unavailable")
                chunks.append(block)
                hasher.update(block)
            after = os.fstat(fd)
            _need(_identity(before) == _identity(after) and size == before.st_size, "files_unstable", "unavailable")
            raw, digest, identity = b"".join(chunks), hasher.hexdigest(), _identity(after)
            key = (role, path)
            old = self.observations.setdefault(key, (digest, identity))
            _need(old == (digest, identity), "files_unstable", "unavailable")
            self.tick()
            return raw, NativeRegionAuthorityFile(role, path, digest, identity)
        except OSError as exc:
            raise _Refusal("unavailable", "file_unavailable") from exc
        finally:
            if fd is not None:
                os.close(fd)
            os.close(directory)


class _CASReader:
    """Read immutable local CAS objects by layout path and authenticate actual bytes."""
    def __init__(self, authority: NativeRegionAuthority, deadline: float):
        self.authority = authority
        self.deadline = deadline
        self.files = _BoundedFiles(deadline, aggregate_cap=_CAS_LIMIT)
        self.values: dict[str, bytes] = {}
        self.caps: dict[str, int] = {}
        self.total_refs: set[str] = set()

    def read(self, value: str, cap: int, *, retain: bool = True) -> bytes:
        ref = _ref(value)
        previous = self.caps.get(ref)
        self.caps[ref] = cap if previous is None else min(previous, cap)
        _need(len(self.total_refs | {ref}) <= 128, "limit_exceeded", "unavailable")
        self.total_refs.add(ref)
        # A repeated reference is read again under its smallest cap; caching is never proof.
        layout = Layout(hash_algorithm=self.authority.layout.hash_algorithm,
                        shard_width=self.authority.layout.shard_width,
                        shard_depth=self.authority.layout.shard_depth,
                        schema=self.authority.layout.schema)
        rel = layout.relpath(ObjectRef(ref))
        path = self.authority.roots.objects_root.rstrip("/") + "/" + rel
        raw, _ = self.files.read(path, min(cap, self.caps[ref]), "cas:" + ref)
        _need(_sha(raw) == ref[7:], "object_hash_mismatch")
        if retain:
            self.values[ref] = raw
        else:
            self.values.pop(ref, None)
        return raw

    def revalidate(self) -> None:
        for ref, cap in tuple(self.caps.items()):
            self.read(ref, cap, retain=True)
        _need(time.monotonic() < self.deadline, "deadline_exceeded", "unavailable")


def _uint(value: Any) -> bool:
    return type(value) is int and value >= 0


def _string_list(value: Any, *, empty: bool = False, cap: int = 64) -> bool:
    return (type(value) is list and len(value) <= cap and (empty or bool(value))
            and all(_id(item) for item in value) and len(set(value)) == len(value))


def _profile_row(profile: NativeRegionProfileAuthority) -> dict:
    return _json(profile.profile_bytes)


def _selected_profile(authority: NativeRegionAuthority, task: dict, result: dict, closure: dict,
                      verifier_key: str, task_signer: str) -> tuple[NativeRegionProfileAuthority, dict]:
    candidates = []
    for profile in authority.profiles:
        row = _profile_row(profile)
        if row["profile_id"] == closure.get("profile_id"):
            candidates.append((profile, row))
    _need(len(candidates) == 1, "profile_not_configured", "unavailable" if not candidates else "failed")
    return candidates[0]


def _check_revocation(authority: NativeRegionAuthority, key_id: str) -> bool:
    policy = _json(authority.snapshot_bytes)
    revocations = policy["revocations"]
    key_map = {entry.key_id: entry for entry in authority.public_keys}
    entry = key_map.get(key_id)
    if entry is None:
        return False
    return any(candidate in revocations for candidate in (key_id, *entry.lineage))


def _stale_keys(authority: NativeRegionAuthority, record, role: str, allowlist: list[str], ring: Keyring) -> bool:
    key = record.signer_key
    _need(ring.knows(key), "signer_unavailable", "unavailable")
    _need(ring.verify(key, unsigned_bytes(record), record.signature), "bad_signature")
    return (key not in allowlist or ring.role_of(key) != role and not (role == "operator" and ring.role_of(key) == "fleet")
            or _check_revocation(authority, key))


def _validate_profile(row: Any, key_meta: dict[str, tuple[str, tuple[str, ...]]]) -> bytes:
    _fields(row, _PROFILE_FIELDS, "invalid_execution_profile")
    for field in ("profile_id", "kind", "dispatch", "method", "checker_profile", "comparison_policy", "verifier_id"):
        _need(_id(row[field]), "invalid_execution_profile")
    for field in ("profile_sha256", "implementation_source_sha256", "launcher_sha256", "filter_sha256",
                  "environment_sha256", "entrypoint_sha256"):
        _need(_hash(row[field]), "invalid_execution_profile")
    _need(type(row["kind_version"]) is int and row["kind_version"] == 1
          and row["kind"] == "parity-region-check" and row["dispatch"] == "kind"
          and row["method"] == "parity-region-coff-i386-leaf-v1"
          and row["comparison_policy"] == "coff-i386-register-leaf-v1"
          and row["checker_profile"] == "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1"
          and row["verifier_id"] == "parity:bc1e047126f9c6914bd1695798175234642ab9eaf45e886f841b59a4231e1a81",
          "invalid_execution_profile")
    _ref(row["root_inventory_ref"])
    for field in ("basis_hashes", "task_operator_keys", "producer_keys", "verifier_keys"):
        values = row[field]
        _need(type(values) is list and 0 < len(values) <= 64 and all(_id(v) and v != "*" for v in values)
              and len(set(values)) == len(values), "invalid_execution_profile")
    for field, roles in (("task_operator_keys", {"operator", "fleet"}),
                          ("producer_keys", {"node", "operator", "fleet", "donor"}),
                          ("verifier_keys", {"operator", "fleet"})):
        _need(all(key in key_meta and key_meta[key][0] in roles for key in row[field]), "invalid_execution_profile")
    return canonical_json(row)


def _load_once(cfg: NativeRegionReaderConfig, budget: _BoundedFiles) -> NativeRegionAuthority:
    _need(HAVE_CRYPTOGRAPHY, "crypto_unavailable", "unavailable")
    _need(type(cfg) is NativeRegionReaderConfig and type(cfg.owner_config_path) is str
          and bool(cfg.owner_config_path), "owner_config_unavailable", "unavailable")
    owner_path = cfg.owner_config_path
    _path_parts(owner_path, absolute=True)
    owner_raw, owner_file = budget.read(owner_path, 16 * KIB, "owner_config")
    owner = _json(owner_raw)
    _fields(owner, set("schema configuration_revision snapshot_path snapshot_sha256 policy_id generation objects_root log_root public_key_root shard_width shard_depth".split()), "invalid_owner_config")
    _need(owner["schema"] == OWNER_SCHEMA and type(owner["configuration_revision"]) is int
          and owner["configuration_revision"] >= 0 and type(owner["generation"]) is int and owner["generation"] >= 0
          and _hash(owner["snapshot_sha256"]) and _id(owner["policy_id"]), "invalid_owner_config")
    for field in ("snapshot_path", "objects_root", "log_root", "public_key_root"):
        _path_parts(owner[field], absolute=True)
    _need(type(owner["shard_width"]) is int and 0 <= owner["shard_width"] <= 4
          and type(owner["shard_depth"]) is int and 0 <= owner["shard_depth"] <= 2, "invalid_owner_config")
    snapshot_raw, snapshot_file = budget.read(owner["snapshot_path"], MIB, "snapshot")
    _need(_sha(snapshot_raw) == owner["snapshot_sha256"], "snapshot_pin_mismatch")
    snapshot = _json(snapshot_raw)
    _fields(snapshot, set("schema policy_id generation public_keys revocations independence_policy execution_profiles corpus_scope".split()), "invalid_admission_snapshot")
    _need(snapshot["schema"] == SNAPSHOT_SCHEMA and snapshot["policy_id"] == owner["policy_id"]
          and type(snapshot["generation"]) is int and snapshot["generation"] == owner["generation"]
          and snapshot["independence_policy"] == "disjoint-lineage" and snapshot["corpus_scope"] is None,
          "snapshot_pin_mismatch")
    public_rows = snapshot["public_keys"]
    _need(type(public_rows) is list and 0 < len(public_rows) <= 64, "invalid_public_keys")
    keys, key_meta, materials, key_files = [], {}, set(), []
    for row in public_rows:
        budget.tick()
        _fields(row, {"filename", "sha256", "key_id", "algorithm", "role", "lineage"}, "invalid_public_key")
        name = row["filename"]
        _need(type(name) is str and len(_path_parts(name, absolute=False)) == 1 and name.endswith((".pub", ".json"))
              and _hash(row["sha256"]) and _id(row["key_id"]) and row["algorithm"] == "ed25519"
              and row["role"] in ("operator", "fleet", "donor", "node")
              and type(row["lineage"]) is list and len(row["lineage"]) <= 64
              and all(_id(k) for k in row["lineage"]) and len(set(row["lineage"])) == len(row["lineage"]), "invalid_public_key")
        path = owner["public_key_root"].rstrip("/") + "/" + name
        raw, file_obs = budget.read(path, 16 * KIB, "public_key")
        _need(_sha(raw) == row["sha256"], "public_key_hash_mismatch")
        if name.endswith(".pub"):
            material = raw
            _need(row["role"] == "operator" and row["lineage"] == [] and len(material) == 32
                  and row["key_id"] == "ed25519:" + _sha(material), "invalid_public_key")
        else:
            data = _json(raw, canonical=False)
            required, optional = {"key_id", "algorithm", "public", "role", "lineage"}, {"created_at", "expires_at", "previous_key_ids"}
            _need(type(data) is dict and required <= set(data) <= required | optional, "invalid_public_key")
            for field in ("created_at", "expires_at"):
                _need(field not in data or (type(data[field]) in (int, float) and math.isfinite(data[field])),
                      "invalid_public_key")
            _need("previous_key_ids" not in data or _string_list(data["previous_key_ids"], empty=True),
                  "invalid_public_key")
            _need(all(data[k] == row[k] for k in ("key_id", "algorithm", "role", "lineage"))
                  and type(data["public"]) is str and _hash(data["public"]), "public_key_metadata_mismatch")
            material = bytes.fromhex(data["public"])
            from agentdecompile_grid.worker.identity import key_id_for
            _need(len(material) == 32 and row["key_id"] == key_id_for("ed25519", material), "invalid_public_key")
        _need(material not in materials and row["key_id"] not in key_meta, "duplicate_public_key_material")
        materials.add(material)
        key_meta[row["key_id"]] = (row["role"], tuple(row["lineage"]))
        keys.append(NativeRegionPublicKey(name, raw, row["sha256"], row["key_id"], row["algorithm"],
                                         row["role"], tuple(row["lineage"]), material))
        key_files.append({"filename": name, "sha256": row["sha256"]})
        # Keep the per-file identity in the common deterministic observations list.
        del file_obs
    for key_id, (_, lineage) in key_meta.items():
        _need(key_id not in lineage and all(parent in key_meta for parent in lineage), "invalid_lineage")
        for parent in lineage:
            _need(key_id not in key_meta[parent][1] and set(key_meta[parent][1]).issubset(lineage), "invalid_lineage")
    revocations = snapshot["revocations"]
    _need(type(revocations) is dict and len(revocations) <= 4096, "invalid_revocations")
    for revoked_id, item in revocations.items():
        _fields(item, {"at", "by", "reason"}, "invalid_revocations")
        _need(_id(revoked_id) and type(item["at"]) in (int, float) and _id(item["reason"])
              and item["by"] in key_meta and key_meta[item["by"]][0] in ("operator", "fleet"), "invalid_revocations")
    revocation_bytes = canonical_json(revocations)
    profiles_raw = snapshot["execution_profiles"]
    _need(type(profiles_raw) is list and 0 < len(profiles_raw) <= 16, "invalid_execution_profiles")
    profile_rows, seen = [], set()
    for row in profiles_raw:
        encoded = _validate_profile(row, key_meta)
        _need(encoded not in seen, "duplicate_execution_profile")
        seen.add(encoded)
        profile_rows.append((row, encoded))
    layout_path = owner["objects_root"].rstrip("/") + "/layout.json"
    layout_raw, layout_file = budget.read(layout_path, 4 * KIB, "layout")
    layout = _json(layout_raw)
    _fields(layout, {"schema", "hash_algorithm", "shard_width", "shard_depth"}, "unsupported_layout")
    _need(type(layout["schema"]) is int and layout["schema"] == 1 and layout["hash_algorithm"] == "sha256"
          and type(layout["shard_width"]) is int and layout["shard_width"] == owner["shard_width"]
          and type(layout["shard_depth"]) is int and layout["shard_depth"] == owner["shard_depth"], "unsupported_layout")
    root_values = NativeRegionAuthorityRoots(owner_path, owner["snapshot_path"], owner["objects_root"],
                                              owner["log_root"], owner["public_key_root"])
    config_digest, snapshot_digest = _sha(owner_raw), _sha(snapshot_raw)
    auth_profiles = []
    for row, encoded in profile_rows:
        effective = _sha(canonical_json({"predicate": PREDICATE, "configuration_sha256": config_digest,
                                         "snapshot_sha256": snapshot_digest, "public_key_files": sorted(key_files, key=lambda v: v["filename"]),
                                         "execution_profile": row}))
        auth_profiles.append(NativeRegionProfileAuthority(row["profile_id"], encoded, _sha(encoded), effective))
    files = [owner_file, snapshot_file, layout_file]
    files.extend(NativeRegionAuthorityFile(role, path, digest, identity)
                 for (role, path), (digest, identity) in budget.observations.items()
                 if role == "public_key")
    return NativeRegionAuthority(owner_raw, config_digest, owner["configuration_revision"], snapshot_raw,
                                 snapshot_digest, owner["policy_id"], owner["generation"], revocation_bytes,
                                 _sha(revocation_bytes), tuple(sorted(keys, key=lambda k: k.filename)),
                                 tuple(sorted(auth_profiles, key=lambda p: p.profile_bytes)), root_values,
                                 NativeRegionAuthorityLayout(layout["schema"], layout["hash_algorithm"],
                                                             layout["shard_width"], layout["shard_depth"],
                                                             layout_raw, _sha(layout_raw)),
                                 tuple(sorted(files, key=lambda f: (f.role, f.path))))


def load_native_region_authority(cfg: NativeRegionReaderConfig) -> NativeRegionAuthority:
    """Freshly authenticate all owner-selected public policy files, with two coherent passes."""
    deadline = time.monotonic() + 5.0
    budget = _BoundedFiles(deadline, aggregate_cap=8 * MIB)
    try:
        first = _load_once(cfg, budget)
        # Second pass order is fixed: layout, keys, snapshot, config last.
        second = budget
        for file in sorted(first.files, key=lambda f: {"layout": 0, "public_key": 1, "snapshot": 2, "owner_config": 3}[f.role]):
            raw, observed = second.read(file.path, {"owner_config": 16*KIB, "snapshot": MIB, "layout": 4*KIB, "public_key": 16*KIB}[file.role], file.role)
            _need(_sha(raw) == file.sha256 and observed.identity == file.identity, "files_unstable", "unavailable")
        _need(time.monotonic() < deadline, "deadline_exceeded", "unavailable")
        # The complete selected file set was reread in the mandated order and each identity
        # and digest was compared to the first pass. The config is deliberately last.
        _need(time.monotonic() < deadline, "deadline_exceeded", "unavailable")
        return first
    except _Refusal as exc:
        raise NativeRegionAuthorityError(exc.status, exc.reason) from exc
    except NativeRegionAuthorityError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError, GridError) as exc:
        raise NativeRegionAuthorityError("failed", "invalid_owner_authority") from exc


def authenticate_native_region_execution(cfg: NativeRegionReaderConfig,
                                         selection: NativeRegionSelection) -> NativeRegionAdmissionRead:
    """Authenticate an existing signed execution tuple; never run code or mutate storage."""
    deadline = time.monotonic() + 30.0
    authority = None
    admission_identity = None
    selected_refs = None
    closure_ref = None
    try:
        _need(type(selection) is NativeRegionSelection, "invalid_selection")
        _need(5.0 < deadline - time.monotonic(), "deadline_exceeded", "unavailable")
        authority = load_native_region_authority(cfg)
        _need(time.monotonic() < deadline - 5.0, "deadline_exceeded", "unavailable")
        admission_identity = None
        records, lines, chain_digest, keyring, log_budget, log_observation = _read_partition(selection, authority, deadline)
        selected = _select_records(records, lines, selection)
        task, result, verdict = selected
        selected_refs = NativeRegionRecordRefs(*( "sha256:" + _sha(line) for line in (task[1], result[1], verdict[1]) ))
        _need(all(_sha(raw) == ref[7:] for raw, ref in zip((task[1], result[1], verdict[1]),
               (selection.task_record_ref, selection.result_record_ref, selection.verified_record_ref))), "selection_mismatch")
        for record, _ in selected:
            _need(keyring.knows(record.signer_key), "signer_unavailable", "unavailable")
            _need(keyring.verify(record.signer_key, unsigned_bytes(record), record.signature), "bad_signature")
        task_record, task_bytes = task
        result_record, result_line = result
        verdict_record, _ = verdict
        task_body, result_body, verdict_body = task_record.body, result_record.body, verdict_record.body
        _validate_task(task_body, selection.partition)
        result_object_ref = _ref(result_body.get("result_ref"))
        _validate_result_record(result_body, task_body, result_record.signer_key)
        _fields(verdict_body, {"task_id", "result_ref", "outcome", "verifier_key", "method", "producer_key",
                               "verifier_lineage", "nonce", "evidence_ref"}, "invalid_verified_record")
        _need(verdict_body["task_id"] == task_body["task_id"] and verdict_body["result_ref"] == result_object_ref
              and verdict_body["producer_key"] == result_record.signer_key and verdict_body["method"] == _METHOD
              and verdict_body["verifier_key"] == verdict_record.signer_key
              and verdict_body["outcome"] == "verified" and verdict_record.basis_hash == task_body["basis_hash"]
              and result_record.basis_hash == task_body["basis_hash"] and _string_list(verdict_body["verifier_lineage"], empty=True)
              and _id(verdict_body["nonce"]), "tuple_association_mismatch")
        cas = _CASReader(authority, deadline)
        result_object = _json(cas.read(result_object_ref, 64*KIB))
        _validate_result_object(result_object, result_body, task_body)
        enclosing = _json(cas.read(_ref(verdict_body["evidence_ref"]), 2*MIB))
        _fields(enclosing, {"schema", "lane_evidence", "execution_closure_ref"}, "invalid_execution_evidence")
        _need(enclosing["schema"] == READER_RESULT_SCHEMA, "invalid_execution_evidence")
        closure_ref = _ref(enclosing["execution_closure_ref"])
        closure = _json(cas.read(closure_ref, 128*KIB))
        _validate_closure(closure)
        v0_ref = _ref(closure["v0_ref"])
        v0 = _json(cas.read(v0_ref, MIB))
        _validate_v0(v0)
        _need(v0["task_id"] == task_body["task_id"] and v0["result_ref"] == result_object_ref
              and v0["outcome"] == "verified" and v0["method"] == _METHOD
              and v0["verifier_key"] == verdict_record.signer_key and v0["evidence"] == enclosing["lane_evidence"],
              "v0_binding_mismatch")
        _validate_p2_evidence(v0["evidence"])
        profile, profile_row = _selected_profile(authority, task_body, result_body, closure,
                                                 verdict_record.signer_key, task_record.signer_key)
        stale_reasons = _check_signed_roles(authority, selected, task_body, result_body, verdict_record,
                                             profile_row, keyring)
        _need(closure["task_id"] == task_body["task_id"]
              and closure["task_ref"] == "sha256:" + _sha(canonical_json(task_body))
              and closure["result_ref"] == result_object_ref and closure["basis_hash"] == task_body["basis_hash"]
              and closure["producer_key"] == result_record.signer_key and closure["verifier_key"] == verdict_record.signer_key
              and closure["task_record_sha256"] == _sha(task_bytes) and closure["result_record_sha256"] == _sha(result_line)
              and closure["v0_ref"] == v0_ref, "closure_tuple_mismatch")
        for closure_field, profile_field in (("profile_id", "profile_id"), ("profile_sha256", "profile_sha256"),
                                            ("root_inventory_ref", "root_inventory_ref"),
                                            ("implementation_source_sha256", "implementation_source_sha256"),
                                            ("launcher_sha256", "launcher_sha256"), ("filter_sha256", "filter_sha256"),
                                            ("environment_sha256", "environment_sha256"), ("entrypoint_sha256", "entrypoint_sha256")):
            if closure[closure_field] != profile_row[profile_field]:
                stale_reasons.append("profile_pin_mismatch")
        if closure["admission_generation"] != authority.generation or closure["admission_identity"] != profile.effective_authority_digest:
            stale_reasons.append("profile_pin_mismatch")
        _validate_role_graph(cas, closure, task_body, result_body, result_object, profile_row,
                             v0["evidence"], deadline)
        _scan_refutations(records, selection, task_body, result_object_ref, task_record.signer_key,
                          result_record.signer_key, profile_row, authority, keyring)
        raw2, obs2 = log_budget.read(log_observation.path, 16*MIB, "history")
        _need(_sha(raw2) == chain_digest and obs2.identity == log_observation.identity,
              "history_unstable", "unavailable")
        cas.revalidate()
        _need(deadline - time.monotonic() > 5.0, "deadline_exceeded", "unavailable")
        current = load_native_region_authority(cfg)
        _need(time.monotonic() < deadline - 5.0, "deadline_exceeded", "unavailable")
        _need(current == authority, "owner_authority_changed", "unavailable")
        if stale_reasons:
            raise _Refusal("stale", stale_reasons[0])
        return NativeRegionAdmissionRead("authenticated", "current_qualified_native_region",
                                         profile.effective_authority_digest, selected_refs, closure_ref,
                                         True, False, v0["evidence"]["grade"] == "matched", "not_evaluated")
    except NativeRegionAuthorityError as exc:
        return NativeRegionAdmissionRead(exc.status, exc.reason, admission_identity)
    except _Refusal as exc:
        return NativeRegionAdmissionRead(exc.status, exc.reason, admission_identity, selected_refs, closure_ref)
    except (GridError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        return NativeRegionAdmissionRead("failed", "invalid_native_region_evidence", admission_identity,
                                         selected_refs, closure_ref)


def _validate_task(task: dict, partition: str) -> None:
    fields = {"task_id", "kind", "kind_version", "inputs", "params", "basis_hash", "capabilities", "budget", "partition"}
    _fields(task, fields, "invalid_task")
    _need(_hash(task["task_id"]) and _hash(task["basis_hash"]) and task["kind"] == "parity-region-check"
          and type(task["kind_version"]) is int and task["kind_version"] == 1 and task["budget"] == "medium"
          and task["partition"] == partition and type(task["inputs"]) is dict
          and set(task["inputs"]) == {"target_task", "target_result", "parity_task", "parity_result", "target", "candidate"}
          and type(task["params"]) is dict and task["params"] == {"checker_profile": "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1",
                                                                   "comparison_policy": "coff-i386-register-leaf-v1"}
          and task["capabilities"] == ["objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1",
                                       _VERIFIER], "invalid_task")
    _need(all(type(value) is str and _ref(value) for value in task["inputs"].values()), "invalid_task")
    _need(len(canonical_json(task)) <= 64*KIB, "limit_exceeded", "unavailable")
    try:
        spec = TaskSpec.from_record(task)
        _need(spec.to_record() == task and spec.task_id == task["task_id"], "task_identity_mismatch")
    except (GridError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, _Refusal):
            raise
        raise _Refusal("failed", "invalid_task") from exc


def _validate_result_record(body: dict, task: dict, signer: str) -> None:
    fields = {"task_id", "kind", "status", "result_ref", "outputs", "producer_key", "producer_lineage",
              "elapsed_s", "deadline_s", "reason", "nonce"}
    _fields(body, fields, "invalid_result_record")
    _need(body["task_id"] == task["task_id"] and body["kind"] == task["kind"] and body["status"] == "ok"
          and body["producer_key"] == signer and _string_list(body["producer_lineage"], empty=True)
          and type(body["elapsed_s"]) in (int, float) and math.isfinite(body["elapsed_s"]) and body["elapsed_s"] >= 0
          and type(body["deadline_s"]) in (int, float) and math.isfinite(body["deadline_s"]) and body["deadline_s"] >= 0
          and type(body["reason"]) is str and body["reason"] == "" and _id(body["nonce"]), "invalid_result_record")
    _ref(body["result_ref"])
    _need(type(body["outputs"]) is dict and set(body["outputs"]) == {"receipt", "target_inventory", "candidate_inventory"}
          and all(type(value) is str and _ref(value) for value in body["outputs"].values()), "invalid_result_record")


def _validate_result_object(value: dict, result_body: dict, task: dict) -> None:
    fields = {"task_id", "status", "outputs", "producer_key", "basis_hash", "elapsed_s", "reason", "candidates", "metrics"}
    _fields(value, fields, "invalid_result_object")
    _need(value["task_id"] == task["task_id"] and value["basis_hash"] == task["basis_hash"]
          and value["producer_key"] == result_body["producer_key"] and value["status"] == "ok"
          and value["outputs"] == result_body["outputs"] and value["reason"] == result_body["reason"]
          and type(value["elapsed_s"]) in (int, float) and math.isfinite(value["elapsed_s"])
          and value["elapsed_s"] >= 0 and type(value["candidates"]) is list
          and all(type(item) is dict for item in value["candidates"]) and type(value["metrics"]) is dict,
          "result_binding_mismatch")
    try:
        normalized = task_result_from_record(value).to_record()
    except (GridError, ValueError, TypeError, KeyError) as exc:
        raise _Refusal("failed", "invalid_result_object") from exc
    _need(canonical_json(normalized) == canonical_json(value), "result_encoding_mismatch")


def _validate_v0(v0: dict) -> None:
    _fields(v0, {"task_id", "result_ref", "outcome", "verifier_key", "method", "evidence"}, "invalid_v0")
    _need(_hash(v0["task_id"]) and _ref(v0["result_ref"]) and _id(v0["verifier_key"])
          and v0["outcome"] in ("verified", "refuted", "unverifiable") and type(v0["evidence"]) is dict,
          "invalid_v0")


def _validate_p2_evidence(evidence: dict) -> None:
    _fields(evidence, _EVIDENCE_FIELDS, "invalid_p2_evidence")
    _need(evidence["reason"] in ("region_equal", "region_differs") and evidence["grade"] in ("matched", "mismatched")
          and (evidence["reason"] == "region_equal") == (evidence["grade"] == "matched")
          and evidence["target_region_complete"] is (evidence["grade"] == "matched")
          and evidence["region_inventory_complete"] is True and evidence["checker_profile"] == "objdiff-3.8.0-native-linux-x86_64-coff-i386-leaf-v1"
          and evidence["comparison_policy"] == "coff-i386-register-leaf-v1" and evidence["verifier_id"] == _VERIFIER
          and evidence["implementation_source_closure"] == "not_evaluated"
          and evidence["implementation_runtime_closure"] == "not_evaluated"
          and evidence["source_binding"] == "not_evaluated" and evidence["runtime_admission"] == "not_evaluated",
          "invalid_p2_evidence")
    _fields(evidence["proposal_outputs"], {"receipt", "target_inventory", "candidate_inventory"}, "invalid_p2_evidence")
    _fields(evidence["recomputed_outputs"], {"receipt", "target_inventory", "candidate_inventory"}, "invalid_p2_evidence")
    for outputs in (evidence["proposal_outputs"], evidence["recomputed_outputs"]):
        for value in outputs.values():
            _ref(value)
    _fields(evidence["parity_raw_evidence"], {"proposed", "recomputed"}, "invalid_p2_evidence")
    for key in ("proposed", "recomputed"):
        _fields(evidence["parity_raw_evidence"][key], {"receipt", "raw"}, "invalid_p2_evidence")
        for value in evidence["parity_raw_evidence"][key].values():
            _ref(value)
    _fields(evidence["prerequisites"], {"target", "parity"}, "invalid_p2_evidence")
    for name, method in (("target", "mkobj-target-reference-free-v1"), ("parity", "parity-binding-v1")):
        item = evidence["prerequisites"][name]
        _fields(item, {"task_id", "result_ref", "method", "outcome"}, "invalid_p2_evidence")
        _need(_hash(item["task_id"]) and _ref(item["result_ref"]) and item["method"] == method
              and item["outcome"] == "verified", "invalid_p2_evidence")


def _validate_subtask(task: dict, expected_kind: str, basis: str) -> None:
    _fields(task, {"task_id", "kind", "kind_version", "inputs", "params", "basis_hash", "capabilities", "budget", "partition"},
            "invalid_prerequisite_task")
    _need(task["kind"] == expected_kind and type(task["kind_version"]) is int and task["kind_version"] == 1
          and task["basis_hash"] == basis and _hash(task["task_id"]) and type(task["inputs"]) is dict
          and type(task["params"]) is dict and type(task["capabilities"]) is list
          and type(task["partition"]) is str and task["budget"] == "small", "invalid_prerequisite_task")
    try:
        spec = TaskSpec.from_record(task)
        _need(spec.to_record() == task and spec.task_id == task["task_id"], "prerequisite_task_mismatch")
    except (GridError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, _Refusal):
            raise
        raise _Refusal("failed", "invalid_prerequisite_task") from exc
    if expected_kind == "mkobj-target":
        expected_params = {"selection", "selection_sha256", "implementation_basis", "implementation_sha256", "decoder_mode", "timeout_s"}
        _need(set(task["inputs"]) == {"store", "image"} and set(task["params"]) == expected_params
              and type(task["params"]["selection"]) is dict and type(task["params"]["implementation_basis"]) is dict
              and task["params"]["selection_sha256"] == _sha(canonical_json(task["params"]["selection"]))
              and task["params"]["implementation_sha256"] == _sha(canonical_json(task["params"]["implementation_basis"]))
              and task["params"]["selection"].get("store_ref") == task["inputs"]["store"]
              and task["params"]["selection"].get("image_ref") == task["inputs"]["image"]
              and task["capabilities"] == ["mkobj-target-reference-free:" + task["params"]["implementation_sha256"]],
              "invalid_target_task")
        selection = task["params"]["selection"]
        _fields(selection, {"schema", "store_ref", "image_ref", "corpus_scope_sha256", "generation_sha256",
                            "binary_id", "func_id", "addr", "size", "ranges", "report_version", "image_sha256"},
                "invalid_target_selection")
        _need(selection["schema"] == "agentdecompile.mkobj-target-selection/v1"
              and all(_uint(selection[field]) for field in ("addr", "size", "ranges"))
              and _uint(selection["binary_id"]) and selection["binary_id"] > 0
              and _uint(selection["func_id"]) and selection["func_id"] > 0
              and 0 < selection["size"] <= 64*KIB and selection["ranges"] == 1
              and all(_hash(selection[field]) for field in ("corpus_scope_sha256", "generation_sha256",
                                                             "report_version", "image_sha256"))
              and task["params"]["decoder_mode"] == "reference-free-only-v1"
              and type(task["params"]["timeout_s"]) in (int, float)
              and math.isfinite(task["params"]["timeout_s"])
              and 0 < task["params"]["timeout_s"] <= 60, "invalid_target_selection")
        implementation = task["params"]["implementation_basis"]
        _fields(implementation, {"schema", "kind", "kind_version", "decoder_mode", "selection_schema",
                                 "receipt_schema", "sources", "functions", "constants", "python",
                                 "sqlite_version", "external_decoder", "external_decoder_dependencies"},
                "invalid_target_implementation")
        _need(implementation["schema"] == "agentdecompile.mkobj-target-implementation/v1"
              and implementation["kind"] == "mkobj-target" and type(implementation["kind_version"]) is int
              and implementation["kind_version"] == 1
              and implementation["decoder_mode"] == "reference-free-only-v1"
              and implementation["selection_schema"] == "agentdecompile.mkobj-target-selection/v1"
              and implementation["receipt_schema"] == "agentdecompile.mkobj-target/v1"
              and type(implementation["sources"]) is dict and type(implementation["functions"]) is dict
              and all(type(name) is str and _hash(digest) for name, digest in implementation["sources"].items())
              and all(type(name) is str and _hash(digest) for name, digest in implementation["functions"].items())
              and type(implementation["constants"]) is dict and type(implementation["python"]) is dict
              and set(implementation["python"]) == {"implementation", "cache_tag", "version", "optimization"}
              and all(type(implementation["python"][key]) is str for key in ("implementation", "cache_tag"))
              and type(implementation["python"]["version"]) is list and len(implementation["python"]["version"]) == 5
              and all(type(part) is int for part in implementation["python"]["version"][:3])
              and type(implementation["python"]["optimization"]) is int
              and type(implementation["sqlite_version"]) is str and implementation["external_decoder"] is None
              and implementation["external_decoder_dependencies"] == [], "invalid_target_implementation")
    else:
        _need(set(task["inputs"]) == {"target", "candidate"}
              and {"verifier_id", "symbol"} <= set(task["params"]) <= {"verifier_id", "symbol", "timeout_s"}
              and task["params"].get("verifier_id") == _VERIFIER and task["capabilities"] == [_VERIFIER],
              "invalid_parity_task")
        if "timeout_s" in task["params"]:
            _need(type(task["params"]["timeout_s"]) in (int, float) and math.isfinite(task["params"]["timeout_s"])
                  and 0 < task["params"]["timeout_s"] <= 60, "invalid_parity_task")


def _validate_subresult(raw: bytes, task: dict, outputs: set[str], signer: str | None = None) -> dict:
    result = _json(raw)
    _fields(result, {"task_id", "status", "outputs", "producer_key", "basis_hash", "elapsed_s", "reason", "candidates", "metrics"},
            "invalid_prerequisite_result")
    _need(result["task_id"] == task["task_id"] and result["status"] == "ok" and result["basis_hash"] == task["basis_hash"]
          and _id(result["producer_key"]) and (signer is None or result["producer_key"] == signer)
          and type(result["elapsed_s"]) in (int, float) and math.isfinite(result["elapsed_s"])
          and result["elapsed_s"] >= 0 and result["reason"] == "" and type(result["outputs"]) is dict
          and set(result["outputs"]) == outputs and type(result["candidates"]) is list
          and all(type(row) is dict for row in result["candidates"]) and type(result["metrics"]) is dict,
          "invalid_prerequisite_result")
    try:
        _need(canonical_json(task_result_from_record(result).to_record()) == raw, "prerequisite_result_encoding")
    except (GridError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, _Refusal):
            raise
        raise _Refusal("failed", "invalid_prerequisite_result") from exc
    return result


def _validate_closure(value: dict) -> None:
    _fields(value, _C_FIELDS, "invalid_execution_closure")
    _need(value["schema"] == EXECUTION_SCHEMA and _id(value["profile_id"]) and _hash(value["profile_sha256"])
          and _hash(value["admission_identity"]) and _uint(value["admission_generation"]), "invalid_execution_closure")
    for field in ("root_inventory_ref", "task_ref", "result_ref", "v0_ref", "enforcement_ref", "module_diagnostics_ref"):
        _ref(value[field])
    for field in ("implementation_source_sha256", "launcher_sha256", "filter_sha256", "environment_sha256",
                  "entrypoint_sha256", "task_id", "basis_hash", "task_record_sha256", "result_record_sha256",
                  "ipc_transcript_sha256", "nonce"):
        _need(_hash(value[field]), "invalid_execution_closure")
    for field in ("job_id", "producer_key", "verifier_key", "method"):
        _need(_id(value[field]), "invalid_execution_closure")
    _need(value["op"] == "verify" and value["kind"] == "parity-region-check"
          and type(value["kind_version"]) is int and value["kind_version"] == 1 and value["dispatch"] == "kind"
          and value["method"] == _METHOD and _uint(value["elapsed_ms"]), "invalid_execution_closure")
    _fields(value["processes"], {"launcher", "namespace_init", "entrypoint"}, "invalid_execution_closure")
    for process in value["processes"].values():
        _fields(process, {"pid", "start_ticks"}, "invalid_execution_closure")
        _need(_uint(process["pid"]) and process["pid"] > 0 and _uint(process["start_ticks"]), "invalid_execution_closure")
    _fields(value["namespaces"], {"user", "pid", "mnt", "ipc", "net", "uts"}, "invalid_execution_closure")
    _need(all(_uint(item) and item > 0 for item in value["namespaces"].values()), "invalid_execution_closure")
    _fields(value["stage_ms"], {"capture", "stage", "launch_barrier", "run", "tree_termination", "export"}, "invalid_execution_closure")
    _need(all(_uint(item) for item in value["stage_ms"].values()), "invalid_execution_closure")
    for name in ("staged", "exported"):
        rows = value[name]
        _need(type(rows) is list and len(rows) <= 128, "invalid_execution_closure")
        last, seen = "", set()
        for row in rows:
            _fields(row, {"role", "ref", "size", "cap"}, "invalid_execution_closure")
            _need(_id(row["role"]) and row["role"] > last and row["role"] not in seen
                  and _ref(row["ref"]) and _uint(row["size"]) and _uint(row["cap"])
                  and row["size"] <= row["cap"], "invalid_execution_closure")
            seen.add(row["role"])
            last = row["role"]
    _need(value["measurement_scope"] == "complete-permitted-runtime-root" and value["tree_gone"] is True
          and value["collection_status"] == "complete", "invalid_execution_closure")
    _need(len(canonical_json(value)) <= 128*KIB, "limit_exceeded", "unavailable")


def _check_signed_roles(authority, selected, task, result, verdict, profile, ring):
    stale = []
    for (record, _), field, role in zip(selected, ("task_operator_keys", "producer_keys", "verifier_keys"),
                                        ("operator", "producer", "operator")):
        key = record.signer_key
        allowed_roles = (("operator", "fleet") if role == "operator"
                         else ("node", "donor", "operator", "fleet"))
        if ring.role_of(key) not in allowed_roles:
            stale.append("role_disallowed")
        if refusal_reason(record, ring) is not None:
            stale.append("role_disallowed")
        if key not in profile[field]:
            stale.append("key_disallowed")
        lineage = ring.lineage_of(key) or ()
        if _check_revocation(authority, key) or any(_check_revocation(authority, ancestor) for ancestor in lineage):
            stale.append("key_revoked")
    if not ring.independent(selected[1][0].signer_key, verdict.signer_key):
        stale.append("lineage_disallowed")
    if task["basis_hash"] not in profile["basis_hashes"]:
        stale.append("basis_disallowed")
    if selected[0][0].signer_key not in profile["task_operator_keys"]:
        stale.append("key_disallowed")
    if selected[1][0].signer_key not in profile["producer_keys"]:
        stale.append("key_disallowed")
    if verdict.signer_key not in profile["verifier_keys"]:
        stale.append("key_disallowed")
    _need(result["producer_lineage"] == list(ring.lineage_of(selected[1][0].signer_key) or ())
          and verdict.body["verifier_lineage"] == list(ring.lineage_of(verdict.signer_key) or ()), "lineage_mismatch")
    return stale


def _validate_role_graph(cas, closure, task, result_body, result_object, profile, evidence, deadline):
    """Authenticate every fixed staged CAS role and inline exception against the selected tuple."""
    inputs = task["inputs"]
    outputs = result_body["outputs"]
    target_task = _json(cas.read(inputs["target_task"], 64*KIB))
    target_result = _json(cas.read(inputs["target_result"], 64*KIB))
    parity_task = _json(cas.read(inputs["parity_task"], 64*KIB))
    parity_result = _json(cas.read(inputs["parity_result"], 64*KIB))
    target = inputs["target"]
    candidate = inputs["candidate"]
    _need(type(target_task) is dict and type(target_result) is dict and type(parity_task) is dict
          and type(parity_result) is dict, "invalid_prerequisite")
    _validate_subtask(target_task, "mkobj-target", task["basis_hash"])
    _validate_subtask(parity_task, "parity-check", task["basis_hash"])
    tinputs = target_task.get("inputs")
    _need(type(tinputs) is dict and _ref(tinputs.get("store")) and _ref(tinputs.get("image")), "invalid_prerequisite")
    target_result_out = target_result.get("outputs")
    parity_result_out = parity_result.get("outputs")
    target_result = _validate_subresult(cas.values[inputs["target_result"]], target_task, {"target", "receipt"})
    parity_result = _validate_subresult(cas.values[inputs["parity_result"]], parity_task, {"receipt", "raw"})
    target_result_out, parity_result_out = target_result["outputs"], parity_result["outputs"]
    _need(target_result_out["target"] == target, "target_result_object_mismatch")
    target_params = target_task["params"]
    _need(target_params["selection_sha256"] == _sha(canonical_json(target_params["selection"]))
          and target_params["implementation_sha256"] == _sha(canonical_json(target_params["implementation_basis"])),
          "target_selection_digest_mismatch")
    _need(parity_task["inputs"]["target"] == target and parity_task["inputs"]["candidate"] == candidate,
          "parity_input_mismatch")
    _need(parity_task["params"]["symbol"] == f'F_{target_task["params"]["selection"]["addr"]:x}',
          "parity_symbol_mismatch")
    _need(evidence["prerequisites"]["target"]["task_id"] == target_task["task_id"]
          and evidence["prerequisites"]["target"]["result_ref"] == inputs["target_result"]
          and evidence["prerequisites"]["parity"]["task_id"] == parity_task["task_id"]
          and evidence["prerequisites"]["parity"]["result_ref"] == inputs["parity_result"],
          "prerequisite_tuple_mismatch")
    expected = {
        "p2_task": ("sha256:" + _sha(canonical_json(task)), 64*KIB),
        "p2_result": (result_body["result_ref"], 64*KIB),
        "p2_proposed_receipt": (outputs["receipt"], MIB),
        "p2_proposed_target_inventory": (outputs["target_inventory"], MIB),
        "p2_proposed_candidate_inventory": (outputs["candidate_inventory"], MIB),
        "target_task": (inputs["target_task"], 64*KIB), "target_result": (inputs["target_result"], 64*KIB),
        "parity_task": (inputs["parity_task"], 64*KIB), "parity_result": (inputs["parity_result"], 64*KIB),
        "target": (target, 65536+1024), "candidate": (candidate, 64*MIB),
        "target_snapshot": (tinputs["store"], 256*MIB), "target_image": (tinputs["image"], 128*MIB),
        "target_proposed_receipt": (_ref(target_result_out.get("receipt")), 32*KIB),
        "parity_proposed_receipt": (_ref(parity_result_out.get("receipt")), MIB),
        "parity_proposed_raw": (_ref(parity_result_out.get("raw")), 4*MIB),
    }
    staged = {row["role"]: row for row in closure["staged"]}
    _need(set(staged) == set(expected), "invalid_staged_role_graph")
    for role, (expected_ref, cap) in expected.items():
        row = staged[role]
        _need(row["ref"] == expected_ref and row["cap"] == cap, "staged_role_binding_mismatch")
        if role == "p2_task":
            raw = canonical_json(task)
        else:
            raw = cas.read(row["ref"], cap)
        _need(len(raw) == row["size"] and _sha(raw) == row["ref"][7:], "staged_role_bytes_mismatch")
    _need(cas.read(outputs["receipt"], MIB) == cas.values.get(outputs["receipt"]), "missing_proposed_receipt")
    receipt = _json(cas.values[outputs["receipt"]])
    _need(receipt.get("schema") == "agentdecompile.parity-region.v1" and receipt.get("task_id") == task["task_id"]
          and receipt.get("basis_hash") == task["basis_hash"] and receipt.get("checker_profile") == profile["checker_profile"]
          and receipt.get("comparison_policy") == profile["comparison_policy"] and receipt.get("verifier_id") == profile["verifier_id"]
          and receipt.get("inputs") == inputs and receipt.get("inventory_refs") == {
              "target": outputs["target_inventory"], "candidate": outputs["candidate_inventory"]}
          and receipt.get("target_receipt_ref") == target_result_out["receipt"]
          and receipt.get("proposed_parity_receipt_ref") == parity_result_out["receipt"]
          and receipt.get("proposed_parity_raw_ref") == parity_result_out["raw"],
          "p2_receipt_mismatch")
    _need(evidence["proposal_outputs"] == evidence["recomputed_outputs"], "p2_recomputation_mismatch")
    inventories = {}
    reproduced_inventories = {}
    region_codes = {}
    region_tokens = {}
    for role, digest_ref in (("p2_proposed_target_inventory", outputs["target_inventory"]),
                             ("p2_proposed_candidate_inventory", outputs["candidate_inventory"])):
        inventory = _json(cas.values[digest_ref])
        _validate_region_inventory(inventory)
        inventories["target" if role.endswith("target_inventory") else "candidate"] = inventory
        expected_object = inputs["target"] if role.endswith("target_inventory") else inputs["candidate"]
        _need(inventory["object_ref"] == expected_object, "inventory_object_binding_mismatch")
        object_bytes = cas.values[expected_object]
        reproduced, region_bytes, _tokens = _inventory_coff(
            object_bytes, inventory["region"]["name"], inventory["region"]["length"],
            lambda: _need(deadline - time.monotonic() > 5.0, "deadline_exceeded", "unavailable"))
        side = "target" if role.endswith("target_inventory") else "candidate"
        reproduced_inventories[side] = reproduced
        region_codes[side], region_tokens[side] = region_bytes, _tokens
        _need(_sha(region_bytes) == inventory["region"]["sha256"], "region_inventory_reproduction_mismatch")
    reproduced_metadata = _metadata_differences(reproduced_inventories["target"], reproduced_inventories["candidate"])
    for side in ("target", "candidate"):
        reproduced_inventories[side]["metadata_differences"] = reproduced_metadata
        _need(reproduced_inventories[side] == inventories[side], "region_inventory_reproduction_mismatch")
    target_receipt = _json(cas.values[expected["target_proposed_receipt"][0]])
    selection = target_params["selection"]
    target_receipt_fields = {"schema", "claim", "status", "kind", "kind_version", "task_id", "basis_hash",
                             "selection", "selection_sha256", "implementation_basis", "implementation_sha256",
                             "decoder_mode", "mapping", "symbol", "target_ref", "target_sha256", "target_size",
                             "region_sha256", "relocation_count"}
    target_inventory = inventories["target"]
    _fields(target_receipt, target_receipt_fields, "invalid_target_receipt")
    _need(target_receipt["schema"] == "agentdecompile.mkobj-target/v1"
          and target_receipt["claim"] == "raw_image_function_target_object"
          and target_receipt["status"] == "produced" and target_receipt["kind"] == "mkobj-target"
          and type(target_receipt["kind_version"]) is int and target_receipt["kind_version"] == 1
          and target_receipt["task_id"] == target_task["task_id"]
          and target_receipt["basis_hash"] == task["basis_hash"]
          and target_receipt["selection"] == selection
          and target_receipt["selection_sha256"] == target_params["selection_sha256"]
          and target_receipt["implementation_basis"] == target_params["implementation_basis"]
          and target_receipt["implementation_sha256"] == target_params["implementation_sha256"]
          and target_receipt["decoder_mode"] == "reference-free-only-v1"
          and type(target_receipt["mapping"]) is dict
          and set(target_receipt["mapping"]) == {"file_offset", "machine", "optional_magic", "format"}
          and all(_uint(target_receipt["mapping"][key]) for key in ("file_offset", "machine", "optional_magic"))
          and target_receipt["mapping"]["machine"] == 0x14c
          and target_receipt["mapping"]["optional_magic"] == 0x10b
          and target_receipt["mapping"]["format"] == "coff-i386"
          and target_receipt["symbol"] == target_inventory["region"]["name"]
          and target_receipt["symbol"] == f'F_{selection["addr"]:x}'
          and target_receipt["target_ref"] == inputs["target"]
          and target_receipt["target_sha256"] == inputs["target"][7:]
          and target_receipt["target_size"] == target_inventory["object_size"]
          and target_receipt["region_sha256"] == target_inventory["region"]["sha256"]
          and type(target_receipt["relocation_count"]) is int and target_receipt["relocation_count"] == 0,
          "target_receipt_mismatch")
    parity_receipt = _json(cas.values[parity_result_out["receipt"]])
    _validate_parity_receipt(parity_receipt, parity_task, inputs["target"], inputs["candidate"],
                             target_receipt["symbol"], task["basis_hash"])
    _reproduce_parity_receipt(cas.values[parity_result_out["raw"]], parity_receipt, parity_task,
                              inputs["target"], inputs["candidate"], target_receipt["symbol"], task["basis_hash"])
    recomputed_raw = evidence["parity_raw_evidence"]["recomputed"]["raw"]
    proposed_raw = evidence["parity_raw_evidence"]["proposed"]["raw"]
    _validate_strict_parity_reports(cas.values[proposed_raw], cas.values[recomputed_raw], parity_receipt,
                                    target_receipt["symbol"], region_tokens["target"],
                                    region_tokens["candidate"], receipt, region_codes, inventories, deadline)
    _validate_p2_receipt(receipt, task, outputs, target_task, target_result, parity_result,
                         inventories, profile, evidence, region_codes, region_tokens)
    _validate_root_and_enforcement(cas, closure)
    _validate_export_graph(cas, closure, evidence)


def _validate_root_and_enforcement(cas, closure):
    inventory_raw = cas.read(closure["root_inventory_ref"], 8*MIB)
    try:
        from agentdecompile_grid.worker.native_closure_profile import validate_inventory
        inventory = validate_inventory(inventory_raw, expected_sha256=closure["root_inventory_ref"][7:])
    except Exception as exc:
        raise _Refusal("failed", "invalid_root_inventory") from exc
    entries = {entry.path: entry for entry in inventory.entries}
    # A mismatch with today's owner profile is classified as stale by the caller only after
    # every evidence object and the complete current history have authenticated.
    enforcement = _json(cas.read(closure["enforcement_ref"], 64*KIB))
    _fields(enforcement, {"schema", "argv", "environment", "mounts", "rlimits", "no_new_privs",
                          "filter_sha256", "namespace_ids", "work_limit_bytes"}, "invalid_enforcement")
    _need(enforcement["schema"] == "agentdecompile.native-region-enforcement.v1"
          and type(enforcement["argv"]) is list and len(enforcement["argv"]) <= 128
          and all(type(item) is str and len(item.encode("utf-8")) <= 512 and "\x00" not in item for item in enforcement["argv"])
          and enforcement["argv"] == ["/usr/bin/python3.12", "-I", "-S", "-B", "/app/native_closure_entry.py"]
          and type(enforcement["environment"]) is dict
          and enforcement["environment"] == {"AGENT_DECOMPILE_OBJDIFF": "/tools/objdiff", "HOME": "/work/home",
               "LANG": "C", "LC_ALL": "C", "PATH": "/tools", "TMPDIR": "/work/tmp", "TZ": "UTC"}
          and _hash(enforcement["filter_sha256"]) and enforcement["filter_sha256"] == closure["filter_sha256"]
          and enforcement["no_new_privs"] is True and type(enforcement["mounts"]) is list
          and len(enforcement["mounts"]) == 3 and type(enforcement["rlimits"]) is dict
          and all(_id(k) and _uint(v) for k, v in enforcement["rlimits"].items())
          and _uint(enforcement["work_limit_bytes"]) and 0 < enforcement["work_limit_bytes"] <= 1 << 30,
          "invalid_enforcement")
    _fields(enforcement["namespace_ids"], {"user", "pid", "mnt", "ipc", "net", "uts"}, "invalid_enforcement")
    _need(enforcement["namespace_ids"] == closure["namespaces"], "enforcement_namespace_mismatch")
    mounts = {}
    for mount in enforcement["mounts"]:
        _fields(mount, {"target", "source_role", "readonly", "noexec", "nosuid", "nodev"}, "invalid_enforcement")
        _need(type(mount["target"]) is str and type(mount["source_role"]) is str
              and all(type(mount[name]) is bool for name in ("readonly", "noexec", "nosuid", "nodev")),
              "invalid_enforcement")
        _need(mount["target"] not in mounts, "invalid_enforcement")
        mounts[mount["target"]] = mount
    expected_mounts = {
        "/": {"target": "/", "source_role": "capture", "readonly": True, "noexec": False,
              "nosuid": True, "nodev": True},
        "/work": {"target": "/work", "source_role": "work", "readonly": False, "noexec": True,
                   "nosuid": True, "nodev": True},
        "/dev/null": {"target": "/dev/null", "source_role": "null", "readonly": True, "noexec": False,
                      "nosuid": True, "nodev": True},
    }
    _need(mounts == expected_mounts, "invalid_enforcement")
    # Fixed resource names/values are part of this runtime profile.
    expected_limits = {"core": 0, "nofile": 128, "fsize": 256*MIB, "as": 2*MIB*1024,
                       "nproc": 32, "cpu": 300}
    _need(enforcement["rlimits"] == expected_limits, "invalid_enforcement")
    diagnostics = _json(cas.read(closure["module_diagnostics_ref"], MIB))
    _need(type(diagnostics) is list and len(diagnostics) <= 8192, "invalid_module_diagnostics")
    hashes, prior = set(), ""
    for row in diagnostics:
        _fields(row, {"name", "origin", "loader", "artifact_sha256"}, "invalid_module_diagnostics")
        _need(_id(row["name"]) and row["name"] > prior and type(row["origin"]) is str
              and len(row["origin"].encode("utf-8")) <= 512 and _id(row["loader"]), "invalid_module_diagnostics")
        prior = row["name"]
        digest = row["artifact_sha256"]
        if digest is None:
            _need(row["origin"] in ("built-in", "frozen"), "invalid_module_diagnostics")
        else:
            _need(_hash(digest) and any(entry.type == "file" and entry.sha256 == digest for entry in entries.values()),
                  "module_inventory_mismatch")
            hashes.add(digest)




def _coff_need(condition, reason, detail=""):
    _need(condition, reason)


def _scan_region(code: bytes, tick=lambda: None) -> list[dict]:
    """Finite byte grammar, not a general disassembler or address heuristic."""
    _coff_need(0 < len(code) <= REGION_LIMIT, "region_unsupported", "region_size")
    tokens, offset, zero = [], 0, False
    singles = {0x90: "nop", 0x40: "inc", 0x48: "dec", 0xC3: "ret"}
    while offset < len(code):
        tick()
        if code[offset:offset + 2] in (b"\x31\xc0", b"\x33\xc0"):
            length, operation, zero = 2, "xor", True
        else:
            operation = singles.get(code[offset])
            _coff_need(operation is not None, "region_unsupported", "instruction")
            length = 1
        _coff_need(operation != "ret" or offset == len(code) - 1, "region_unsupported", "return_extent")
        tokens.append({"offset": offset, "length": length, "encoding": code[offset:offset + length].hex(),
                       "operation": operation})
        offset += length
    _coff_need(zero and tokens[-1]["operation"] == "ret", "region_unsupported", "leaf_grammar")
    return tokens

def _inventory_coff(data: bytes, symbol: str, expected_size: int, tick=lambda: None) -> tuple[dict, bytes, list[dict]]:
    """Inventory every byte of the admitted standard COFF subset, without fixups."""
    malformed, unsupported = "object_malformed", "region_unsupported"
    _coff_need(type(data) is bytes and len(data) <= OBJECT_LIMIT, "limit_exceeded")
    _coff_need(type(symbol) is str and re.fullmatch(r"F_[0-9a-f]+", symbol) is not None
          and len(symbol) <= 4096 and type(expected_size) is int, "proposal_binding_invalid", "region_identity")

    def extent(start, count, width=1):
        tick()
        _coff_need(0 <= start <= len(data) and 0 <= count <= (len(data) - start) // width, malformed, "extent")
        return data[start:start + count * width]

    _coff_need(len(data) >= 20, malformed, "header")
    machine, sections, timestamp, symptr, slots, optional, characteristics = struct.unpack_from("<HHIIIHH", data)
    _coff_need(machine == 0x14C, unsupported, "machine")
    extent(20, sections, 40)
    _coff_need(optional == 0 and sections == 1 and characteristics in (0, 0x100), unsupported, "file_form")
    raw_name, physical, address, size, rawptr, relptr, lineptr, relcount, linecount, flags = struct.unpack_from("<8sIIIIIIHHI", data, 20)
    _coff_need(raw_name == b".text\0\0\0" and physical == address == 0, unsupported, "section")
    extent(rawptr, size)
    # Inspect declared relocation/line extents before refusing a valid unsupported declaration.
    extent(relptr, relcount, 10)
    extent(lineptr, linecount, 6)
    _coff_need(flags == 0x60500020 and relptr == relcount == lineptr == linecount == 0, unsupported, "section_dependencies")
    _coff_need(0 < size <= REGION_LIMIT, unsupported, "region_size")
    _coff_need(size == expected_size, unsupported, "region_association")
    _coff_need(0 < slots <= 256, "limit_exceeded" if slots > 256 else malformed, "symbol_slots")
    _coff_need(symptr > 0, malformed, "symbol_pointer")
    extent(symptr, slots, 18)
    strptr = symptr + slots * 18
    extent(strptr, 4)
    strsize = struct.unpack_from("<I", data, strptr)[0]
    _coff_need(4 <= strsize <= 16 << 10, "limit_exceeded" if strsize > 16 << 10 else malformed, "string_size")
    strings_raw = extent(strptr, strsize)
    _coff_need(strptr + strsize == len(data), malformed, "trailing_payload")
    entries, position, names = {}, 4, set()
    while position < strsize:
        tick()
        end = strings_raw.find(b"\0", position)
        _coff_need(end != -1, malformed, "string_termination")
        value = strings_raw[position:end]
        _coff_need(0 < len(value) <= 4096 and value.isascii(), malformed, "string_name")
        name = value.decode("ascii")
        _coff_need(name not in names, malformed, "duplicate_string")
        names.add(name)
        entries[position] = {"offset": position, "size": len(value) + 1, "name": name, "references": []}
        position = end + 1

    intervals = []
    def interval(start, end, classification):
        payload = extent(start, end - start)
        intervals.append({"start": start, "end": end, "class": classification, "sha256": _sha(payload)})

    def gap(start, end):
        _coff_need(0 <= end - start <= 3 and (start == end or end % 4 == 0), malformed, "file_gap")
        if end > start:
            _coff_need(not any(extent(start, end - start)), malformed, "nonzero_gap")
            interval(start, end, "zero_alignment")

    interval(0, 20, "file_header")
    interval(20, 60, "section_table")
    gap(60, rawptr)
    interval(rawptr, rawptr + size, "region")
    gap(rawptr + size, symptr)
    interval(symptr, strptr, "symbol_table")
    interval(strptr, len(data), "string_table")
    primaries, seen, slot, file_metadata = [], set(), 0, None
    while slot < slots:
        tick()
        start = symptr + slot * 18
        name_raw, value, section, typ, storage, aux_count = struct.unpack_from("<8sIhHBB", data, start)
        _coff_need(slot + 1 + aux_count <= slots, malformed, "aux_count")
        long_offset = None
        if name_raw[:4] == b"\0" * 4:
            long_offset = struct.unpack_from("<I", name_raw, 4)[0]
            _coff_need(long_offset in entries, malformed, "string_entry_start")
            name = entries[long_offset]["name"]
            entries[long_offset]["references"].append(slot)
        else:
            short, separator, padding = name_raw.partition(b"\0")
            _coff_need(bool(short) and short.isascii() and not any(padding), malformed, "inline_name")
            name = short.decode("ascii")
        _coff_need(name not in seen, malformed, "duplicate_symbol")
        seen.add(name)
        auxiliary = data[start + 18:start + (aux_count + 1) * 18]
        record = {"slot": slot, "end_slot": slot + 1 + aux_count, "name": name,
                  "name_field_hex": name_raw.hex(), "string_offset": long_offset,
                  "value": value, "section": section, "type": typ, "storage_class": storage, "aux_count": aux_count}
        if name == symbol:
            _coff_need(value == 0 and section == 1 and typ == 0x20 and storage == 2 and aux_count == 0,
                  unsupported, "function_symbol")
            record.update({"class": "function", "auxiliary_hex": []})
        elif name == ".text":
            _coff_need(long_offset is None and value == 0 and section == 1 and typ == 0 and storage == 3 and aux_count == 1,
                  unsupported, "section_symbol")
            expected_aux = struct.pack("<IHHIhBBh", size, 0, 0, 0, 0, 0, 0, 0)
            _coff_need(auxiliary == expected_aux, unsupported, "section_auxiliary")
            record.update({"class": "section_definition", "auxiliary_hex": [auxiliary.hex()]})
        elif name == ".file":
            _coff_need(long_offset is None and value == 0 and section == -2 and typ == 0 and storage == 103
                  and 1 <= aux_count <= 228, unsupported, "file_symbol")
            filename, terminator, fill = auxiliary.partition(b"\0")
            _coff_need(bool(terminator) and 0 < len(filename) <= 4096 and all(32 <= b <= 126 for b in filename)
                  and not any(fill) and (len(filename) + 1 + 17) // 18 == aux_count, malformed, "file_auxiliary")
            file_metadata = {"length": len(filename), "sha256": _sha(filename), "class": "file_metadata"}
            record.update({"class": "file", "filename": file_metadata})
        else:
            raise ValueError(unsupported, "extra_symbol")
        primaries.append(record)
        slot += 1 + aux_count
    _coff_need(seen in ({symbol, ".text"}, {symbol, ".text", ".file"}), unsupported, "symbol_inventory")
    _coff_need(all(entry["name"] == symbol and len(entry["references"]) == 1 for entry in entries.values()),
          malformed, "unreferenced_string")
    code = data[rawptr:rawptr + size]
    tokens = scan_region(code, tick)
    inventory = {
        "schema": "agentdecompile.parity-region-inventory.v1", "policy": "coff-i386-register-leaf-v1",
        "object_ref": "sha256:" + _sha(data), "object_sha256": _sha(data), "object_size": len(data),
        "header": {"machine": machine, "sections": sections, "timestamp": timestamp, "symbol_pointer": symptr,
                   "symbol_slots": slots, "optional_header_size": optional, "characteristics": characteristics},
        "section": {"name": ".text", "physical_address": physical, "virtual_address": address, "size": size,
                    "raw_pointer": rawptr, "relocation_pointer": relptr, "relocation_count": relcount,
                    "line_pointer": lineptr, "line_count": linecount, "characteristics": flags},
        "symbols": primaries, "strings": list(entries.values()), "string_table": {"offset": strptr, "size": strsize},
        "intervals": intervals, "region": {"name": symbol, "section": ".text", "offset": 0, "file_offset": rawptr,
                                           "length": size, "sha256": _sha(code)},
        "relocations": [], "line_numbers": [], "dependencies": [], "file_metadata": file_metadata,
        "coverage_bytes": len(data), "unclassified_bytes": 0,
    }
    tick()
    return inventory, code, tokens

def _validate_region_inventory(value: dict) -> None:
    fields = {"schema", "policy", "object_ref", "object_sha256", "object_size", "header", "section", "symbols",
              "strings", "string_table", "intervals", "region", "relocations", "line_numbers", "dependencies",
              "file_metadata", "coverage_bytes", "unclassified_bytes", "metadata_differences"}
    _fields(value, fields, "invalid_region_inventory")
    _need(value["schema"] == "agentdecompile.parity-region-inventory.v1"
          and value["policy"] == "coff-i386-register-leaf-v1" and _ref(value["object_ref"])
          and value["object_sha256"] == value["object_ref"][7:] and _uint(value["object_size"])
          and value["coverage_bytes"] == value["object_size"] and value["unclassified_bytes"] == 0
          and type(value["intervals"]) is list and type(value["region"]) is dict
          and value["region"].get("section") == ".text" and _hash(value["region"].get("sha256"))
          and _uint(value["region"].get("length")) and 0 < value["region"]["length"] <= 65536
          and value["relocations"] == [] and value["line_numbers"] == [] and value["dependencies"] == [],
          "invalid_region_inventory")
    _need(type(value["metadata_differences"]) is list
          and all(type(item) is str for item in value["metadata_differences"])
          and value["metadata_differences"] == sorted(set(value["metadata_differences"])),
          "invalid_region_inventory")
    cursor = 0
    for interval in value["intervals"]:
        _fields(interval, {"start", "end", "class", "sha256"}, "invalid_region_inventory")
        _need(_uint(interval["start"]) and _uint(interval["end"]) and interval["start"] == cursor
              and interval["end"] > interval["start"] and _hash(interval["sha256"]), "invalid_region_inventory")
        cursor = interval["end"]
    _need(cursor == value["coverage_bytes"], "invalid_region_inventory")


def _validate_parity_receipt(value, task, target_ref, candidate_ref, symbol, basis):
    required = {"schema", "status", "differences", "message", "objdiffExit", "detailLevel",
                "kind", "kind_version", "verifier_id", "verifier", "sides", "symbol", "grade", "basis_hash"}
    allowed = required | {"mismatchHistogram", "instructionMismatchCount", "alignedDiff"}
    _need(type(value) is dict and required <= set(value) <= allowed, "invalid_parity_receipt")
    grade = value["grade"]
    _need(value["schema"] == "agentdecompile.verify-objdiff.v1" and value["kind"] == "parity-check"
          and type(value["kind_version"]) is int and value["kind_version"] == 1
          and value["verifier_id"] == _VERIFIER and value["verifier"] == "native"
          and value["sides"] == {"target": target_ref[7:], "candidate": candidate_ref[7:]}
          and value["symbol"] == symbol and value["basis_hash"] == basis
          and grade in ("matched", "mismatched") and value["status"] == grade
          and type(value["differences"]) is int and type(value["objdiffExit"]) is int
          and value["objdiffExit"] == 0 and value["message"] == ("Object files match" if grade == "matched" else "Object files do not match")
          and value["detailLevel"] in ("instruction", "scalar-only")
          and ((grade == "matched" and value["differences"] == 0)
               or (grade == "mismatched" and value["differences"] > 0)), "invalid_parity_receipt")
    if "mismatchHistogram" in value:
        histogram = value["mismatchHistogram"]
        _need(type(histogram) is dict and all(key in {"INSERTION", "DELETION", "REPLACEMENT", "OPCODE_MISMATCH", "ARGUMENT_MISMATCH"}
                                             and type(count) is int and count > 0 for key, count in histogram.items()),
              "invalid_parity_receipt")
    if "instructionMismatchCount" in value:
        _need(type(value["instructionMismatchCount"]) is int and value["instructionMismatchCount"] >= 0
              and "mismatchHistogram" in value
              and value["instructionMismatchCount"] == sum(value["mismatchHistogram"].values()),
              "invalid_parity_receipt")
    if "alignedDiff" in value:
        _need(type(value["alignedDiff"]) is list and len(value["alignedDiff"]) <= 200,
              "invalid_parity_receipt")
        for row in value["alignedDiff"]:
            _fields(row, {"index", "target", "candidate", "diffKind", "differs"}, "invalid_parity_receipt")
            _need(_uint(row["index"]) and (row["target"] is None or type(row["target"]) is str)
                  and (row["candidate"] is None or type(row["candidate"]) is str)
                  and (row["diffKind"] is None or type(row["diffKind"]) is str)
                  and type(row["differs"]) is bool, "invalid_parity_receipt")
    _need(value["detailLevel"] == ("instruction" if value.get("mismatchHistogram") else "scalar-only"),
          "invalid_parity_receipt")


def _reproduce_parity_receipt(raw: bytes, receipt: dict, task: dict, target_ref: str,
                              candidate_ref: str, symbol: str, basis: str) -> None:
    try:
        _json(raw, canonical=False)
        output = raw.decode("utf-8", "strict")
        from agentdecompile_recovery.objdiff_verification import parse_objdiff_report
        report = parse_objdiff_report(0, output)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise _Refusal("failed", "invalid_parity_report") from exc
    _need(report.get("status") in ("matched", "mismatched"), "invalid_parity_report")
    reproduced = {key: value for key, value in report.items() if key != "output"}
    reproduced.update({"kind": "parity-check", "kind_version": 1, "verifier_id": _VERIFIER,
                       "verifier": "native", "sides": {"target": target_ref[7:], "candidate": candidate_ref[7:]},
                       "symbol": symbol, "grade": report["status"], "basis_hash": basis})
    _need(canonical_json(reproduced) == canonical_json(receipt), "parity_receipt_reproduction_mismatch")


def _strict_parity_report(raw: bytes, symbol: str, left_tokens: list[dict], right_tokens: list[dict],
                          grade: str, deadline: float) -> dict:
    try:
        from agentdecompile_recovery.grid_lanes.objdiff_v380 import parse_report
        return parse_report(raw, symbol, left_tokens, right_tokens, checker_grade=grade,
                            tick=lambda: _need(deadline - time.monotonic() > 5.0,
                                               "deadline_exceeded", "unavailable"))
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise _Refusal("failed", "invalid_strict_parity_report") from exc


def _metadata_differences(left: dict, right: dict) -> list[str]:
    checks = {
        "timestamp": (left["header"]["timestamp"], right["header"]["timestamp"]),
        "redundant_i386_characteristic": (left["header"]["characteristics"], right["header"]["characteristics"]),
        "file_offsets": ([left["section"]["raw_pointer"], left["header"]["symbol_pointer"], left["string_table"]["offset"]],
                         [right["section"]["raw_pointer"], right["header"]["symbol_pointer"], right["string_table"]["offset"]]),
        "zero_alignment": ([item for item in left["intervals"] if item["class"] == "zero_alignment"],
                           [item for item in right["intervals"] if item["class"] == "zero_alignment"]),
        "symbol_order": ([item["name"] for item in left["symbols"]], [item["name"] for item in right["symbols"]]),
        "function_name_representation": ([item["name_field_hex"] for item in left["symbols"] if item.get("class") == "function"],
                                          [item["name_field_hex"] for item in right["symbols"] if item.get("class") == "function"]),
        "string_table_layout": (left["strings"], right["strings"]),
        "optional_file_metadata": (left["file_metadata"], right["file_metadata"]),
    }
    return sorted(key for key, (first, second) in checks.items() if first != second)


def _validate_strict_parity_reports(proposed_raw: bytes, recomputed_raw: bytes, parity_receipt: dict,
                                    symbol: str, left_tokens: list[dict], right_tokens: list[dict],
                                    receipt: dict, region_codes: dict, inventories: dict, deadline: float) -> None:
    grade = parity_receipt["grade"]
    proposed = _strict_parity_report(proposed_raw, symbol, left_tokens, right_tokens, grade, deadline)
    recomputed = _strict_parity_report(recomputed_raw, symbol, left_tokens, right_tokens, grade, deadline)
    _need(proposed == recomputed and _sha(canonical_json(proposed)) == receipt["strict_report_sha256"],
          "strict_report_recomputation_mismatch")
    differences = sum(first != second for first, second in zip(region_codes["target"], region_codes["candidate"]))
    _need(len(region_codes["target"]) == len(region_codes["candidate"])
          and receipt["byte_difference_count"] == differences
          and receipt["grade"] == ("mismatched" if differences else "matched")
          and receipt["checker_grade"] == grade
          and receipt["instruction_count"] == {"target": len(left_tokens), "candidate": len(right_tokens)}
          and receipt["metadata_differences"] == _metadata_differences(inventories["target"], inventories["candidate"]),
          "strict_report_join_mismatch")


def _validate_p2_receipt(receipt, task, outputs, target_task, target_result, parity_result,
                         inventories, profile, evidence, region_codes, region_tokens):
    fields = set("schema kind kind_version task_id basis_hash checker_profile comparison_policy verifier_id upstream_commit upstream_asset_sha256 inputs prerequisites target_receipt_ref proposed_parity_receipt_ref proposed_parity_raw_ref objects target_selection selection_sha256 inventory_refs strict_report_sha256 section symbol region_length region_sha256 grade checker_grade byte_difference_count instruction_count relocation_count coverage_bytes unclassified_bytes metadata_differences comparison_scope reference_policy target_producer_scope runtime_admission source_binding linked_image_metadata".split())
    _fields(receipt, fields, "invalid_p2_receipt")
    _need(receipt["schema"] == "agentdecompile.parity-region.v1" and receipt["kind"] == task["kind"]
          and type(receipt["kind_version"]) is int and receipt["kind_version"] == 1
          and receipt["task_id"] == task["task_id"] and receipt["basis_hash"] == task["basis_hash"]
          and receipt["checker_profile"] == profile["checker_profile"]
          and receipt["comparison_policy"] == profile["comparison_policy"] and receipt["verifier_id"] == profile["verifier_id"]
          and receipt["upstream_commit"] == "784a16740a8a67b835b752ab867e76347d8a9691"
          and receipt["upstream_asset_sha256"] == _VERIFIER[7:] and receipt["inputs"] == task["inputs"]
          and receipt["target_receipt_ref"] == target_result["outputs"]["receipt"]
          and receipt["proposed_parity_receipt_ref"] == parity_result["outputs"]["receipt"]
          and receipt["proposed_parity_raw_ref"] == parity_result["outputs"]["raw"]
          and receipt["inventory_refs"] == {"target": outputs["target_inventory"], "candidate": outputs["candidate_inventory"]}
          and receipt["objects"] == {side: {"sha256": inventories[side]["object_sha256"],
                                                  "size": inventories[side]["object_size"]} for side in ("target", "candidate")}
          and receipt["region_sha256"] == {side: inventories[side]["region"]["sha256"] for side in ("target", "candidate")}
          and receipt["region_length"] == inventories["target"]["region"]["length"]
          and receipt["region_length"] == inventories["candidate"]["region"]["length"]
          and receipt["section"] == ".text" and receipt["symbol"] == inventories["target"]["region"]["name"]
          and receipt["symbol"] == inventories["candidate"]["region"]["name"]
          and receipt["coverage_bytes"] == receipt["region_length"]
          and receipt["unclassified_bytes"] == 0 and receipt["comparison_scope"] == "complete-emitted-reference-free-region"
          and receipt["reference_policy"] == "coff-i386-register-leaf-v1"
          and receipt["target_producer_scope"] == "conservative-pc-relative-byte-screen"
          and receipt["runtime_admission"] == "not_evaluated" and receipt["source_binding"] == "not_evaluated"
          and receipt["linked_image_metadata"] == "not_evaluated" and _hash(receipt["strict_report_sha256"])
          and receipt["grade"] == evidence["grade"] and receipt["grade"] in ("matched", "mismatched")
          and receipt["checker_grade"] in ("matched", "mismatched")
          and type(receipt["byte_difference_count"]) is int and receipt["byte_difference_count"] >= 0
          and ((receipt["grade"] == "matched" and receipt["byte_difference_count"] == 0)
               or (receipt["grade"] == "mismatched" and receipt["byte_difference_count"] > 0))
          and receipt["target_selection"] == {key: target_task["params"]["selection"][key]
                                                for key in ("image_sha256", "report_version", "binary_id", "func_id", "addr", "size")}
          and receipt["selection_sha256"] == target_task["params"]["selection_sha256"], "p2_receipt_mismatch")
    prerequisites = evidence["prerequisites"]
    expected_prereqs = {name: {key: item[key] for key in ("task_id", "result_ref", "method")}
                        for name, item in prerequisites.items()}
    _need(receipt["prerequisites"] == expected_prereqs, "p2_prerequisite_receipt_mismatch")
    _need(type(receipt["metadata_differences"]) is list
          and all(type(value) is str for value in receipt["metadata_differences"])
          and receipt["metadata_differences"] == sorted(set(receipt["metadata_differences"]))
          and type(receipt["instruction_count"]) is dict and set(receipt["instruction_count"]) == {"target", "candidate"}
          and all(_uint(value) for value in receipt["instruction_count"].values())
          and type(receipt["relocation_count"]) is int and receipt["relocation_count"] == 0,
          "p2_receipt_mismatch")


def _validate_export_graph(cas, closure, evidence):
    expected = {}
    for prefix, outputs in (("p2_proposed", evidence["proposal_outputs"]),
                            ("p2_recomputed", evidence["recomputed_outputs"])):
        for key, ref in outputs.items():
            expected[prefix + "_" + key] = (ref, MIB)
    for stage, rows in evidence["parity_raw_evidence"].items():
        for key, ref in rows.items():
            expected["parity_" + stage + "_" + key] = (ref, MIB if key == "receipt" else 4*MIB)
    staged = {row["role"]: row for row in closure["staged"]}
    for stage in ("target", "parity"):
        expected[f"{stage}_task"] = (staged[f"{stage}_task"]["ref"], 64*KIB)
        expected[f"{stage}_result"] = (staged[f"{stage}_result"]["ref"], 64*KIB)
    _need(set(expected) == {
        "p2_proposed_receipt", "p2_proposed_target_inventory", "p2_proposed_candidate_inventory",
        "p2_recomputed_receipt", "p2_recomputed_target_inventory", "p2_recomputed_candidate_inventory",
        "parity_proposed_receipt", "parity_proposed_raw", "parity_recomputed_receipt", "parity_recomputed_raw",
        "target_task", "target_result", "parity_task", "parity_result",
    }, "invalid_export_evidence_shape")
    exported = {row["role"]: row for row in closure["exported"]}
    _need(set(exported) == set(expected), "invalid_export_role_graph")
    _need(len(exported) <= 128 and sum(row["size"] for row in exported.values()) <= 64*MIB,
          "export_budget_exceeded")
    for role, (ref, cap) in expected.items():
        row = exported[role]
        _need(row["ref"] == ref and row["cap"] == cap and row["size"] <= cap,
              "export_role_binding_mismatch")
        raw = cas.read(ref, cap)
        _need(len(raw) == row["size"], "export_size_mismatch")


def _scan_refutations(records, selection, task, result_ref, task_operator, producer_key, profile, authority, ring):
    for record in records:
        if record.type != RecordType.REFUTED or record.body.get("task_id") != task["task_id"]:
            continue
        if record.body.get("result_ref") != result_ref:
            continue
        key = record.signer_key
        if not ring.knows(key):
            continue
        allowed = (key in profile["verifier_keys"] and task["basis_hash"] in profile["basis_hashes"]
                   and task_operator in profile["task_operator_keys"] and producer_key in profile["producer_keys"]
                   and ring.role_of(task_operator) in ("operator", "fleet")
                   and ring.role_of(producer_key) in ("node", "donor", "operator", "fleet")
                   and ring.role_of(key) in ("operator", "fleet")
                   and ring.independent(producer_key, key))
        if not allowed:
            continue
        # A bad signature from an otherwise currently eligible refuter is corruption, not silence.
        _need(ring.verify(key, unsigned_bytes(record), record.signature), "bad_negative_signature")
        _need(refusal_reason(record, ring) is None, "negative_signer_disallowed")
        revoked = _check_revocation(authority, key)
        lineage = ring.lineage_of(key) or ()
        if revoked or any(_check_revocation(authority, parent) for parent in lineage):
            continue
        body = record.body
        _need(type(body) is dict and (type(body.get("evidence")) is dict) != ("evidence_ref" in body),
              "negative_verdict_association_mismatch")
        evidence_field = "evidence" if "evidence" in body else "evidence_ref"
        _fields(body, {"task_id", "result_ref", "outcome", "verifier_key", "method", "producer_key",
                       "verifier_lineage", "nonce", evidence_field}, "negative_verdict_association_mismatch")
        _need(type(body) is dict and body.get("task_id") == task["task_id"] and body.get("result_ref") == result_ref
              and body.get("producer_key") == producer_key and body.get("method") == _METHOD
              and body.get("verifier_key") == key and body.get("outcome") == "refuted"
              and body.get("verifier_lineage") == list(ring.lineage_of(key) or ())
              and _id(body.get("nonce")) and record.basis_hash == task["basis_hash"],
              "negative_verdict_association_mismatch")
        raise _Refusal("failed", "conflicting_refutation")


def _read_partition(selection: NativeRegionSelection, authority: NativeRegionAuthority, deadline: float):
    _need(type(selection.partition) is str, "invalid_selection")
    validate_partition(selection.partition)
    _need(HAVE_CRYPTOGRAPHY, "crypto_unavailable", "unavailable")
    budget = _BoundedFiles(deadline, aggregate_cap=640 * MIB)
    log_path = authority.roots.log_root.rstrip("/") + "/" + selection.partition + "/records.jsonl"
    raw, observation = budget.read(log_path, 16 * MIB, "history")
    _need(raw and raw.endswith(b"\n"), "history_unavailable", "unavailable")
    lines = raw.splitlines(keepends=True)
    _need(len(lines) <= 4096, "limit_exceeded", "unavailable")
    records = []
    for line in lines:
        _need(time.monotonic() < deadline, "deadline_exceeded", "unavailable")
        _need(line.endswith(b"\n") and len(line) <= 128 * KIB, "limit_exceeded", "unavailable")
        data = _json(line[:-1])
        _fields(data, {"schema", "partition", "seq", "type", "body", "prev", "signer_key", "signature", "basis_hash"},
                "invalid_record")
        _need(type(data["schema"]) is int and data["schema"] == 1 and type(data["seq"]) is int
              and type(data["body"]) is dict and all(type(data[field]) is str
              for field in ("partition", "type", "prev", "signer_key", "signature", "basis_hash")),
              "invalid_record")
        try:
            record = record_from_dict(data)
            validate_record(record)
        except GridError as exc:
            raise _Refusal("failed", "invalid_record") from exc
        _need(canonical_json(record_to_dict(record)) == line[:-1], "record_encoding_mismatch")
        records.append(record)
    _need(records[0].seq == 1 and records[0].prev == "", "history_unavailable", "unavailable")
    try:
        verify_chain(records, partition=selection.partition)
    except GridError as exc:
        raise _Refusal("failed", "chain_mismatch") from exc
    ring = Keyring(allow_null=False)
    # Keyring public methods validate content-derived ids and cryptographic formats.
    for key in authority.public_keys:
        try:
            if key.filename.endswith(".pub"):
                _need(ring.add_ed25519_public(key.public_material, role=key.role) == key.key_id, "public_key_identity_mismatch")
            else:
                _need(ring.add_node_public(key.key_id, key.algorithm, key.public_material,
                                           role=key.role, lineage=key.lineage) == key.key_id,
                      "public_key_identity_mismatch")
        except Exception as exc:
            raise _Refusal("failed", "invalid_public_key") from exc
    return records, lines, _sha(raw), ring, budget, observation


def _select_records(records, lines, selection):
    wanted = (selection.task_record_ref, selection.result_record_ref, selection.verified_record_ref)
    _need(all(type(ref) is str and ref.startswith("sha256:") and _hash(ref[7:]) for ref in wanted), "invalid_selection")
    output = []
    for ref, expected in zip(wanted, (RecordType.TASK, RecordType.RESULT, RecordType.VERIFIED)):
        matches = [(record, line[:-1]) for record, line in zip(records, lines) if _sha(line[:-1]) == ref[7:]]
        _need(len(matches) == 1, "selected_record_unavailable" if not matches else "duplicate_selected_record",
              "unavailable" if not matches else "failed")
        record, raw = matches[0]
        _need(record.type == expected, "record_type_mismatch")
        output.append((record, raw))
    _need(output[0][0].seq < output[1][0].seq < output[2][0].seq, "causal_order_mismatch")
    return output


def _verify_selected(selected, ring: Keyring) -> bool:
    for record, _ in selected:
        verify_record(record, ring)
    return True
