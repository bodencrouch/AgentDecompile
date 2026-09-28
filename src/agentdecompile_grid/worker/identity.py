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

Key algorithms are a registry.  ``ed25519`` is the working algorithm when the ``cryptography``
package imports; ``hash-token`` (HMAC over a random secret) always works and exists so a
single-host grid or the determinism harness needs no signing library — its "public" material is
the secret itself, so it verifies only inside the process (or keyring) that holds the secret.

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
    """Working when the ``cryptography`` package imports; otherwise ``NotConfigured`` names it."""

    name = "ed25519"

    @staticmethod
    def _module():
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519
        except Exception as exc:  # pragma: no cover - depends on the environment
            raise NotConfigured("key algorithm 'ed25519' needs the 'cryptography' package (the 'agentdecompile[signing]' extra); use key_algorithm='hash-token' for a single-host grid") from exc
        return serialization, ed25519

    def generate(self) -> tuple[bytes, bytes]:
        serialization, ed25519 = self._module()
        private = ed25519.Ed25519PrivateKey.generate()
        secret = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return secret, public

    def sign(self, secret: bytes, data: bytes) -> bytes:
        _, ed25519 = self._module()
        return ed25519.Ed25519PrivateKey.from_private_bytes(secret).sign(data)

    def verify(self, material: bytes, data: bytes, signature: bytes) -> bool:
        _, ed25519 = self._module()
        try:
            ed25519.Ed25519PublicKey.from_public_bytes(material).verify(signature, data)
            return True
        except Exception:
            return False

    def describe(self) -> Mapping[str, Any]:
        try:
            self._module()
            status = "working"
        except NotConfigured:
            status = "declared"
        return {"name": self.name, "status": status, "needs": ["cryptography"], "public": "32-byte raw Ed25519 public key"}


class HashTokenAlgorithm:
    """Always working.  ``public`` is a commitment to the secret; verification needs the secret."""

    name = "hash-token"
    _DOMAIN = b"adgrid/hash-token/v1/"

    def generate(self) -> tuple[bytes, bytes]:
        secret = secrets.token_bytes(32)
        return secret, hashlib.sha256(self._DOMAIN + b"public" + secret).digest()

    def sign(self, secret: bytes, data: bytes) -> bytes:
        return hmac.new(secret, self._DOMAIN + data, hashlib.sha256).digest()

    def verify(self, material: bytes, data: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(material, data), signature)

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "needs": [], "public": "sha256 commitment; verification needs the secret (local/harness only)"}


KEY_ALGORITHMS.register("ed25519", Ed25519Algorithm())
KEY_ALGORITHMS.register("hash-token", HashTokenAlgorithm())


def key_id_for(algorithm: str, public: bytes) -> str:
    """A key id is a content address of the public material, never the material itself."""
    return digest(canonical_json({"alg": algorithm, "pub": public.hex()}))[:32]


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


class Keyring:
    """key_id -> (algorithm, verification material).  Filled from invites, manifests and the local key."""

    def __init__(self) -> None:
        self._keys: dict[str, tuple[str, bytes]] = {}

    def add(self, key_id: str, algorithm: str, material: bytes) -> None:
        self._keys[key_id] = (algorithm, material)

    def add_node_key(self, key: NodeKey) -> None:
        material = key.secret if key.algorithm == "hash-token" else key.public
        self.add(key.key_id, key.algorithm, material)

    def get(self, key_id: str) -> tuple[str, bytes] | None:
        return self._keys.get(key_id)

    def __contains__(self, key_id: object) -> bool:
        return key_id in self._keys

    def key_ids(self) -> list[str]:
        return sorted(self._keys)


class NodeSigner:
    """``core.Signer`` over a ``NodeKey``; verification of other keys goes through the keyring."""

    def __init__(self, key: NodeKey, keyring: Keyring | None = None) -> None:
        self.key = key
        self.key_id = key.key_id
        self.keyring = keyring or Keyring()
        self.keyring.add_node_key(key)
        self._algorithm: KeyAlgorithm = KEY_ALGORITHMS.get(key.algorithm)

    def sign(self, data: bytes) -> str:
        return _b64e(self._algorithm.sign(self.key.secret, data))

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        entry = self.keyring.get(key_id)
        if entry is None:
            return False
        algorithm_name, material = entry
        try:
            return KEY_ALGORITHMS.get(algorithm_name).verify(material, data, _b64d(signature))
        except (KeyError, ValueError):
            return False


