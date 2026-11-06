"""Records: build, seal and verify one hash-chained, signed log entry.

A record's identity is ``Record.digest()``: sha256 of the canonical JSON of the record *without* its
signature.  The signature is over exactly those bytes (``unsigned_bytes``).  ``prev`` of record
``seq`` is the digest of record ``seq - 1`` in the same partition; ``""`` for ``seq == 1``.  After
compaction pruned a prefix, the first stored record still carries its real ``prev``, so a reader
learns where the stored chain starts from the first line alone.

Drafting is separate from sealing because a record cannot know its ``seq`` and ``prev`` until the
appender has read the head.  A CAS loss means the whole batch is re-sealed against the new head;
nothing is ever patched in place.  A draft body may be a callable of the final ``seq`` (the INTENT
fence is the issuing record's own seq, which only exists at seal time).

Body validators are a registry keyed by ``RecordType`` so a deployment can tighten a shape without
touching this module.  Record-level invariants bind bodies to the signing key: an INTENT's
``key_id``, a RESULT's ``producer_key`` and a VERIFIED/REFUTED ``verifier_key`` must equal
``signer_key``; otherwise a key could lease, claim or verify in someone else's name.

Acceptance tests (named here, written in the verification phase):
  U122 (d) a batch of 64 sealed records verifies offline via ``verify_chain`` with a keyring;
  U122 (c) ``verify_chain`` over a whole partition returns the live head;
  records-validators: every required key of every body type is rejected by name when missing;
  records-identity: an INTENT whose ``key_id`` != ``signer_key`` is refused by name; a TASK whose
  ``task_id`` is not the digest of its content is refused by name; an INTENT with
  ``issued_seq > seq`` (a fence from the future) is refused by name;
  records-schema: a record with another ``schema`` value fails ``record_from_dict`` by name.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any, Protocol
from collections.abc import Callable, Iterable, Mapping, Sequence

from agentdecompile_grid.core import (
    GRID_SCHEMA_VERSION,
    GridError,
    ObjectRef,
    Record,
    RecordType,
    Registry,
    ResultStatus,
    Signer,
    TaskSpec,
    Verification,
    VerificationOutcome,
    canonical_json,
)
from agentdecompile_grid.log._fs import InvalidPartition, validate_partition  # noqa: F401  (re-exported)

Head = tuple[int, str]
"""``(seq, digest)`` of the last record in a partition; ``(0, "")`` for an empty partition."""

EMPTY_HEAD: Head = (0, "")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_OBJECT_REF = re.compile(r"^sha256:[0-9a-f]{64}$")


# --------------------------------------------------------------------------- errors
class RecordError(GridError):
    """Base for everything a single record or a run of records can be wrong about."""


class InvalidRecord(RecordError):
    """A record field (not the body) is malformed: seq, prev, type, partition, signer."""


class InvalidBody(RecordError):
    """A body fails the validator for its record type; the message names the key."""


class SchemaMismatch(RecordError):
    """A stored record carries another ``schema`` value than this code understands."""


class ChainBroken(RecordError):
    """Linkage violated: ``seq`` not dense or ``prev`` not the predecessor's digest."""

    def __init__(self, partition: str, seq: int, what: str, expected: Any, found: Any) -> None:
        super().__init__(f"chain broken in {partition!r} at seq {seq}: {what} expected {expected!r}, found {found!r}")
        self.partition, self.seq, self.what, self.expected, self.found = partition, seq, what, expected, found


class BadSignature(RecordError):
    """The signature does not verify under the record's ``signer_key``."""


class UnknownSigner(RecordError):
    """The keyring has no public material for ``signer_key``."""


class SignerNotAuthorized(RecordError):
    """The signature verifies, but the signer's role may not write this record type (a TASK or
    CHECKPOINT not signed by an operator key)."""


# --------------------------------------------------------------------------- body validators
BODY_VALIDATORS = Registry("record body validator")
"""``RecordType.value -> Callable[[Mapping], None]``; raise ``InvalidBody`` naming the offending key."""


def body_validator(record_type: RecordType) -> Callable[[Callable[[Mapping[str, Any]], None]], Callable[[Mapping[str, Any]], None]]:
    def deco(fn: Callable[[Mapping[str, Any]], None]) -> Callable[[Mapping[str, Any]], None]:
        BODY_VALIDATORS.register(record_type.value, fn, replace=True)
        return fn
    return deco


