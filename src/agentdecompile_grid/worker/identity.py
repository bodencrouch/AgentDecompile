"""Node identity: the key directory, invites, lineage and the independence primitive.

A node is a key.  The key is generated at first join and lives in ``<state_dir>/keys`` (secret
0600).  An invite is the fragment of ``https://<fabric>/g/<fabric_id>#<token>``: base64url of a
canonical-JSON payload signed by the *issuer* key, carrying the issuer's role, the issuer's own
lineage, the role being granted and an expiry.  The joiner's lineage is the issuer's lineage plus
the issuer key, so lineage is the chain of invite key ids back to an operator root key.

Independence (the rule every verification path relies on) is **disjoint lineage** as
``core.NodeIdentity`` states: two keys are independent when ``{key} | set(lineage)`` of one is
disjoint from that of the other.  Two identities minted from the same public invite therefore
share the issuer in their lineage and are *not* independent, which is what closes the "a donor
invites itself twice" hole.  Design §2.5's weaker rule (neither key in the other's ancestry) is
registered as a second policy in ``verify.policy`` and is never the default.

Roles differ only in what a node mirrors and whether it may sign invites, run verifiers and run
appliers: ``operator`` signs any invite, ``fleet`` signs fleet and donor invites, ``donor`` signs
nothing.  A donor-issued invite is refused at parse time by name.

Key algorithms are a registry.  ``ed25519`` is the working algorithm when a signing backend
imports (``log.signing.SIGNING_BACKENDS``: cryptography, pynacl) and the default; ``hash-token``
(HMAC over a random secret) always works and exists so a single-host grid or the determinism
harness needs no signing library — its "public" material is a commitment to the secret, so it
verifies only inside the process (or keyring) that holds the secret.

**One key-id scheme (U126)**: ``key_id_for(algorithm, public) = "<algorithm>:<hex sha256(public)>"``,
identical to ``log.signing.key_id_of`` — for ed25519 the id in ``signer_key`` is the id a
``log.signing.Keyring`` looks up, so node-signed records verify offline through the same keyring
as operator-signed ones.  ``NodeSigner`` wraps the matching ``log.signing`` signer
(``Ed25519Signer`` / ``HashTokenSigner``) and the node's keyring *is* ``log.signing.Keyring``.

**Key lifetime**: ``key_lifetime_s`` (default 7 days, ``identity.key_lifetime_s``).  ``NodeKeyStore.renew``
rotates a key past its lifetime to a fresh one that remembers its predecessors
(``previous_key_ids``), refused by name unless the canaries were just re-proven
(``after_canary=True``); the new key's KEY_ANNOUNCE record (``announce_body``) lists the old id
under ``supersedes``.

Acceptance tests named for the final verification phase (design §15.0, U125/U126):
  * ``test_invite_roles``: a fleet key signs a donor and a fleet invite; a donor key's invite is
    refused by name; an operator key signs all three roles.
  * ``test_invite_expiry_and_signature``: an expired token and a token whose signature does not
    verify are refused by name; a token with a tampered role fails verification.
  * ``test_self_invite_not_independent``: two keys joined from one invite are not independent;
    a key and one it invited are not independent; keys under two operator roots are.
  * ``test_two_lineages_asserted``: ``assert_two_lineages`` refuses a fleet key set with a single
    lineage by name.
  * ``test_key_lifetime``: a key expires at 7 days and ``renew`` extends it only when told the
    canaries passed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from ..core import GridError, NodeIdentity, NotConfigured, Refused, Registry, canonical_json, digest
from ..log import signing as _signing
from ..log.keys import KEYS_PARTITION, key_announce_body
from ..log.signing import Ed25519Signer, HashTokenSigner, Keyring, key_id_of

INVITE_VERSION = 1
DEFAULT_KEY_LIFETIME_S = 7 * 24 * 3600          # design §6.2: short-lived keys, renewed by canary re-run
DEFAULT_INVITE_LIFETIME_S = 30 * 24 * 3600
ROLES = ("operator", "fleet", "donor")
ROLE_MAY_SIGN: Mapping[str, frozenset[str]] = {
    "operator": frozenset({"operator", "fleet", "donor"}),
    "fleet": frozenset({"fleet", "donor"}),
    "donor": frozenset(),
}
ROLE_MAY_VERIFY: frozenset[str] = frozenset({"operator", "fleet"})   # design §9.2 T4: donor keys are never verifier keys


class InviteError(GridError):
    """An invite token is malformed, expired, signed by a role that may not sign, or unverifiable."""


class IdentityError(GridError):
    """The key directory is missing, unreadable or inconsistent."""


# --------------------------------------------------------------------------- key algorithms
class KeyAlgorithm(Protocol):
    """Generates a keypair and signs/verifies bytes.  ``material`` for verification is the public key
    for asymmetric algorithms and the secret for ``hash-token`` (never leaves the host)."""

    name: str

    def generate(self) -> tuple[bytes, bytes]: ...          # (secret, public)
    def sign(self, secret: bytes, data: bytes) -> bytes: ...
    def verify(self, material: bytes, data: bytes, signature: bytes) -> bool: ...
    def describe(self) -> Mapping[str, Any]: ...


KEY_ALGORITHMS = Registry("key algorithm")


class Ed25519Algorithm:
    """The ``log.signing`` ed25519 backend (first importable of cryptography, pynacl); the default."""

    name = "ed25519"

    @staticmethod
    def _backend(name: str = ""):
        try:
            return _signing.select_backend(name)
        except NotConfigured as exc:
            raise NotConfigured(f"key algorithm 'ed25519': {exc}; use worker.key_algorithm='hash-token' for a single-host harness") from exc

    def generate(self) -> tuple[bytes, bytes]:
        return self._backend().generate()

    def sign(self, secret: bytes, data: bytes) -> bytes:
        return self._backend().sign(secret, data)

    def verify(self, material: bytes, data: bytes, signature: bytes) -> bool:
        return self._backend().verify(material, data, signature)

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working" if _signing.have_backend() else "declared", "default": True,
                "needs": ["one of " + ", ".join(_signing.BACKEND_ORDER)], "public": "32-byte raw Ed25519 public key"}


class HashTokenAlgorithm:
    """Always working.  ``public`` is a commitment to the secret; verification needs the secret."""

    name = "hash-token"

    def generate(self) -> tuple[bytes, bytes]:
        secret = secrets.token_bytes(32)
        return secret, _signing.hash_token_public(secret)

    def sign(self, secret: bytes, data: bytes) -> bytes:
        return _signing.hash_token_sign(secret, data)

    def verify(self, material: bytes, data: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(material, data), signature)

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "needs": [], "public": "sha256 commitment; verification needs the secret (local/harness only)"}


KEY_ALGORITHMS.register("ed25519", Ed25519Algorithm())
KEY_ALGORITHMS.register("hash-token", HashTokenAlgorithm())


def key_id_for(algorithm: str, public: bytes) -> str:
    """The one key-id scheme: ``<algorithm>:<hex sha256 of the raw public material>`` (= ``log.signing.key_id_of``)."""
    return key_id_of(algorithm, public)


# --------------------------------------------------------------------------- node key
@dataclass(frozen=True)
class NodeKey:
    algorithm: str
    key_id: str
    secret: bytes
    public: bytes
    created_at: float
    expires_at: float
    previous_key_ids: tuple[str, ...] = ()

    def expired(self, now: float) -> bool:
        return now >= self.expires_at

    def public_record(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm, "key_id": self.key_id, "public": self.public.hex(),
            "created_at": self.created_at, "expires_at": self.expires_at, "previous_key_ids": list(self.previous_key_ids),
        }


# ``Keyring`` is ``log.signing.Keyring``: one keyring type for operator and node keys (U126).
# ``add(key_id, algorithm, material)``, ``get``, ``__contains__`` and ``key_ids`` keep this module's spelling.


def _keyring_add_node_key(self: Keyring, key: "NodeKey") -> None:
    material = key.secret if key.algorithm == "hash-token" else key.public
    self.add(key.key_id, key.algorithm, material, expires_at=key.expires_at, supersedes=list(key.previous_key_ids))


Keyring.add_node_key = _keyring_add_node_key  # type: ignore[attr-defined]


class NodeSigner:
    """``core.Signer`` over a ``NodeKey``: wraps the ``log.signing`` signer for the key's algorithm
    (``inner``: ``Ed25519Signer`` or ``HashTokenSigner``), so a node signature is byte-for-byte what
    the operator signer of the same algorithm would produce and verifies through any ``Keyring``
    holding the public key.  Verification of *other* keys goes through ``keyring``."""

    def __init__(self, key: NodeKey, keyring: Keyring | None = None) -> None:
        self.key = key
        self.key_id = key.key_id
        self.keyring = keyring or Keyring()
        self.keyring.add_node_key(key)
        self._algorithm: KeyAlgorithm = KEY_ALGORITHMS.get(key.algorithm)
        if key.algorithm == "ed25519":
            self.inner: Any = Ed25519Signer(key.secret)
        elif key.algorithm == "hash-token":
            self.inner = HashTokenSigner(key.secret)
        else:
            raise IdentityError(f"no log.signing signer for key algorithm {key.algorithm!r}")
        if self.inner.key_id != key.key_id:
            raise IdentityError("node key id does not match its public material; the key directory is inconsistent")

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def public_bytes(self) -> bytes:
        return self.inner.public_bytes

    def sign(self, data: bytes) -> str:
        return self.inner.sign(data)

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        return self.keyring.verify(key_id, data, signature)


class NodeKeyStore:
    """The key directory: ``keys/node.json`` (public record) + ``keys/node.secret`` (0600) + ``identity.json``
    + ``keys/announced`` (key ids whose KEY_ANNOUNCE was enqueued).  ``key_lifetime_s`` is the default
    lifetime of every key it creates or renews (``identity.key_lifetime_s``)."""

    def __init__(self, state_dir: str | os.PathLike[str], *, key_lifetime_s: float = DEFAULT_KEY_LIFETIME_S) -> None:
        self.state_dir = Path(state_dir)
        self.keys_dir = self.state_dir / "keys"
        self.public_path = self.keys_dir / "node.json"
        self.secret_path = self.keys_dir / "node.secret"
        self.identity_path = self.state_dir / "identity.json"
        self.announced_path = self.keys_dir / "announced"
        self.key_lifetime_s = float(key_lifetime_s)

    # -- keys
    def exists(self) -> bool:
        return self.public_path.exists() and self.secret_path.exists()

    def create(self, *, algorithm: str = "ed25519", now: float, lifetime_s: float | None = None, previous: Sequence[str] = ()) -> NodeKey:
        alg = KEY_ALGORITHMS.get(algorithm)
        secret, public = alg.generate()
        lifetime = self.key_lifetime_s if lifetime_s is None else float(lifetime_s)
        key = NodeKey(algorithm, key_id_for(algorithm, public), secret, public, float(now), float(now) + lifetime, tuple(previous))
        self._write(key)
        return key

    def load(self) -> NodeKey:
        if not self.exists():
            raise IdentityError(f"no node key under {self.keys_dir}; run join to create one")
        try:
            rec = json.loads(self.public_path.read_text("utf-8"))
            secret = bytes.fromhex(self.secret_path.read_text("utf-8").strip())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise IdentityError(f"node key under {self.keys_dir} is unreadable: {exc.__class__.__name__}") from exc
        key = NodeKey(rec["algorithm"], rec["key_id"], secret, bytes.fromhex(rec["public"]), float(rec["created_at"]), float(rec["expires_at"]), tuple(rec.get("previous_key_ids", ())))
        if key_id_for(key.algorithm, key.public) != key.key_id:
            raise IdentityError("node key id does not match its public material; the key directory is inconsistent")
        return key

    def load_or_create(self, *, algorithm: str = "ed25519", now: float, lifetime_s: float | None = None) -> NodeKey:
        return self.load() if self.exists() else self.create(algorithm=algorithm, now=now, lifetime_s=lifetime_s)

    def renew(self, key: NodeKey, *, now: float, canaries_passed: bool = False, after_canary: bool = True,
              lifetime_s: float | None = None, force: bool = False) -> NodeKey:
        """A key past its lifetime (or ``force``) is *rotated* to a fresh key that lists it under
        ``previous_key_ids`` — the old key is announced as superseded by the new key's KEY_ANNOUNCE
        (``announce_body``).  With ``after_canary`` (the default) the rotation is refused by name
        unless the canaries were just re-proven (design §6.2).  A key inside its lifetime is
        returned unchanged."""
        if not force and not key.expired(now):
            return key
        if after_canary and not canaries_passed:
            raise Refused("key-renewal-needs-canaries")
        return self.rotate(key, now=now, lifetime_s=lifetime_s)

    def rotate(self, key: NodeKey, *, now: float, lifetime_s: float | None = None) -> NodeKey:
        """A new key that remembers its predecessors so old records stay attributable."""
        return self.create(algorithm=key.algorithm, now=now, lifetime_s=lifetime_s, previous=(key.key_id, *key.previous_key_ids))

    # -- announcements
    def announced(self, key_id: str) -> bool:
        if not self.announced_path.exists():
            return False
        return key_id in self.announced_path.read_text("utf-8").split()

    def mark_announced(self, key_id: str) -> None:
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        existing = self.announced_path.read_text("utf-8") if self.announced_path.exists() else ""
        if key_id not in existing.split():
            _write_atomic(self.announced_path, (existing + key_id + "\n").encode("utf-8"))

    def _write(self, key: NodeKey) -> None:
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.keys_dir, stat.S_IRWXU)
        except OSError:
            pass
        _write_private(self.secret_path, key.secret.hex().encode("ascii"))
        _write_atomic(self.public_path, json.dumps(key.public_record(), sort_keys=True, indent=1).encode("utf-8"))

    # -- identity (the bound NodeIdentity plus the fabric it belongs to)
    def save_identity(self, identity: NodeIdentity, extra: Mapping[str, Any]) -> None:
        rec = {
            "key_id": identity.key_id, "role": identity.role,
            "capabilities": list(identity.capabilities), "invite_lineage": list(identity.invite_lineage),
            **dict(extra),
        }
        self.state_dir.mkdir(parents=True, exist_ok=True)
        _write_atomic(self.identity_path, json.dumps(rec, sort_keys=True, indent=1).encode("utf-8"))

    def load_identity(self) -> tuple[NodeIdentity, dict[str, Any]] | None:
        if not self.identity_path.exists():
            return None
        rec = json.loads(self.identity_path.read_text("utf-8"))
        identity = NodeIdentity(key_id=rec["key_id"], capabilities=tuple(rec.get("capabilities", ())), invite_lineage=tuple(rec.get("invite_lineage", ())), role=rec.get("role", "donor"))
        extra = {k: v for k, v in rec.items() if k not in {"key_id", "role", "capabilities", "invite_lineage"}}
        return identity, extra


# --------------------------------------------------------------------------- invites
@dataclass(frozen=True)
class Invite:
    """A parsed invite.  ``lineage`` is the *issuer's* ancestry; the joiner's is ``joiner_lineage``."""

    fabric_url: str
    fabric_id: str
    role: str
    issuer_key: str
    issuer_role: str
    lineage: tuple[str, ...]
    issued_at: float
    expires_at: float
    nonce: str
    signature: str = ""
    issuer_algorithm: str = ""
    issuer_public: str = ""            # hex; lets a joiner add the issuer to its keyring
    labels: Mapping[str, str] = field(default_factory=dict)

    @property
    def joiner_lineage(self) -> tuple[str, ...]:
        return (*self.lineage, self.issuer_key)

    def payload(self) -> dict[str, Any]:
        return {
            "v": INVITE_VERSION, "fabric_id": self.fabric_id, "role": self.role,
            "issuer_key": self.issuer_key, "issuer_role": self.issuer_role, "lineage": list(self.lineage),
            "issued_at": self.issued_at, "expires_at": self.expires_at, "nonce": self.nonce,
            "issuer_algorithm": self.issuer_algorithm, "issuer_public": self.issuer_public, "labels": dict(self.labels),
        }

    def signed_bytes(self) -> bytes:
        return canonical_json(self.payload())

    def token(self) -> str:
        return _b64e(canonical_json({**self.payload(), "sig": self.signature}))

    def url(self) -> str:
        return f"{self.fabric_url}#{self.token()}"

    def fingerprint(self) -> str:
        return digest(self.signed_bytes())[:16]


def make_invite(fabric_url: str, role: str, issuer: NodeIdentity, signer: NodeSigner, *, now: float, lifetime_s: float = DEFAULT_INVITE_LIFETIME_S, nonce: str | None = None, labels: Mapping[str, str] | None = None) -> Invite:
    """Sign an invite.  Refused by name when ``issuer.role`` may not grant ``role`` (donors sign nothing)."""
    if role not in ROLES:
        raise InviteError(f"unknown role {role!r}; known: {ROLES}")
    if role not in ROLE_MAY_SIGN.get(issuer.role, frozenset()):
        raise InviteError(f"role {issuer.role!r} may not sign a {role!r} invite (operator: any; fleet: fleet, donor; donor: none)")
    if signer.key_id != issuer.key_id:
        raise InviteError("the signer's key is not the issuer's key")
    fabric_url, fabric_id = split_fabric_url(fabric_url)
    unsigned = Invite(
        fabric_url=fabric_url, fabric_id=fabric_id, role=role, issuer_key=issuer.key_id, issuer_role=issuer.role,
        lineage=tuple(issuer.invite_lineage), issued_at=float(now), expires_at=float(now) + float(lifetime_s),
        nonce=nonce or secrets.token_hex(8), issuer_algorithm=signer.key.algorithm,
        issuer_public=(signer.key.public.hex() if signer.key.algorithm != "hash-token" else ""), labels=dict(labels or {}),
    )
    return replace(unsigned, signature=signer.sign(unsigned.signed_bytes()))


def split_fabric_url(url: str) -> tuple[str, str]:
    """``https://<fabric>/g/<id>[#...]`` -> (url without fragment, fabric id).  Local roots are allowed
    (``file:///path/g/<id>`` or a bare path ending in ``/g/<id>``) so a single-host grid needs no host."""
    parts = urlsplit(url)
    path = parts.path
    marker = "/g/"
    if marker not in path:
        raise InviteError("invite url must contain '/g/<fabric_id>'")
    fabric_id = path.rsplit(marker, 1)[1].strip("/").split("/", 1)[0]
    if not fabric_id:
        raise InviteError("invite url has an empty fabric id")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, "")), fabric_id


