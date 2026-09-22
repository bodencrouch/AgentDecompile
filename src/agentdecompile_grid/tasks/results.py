"""agentdecompile_grid.tasks.results — ``TaskResult`` and ``Verification`` objects and their pointers.

Layout in the object store (design 1.1, 2.6):

* the result record is an immutable object (canonical JSON of ``TaskResult.to_record()`` plus
  ``schema``/``record`` tags);
* ``results/<task_id>/<producer_key>`` is a named pointer to it — one per producer, so no two
  nodes ever read-modify-write the same pointer;
* ``results/<task_id>.index`` is a *derived* index (a grid document: ``{"producers": {key: ref},
  "refs": [...]}``) rebuilt from the per-producer pointers on every write; it is a cache for
  stores that cannot enumerate names and a GC root (its ``refs`` pin the records, whose
  ``outputs`` pin the produced objects).  ``proposal_count`` never trusts it when enumeration
  is available.  (The design names it ``results/<task_id>``; a POSIX tree cannot hold that file
  next to the ``results/<task_id>/`` directory, so the ``.index`` suffix is the portable spelling.)
* ``verifications/<task_id>/<verifier_key>`` and ``verifications/<task_id>.index`` mirror the same shape.

The proposal cap (``tasks.proposal_cap``, default 4) is enforced here as a *local* gate:
``write_result`` refuses the (cap+1)-th distinct producer with ``ProposalCapExceeded`` (a
``Refused`` with reason ``proposal-cap:<n>``).  Across nodes the log layer's append-time check
is authoritative (design 2.6); this gate stops a node from even uploading a doomed proposal.
A producer re-writing its own pointer does not count twice.

Enumeration needs ``objects.base.NamedIndexStore`` (``LocalDirStore``, ``LayeredStore`` with a
local layer, ``S3CompatibleStore``, ``PeerHTTPStore``); a store without it falls back to the
index document, and ``write_result`` on such a store raises ``NotConfigured`` by name.

Acceptance tests (named here, landed in the verification phase):

* ``test_write_result_roundtrip_and_pointer_layout``.
* ``test_proposal_cap_refuses_fifth_producer_by_name_and_same_producer_rewrites``.
* ``test_result_index_rebuilt_from_pointers_and_pins_outputs``.
* ``test_verification_roundtrip_and_verified_result``.
"""
from __future__ import annotations

import json
from typing import Any, Iterator, Mapping

from ..config import TasksConfig
from ..core import (
    GRID_SCHEMA_VERSION, GridError, NotConfigured, ObjectRef, ObjectStore, Refused, ResultStatus, TaskResult, Verification,
    VerificationOutcome, canonical_json,
)
from ..objects.base import ObjectMissing, can_list_named, is_ref, validate_name, validate_owner, validate_ref

PROPOSAL_CAP = TasksConfig().proposal_cap      # the configured default (4); pass config= to use a file's value
RESULTS_PREFIX = "results"
VERIFICATIONS_PREFIX = "verifications"
INDEX_SUFFIX = ".index"
RESULT_RECORD = "result"
VERIFICATION_RECORD = "verification"
INDEX_RECORD = "result-index"


class ResultError(GridError):
    """A result/verification record or name is malformed; the message names the field."""


class ProposalCapExceeded(Refused):
    """A further proposal for a task that already has ``cap`` distinct producers."""

    def __init__(self, task_id: str, cap: int, producers: list[str]) -> None:
        super().__init__(f"proposal-cap:{cap}")
        self.task_id = task_id
        self.cap = cap
        self.producers = tuple(producers)

    def __str__(self) -> str:
        return f"task {self.task_id} already has {len(self.producers)} proposal(s) from {list(self.producers)}; cap is {self.cap}"


# --------------------------------------------------------------------------- names
def _task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or len(task_id) != 64 or any(c not in "0123456789abcdef" for c in task_id):
        raise ResultError(f"task_id must be 64 lowercase hex characters, got {task_id!r}")
    return task_id