def _require(body: Mapping[str, Any], keys: Sequence[str], what: str) -> None:
    if not isinstance(body, Mapping):
        raise InvalidBody(f"{what} body must be a mapping, got {type(body).__name__}")
    missing = [k for k in keys if k not in body]
    if missing:
        raise InvalidBody(f"{what} body is missing {missing}")


def _int_field(body: Mapping[str, Any], key: str, what: str, *, minimum: int = 0) -> int:
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidBody(f"{what} body {key!r} must be an int, got {type(value).__name__}")
    if value < minimum:
        raise InvalidBody(f"{what} body {key!r} must be >= {minimum}, got {value}")
    return value


def _number_field(body: Mapping[str, Any], key: str, what: str) -> float:
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidBody(f"{what} body {key!r} must be a number, got {type(value).__name__}")
    if value < 0:
        raise InvalidBody(f"{what} body {key!r} must be >= 0, got {value}")
    return float(value)


def _str_field(body: Mapping[str, Any], key: str, what: str, *, pattern: re.Pattern[str] | None = None, allow_empty: bool = False) -> str:
    value = body[key]
    if not isinstance(value, str):
        raise InvalidBody(f"{what} body {key!r} must be a str, got {type(value).__name__}")
    if not value and not allow_empty:
        raise InvalidBody(f"{what} body {key!r} must not be empty")
    if pattern is not None and value and not pattern.match(value):
        raise InvalidBody(f"{what} body {key!r} does not match {pattern.pattern}: {value!r}")
    return value


def _task_id(body: Mapping[str, Any], what: str) -> str:
    return _str_field(body, "task_id", what, pattern=_HEX64)


def _object_ref(body: Mapping[str, Any], key: str, what: str) -> str:
    return _str_field(body, key, what, pattern=_OBJECT_REF)


def _mapping_field(body: Mapping[str, Any], key: str, what: str) -> Mapping[str, Any]:
    value = body[key]
    if not isinstance(value, Mapping):
        raise InvalidBody(f"{what} body {key!r} must be a mapping, got {type(value).__name__}")
    return value


@body_validator(RecordType.TASK)
def validate_task_body(body: Mapping[str, Any]) -> None:
    """TASK body = ``TaskSpec.to_record()``; ``task_id`` must be the digest of the content."""
    _require(body, ("task_id", "kind", "kind_version", "inputs", "params", "basis_hash"), "task")
    _task_id(body, "task")
    _str_field(body, "kind", "task")
    _int_field(body, "kind_version", "task")
    _str_field(body, "basis_hash", "task")
    inputs = _mapping_field(body, "inputs", "task")
    for name, ref in inputs.items():
        if not isinstance(ref, str) or not _OBJECT_REF.match(ref):
            raise InvalidBody(f"task body input {name!r} is not an object ref (sha256:<hex>): {ref!r}")
    _mapping_field(body, "params", "task")
    try:
        spec = TaskSpec.from_record(body)
        computed = spec.task_id
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidBody(f"task body does not decode as a TaskSpec: {exc}") from exc
    if computed != body["task_id"]:
        raise InvalidBody(f"task body task_id {body['task_id']!r} is not the digest of its content ({computed})")
    if "partition" in body:
        validate_partition(str(body["partition"]))


@body_validator(RecordType.INTENT)
def validate_intent_body(body: Mapping[str, Any]) -> None:
    """INTENT body = ``{task_id, key_id, ttl_s, issued_seq, issued_at}``; ``ttl_s == 0`` is a release."""
    _require(body, ("task_id", "key_id", "ttl_s", "issued_seq", "issued_at"), "intent")
    _task_id(body, "intent")
    _str_field(body, "key_id", "intent")
    _int_field(body, "ttl_s", "intent")
    _int_field(body, "issued_seq", "intent", minimum=1)
    _number_field(body, "issued_at", "intent")


