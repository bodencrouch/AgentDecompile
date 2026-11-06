"""Where a keyring learns keys, and what revokes them (U126).

One key-id scheme (``log.signing.key_id_of``) means every key-carrying object below is an
attestation *about* a key id that a ``Keyring`` can look up from a record alone.  Three working
``core.KEY_SOURCES`` entries and one declared slot:

* ``local-identity`` — the node state directories under ``<root>/nodes/<name>/keys/node.json``
  (the public record ``worker.identity.NodeKeyStore`` writes) and any ``*.pub`` files under a
  trusted key directory (``keyring.key_dir``).  What one host holds.
* ``invites`` — ``invite.v1`` objects: ``{schema: "invite.v1", key_id, algorithm, pub, role,
  issued_by, issued_by_role, issued_seq, expires_at_seq, lineage, signature}`` signed by an
  operator or fleet key (``ROLE_MAY_SIGN``).  Stored under the named pointer
  ``invites/<key_id>`` (one per admitted key, written by the issuer).  Expiry is in *log seq*
  (``expires_at_seq``), not wall clock, so two nodes agree on it from the log alone.
* ``log-announce`` — ``KEY_ANNOUNCE`` records (partition ``keys``): a node announces its own
  public key, role, lineage, expiry and the key ids it supersedes.  The record is signed by the
  announced key (possession proof; ``signer_key == body.key_id``).  Role and lineage from an
  announce are the node's *claim* (``claimed_role`` / ``claimed_lineage`` in the keyring's notes);
  the attested ``role`` comes only from an invite or a local identity directory, and that is what
  ``verify_key_invite`` authorises on.  ``supersedes`` is the node's own statement of its previous
  key ids (``NodeKey.previous_key_ids``), attribution only.
* ``remote-directory`` — slot: a fabric's HTTPS key directory; ``NotConfigured`` names the url.

``RevocationList`` is an append-only list of ``{key_id, reason, by, seq}`` any fleet or operator
key may extend (``extend``); ``Keyring.is_revoked`` reads it; ``log.frontier.RevocationFilter``
drops a revoked key's records; ``verify_record`` raises ``RevokedSigner``.  It lives at the named
pointer ``policy/revoked`` (``verify.policy.REVOCATIONS_POINTER`` re-exports the name).

Acceptance tests (named here, written in the verification phase):
  keys-invite-roundtrip: an ``invite.v1`` signed by a fleet key verifies against a keyring that
  holds the fleet key and adds the invited key; a donor-signed one is refused by name;
  keys-invite-expiry: ``at_seq >= expires_at_seq`` is refused by name;
  keys-announce-source: a KEY_ANNOUNCE record teaches the keyring the key and its supersedes;
  keys-revocation-append-only: ``extend`` by a donor is refused; ``is_revoked`` after an operator
  extension; ``to_record`` keeps every entry in order.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol
from collections.abc import Iterable, Mapping, Sequence

from agentdecompile_grid.core import (
    GRID_SCHEMA_VERSION, KEY_SOURCES, GridError, LogStore, NotConfigured, ObjectStore, RecordType, Refused, Signer, canonical_json,
)
from agentdecompile_grid.log.records import InvalidBody, body_validator, _require, _str_field  # noqa: PLC2701 - the validator helpers are the contract
from agentdecompile_grid.log.signing import Keyring, algorithm_of, key_id_of

INVITE_SCHEMA = "invite.v1"
INVITES_PREFIX = "invites/"
REVOCATIONS_POINTER = "policy/revoked"
KEYS_PARTITION = "keys"
ROLES = ("operator", "fleet", "donor")
ROLE_MAY_SIGN: Mapping[str, frozenset[str]] = {
    "operator": frozenset({"operator", "fleet", "donor"}),
    "fleet": frozenset({"fleet", "donor"}),
    "donor": frozenset(),
}
ROLE_MAY_REVOKE: frozenset[str] = frozenset({"operator", "fleet"})


class KeyError_(GridError):
    """A key attestation (invite, announce, revocation) is malformed, unsigned, expired or unauthorised."""


InviteRefused = KeyError_


# --------------------------------------------------------------------------- invite.v1
@dataclass(frozen=True)
class KeyInvite:
    """An admitted key: the issuer vouches that ``key_id`` (= ``key_id_of(algorithm, pub)``) holds ``role``."""

    key_id: str
    algorithm: str
    pub: str                         # hex of the raw public material
    role: str
    issued_by: str
    issued_by_role: str
    issued_seq: int
    expires_at_seq: int
    lineage: tuple[str, ...] = ()    # the issuer's lineage; the joiner's is lineage + issued_by
    signature: str = ""

    @property
    def joiner_lineage(self) -> tuple[str, ...]:
        return (*self.lineage, self.issued_by)

    def payload(self) -> dict[str, Any]:
        return {"schema": INVITE_SCHEMA, "key_id": self.key_id, "algorithm": self.algorithm, "pub": self.pub, "role": self.role,
                "issued_by": self.issued_by, "issued_by_role": self.issued_by_role, "issued_seq": int(self.issued_seq),
                "expires_at_seq": int(self.expires_at_seq), "lineage": list(self.lineage)}

    def signed_bytes(self) -> bytes:
        return canonical_json(self.payload())

    def to_record(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    def to_bytes(self) -> bytes:
        return canonical_json(self.to_record())

    @classmethod
    def from_record(cls, rec: Mapping[str, Any]) -> KeyInvite:
        if not isinstance(rec, Mapping) or rec.get("schema") != INVITE_SCHEMA:
            raise KeyError_(f"not an {INVITE_SCHEMA} object: schema={rec.get('schema') if isinstance(rec, Mapping) else type(rec).__name__!r}")
        missing = [k for k in ("key_id", "algorithm", "pub", "role", "issued_by", "issued_by_role", "issued_seq", "expires_at_seq", "signature") if k not in rec]
        if missing:
            raise KeyError_(f"{INVITE_SCHEMA} object lacks fields: {missing}")
        return cls(key_id=str(rec["key_id"]), algorithm=str(rec["algorithm"]), pub=str(rec["pub"]), role=str(rec["role"]),
                   issued_by=str(rec["issued_by"]), issued_by_role=str(rec["issued_by_role"]), issued_seq=int(rec["issued_seq"]),
                   expires_at_seq=int(rec["expires_at_seq"]), lineage=tuple(str(x) for x in rec.get("lineage", ())), signature=str(rec["signature"]))

    @classmethod
    def from_bytes(cls, data: bytes) -> KeyInvite:
        try:
            return cls.from_record(json.loads(data.decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as exc:
            raise KeyError_(f"{INVITE_SCHEMA} object is not JSON ({type(exc).__name__})") from exc


def make_key_invite(signer: Signer, *, issuer_role: str, issuer_lineage: Sequence[str], key_id: str, algorithm: str, pub: bytes,
                    role: str, issued_seq: int, expires_at_seq: int) -> KeyInvite:
    """Sign an ``invite.v1`` for ``key_id``.  Refused by name when ``issuer_role`` may not grant ``role``
    (donors sign nothing), the id does not hash from ``pub``, or the expiry is not after issue."""
    if role not in ROLES:
        raise KeyError_(f"unknown role {role!r}; known: {ROLES}")
    if role not in ROLE_MAY_SIGN.get(issuer_role, frozenset()):
        raise KeyError_(f"role {issuer_role!r} may not sign a {role!r} invite (operator: any; fleet: fleet, donor; donor: none)")
    if key_id_of(algorithm, pub) != key_id:
        raise KeyError_("invite key_id is not the id of the given public material")
    if int(expires_at_seq) <= int(issued_seq):
        raise KeyError_("invite expires_at_seq must be after issued_seq")
    unsigned = KeyInvite(key_id=key_id, algorithm=algorithm, pub=pub.hex(), role=role, issued_by=signer.key_id, issued_by_role=issuer_role,
                         issued_seq=int(issued_seq), expires_at_seq=int(expires_at_seq), lineage=tuple(issuer_lineage))
    return replace(unsigned, signature=signer.sign(unsigned.signed_bytes()))


def verify_key_invite(invite: KeyInvite, keyring: Keyring, *, at_seq: int, require_issuer_role: bool = True) -> KeyInvite:
    """Structural, role, expiry and signature checks by name; the issuer's key must be in the keyring
    (and, with ``require_issuer_role``, be known there under a role that may grant ``invite.role``)."""
    if invite.role not in ROLES or invite.issued_by_role not in ROLES:
        raise KeyError_(f"invite names an unknown role ({invite.role!r} by {invite.issued_by_role!r})")
    if invite.role not in ROLE_MAY_SIGN[invite.issued_by_role]:
        raise KeyError_(f"invite signed by a {invite.issued_by_role!r} key cannot grant {invite.role!r}")
    try:
        pub = bytes.fromhex(invite.pub)
    except ValueError as exc:
        raise KeyError_("invite carries malformed public material") from exc
    if key_id_of(invite.algorithm, pub) != invite.key_id:
        raise KeyError_("invite key_id does not hash from its public material")
    if invite.issued_by in invite.lineage:
        raise KeyError_("invite issuer appears in its own lineage")
    if int(at_seq) >= int(invite.expires_at_seq):
        raise KeyError_(f"invite expired at seq {invite.expires_at_seq} (now seq {at_seq})")
    if keyring.is_revoked(invite.issued_by):
        raise KeyError_(f"invite issuer {invite.issued_by} is revoked")
    if not keyring.knows(invite.issued_by):
        raise KeyError_(f"invite issuer {invite.issued_by} is not in the keyring")
    known_role = keyring.role_of(invite.issued_by)
    if require_issuer_role and known_role and known_role != invite.issued_by_role:
        raise KeyError_(f"invite claims issuer role {invite.issued_by_role!r} but the keyring knows {invite.issued_by} as {known_role!r}")
    if require_issuer_role and not known_role:
        raise KeyError_(f"invite issuer {invite.issued_by} has no known role in the keyring (a root key must be noted with its role)")
    if not keyring.verify(invite.issued_by, invite.signed_bytes(), invite.signature):
        raise KeyError_(f"invite signature by {invite.issued_by} does not verify")
    return invite


def invite_name(key_id: str) -> str:
    return INVITES_PREFIX + key_id.replace(":", ".")


def write_key_invite(objects: ObjectStore, invite: KeyInvite) -> str:
    """Store the invite object and point ``invites/<key_id>`` at its bytes; returns the pointer name."""
    name = invite_name(invite.key_id)
    objects.put_named(name, invite.to_bytes())
    return name


# --------------------------------------------------------------------------- key announce records
def key_announce_body(*, key_id: str, algorithm: str, pub: bytes, role: str, lineage: Sequence[str], expires_at: float,
                      supersedes: Sequence[str] = (), created_at: float = 0.0) -> dict[str, Any]:
    body = {"key_id": key_id, "algorithm": algorithm, "pub": pub.hex(), "role": role, "lineage": list(lineage),
            "expires_at": float(expires_at), "supersedes": list(supersedes)}
    if created_at:
        body["created_at"] = float(created_at)
    return body


@body_validator(RecordType.KEY_ANNOUNCE)
def validate_key_announce_body(body: Mapping[str, Any]) -> None:
    """KEY_ANNOUNCE body = ``{key_id, algorithm, pub, role, lineage, expires_at, supersedes}``; the id must hash from ``pub``."""
    _require(body, ("key_id", "algorithm", "pub", "role", "lineage", "expires_at", "supersedes"), "key-announce")
    key_id = _str_field(body, "key_id", "key-announce")
    algorithm = _str_field(body, "algorithm", "key-announce")
    pub_hex = _str_field(body, "pub", "key-announce")
    role = _str_field(body, "role", "key-announce")
    if role not in ROLES:
        raise InvalidBody(f"key-announce body role {role!r} is not one of {ROLES}")
    try:
        pub = bytes.fromhex(pub_hex)
    except ValueError:
        raise InvalidBody("key-announce body pub is not hex") from None
    if key_id_of(algorithm, pub) != key_id:
        raise InvalidBody(f"key-announce body key_id {key_id!r} is not the id of its pub under {algorithm!r}")
    if not isinstance(body["lineage"], list) or not all(isinstance(x, str) for x in body["lineage"]):
        raise InvalidBody("key-announce body lineage must be a list of key ids")
    if not isinstance(body["supersedes"], list) or not all(isinstance(x, str) for x in body["supersedes"]):
        raise InvalidBody("key-announce body supersedes must be a list of key ids")
    if key_id in body["supersedes"] or key_id in body["lineage"]:
        raise InvalidBody("key-announce body key_id appears in its own supersedes or lineage")
    if isinstance(body["expires_at"], bool) or not isinstance(body["expires_at"], (int, float)):
        raise InvalidBody("key-announce body expires_at must be a number")


# --------------------------------------------------------------------------- revocation list
@dataclass(frozen=True)
class Revocation:
    key_id: str
    reason: str
    by: str
    seq: int

    def to_record(self) -> dict[str, Any]:
        return {"key_id": self.key_id, "reason": self.reason, "by": self.by, "seq": int(self.seq)}


class RevocationList:
    """Append-only ``[{key_id, reason, by, seq}, ...]``; any fleet or operator key may extend it."""

    def __init__(self, entries: Iterable[Mapping[str, Any] | Revocation] = ()) -> None:
        self._entries: list[Revocation] = []
        for e in entries:
            self._entries.append(e if isinstance(e, Revocation) else Revocation(str(e["key_id"]), str(e.get("reason", "")), str(e.get("by", "")), int(e.get("seq", 0))))

    def extend(self, key_id: str, *, reason: str, by_key: str, by_role: str, seq: int) -> Revocation:
        """Append one revocation; refused by name unless ``by_role`` is fleet or operator.  Idempotent per (key_id, by)."""
        if by_role not in ROLE_MAY_REVOKE:
            raise Refused(f"revocation-needs-fleet-or-operator-key:{by_role}")
        for existing in self._entries:
            if existing.key_id == key_id and existing.by == by_key:
                return existing
        entry = Revocation(key_id, reason, by_key, int(seq))
        self._entries.append(entry)
        return entry

    def revoke(self, key_id: str, *, by: Any, reason: str, seq: int = 0, now: float = 0.0) -> Revocation:
        """``verify.policy`` spelling: ``by`` is a ``core.NodeIdentity`` (role-checked)."""
        return self.extend(key_id, reason=reason, by_key=str(by.key_id), by_role=str(by.role), seq=int(seq or now))

    def is_revoked(self, key_id: str) -> bool:
        return any(e.key_id == key_id for e in self._entries)

    def entry(self, key_id: str) -> Mapping[str, Any] | None:
        for e in self._entries:
            if e.key_id == key_id:
                return e.to_record()
        return None

    def entries(self) -> list[Revocation]:
        return list(self._entries)

    def key_ids(self) -> list[str]:
        return sorted({e.key_id for e in self._entries})

    def __len__(self) -> int:
        return len(self._entries)

    def to_record(self) -> list[dict[str, Any]]:
        return [e.to_record() for e in self._entries]

    @classmethod
    def from_record(cls, rec: Any) -> RevocationList:
        if isinstance(rec, Mapping):          # the pre-U126 mapping shape: key_id -> {at, by, reason}
            return cls(Revocation(str(k), str(v.get("reason", "")), str(v.get("by", "")), int(v.get("seq", v.get("at", 0)) or 0)) for k, v in rec.items())
        return cls(rec)

    def save(self, objects: ObjectStore, name: str = REVOCATIONS_POINTER) -> None:
        objects.put_named(name, canonical_json(self.to_record()))

    @classmethod
    def load(cls, objects: ObjectStore, name: str = REVOCATIONS_POINTER) -> RevocationList:
        raw = objects.get_named(name)
        return cls() if raw is None else cls.from_record(json.loads(raw.decode("utf-8")))


# --------------------------------------------------------------------------- key sources
class KeySource(Protocol):
    """Fills a keyring; returns the key ids it added.  Pure over its inputs (a directory, a store, a log)."""

    name: str

    def load_into(self, keyring: Keyring) -> Sequence[str]: ...


class LocalIdentitySource:
    """``<nodes_dir>/*/keys/node.json`` public records plus ``*.pub`` files under ``key_dir``."""

    name = "local-identity"

    def __init__(self, *, nodes_dir: str | Path | None = None, key_dir: str | Path | None = None) -> None:
        self.nodes_dir = Path(nodes_dir) if nodes_dir else None
        self.key_dir = Path(key_dir) if key_dir else None

    def load_into(self, keyring: Keyring) -> list[str]:
        loaded: list[str] = []
        if self.nodes_dir is not None and self.nodes_dir.is_dir():
            for public_path in sorted(self.nodes_dir.glob("*/keys/node.json")):
                try:
                    rec = json.loads(public_path.read_text("utf-8"))
                    algorithm, pub = str(rec["algorithm"]), bytes.fromhex(str(rec["public"]))
                except (OSError, ValueError, KeyError):
                    continue
                if algorithm != "ed25519":
                    continue                      # a hash-token key has no public material to learn
                meta: dict[str, Any] = {"expires_at": rec.get("expires_at"), "supersedes": list(rec.get("previous_key_ids", ()))}
                identity_path = public_path.parent.parent / "identity.json"
                if identity_path.is_file():
                    try:
                        ident = json.loads(identity_path.read_text("utf-8"))
                        meta["role"] = ident.get("role")
                        meta["lineage"] = list(ident.get("invite_lineage", ()))
                    except (OSError, ValueError):
                        pass
                loaded.append(keyring.add_ed25519_public(pub, **meta))
        if self.key_dir is not None and self.key_dir.is_dir():
            loaded.extend(keyring.load_dir(self.key_dir))
        return loaded