def result_name(task_id: str, producer_key: str) -> str:
    return validate_name(f"{RESULTS_PREFIX}/{_task_id(task_id)}/{validate_owner(producer_key)}")


def result_index_name(task_id: str) -> str:
    return validate_name(f"{RESULTS_PREFIX}/{_task_id(task_id)}{INDEX_SUFFIX}")


def verification_name(task_id: str, verifier_key: str) -> str:
    return validate_name(f"{VERIFICATIONS_PREFIX}/{_task_id(task_id)}/{validate_owner(verifier_key)}")


def verification_index_name(task_id: str) -> str:
    return validate_name(f"{VERIFICATIONS_PREFIX}/{_task_id(task_id)}{INDEX_SUFFIX}")


# --------------------------------------------------------------------------- records
def result_to_record(result: TaskResult) -> dict[str, Any]:
    rec = result.to_record()
    rec["schema"] = GRID_SCHEMA_VERSION
    rec["record"] = RESULT_RECORD
    return rec


def result_from_record(rec: Mapping[str, Any]) -> TaskResult:
    if rec.get("record", RESULT_RECORD) != RESULT_RECORD:
        raise ResultError(f"not a result record: record={rec.get('record')!r}")
    try:
        return _result_from_record(rec)
    except (KeyError, ValueError, TypeError) as exc:
        raise ResultError(f"malformed result record: {type(exc).__name__}: {exc}") from None


def _result_from_record(rec: Mapping[str, Any]) -> TaskResult:
    return TaskResult(
        task_id=_task_id(str(rec["task_id"])), status=ResultStatus(rec["status"]),
        outputs={str(k): validate_ref(str(v)) for k, v in sorted(dict(rec.get("outputs", {})).items())},
        producer_key=str(rec.get("producer_key", "")), basis_hash=str(rec.get("basis_hash", "")),
        elapsed_s=float(rec.get("elapsed_s", 0.0)), reason=str(rec.get("reason", "")),
        candidates=tuple(dict(c) for c in rec.get("candidates", ())), metrics=dict(rec.get("metrics", {})),
    )


def verification_to_record(v: Verification) -> dict[str, Any]:
    return {"schema": GRID_SCHEMA_VERSION, "record": VERIFICATION_RECORD, "task_id": v.task_id,
            "result_ref": str(v.result_ref), "outcome": VerificationOutcome(v.outcome).value,
            "verifier_key": v.verifier_key, "method": v.method, "evidence": dict(v.evidence),
            "refs": [str(v.result_ref)]}


def verification_from_record(rec: Mapping[str, Any]) -> Verification:
    if rec.get("record", VERIFICATION_RECORD) != VERIFICATION_RECORD:
        raise ResultError(f"not a verification record: record={rec.get('record')!r}")
    try:
        return _verification_from_record(rec)
    except (KeyError, ValueError, TypeError) as exc:
        raise ResultError(f"malformed verification record: {type(exc).__name__}: {exc}") from None


def _verification_from_record(rec: Mapping[str, Any]) -> Verification:
    return Verification(task_id=_task_id(str(rec["task_id"])), result_ref=validate_ref(str(rec["result_ref"])),
                        outcome=VerificationOutcome(rec["outcome"]), verifier_key=str(rec["verifier_key"]),
                        method=str(rec.get("method", "")), evidence=dict(rec.get("evidence", {})))


# --------------------------------------------------------------------------- enumeration
def _can_enumerate(store: ObjectStore) -> bool:
    return can_list_named(store)


def _pointers(store: ObjectStore, prefix: str, index_name: str) -> dict[str, ObjectRef]:
    """key -> ref from per-key pointers (authoritative) or, failing enumeration, from the index document."""
    if _can_enumerate(store):
        out: dict[str, ObjectRef] = {}
        for name in store.list_named(prefix):  # type: ignore[attr-defined]
            key = name[len(prefix):]
            if "/" in key or not key:
                continue
            data = store.get_named(name)
            if data is None:
                continue
            text = data.decode("ascii", "replace").strip()
            if is_ref(text):
                out[key] = ObjectRef(text)
        return dict(sorted(out.items()))
    data = store.get_named(index_name)
    if data is None:
        return {}
    try:
        doc = json.loads(data.decode("utf-8"))
    except ValueError:
        return {}
    producers = doc.get("producers", {}) if isinstance(doc, dict) else {}
    return {str(k): ObjectRef(v) for k, v in sorted(producers.items()) if is_ref(v)}