@body_validator(RecordType.RESULT)
def validate_result_body(body: Mapping[str, Any]) -> None:
    """RESULT body = ``{task_id, result_ref, producer_key, status}``."""
    _require(body, ("task_id", "result_ref", "producer_key", "status"), "result")
    _task_id(body, "result")
    _object_ref(body, "result_ref", "result")
    _str_field(body, "producer_key", "result")
    status = _str_field(body, "status", "result")
    if status not in {s.value for s in ResultStatus}:
        raise InvalidBody(f"result body status {status!r} is not one of {sorted(s.value for s in ResultStatus)}")


def _validate_verification_body(body: Mapping[str, Any], expected: VerificationOutcome, what: str) -> None:
    _require(body, ("task_id", "result_ref", "outcome", "verifier_key", "method"), what)
    _task_id(body, what)
    _object_ref(body, "result_ref", what)
    _str_field(body, "verifier_key", what)
    _str_field(body, "method", what)
    outcome = _str_field(body, "outcome", what)
    if outcome != expected.value:
        raise InvalidBody(f"{what} body outcome must be {expected.value!r}, got {outcome!r}")
    if "evidence" in body:
        _mapping_field(body, "evidence", what)


@body_validator(RecordType.VERIFIED)
def validate_verified_body(body: Mapping[str, Any]) -> None:
    """VERIFIED body = ``verification_to_body(Verification)`` with outcome ``verified``."""
    _validate_verification_body(body, VerificationOutcome.VERIFIED, "verified")


@body_validator(RecordType.REFUTED)
def validate_refuted_body(body: Mapping[str, Any]) -> None:
    """REFUTED body = ``verification_to_body(Verification)`` with outcome ``refuted``."""
    _validate_verification_body(body, VerificationOutcome.REFUTED, "refuted")


@body_validator(RecordType.POISON)
def validate_poison_body(body: Mapping[str, Any]) -> None:
    """POISON body = ``{task_id, reason, evidence}``."""
    _require(body, ("task_id", "reason", "evidence"), "poison")
    _task_id(body, "poison")
    _str_field(body, "reason", "poison")
    _mapping_field(body, "evidence", "poison")


@body_validator(RecordType.CHECKPOINT)
def validate_checkpoint_body(body: Mapping[str, Any]) -> None:
    """CHECKPOINT body = ``{through_seq, summary_ref}`` plus optional ``through_digest``."""
    _require(body, ("through_seq", "summary_ref"), "checkpoint")
    _int_field(body, "through_seq", "checkpoint")
    _object_ref(body, "summary_ref", "checkpoint")
    if "through_digest" in body:
        _str_field(body, "through_digest", "checkpoint", pattern=_HEX64, allow_empty=True)


@body_validator(RecordType.NOTE)
def validate_note_body(body: Mapping[str, Any]) -> None:
    """NOTE body = any mapping; never load-bearing."""
    if not isinstance(body, Mapping):
        raise InvalidBody(f"note body must be a mapping, got {type(body).__name__}")


def validate_body(record_type: RecordType, body: Mapping[str, Any]) -> None:
    BODY_VALIDATORS.get(record_type.value)(body)


# --------------------------------------------------------------------------- record-level invariants
_IDENTITY_KEYS: Mapping[RecordType, str] = {
    RecordType.INTENT: "key_id",
    RecordType.RESULT: "producer_key",
    RecordType.VERIFIED: "verifier_key",
    RecordType.REFUTED: "verifier_key",
}