class InviteSource:
    """Every ``invites/<key_id>`` object that verifies against the keyring at ``at_seq`` (issuers first)."""

    name = "invites"

    def __init__(self, objects: ObjectStore, *, at_seq: int, names: Iterable[str] | None = None) -> None:
        self.objects = objects
        self.at_seq = int(at_seq)
        self.names = list(names) if names is not None else None
        self.refused: dict[str, str] = {}

    def _names(self) -> list[str]:
        if self.names is not None:
            return list(self.names)
        lister = getattr(self.objects, "list_named", None)
        if not callable(lister):
            return []
        return sorted(lister(INVITES_PREFIX))

    def load_into(self, keyring: Keyring) -> list[str]:
        pending: list[KeyInvite] = []
        for name in self._names():
            data = self.objects.get_named(name)
            if data is None:
                continue
            try:
                pending.append(KeyInvite.from_bytes(data))
            except KeyError_ as exc:
                self.refused[name] = str(exc)
        loaded: list[str] = []
        progress = True
        while pending and progress:           # issuers admitted by earlier invites unlock later ones
            progress = False
            for invite in list(pending):
                try:
                    verify_key_invite(invite, keyring, at_seq=self.at_seq)
                except KeyError_ as exc:
                    self.refused[invite_name(invite.key_id)] = str(exc)
                    continue
                keyring.add(invite.key_id, invite.algorithm, bytes.fromhex(invite.pub), role=invite.role, lineage=list(invite.joiner_lineage),
                            invited_by=invite.issued_by, expires_at_seq=invite.expires_at_seq)
                self.refused.pop(invite_name(invite.key_id), None)
                loaded.append(invite.key_id)
                pending.remove(invite)
                progress = True
        return loaded