def _index_doc(task_id: str, producers: Mapping[str, ObjectRef], kind: str) -> bytes:
    return canonical_json({"schema": GRID_SCHEMA_VERSION, "record": INDEX_RECORD, "kind": kind, "task_id": task_id,
                           "producers": {k: str(v) for k, v in sorted(producers.items())},
                           "refs": sorted({str(v) for v in producers.values()})})


def result_refs(store: ObjectStore, task_id: str) -> dict[str, ObjectRef]:
    """producer_key -> result ref, sorted by key."""
    return _pointers(store, f"{RESULTS_PREFIX}/{_task_id(task_id)}/", result_index_name(task_id))


def proposal_count(store: ObjectStore, task_id: str) -> int:
    """Distinct producers with a proposal for ``task_id``; 0 when unknown."""
    return len(result_refs(store, task_id))


def rebuild_result_index(store: ObjectStore, task_id: str) -> dict[str, ObjectRef]:
    if not _can_enumerate(store):
        raise NotConfigured(f"{type(store).__name__} cannot enumerate named pointers; use LocalDirStore or a LayeredStore with a local layer")
    producers = result_refs(store, task_id)
    store.put_named(result_index_name(task_id), _index_doc(task_id, producers, "results"))
    return producers


# --------------------------------------------------------------------------- results
def write_result(store: ObjectStore, result: TaskResult, *, cap: int | None = None, config: Any = None,
                 update_index: bool = True) -> ObjectRef:
    """Store the record, point ``results/<task_id>/<producer_key>`` at it, refresh the index.  Returns the ref.

    Raises ``ProposalCapExceeded`` for a new producer beyond the cap; ``NotConfigured`` when the
    store cannot enumerate names (the cap cannot be checked there).
    """
    if not result.producer_key:
        raise ResultError("result.producer_key is empty; stamp it (tasks.registry.stamp/execute) before writing")
    task_id = _task_id(result.task_id)
    name = result_name(task_id, result.producer_key)
    if not _can_enumerate(store):
        raise NotConfigured(f"{type(store).__name__} cannot enumerate named pointers, so the proposal cap cannot be checked; "
                            f"write results through a LocalDirStore or a LayeredStore with a local layer")
    limit = int(cap if cap is not None else (config.tasks.proposal_cap if config is not None else PROPOSAL_CAP))
    existing = result_refs(store, task_id)
    if result.producer_key not in existing and len(existing) >= limit:
        raise ProposalCapExceeded(task_id, limit, sorted(existing))
    ref = store.put(canonical_json(result_to_record(result)))
    store.put_named(name, str(ref).encode("ascii"))
    if update_index:
        existing[result.producer_key] = ref
        store.put_named(result_index_name(task_id), _index_doc(task_id, existing, "results"))
    return ref


def read_result(store: ObjectStore, ref: ObjectRef) -> TaskResult:
    return result_from_record(json.loads(store.get(ref).decode("utf-8")))


def results_for(store: ObjectStore, task_id: str) -> list[TaskResult]:
    """Every proposal for ``task_id`` in producer-key order (missing objects are skipped)."""
    out: list[TaskResult] = []
    for _key, ref in result_refs(store, task_id).items():
        try:
            out.append(read_result(store, ref))
        except (ObjectMissing, KeyError):
            continue
    return out


def result_ref_for(store: ObjectStore, task_id: str, producer_key: str) -> ObjectRef | None:
    data = store.get_named(result_name(task_id, producer_key))
    if data is None:
        return None
    text = data.decode("ascii", "replace").strip()
    return ObjectRef(text) if is_ref(text) else None