def validate_record(record: Record, *, bind_identity: bool = True) -> None:
    """Structural checks plus the body validator; ``bind_identity`` enforces body key == signer_key."""
    validate_partition(record.partition)
    if isinstance(record.seq, bool) or not isinstance(record.seq, int) or record.seq < 1:
        raise InvalidRecord(f"record seq must be an int >= 1, got {record.seq!r}")
    if not isinstance(record.type, RecordType):
        raise InvalidRecord(f"record type must be a RecordType, got {record.type!r}")
    if not isinstance(record.prev, str) or (record.prev and not _HEX64.match(record.prev)):
        raise InvalidRecord(f"record prev must be '' or a sha256 hex digest, got {record.prev!r}")
    if record.seq == 1 and record.prev:
        raise InvalidRecord("record seq 1 must have prev == ''")
    if record.seq > 1 and not record.prev:
        raise InvalidRecord(f"record seq {record.seq} must carry the digest of seq {record.seq - 1} as prev")
    if not isinstance(record.signer_key, str) or not record.signer_key:
        raise InvalidRecord("record signer_key must be a non-empty str")
    if not isinstance(record.basis_hash, str):
        raise InvalidRecord("record basis_hash must be a str")
    validate_body(record.type, record.body)
    body_basis = record.body.get("basis_hash") if isinstance(record.body, Mapping) else None
    if record.basis_hash and isinstance(body_basis, str) and body_basis and body_basis != record.basis_hash:
        raise InvalidRecord(f"record basis_hash {record.basis_hash!r} differs from body basis_hash {body_basis!r}")
    if record.type is RecordType.INTENT and int(record.body["issued_seq"]) > record.seq:
        raise InvalidRecord(f"intent issued_seq {record.body['issued_seq']} is later than the record's own seq {record.seq}")
    if bind_identity:
        key = _IDENTITY_KEYS.get(record.type)
        if key is not None and record.body[key] != record.signer_key:
            raise InvalidRecord(f"{record.type.value} body {key} {record.body[key]!r} must equal signer_key {record.signer_key!r}")


# --------------------------------------------------------------------------- drafting and sealing
BodyFactory = Callable[[int], Mapping[str, Any]]


@dataclass(frozen=True)
class Draft:
    """What a caller wants appended, before ``seq``/``prev``/signature exist.

    ``body`` may be a callable of the final ``seq`` for bodies that embed their own position
    (the INTENT fence).  ``basis_hash`` defaults to the body's ``basis_hash`` when present.
    """

    type: RecordType
    body: Mapping[str, Any] | BodyFactory
    basis_hash: str = ""

    def body_for(self, seq: int) -> Mapping[str, Any]:
        body = self.body(seq) if callable(self.body) else self.body
        return dict(body)


def unsigned_bytes(record: Record) -> bytes:
    """The bytes that are signed and hashed: canonical JSON of the record without its signature."""
    return canonical_json(record.to_record(include_signature=False))


def build_record(
    partition: str,
    seq: int,
    record_type: RecordType,
    body: Mapping[str, Any],
    prev: str,
    signer: Signer,
    *,
    basis_hash: str = "",
    validate: bool = True,
) -> Record:
    """Validate, then sign one record at a known position.  Prefer ``seal`` for a batch."""
    body = dict(body)
    if not basis_hash:
        candidate = body.get("basis_hash")
        basis_hash = candidate if isinstance(candidate, str) else ""
    unsigned = Record(
        partition=partition, seq=seq, type=record_type, body=body, prev=prev,
        signer_key=signer.key_id, signature="", basis_hash=basis_hash,
    )
    if validate:
        validate_record(unsigned)
    return replace(unsigned, signature=signer.sign(unsigned_bytes(unsigned)))


def seal(partition: str, drafts: Sequence[Draft], head: Head, signer: Signer, *, validate: bool = True) -> list[Record]:
    """Chain ``drafts`` onto ``head`` as records ``head.seq + 1 ..``; pure given the head."""
    validate_partition(partition)
    seq, prev = head
    sealed: list[Record] = []
    for draft in drafts:
        seq += 1
        record = build_record(partition, seq, draft.type, draft.body_for(seq), prev, signer, basis_hash=draft.basis_hash, validate=validate)
        sealed.append(record)
        prev = record.digest()
    return sealed


def head_of(records: Sequence[Record], *, before: Head = EMPTY_HEAD) -> Head:
    """``(seq, digest)`` of the last record, or ``before`` when the run is empty."""
    if not records:
        return before
    last = records[-1]
    return last.seq, last.digest()


# --------------------------------------------------------------------------- encoding
def record_to_dict(record: Record) -> dict[str, Any]:
    return record.to_record(include_signature=True)