class LogAnnounceSource:
    """KEY_ANNOUNCE records in ``partition`` (default ``keys``); the announced key must be the signer."""

    name = "log-announce"

    def __init__(self, log: LogStore, *, partition: str = KEYS_PARTITION, partitions: Iterable[str] | None = None) -> None:
        self.log = log
        self.partitions = list(partitions) if partitions is not None else [partition]

    def load_into(self, keyring: Keyring) -> list[str]:
        loaded: list[str] = []
        known = set(self.log.partitions())
        for partition in self.partitions:
            if partition not in known:
                continue
            for rec in self.log.read(partition, 0):
                if rec.type is not RecordType.KEY_ANNOUNCE:
                    continue
                body = rec.body
                if rec.signer_key != body.get("key_id"):
                    continue                              # not a possession proof; ignored
                if body.get("algorithm") != "ed25519":
                    continue
                try:
                    pub = bytes.fromhex(str(body["pub"]))
                except (KeyError, ValueError):
                    continue
                # the announce is self-signed: its role and lineage are the node's *claim*
                # (``claimed_role`` / ``claimed_lineage``), never the attested ``role`` an invite or
                # a local identity dir gives — ``verify_key_invite`` authorises on the attested one
                key_id = key_id_of("ed25519", pub)
                if not keyring.knows(key_id):
                    keyring.add_ed25519_public(pub)
                if not keyring.verify(key_id, _unsigned(rec), rec.signature):
                    keyring.forget(key_id)                   # the announce does not verify under the key it announces
                    continue
                keyring.note(key_id, claimed_role=body.get("role"), claimed_lineage=list(body.get("lineage", ())),
                             expires_at=body.get("expires_at"), supersedes=list(body.get("supersedes", ())),
                             announced_seq=rec.seq, announced_partition=partition)
                loaded.append(key_id)
        return loaded