def parse_invite_url(url: str, *, now: float, verifier: NodeSigner | None = None, keyring: Keyring | None = None, max_lifetime_s: float = 365 * 24 * 3600) -> Invite:
    """Parse and validate.  Structural checks always run; the signature is checked when a verifier is
    given (the issuer's public material is taken from the token itself for asymmetric algorithms and
    added to the keyring, so a joiner can verify a fresh invite with no prior contact)."""
    fragment = urlsplit(url).fragment
    if not fragment:
        raise InviteError("invite url has no '#<token>' fragment")
    fabric_url, fabric_id = split_fabric_url(url)
    try:
        rec = json.loads(_b64d(fragment).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InviteError(f"invite token is not base64url canonical JSON ({exc.__class__.__name__})") from exc
    if not isinstance(rec, dict) or rec.get("v") != INVITE_VERSION:
        raise InviteError(f"invite token version is not {INVITE_VERSION}")
    missing = [k for k in ("fabric_id", "role", "issuer_key", "issuer_role", "lineage", "issued_at", "expires_at", "nonce", "sig") if k not in rec]
    if missing:
        raise InviteError(f"invite token lacks fields: {missing}")
    if rec["fabric_id"] != fabric_id:
        raise InviteError("invite token fabric id does not match the url")
    if rec["role"] not in ROLES or rec["issuer_role"] not in ROLES:
        raise InviteError(f"invite names an unknown role ({rec['role']!r} by {rec['issuer_role']!r})")
    if rec["role"] not in ROLE_MAY_SIGN[rec["issuer_role"]]:
        raise InviteError(f"invite signed by a {rec['issuer_role']!r} key cannot grant {rec['role']!r} (operator: any; fleet: fleet, donor; donor: none)")
    invite = Invite(
        fabric_url=fabric_url, fabric_id=fabric_id, role=rec["role"], issuer_key=rec["issuer_key"], issuer_role=rec["issuer_role"],
        lineage=tuple(rec["lineage"]), issued_at=float(rec["issued_at"]), expires_at=float(rec["expires_at"]), nonce=str(rec["nonce"]),
        signature=str(rec["sig"]), issuer_algorithm=str(rec.get("issuer_algorithm", "")), issuer_public=str(rec.get("issuer_public", "")),
        labels=dict(rec.get("labels", {})),
    )
    if invite.issuer_key in invite.lineage:
        raise InviteError("invite issuer appears in its own lineage")
    if now >= invite.expires_at:
        raise InviteError(f"invite expired at {invite.expires_at:.0f} (now {now:.0f})")
    if invite.expires_at - invite.issued_at > max_lifetime_s:
        raise InviteError("invite lifetime exceeds the maximum")
    if verifier is not None:
        ring = keyring or verifier.keyring
        if invite.issuer_key not in ring and invite.issuer_algorithm and invite.issuer_public:
            try:
                public = bytes.fromhex(invite.issuer_public)
            except ValueError as exc:
                raise InviteError("invite carries malformed issuer public material") from exc
            if key_id_for(invite.issuer_algorithm, public) != invite.issuer_key:
                raise InviteError("invite issuer public material does not hash to the issuer key id")
            ring.add(invite.issuer_key, invite.issuer_algorithm, public)
        if not verifier.verify(invite.issuer_key, invite.signed_bytes(), invite.signature):
            raise InviteError(f"invite signature by {invite.issuer_key} does not verify (unknown issuer key or tampered token)")
    return invite


def lineage_for_joiner(invite: Invite) -> tuple[str, ...]:
    return invite.joiner_lineage


def bind_identity(key: NodeKey, invite: Invite, capabilities: Iterable[str]) -> NodeIdentity:
    return NodeIdentity(key_id=key.key_id, capabilities=tuple(sorted(set(capabilities))), invite_lineage=invite.joiner_lineage, role=invite.role)


# --------------------------------------------------------------------------- announcements
def announce_body(key: NodeKey, identity: NodeIdentity) -> dict[str, Any]:
    """The KEY_ANNOUNCE body for ``key`` (partition ``log.keys.KEYS_PARTITION``): public material,
    role, lineage, expiry and the key ids it supersedes (``previous_key_ids``).  Signed by the key
    itself when written (``log.records`` binds ``body.key_id == signer_key``)."""
    if key.key_id != identity.key_id:
        raise IdentityError("announce: the identity's key is not the key being announced")
    return key_announce_body(key_id=key.key_id, algorithm=key.algorithm, pub=key.public, role=identity.role, lineage=identity.invite_lineage,
                             expires_at=key.expires_at, supersedes=key.previous_key_ids, created_at=key.created_at)


def enqueue_announce(outbox: Any, keystore: NodeKeyStore, key: NodeKey, identity: NodeIdentity, *, partition: str = KEYS_PARTITION) -> bool:
    """Enqueue the KEY_ANNOUNCE once per key id (``keystore.announced``); returns True when enqueued."""
    if key.algorithm != "ed25519" or keystore.announced(key.key_id):
        return False
    from ..core import RecordType
    from .outbox import PendingRecord

    outbox.enqueue(record=PendingRecord(partition, RecordType.KEY_ANNOUNCE, announce_body(key, identity), ""))
    keystore.mark_announced(key.key_id)
    return True


# --------------------------------------------------------------------------- independence
def lineage_set(key_id: str, lineage: Iterable[str]) -> frozenset[str]:
    return frozenset({key_id, *lineage})


def independent(a_key: str, a_lineage: Iterable[str], b_key: str, b_lineage: Iterable[str]) -> bool:
    """Disjoint lineage (core contract).  Same key: never independent."""
    if a_key == b_key:
        return False
    return lineage_set(a_key, a_lineage).isdisjoint(lineage_set(b_key, b_lineage))


def independent_identities(a: NodeIdentity, b: NodeIdentity) -> bool:
    return independent(a.key_id, a.invite_lineage, b.key_id, b.invite_lineage)


def assert_two_lineages(identities: Sequence[NodeIdentity], *, roles: Iterable[str] = ROLE_MAY_VERIFY) -> tuple[frozenset[str], frozenset[str]]:
    """The verifier key set must hold two keys with disjoint lineage or no proposal can ever be
    verified (design §2.5).  Returns one such pair's lineage sets; refuses by name otherwise."""
    roles = frozenset(roles)
    verifiers = [i for i in identities if i.role in roles]
    for i, a in enumerate(verifiers):
        for b in verifiers[i + 1:]:
            if independent_identities(a, b):
                return lineage_set(a.key_id, a.invite_lineage), lineage_set(b.key_id, b.invite_lineage)
    raise Refused("verifier-key-set-has-one-lineage", candidates=[{"key_id": i.key_id, "lineage": list(i.invite_lineage)} for i in verifiers])


# --------------------------------------------------------------------------- helpers
def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _write_private(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


__all__ = [
    "DEFAULT_INVITE_LIFETIME_S", "DEFAULT_KEY_LIFETIME_S", "Ed25519Algorithm", "HashTokenAlgorithm", "INVITE_VERSION", "IdentityError",
    "Invite", "InviteError", "KEY_ALGORITHMS", "KeyAlgorithm", "Keyring", "NodeKey", "NodeKeyStore", "NodeSigner", "ROLES", "ROLE_MAY_SIGN",
    "ROLE_MAY_VERIFY", "assert_two_lineages", "bind_identity", "independent", "independent_identities", "key_id_for", "lineage_for_joiner",
    "lineage_set", "make_invite", "parse_invite_url", "split_fabric_url", "announce_body", "enqueue_announce",
]