def record_from_dict(data: Mapping[str, Any]) -> Record:
    """Decode a stored record; refuses another schema version or an unknown type by name."""
    if not isinstance(data, Mapping):
        raise InvalidRecord(f"record must be a mapping, got {type(data).__name__}")
    schema = data.get("schema")
    if schema != GRID_SCHEMA_VERSION:
        raise SchemaMismatch(f"record schema {schema!r} is not {GRID_SCHEMA_VERSION}")
    try:
        record_type = RecordType(data["type"])
    except (KeyError, ValueError) as exc:
        raise InvalidRecord(f"record type unknown or missing: {data.get('type')!r}") from exc
    try:
        return Record(
            partition=str(data["partition"]), seq=int(data["seq"]), type=record_type, body=dict(data["body"]),
            prev=str(data["prev"]), signer_key=str(data["signer_key"]), signature=str(data.get("signature", "")),
            basis_hash=str(data.get("basis_hash", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidRecord(f"record is missing or mistypes a field: {exc}") from exc


def encode_line(record: Record) -> bytes:
    """One JSONL line: canonical JSON plus newline.  Lines never contain a raw newline."""
    return canonical_json(record_to_dict(record)) + b"\n"


def decode_line(line: bytes) -> Record:
    try:
        data = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InvalidRecord(f"record line is not JSON: {exc}") from exc
    return record_from_dict(data)


# --------------------------------------------------------------------------- verification
class SignatureVerifier(Protocol):
    """Anything that can check a signature for a key id: a ``Signer`` or a ``signing.Keyring``."""

    def verify(self, key_id: str, data: bytes, signature: str) -> bool: ...


def verify_chain(
    records: Iterable[Record],
    *,
    head: Head = EMPTY_HEAD,
    verifier: SignatureVerifier | None = None,
    validate: bool = True,
    partition: str | None = None,
) -> Head:
    """Walk ``records`` from ``head``; return the new head or raise the first defect by name.

    Checks, per record: partition constant, ``seq`` dense, ``prev`` = predecessor digest, then the
    record invariants and body validator, then the signature when a verifier is given.
    """
    seq, prev = head
    for record in records:
        if partition is None:
            partition = record.partition
        elif record.partition != partition:
            raise ChainBroken(partition, record.seq, "partition", partition, record.partition)
        if record.seq != seq + 1:
            raise ChainBroken(record.partition, record.seq, "seq", seq + 1, record.seq)
        if record.prev != prev:
            raise ChainBroken(record.partition, record.seq, "prev", prev, record.prev)
        if validate:
            validate_record(record)
        if verifier is not None and not verifier.verify(record.signer_key, unsigned_bytes(record), record.signature):
            raise BadSignature(f"record {record.partition!r}#{record.seq} signature does not verify under {record.signer_key!r}")
        seq, prev = record.seq, record.digest()
    return seq, prev


# --------------------------------------------------------------------------- body helpers
def verification_to_body(verification: Verification) -> dict[str, Any]:
    """The VERIFIED/REFUTED body for a ``core.Verification``."""
    return {
        "task_id": verification.task_id,
        "result_ref": str(verification.result_ref),
        "outcome": verification.outcome.value,
        "verifier_key": verification.verifier_key,
        "method": verification.method,
        "evidence": dict(verification.evidence),
    }


def verification_from_body(body: Mapping[str, Any]) -> Verification:
    return Verification(
        task_id=body["task_id"], result_ref=ObjectRef(body["result_ref"]),
        outcome=VerificationOutcome(body["outcome"]), verifier_key=body["verifier_key"],
        method=body["method"], evidence=dict(body.get("evidence", {})),
    )


def record_type_for(verification: Verification) -> RecordType:
    """VERIFIED or REFUTED; an UNVERIFIABLE outcome has no record (it stays a proposal)."""
    if verification.outcome is VerificationOutcome.VERIFIED:
        return RecordType.VERIFIED
    if verification.outcome is VerificationOutcome.REFUTED:
        return RecordType.REFUTED
    raise InvalidBody(f"verification outcome {verification.outcome.value!r} has no record type")


__all__ = [
    "BODY_VALIDATORS", "BadSignature", "BodyFactory", "ChainBroken", "Draft", "EMPTY_HEAD", "Head",
    "InvalidBody", "InvalidPartition", "InvalidRecord", "RecordError", "SchemaMismatch", "SignatureVerifier", "SignerNotAuthorized",
    "UnknownSigner", "body_validator", "build_record", "decode_line", "encode_line", "head_of", "record_from_dict",
    "record_to_dict", "record_type_for", "seal", "unsigned_bytes", "validate_body", "validate_partition",
    "validate_record", "verification_from_body", "verification_to_body", "verify_chain",
]