def _unsigned(record: Any) -> bytes:
    from agentdecompile_grid.log.records import unsigned_bytes
    return unsigned_bytes(record)


class RemoteDirectorySource:
    """Slot: a fabric key directory over HTTPS (``keyring.remote_url``)."""

    name = "remote-directory"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotConfigured("RemoteDirectorySource is declared, not implemented: it needs keyring.remote_url and the fabric's directory format")

    def load_into(self, keyring: Keyring) -> list[str]:  # pragma: no cover - never constructed
        return []


for _src in (LocalIdentitySource, InviteSource, LogAnnounceSource, RemoteDirectorySource):
    KEY_SOURCES.register(_src.name, _src, replace=True)


def sources_from_config(config: Mapping[str, Any], *, log: LogStore | None = None, objects: ObjectStore | None = None) -> list[KeySource]:
    """``GridConfig.keyring_locator()`` -> the configured sources that can run here (a source whose
    input is absent is skipped; a declared slot raises ``NotConfigured`` by name when named)."""
    out: list[KeySource] = []
    for name in config.get("sources", ("local-identity", "invites", "log-announce")):
        if name == "local-identity":
            out.append(LocalIdentitySource(nodes_dir=config.get("nodes_dir"), key_dir=config.get("key_dir")))
        elif name == "invites":
            if objects is not None:
                at_seq = 0
                if log is not None:
                    at_seq = max((log.last_seq(p) for p in log.partitions()), default=0)
                out.append(InviteSource(objects, at_seq=int(config.get("at_seq", at_seq))))
        elif name == "log-announce":
            if log is not None:
                out.append(LogAnnounceSource(log, partition=str(config.get("announce_partition", KEYS_PARTITION))))
        else:
            out.append(KEY_SOURCES.get(str(name))())
    return out


__all__ = [
    "INVITES_PREFIX", "INVITE_SCHEMA", "InviteRefused", "InviteSource", "KEYS_PARTITION", "KeyError_", "KeyInvite", "KeySource",
    "LocalIdentitySource", "LogAnnounceSource", "REVOCATIONS_POINTER", "ROLES", "ROLE_MAY_REVOKE", "ROLE_MAY_SIGN", "RemoteDirectorySource",
    "Revocation", "RevocationList", "invite_name", "key_announce_body", "make_key_invite", "sources_from_config", "validate_key_announce_body",
    "verify_key_invite", "write_key_invite",
]