def delete_result(store: ObjectStore, task_id: str, producer_key: str) -> bool:
    """Drop a producer's pointer (the record object stays until GC); refreshes the index."""
    if not _can_enumerate(store):
        raise NotConfigured(f"{type(store).__name__} cannot delete named pointers")
    removed = bool(store.delete_named(result_name(task_id, producer_key)))  # type: ignore[attr-defined]
    if removed:
        rebuild_result_index(store, task_id)
    return removed


# --------------------------------------------------------------------------- verifications
def write_verification(store: ObjectStore, v: Verification, *, update_index: bool = True) -> ObjectRef:
    if not v.verifier_key:
        raise ResultError("verification.verifier_key is empty")
    task_id = _task_id(v.task_id)
    validate_ref(v.result_ref)
    ref = store.put(canonical_json(verification_to_record(v)))
    store.put_named(verification_name(task_id, v.verifier_key), str(ref).encode("ascii"))
    if update_index and _can_enumerate(store):
        producers = verification_refs(store, task_id)
        producers[v.verifier_key] = ref
        store.put_named(verification_index_name(task_id), _index_doc(task_id, producers, "verifications"))
    return ref


def read_verification(store: ObjectStore, ref: ObjectRef) -> Verification:
    return verification_from_record(json.loads(store.get(ref).decode("utf-8")))


def verification_refs(store: ObjectStore, task_id: str) -> dict[str, ObjectRef]:
    return _pointers(store, f"{VERIFICATIONS_PREFIX}/{_task_id(task_id)}/", verification_index_name(task_id))


def verifications_for(store: ObjectStore, task_id: str) -> list[Verification]:
    out: list[Verification] = []
    for _key, ref in verification_refs(store, task_id).items():
        try:
            out.append(read_verification(store, ref))
        except (ObjectMissing, KeyError):
            continue
    return out


def verified_result_ref(store: ObjectStore, task_id: str) -> ObjectRef | None:
    """The result ref of the first (by verifier key) VERIFIED verification, else None."""
    for v in verifications_for(store, task_id):
        if v.outcome is VerificationOutcome.VERIFIED:
            return v.result_ref
    return None


def is_done(store: ObjectStore, task_id: str) -> bool:
    """Done = a verified result exists (design 1.1: 'done' is an existence check)."""
    return verified_result_ref(store, task_id) is not None


def iter_task_ids(store: ObjectStore, *, prefix: str = RESULTS_PREFIX) -> Iterator[str]:
    """Task ids that have at least one pointer under ``prefix`` (needs enumeration), sorted."""
    if not _can_enumerate(store):
        raise NotConfigured(f"{type(store).__name__} cannot enumerate named pointers")
    seen: set[str] = set()
    for name in store.list_named(prefix + "/"):  # type: ignore[attr-defined]
        rest = name[len(prefix) + 1:]
        tid = rest.split("/", 1)[0]
        if len(tid) == 64:
            seen.add(tid)
    yield from sorted(seen)


def describe_task(store: ObjectStore, task_id: str) -> dict[str, Any]:
    return {"task_id": _task_id(task_id), "proposals": {k: str(v) for k, v in result_refs(store, task_id).items()},
            "verifications": {k: str(v) for k, v in verification_refs(store, task_id).items()},
            "verified_result": str(verified_result_ref(store, task_id) or ""), "done": is_done(store, task_id)}


__all__ = [
    "PROPOSAL_CAP", "RESULTS_PREFIX", "VERIFICATIONS_PREFIX", "INDEX_SUFFIX", "ResultError", "ProposalCapExceeded",
    "result_name", "result_index_name", "verification_name", "verification_index_name",
    "result_to_record", "result_from_record", "verification_to_record", "verification_from_record",
    "write_result", "read_result", "results_for", "result_refs", "result_ref_for", "proposal_count",
    "rebuild_result_index", "delete_result",
    "write_verification", "read_verification", "verification_refs", "verifications_for", "verified_result_ref",
    "is_done", "iter_task_ids", "describe_task",
]