class NodeKeyStore:
    """The key directory: ``keys/node.json`` (public record) + ``keys/node.secret`` (0600) + ``identity.json``."""

    def __init__(self, state_dir: str | os.PathLike[str]) -> None:
        self.state_dir = Path(state_dir)
        self.keys_dir = self.state_dir / "keys"
        self.public_path = self.keys_dir / "node.json"
        self.secret_path = self.keys_dir / "node.secret"
        self.identity_path = self.state_dir / "identity.json"

    # -- keys
    def exists(self) -> bool:
        return self.public_path.exists() and self.secret_path.exists()

    def create(self, *, algorithm: str = "ed25519", now: float, lifetime_s: float = DEFAULT_KEY_LIFETIME_S, previous: Sequence[str] = ()) -> NodeKey:
        alg = KEY_ALGORITHMS.get(algorithm)
        secret, public = alg.generate()
        key = NodeKey(algorithm, key_id_for(algorithm, public), secret, public, float(now), float(now) + float(lifetime_s), tuple(previous))
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

    def load_or_create(self, *, algorithm: str = "ed25519", now: float, lifetime_s: float = DEFAULT_KEY_LIFETIME_S) -> NodeKey:
        return self.load() if self.exists() else self.create(algorithm=algorithm, now=now, lifetime_s=lifetime_s)

    def renew(self, key: NodeKey, *, now: float, canaries_passed: bool, lifetime_s: float = DEFAULT_KEY_LIFETIME_S) -> NodeKey:
        """Extend the expiry.  Refused by name unless the canaries were just re-proven (design §6.2)."""
        if not canaries_passed:
            raise Refused("key-renewal-needs-canaries")
        renewed = replace(key, expires_at=float(now) + float(lifetime_s))
        self._write(renewed)
        return renewed

    def rotate(self, key: NodeKey, *, now: float, lifetime_s: float = DEFAULT_KEY_LIFETIME_S) -> NodeKey:
        """A new key that remembers its predecessors so old records stay attributable."""
        return self.create(algorithm=key.algorithm, now=now, lifetime_s=lifetime_s, previous=(key.key_id, *key.previous_key_ids))

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
    """Parse and validate an invite without creating trust from its own token.

    When ``verifier`` is supplied, its keyring (or the explicit identity keyring) must already
    contain the issuer.  The token's ``issuer_public`` is descriptive material only: accepting it
    as a trust root would make every self-signed invite valid.
    """
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
        if not verifier.verify(invite.issuer_key, invite.signed_bytes(), invite.signature):
            raise InviteError(f"invite signature by unknown issuer {invite.issuer_key} does not verify")
    return invite


def verify_invite(invite: Invite, keyring: Any) -> None:
    """Verify an invite against the fabric's pinned signing keyring.

    The issuer must already be trusted, its configured role must match ``issuer_role``, and the
    token signature must verify.  Nothing carried by the token adds a key to the trust root.
    """
    if not keyring.knows(invite.issuer_key):
        raise InviteError(f"invite issuer {invite.issuer_key} is not in the trusted keyring")
    trusted_role = keyring.role_of(invite.issuer_key)
    if trusted_role != invite.issuer_role:
        raise InviteError(
            f"invite issuer role {invite.issuer_role!r} does not match trusted role {trusted_role!r}"
        )
    if not keyring.verify(invite.issuer_key, invite.signed_bytes(), invite.signature):
        raise InviteError(f"invite signature by {invite.issuer_key} does not verify")


def lineage_for_joiner(invite: Invite) -> tuple[str, ...]:
    return invite.joiner_lineage


def bind_identity(key: NodeKey, invite: Invite, capabilities: Iterable[str]) -> NodeIdentity:
    return NodeIdentity(key_id=key.key_id, capabilities=tuple(sorted(set(capabilities))), invite_lineage=invite.joiner_lineage, role=invite.role)


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
    "lineage_set", "make_invite", "parse_invite_url", "split_fabric_url", "verify_invite",
]
