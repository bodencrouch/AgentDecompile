"""Signers and keyrings: key ids are the node identity everywhere.

**One key-id scheme** (U126): ``<algorithm>:<hex sha256 of the raw public key>``, for ed25519
``ed25519:<64 hex>``.  Chosen by the criterion "offline verifiability from the record alone": a
``Keyring`` that has learned the public key (from a key directory, an ``invite.v1`` object or a
KEY_ANNOUNCE record, see ``log.keys.KEY_SOURCES``) finds it by the id in ``signer_key`` and needs
nothing else.  ``worker.identity.key_id_for`` spells the same id, so a node-signed record verifies
through the same keyring as an operator-signed one.

**One class hierarchy**: every signer meets ``core.Signer``; ``Ed25519Signer`` is the default
whenever a signing backend imports (``core.SIGNING_BACKENDS``: ``cryptography`` working, ``pynacl``
declared; first importable wins, ``NotConfigured`` names both when none does), ``NullSigner`` is
the explicit fallback by name (``signing.adapter = null``), ``HMACSigner`` the shared-secret one,
``HashTokenSigner`` the local-only harness one, and ``HsmSigner`` / ``SshAgentSigner`` are declared
slots.  ``worker.identity.NodeSigner`` wraps one of these with the node's key record.

The ``core.Signer`` implementations registered in ``core.SIGNERS``:

* ``NullSigner`` — hash-chain only.  ``sign`` returns ``null:<sha256 of the bytes>`` so a record is
  still tamper-evident (integrity), but nothing proves *who* wrote it (no authorship).  ``key_id``
  is ``null`` or ``null:<label>`` so a laptop grid can still tell its nodes apart.  A keyring only
  accepts null signatures when built with ``allow_null=True``.
* ``HMACSigner`` — shared secret for a single-operator grid.  Every node derives a per-label key
  from the one secret; ``key_id`` is ``hmac:<label>:<id>`` where ``id`` is an HMAC of a fixed tag
  under the derived key (never a bare hash of the secret, which would be an offline oracle).
  Anyone holding the secret can sign for any label: that is the stated trust model.
* ``Ed25519Signer`` — real public-key signatures through the first importable backend.  Keys
  live in a directory (``ed25519.key`` raw 32-byte private, mode 0600; ``ed25519.pub`` raw public;
  ``key_id`` text); ``key_id`` is ``ed25519:<sha256 of the raw public key>``.  The class is always
  declared and registered; construction raises ``NotConfigured`` naming the missing packages.

``Keyring`` holds public material for many key ids, metadata learned from trusted sources, and the
revocation list. ``verify_record`` verifies presence, revocation and signature; ``authorize_record``
also enforces that TASK/CHECKPOINT records need an operator role. Every log reader calls that
authorization contract before folding; ``refusal_reason`` is its non-raising, reported form. Invites
and self-announcements may add key material, but a self-claimed role never grants operator authority.

Acceptance tests (named here, written in the verification phase):
  signing-roundtrip: for each signer, a sealed record verifies through a keyring holding only the
  public part, and fails after flipping one body byte;
  signing-null-policy: a null-signed record is refused by a keyring without ``allow_null``;
  signing-hmac-labels: two labels under one secret have different key ids and verify each other;
  signing-ed25519-declared: with ``cryptography`` absent, ``Ed25519Signer.generate`` raises
  ``NotConfigured`` naming the package, and ``SIGNERS`` still lists ``ed25519``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any, Protocol
from collections.abc import Iterable, Iterator, Mapping

from agentdecompile_grid.core import SIGNERS, SIGNING_BACKENDS, GridError, NotConfigured, Record, Registry, Signer, digest
from agentdecompile_grid.log.records import (
    BadSignature, RevokedSigner, SignerNotAuthorized, UnknownSigner, unsigned_bytes,
)


# --------------------------------------------------------------------------- signing backends
class SigningBackend(Protocol):
    """An ed25519 implementation: raw 32-byte private and public keys, raw 64-byte signatures."""

    name: str
    package: str

    def available(self) -> bool: ...
    def generate(self) -> tuple[bytes, bytes]: ...                    # (private, public)
    def public_of(self, private: bytes) -> bytes: ...
    def sign(self, private: bytes, data: bytes) -> bytes: ...
    def verify(self, public: bytes, data: bytes, signature: bytes) -> bool: ...


class CryptographyBackend:
    name = "cryptography"
    package = "cryptography"

    @staticmethod
    def _mod():
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        return InvalidSignature, serialization, Ed25519PrivateKey, Ed25519PublicKey

    def available(self) -> bool:
        try:
            self._mod()
            return True
        except ImportError:
            return False

    def generate(self) -> tuple[bytes, bytes]:
        _, ser, Priv, _ = self._mod()
        private = Priv.generate()
        raw = private.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption())
        return raw, self.public_of(raw)

    def public_of(self, private: bytes) -> bytes:
        _, ser, Priv, _ = self._mod()
        return Priv.from_private_bytes(private).public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)

    def sign(self, private: bytes, data: bytes) -> bytes:
        _, _, Priv, _ = self._mod()
        return Priv.from_private_bytes(private).sign(data)

    def verify(self, public: bytes, data: bytes, signature: bytes) -> bool:
        InvalidSignature, _, _, Pub = self._mod()
        try:
            Pub.from_public_bytes(public).verify(signature, data)
            return True
        except (ValueError, InvalidSignature):
            return False

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "status": "working" if self.available() else "declared", "requires": [self.package]}


class PyNaclBackend:
    name = "pynacl"
    package = "pynacl"

    @staticmethod
    def _mod():
        from nacl import exceptions, signing
        return exceptions, signing

    def available(self) -> bool:
        try:
            self._mod()
            return True
        except ImportError:
            return False

    def generate(self) -> tuple[bytes, bytes]:
        _, signing = self._mod()
        key = signing.SigningKey.generate()
        return bytes(key), bytes(key.verify_key)

    def public_of(self, private: bytes) -> bytes:
        _, signing = self._mod()
        return bytes(signing.SigningKey(private).verify_key)

    def sign(self, private: bytes, data: bytes) -> bytes:
        _, signing = self._mod()
        return bytes(signing.SigningKey(private).sign(data).signature)

    def verify(self, public: bytes, data: bytes, signature: bytes) -> bool:
        exceptions, signing = self._mod()
        try:
            signing.VerifyKey(public).verify(data, signature)
            return True
        except (exceptions.BadSignatureError, ValueError):
            return False

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "status": "working" if self.available() else "declared", "requires": [self.package]}


BACKEND_ORDER = ("cryptography", "pynacl")
for _backend in (CryptographyBackend(), PyNaclBackend()):
    SIGNING_BACKENDS.register(_backend.name, _backend, replace=True)


def select_backend(name: str = "") -> SigningBackend:
    """The named backend when it imports, else the first importable in ``BACKEND_ORDER``;
    ``NotConfigured`` names every package that would make ed25519 work and the explicit fallback."""
    if name:
        backend = SIGNING_BACKENDS.get(name)
        if not backend.available():
            raise NotConfigured(f"signing backend {name!r} needs the {backend.package!r} package; "
                                f"signing.backend='' picks the first importable of {list(BACKEND_ORDER)}, signing.adapter=null is the explicit fallback")
        return backend
    for candidate in BACKEND_ORDER:
        backend = SIGNING_BACKENDS.get(candidate)
        if backend.available():
            return backend
    raise NotConfigured("no ed25519 signing backend imports (pip install cryptography, or pynacl); "
                        "signing.adapter=null is the explicit fallback (hash chain only, no authorship)")


def have_backend(name: str = "") -> bool:
    try:
        select_backend(name)
        return True
    except NotConfigured:
        return False


HAVE_CRYPTOGRAPHY = CryptographyBackend().available()

SignerRegistry = Registry
SIGNER_REGISTRY = SIGNERS
"""The signer registry is ``core.SIGNERS``; this alias exists so callers can spell it locally."""

_LABEL = re.compile(r"^[A-Za-z0-9._-]{0,64}$")
_HMAC_KEY_TAG = b"agentdecompile-grid/hmac/v1/"
_HMAC_ID_TAG = b"agentdecompile-grid/hmac/v1/key-id"
_HMAC_KEY_ID = re.compile(r"^hmac:([A-Za-z0-9._-]*):([0-9a-f]{32})$")


class KeyMaterialError(GridError):
    """Key material is missing, malformed or unreadable; the message names the path or variable."""


class KeyMaterialMissing(KeyMaterialError):
    """A key directory, file or environment variable that must hold key material does not."""


def _check_label(label: str) -> str:
    if not _LABEL.match(label):
        raise KeyMaterialError(f"key label {label!r} must match [A-Za-z0-9._-]{{0,64}}")
    return label


# --------------------------------------------------------------------------- null
class NullSigner:
    """Hash-chain only.  Integrity without authorship; ``key_id`` = ``null`` or ``null:<label>``."""

    name = "null"

    def __init__(self, label: str = "") -> None:
        self.key_id = f"null:{_check_label(label)}" if label else "null"

    def sign(self, data: bytes) -> str:
        return f"null:{digest(data)}"

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        return is_null_key(key_id) and hmac.compare_digest(signature, f"null:{digest(data)}")

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "properties": {"adapter": {"const": "null"}, "label": {"type": "string"}}}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "working", "requires": [], "config_schema": cls.config_schema(),
                "semantics": "integrity only: signature = sha256 of the canonical bytes; no authorship"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> NullSigner:
        return cls(label=str(config.get("label", "")))


def is_null_key(key_id: str) -> bool:
    return key_id == "null" or key_id.startswith("null:")


# --------------------------------------------------------------------------- hmac
def _hmac_derive(secret: bytes, label: str) -> bytes:
    return hmac.new(secret, _HMAC_KEY_TAG + label.encode("utf-8"), hashlib.sha256).digest()


def _hmac_key_id(derived: bytes, label: str) -> str:
    return f"hmac:{label}:{hmac.new(derived, _HMAC_ID_TAG, hashlib.sha256).hexdigest()[:32]}"


def _hmac_verify_with(secret: bytes, key_id: str, data: bytes, signature: str) -> bool:
    match = _HMAC_KEY_ID.match(key_id)
    if not match:
        return False
    label = match.group(1)
    derived = _hmac_derive(secret, label)
    if not hmac.compare_digest(_hmac_key_id(derived, label), key_id):
        return False
    expected = "hmac:" + hmac.new(derived, data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class HMACSigner:
    """Shared-secret fallback for a single-operator grid; per-node labels give distinct key ids."""

    name = "hmac"

    def __init__(self, secret: bytes, *, label: str = "") -> None:
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
            raise KeyMaterialError("HMAC secret must be bytes of at least 16 bytes")
        self._secret = bytes(secret)
        self.label = _check_label(label)
        self._derived = _hmac_derive(self._secret, self.label)
        self.key_id = _hmac_key_id(self._derived, self.label)

    def sign(self, data: bytes) -> str:
        return "hmac:" + hmac.new(self._derived, data, hashlib.sha256).hexdigest()

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        return _hmac_verify_with(self._secret, key_id, data, signature)

    @property
    def secret(self) -> bytes:
        return self._secret

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "adapter": {"const": "hmac"}, "label": {"type": "string"},
            "secret_env": {"type": "string", "description": "environment variable holding the secret (utf-8 or hex:)"},
            "secret_file": {"type": "string", "description": "file holding the raw secret bytes"},
        }, "oneOf": [{"required": ["secret_env"]}, {"required": ["secret_file"]}]}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "working", "requires": ["a shared secret via secret_env or secret_file"],
                "config_schema": cls.config_schema(),
                "semantics": "HMAC-SHA256 under a per-label key derived from one shared secret; holders of the secret can sign for any label"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any], *, environ: Mapping[str, str] | None = None) -> HMACSigner:
        environ = os.environ if environ is None else environ
        label = str(config.get("label", ""))
        if config.get("secret_env"):
            raw = environ.get(str(config["secret_env"]))
            if raw is None:
                raise KeyMaterialMissing(f"environment variable {config['secret_env']!r} is not set")
            secret = bytes.fromhex(raw[4:]) if raw.startswith("hex:") else raw.encode("utf-8")
            return cls(secret, label=label)
        if config.get("secret_file"):
            path = Path(str(config["secret_file"]))
            if not path.is_file():
                raise KeyMaterialMissing(f"secret file {path} does not exist")
            return cls(path.read_bytes().strip(), label=label)
        raise KeyMaterialMissing("HMAC signer config needs secret_env or secret_file")


# --------------------------------------------------------------------------- ed25519
_PRIVATE_FILE = "ed25519.key"
_PUBLIC_FILE = "ed25519.pub"
_KEY_ID_FILE = "key_id"
_KEY_ID_RE = re.compile(r"^([a-z0-9-]+):([0-9a-f]{64})$")


def key_id_of(algorithm: str, public_bytes: bytes) -> str:
    """The one key-id scheme: ``<algorithm>:<hex sha256 of the raw public material>``."""
    return f"{algorithm}:{hashlib.sha256(public_bytes).hexdigest()}"


def ed25519_key_id(public_bytes: bytes) -> str:
    return key_id_of("ed25519", public_bytes)


def algorithm_of(key_id: str) -> str:
    """``ed25519`` / ``hash-token`` / ``hmac`` / ``null`` / ``""`` for an unrecognised id."""
    if is_null_key(key_id):
        return "null"
    if _HMAC_KEY_ID.match(key_id):
        return "hmac"
    match = _KEY_ID_RE.match(key_id)
    return match.group(1) if match else ""


def _need_cryptography() -> None:
    select_backend()


def _ed25519_verify_bytes(public_bytes: bytes, data: bytes, signature: str, backend: SigningBackend | None = None) -> bool:
    backend = backend or select_backend()
    if not signature.startswith("ed25519:"):
        return False
    try:
        raw = bytes.fromhex(signature[len("ed25519:"):])
    except ValueError:
        return False
    return backend.verify(public_bytes, data, raw)


class Ed25519Signer:
    """Public-key signatures via the first importable backend; declared always, usable when one imports.
    The default signer of the grid: ``signing.default = ed25519``."""

    name = "ed25519"
    algorithm = "ed25519"

    def __init__(self, private_bytes: bytes, *, backend: str | SigningBackend = "") -> None:
        self.backend: SigningBackend = backend if not isinstance(backend, str) else select_backend(backend)
        if len(private_bytes) != 32:
            raise KeyMaterialError("ed25519 private key must be 32 raw bytes")
        self._private = bytes(private_bytes)
        self.public_bytes = self.backend.public_of(self._private)
        self.key_id = ed25519_key_id(self.public_bytes)

    def sign(self, data: bytes) -> str:
        return "ed25519:" + self.backend.sign(self._private, data).hex()

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        """Only this node's own key; foreign keys need a ``Keyring``."""
        return key_id == self.key_id and _ed25519_verify_bytes(self.public_bytes, data, signature, self.backend)

    @classmethod
    def generate(cls, key_dir: str | os.PathLike[str], *, backend: str = "") -> Ed25519Signer:
        """Create a fresh key pair under ``key_dir``; refuses to overwrite an existing one."""
        chosen = select_backend(backend)
        directory = Path(key_dir)
        directory.mkdir(parents=True, exist_ok=True)
        private_path = directory / _PRIVATE_FILE
        if private_path.exists():
            raise KeyMaterialError(f"{private_path} already exists; load it or choose another key_dir")
        raw, _public = chosen.generate()
        fd = os.open(str(private_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        signer = cls(raw, backend=chosen)
        (directory / _PUBLIC_FILE).write_bytes(signer.public_bytes)
        (directory / _KEY_ID_FILE).write_text(signer.key_id + "\n", encoding="utf-8")
        return signer

    @classmethod
    def load(cls, key_dir: str | os.PathLike[str], *, backend: str = "") -> Ed25519Signer:
        private_path = Path(key_dir) / _PRIVATE_FILE
        if not private_path.is_file():
            raise KeyMaterialMissing(f"{private_path} does not exist; run Ed25519Signer.generate(key_dir) once")
        return cls(private_path.read_bytes(), backend=backend)

    @classmethod
    def load_or_generate(cls, key_dir: str | os.PathLike[str], *, backend: str = "") -> Ed25519Signer:
        if (Path(key_dir) / _PRIVATE_FILE).is_file():
            return cls.load(key_dir, backend=backend)
        return cls.generate(key_dir, backend=backend)

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "adapter": {"const": "ed25519"},
            "key_dir": {"type": "string", "description": "directory holding ed25519.key / ed25519.pub / key_id"},
            "generate": {"type": "boolean", "default": True, "description": "create the pair when key_dir is empty"},
            "backend": {"type": "string", "default": "", "description": "cryptography | pynacl; empty = first importable"},
        }, "required": ["key_dir"]}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "working" if have_backend() else "declared", "default": True,
                "requires": ["one of the signing backends: " + ", ".join(BACKEND_ORDER), "signing.key_dir"], "config_schema": cls.config_schema(),
                "backends": {n: b.describe() for n, b in SIGNING_BACKENDS.items()},
                "semantics": "Ed25519 over the canonical unsigned bytes; key_id = ed25519:<sha256(public key)>"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> Ed25519Signer:
        if not config.get("key_dir"):
            raise KeyMaterialMissing("ed25519 signer config needs key_dir")
        backend = str(config.get("backend", "") or "")
        if config.get("generate", True):
            return cls.load_or_generate(str(config["key_dir"]), backend=backend)
        return cls.load(str(config["key_dir"]), backend=backend)


# --------------------------------------------------------------------------- hash-token (local only)
_HASH_TOKEN_DOMAIN = b"adgrid/hash-token/v1/"


class HashTokenSigner:
    """Always working, verifies only where the secret is: the single-host harness signer.
    ``key_id = hash-token:<sha256 of the commitment>``; a keyring accepts it only when the secret
    was added explicitly (``Keyring.add_hash_token_secret``)."""

    name = "hash-token"
    algorithm = "hash-token"

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 16:
            raise KeyMaterialError("hash-token secret must be at least 16 bytes")
        self._secret = bytes(secret)
        self.public_bytes = hash_token_public(self._secret)
        self.key_id = key_id_of("hash-token", self.public_bytes)

    @property
    def secret(self) -> bytes:
        return self._secret

    def sign(self, data: bytes) -> str:
        return "hash-token:" + hash_token_sign(self._secret, data).hex()

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        return key_id == self.key_id and hash_token_verify(self._secret, data, signature)

    @classmethod
    def generate(cls) -> HashTokenSigner:
        return cls(os.urandom(32))

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "working", "requires": [], "semantics": "HMAC-SHA256 under a per-node secret; verifies only where the secret is (harness / single host)"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> HashTokenSigner:
        raise NotConfigured("hash-token is a node key algorithm (worker.key_algorithm), not an operator signer; use signing.adapter=ed25519 or null")


def hash_token_public(secret: bytes) -> bytes:
    return hashlib.sha256(_HASH_TOKEN_DOMAIN + b"public" + secret).digest()


def hash_token_sign(secret: bytes, data: bytes) -> bytes:
    return hmac.new(secret, _HASH_TOKEN_DOMAIN + data, hashlib.sha256).digest()


def hash_token_verify(secret: bytes, data: bytes, signature: str) -> bool:
    if not signature.startswith("hash-token:"):
        return False
    try:
        raw = bytes.fromhex(signature[len("hash-token:"):])
    except ValueError:
        return False
    return hmac.compare_digest(hash_token_sign(secret, data), raw)


# --------------------------------------------------------------------------- declared slots
class HsmSigner:
    """Slot: a PKCS#11 / cloud KMS ed25519 key that never leaves the module."""

    name = "hsm"
    algorithm = "ed25519"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotConfigured("HsmSigner is declared, not implemented: it needs a PKCS#11 module path and a key label (signing.hsm.*)")

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "declared", "requires": ["a PKCS#11 module", "signing.hsm.module", "signing.hsm.label"]}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> HsmSigner:
        return cls()


class SshAgentSigner:
    """Slot: sign through a running ssh-agent holding an ed25519 key (``SSH_AUTH_SOCK``)."""

    name = "ssh-agent"
    algorithm = "ed25519"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotConfigured("SshAgentSigner is declared, not implemented: it needs SSH_AUTH_SOCK and the agent protocol client (signing.ssh_agent.*)")

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "declared", "requires": ["SSH_AUTH_SOCK", "an ed25519 key loaded in the agent"]}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> SshAgentSigner:
        return cls()


# --------------------------------------------------------------------------- keyring
OPERATOR_ROLE = "operator"
OPERATOR_ONLY_TYPES: frozenset[RecordType] = frozenset({RecordType.TASK, RecordType.CHECKPOINT})
"""Record types only an operator key may sign: a TASK decides what every worker runs, and a
CHECKPOINT summary is folded by readers in place of the records it covers."""

NODE_KEY_ROLE = "node"
"""Role of a trusted node key whose trust file names no role.  Not an operator."""


def _node_algorithms() -> tuple[Any, Any]:
    """``worker.identity``'s key-algorithm registry and ``key_id_for``, imported on use (the worker
    package imports the log package; the reverse import at module load would be a cycle)."""
    from agentdecompile_grid.worker.identity import KEY_ALGORITHMS, key_id_for

    return KEY_ALGORITHMS, key_id_for


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode((text + "=" * (-len(text) % 4)).encode("ascii"))


class Keyring:
    """Public material for many key ids; the ``verifier`` for ``records.verify_chain``.

    Holds ed25519/node/hash-token material, HMAC secrets, trust metadata, and revocations. Trusted
    ``*.pub`` keys and HMAC keys are operator keys; null is operator-only when explicitly enabled;
    node roles come from trusted local identity or invite metadata, never an unverified claim.
    """

    def __init__(self, *, allow_null: bool = False, revocations: Any = None) -> None:
        self.allow_null = allow_null
        self._ed25519: dict[str, bytes] = {}
        self._hash_token: dict[str, bytes] = {}
        self._hmac_secrets: list[bytes] = []
        self._node: dict[str, tuple[str, bytes]] = {}
        self._roles: dict[str, str] = {}
        self._lineage: dict[str, tuple[str, ...]] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._backend: SigningBackend | None = None
        self.revocations = revocations
        self.sources_loaded: list[dict[str, Any]] = []

    @classmethod
    def from_locator(cls, locator: Mapping[str, Any]) -> Keyring:
        """``GridConfig.keyring_locator()`` -> a keyring.  A missing ``key_dir`` is an empty keyring,
        not an error; ``trust_local_nodes`` also trusts every node key under ``nodes_dir``."""
        return cls.from_config(locator)

    # -- population
    def _set_meta(self, key_id: str, role: str, lineage: Iterable[str]) -> None:
        lineage = tuple(str(k) for k in lineage)
        self._roles[key_id] = str(role)
        self._lineage[key_id] = lineage
        self.note(key_id, role=str(role), lineage=list(lineage))

    def add_ed25519_public(self, public_bytes: bytes, *, role: str = OPERATOR_ROLE, **meta: Any) -> str:
        if len(public_bytes) != 32:
            raise KeyMaterialError("ed25519 public key must be 32 raw bytes")
        key_id = ed25519_key_id(public_bytes)
        self._ed25519[key_id] = bytes(public_bytes)
        self._roles[key_id] = role
        if role:
            meta.setdefault("role", role)
        if meta:
            self.note(key_id, **meta)
        return key_id

    def add_hash_token_secret(self, secret: bytes, **meta: Any) -> str:
        """Local-only: a hash-token key verifies only where its secret is."""
        signer = HashTokenSigner(secret)
        self._hash_token[signer.key_id] = signer.secret
        if meta:
            self.note(signer.key_id, **meta)
        return signer.key_id

    def add(self, key_id: str, algorithm: str, material: bytes, **meta: Any) -> str:
        """``worker.identity`` spelling: (key id, algorithm, material) where material is the public
        key for ed25519 and the secret for hash-token; the id must hash from the material."""
        if algorithm == "ed25519":
            computed = self.add_ed25519_public(material, **meta)
        elif algorithm == "hash-token":
            computed = self.add_hash_token_secret(material, **meta)
        else:
            raise KeyMaterialError(f"keyring cannot hold algorithm {algorithm!r}; known: ed25519, hash-token")
        if computed != key_id:
            self._ed25519.pop(computed, None)
            self._hash_token.pop(computed, None)
            raise KeyMaterialError(f"key id {key_id!r} is not the id of the given {algorithm} material ({computed})")
        return computed

    def add_hmac_secret(self, secret: bytes) -> None:
        if len(secret) < 16:
            raise KeyMaterialError("HMAC secret must be at least 16 bytes")
        if bytes(secret) not in self._hmac_secrets:
            self._hmac_secrets.append(bytes(secret))

    def add_node_public(self, key_id: str, algorithm: str, public: bytes, *, role: str = NODE_KEY_ROLE,
                        lineage: Iterable[str] = ()) -> str:
        """Trust a node key by its public material; the key id must be its content address."""
        algorithms, key_id_for = _node_algorithms()
        if algorithm not in algorithms:
            raise KeyMaterialError(f"node key {key_id!r}: unknown key algorithm {algorithm!r}; known: {algorithms.names()}")
        if algorithm == "hash-token":
            raise KeyMaterialError(f"node key {key_id!r} is hash-token: its public part is a commitment that verifies "
                                   "nothing; trust it with add_node_key on the host that holds the secret")
        if key_id_for(algorithm, bytes(public)) != key_id:
            raise KeyMaterialError(f"node key id {key_id!r} is not the content address of its {algorithm} public material")
        self._node[key_id] = (algorithm, bytes(public))
        self._set_meta(key_id, role, lineage)
        return key_id

    def add_node_key(self, key: Any, *, role: str = NODE_KEY_ROLE, lineage: Iterable[str] = ()) -> str:
        """Trust a ``worker.identity.NodeKey`` held in this process (a hash-token key verifies with its secret)."""
        _, key_id_for = _node_algorithms()
        if key_id_for(key.algorithm, key.public) != key.key_id:
            raise KeyMaterialError(f"node key id {key.key_id!r} is not the content address of its public material")
        material = key.secret if key.algorithm == "hash-token" else key.public
        self._node[key.key_id] = (key.algorithm, bytes(material))
        self._set_meta(key.key_id, role, lineage)
        return key.key_id

    def add_node_record(self, record: Mapping[str, Any], *, source: str = "node key record") -> str:
        """Trust a node key from its public record (``NodeKey.public_record()``: ``key_id``,
        ``algorithm``, hex ``public``), plus the optional ``role`` and ``lineage`` the operator
        wrote into the trust file."""
        try:
            key_id, algorithm = str(record["key_id"]), str(record["algorithm"])
            public = bytes.fromhex(str(record["public"]))
            lineage = [str(k) for k in record.get("lineage", ())]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise KeyMaterialError(f"{source}: needs key_id, algorithm and a hex public key ({type(exc).__name__})") from exc
        try:
            return self.add_node_public(key_id, algorithm, public, role=str(record.get("role", NODE_KEY_ROLE)), lineage=lineage)
        except KeyMaterialError as exc:
            raise KeyMaterialError(f"{source}: {exc}") from exc

    def add_signer(self, signer: Signer, **meta: Any) -> str:
        """Trust a signer's *public* part; for HMAC that is the shared secret, for null the policy bit."""
        inner = getattr(signer, "inner", None)          # worker.identity.NodeSigner wraps one of ours
        if inner is not None and inner is not signer:
            return self.add_signer(inner, **meta)
        if isinstance(signer, Ed25519Signer):
            return self.add_ed25519_public(signer.public_bytes, **meta)
        if isinstance(signer, HashTokenSigner):
            return self.add_hash_token_secret(signer.secret, **meta)
        if isinstance(signer, HMACSigner):
            self.add_hmac_secret(signer.secret)
            return signer.key_id
        if isinstance(signer, NullSigner):
            self.allow_null = True
            return signer.key_id
        raise KeyMaterialError(f"cannot extract public material from signer {type(signer).__name__}")

    def load_dir(self, key_dir: str | os.PathLike[str], *, missing_ok: bool = False) -> list[str]:
        """Load every ``*.pub`` (raw ed25519 operator public key) and ``*.json`` (node key public
        record) under ``key_dir``; returns the key ids.  A bad file is refused naming its path."""
        directory = Path(key_dir)
        if not directory.is_dir():
            if missing_ok:
                return []
            raise KeyMaterialMissing(f"keyring directory {directory} does not exist")
        loaded = []
        for path in sorted(directory.glob("*.pub")):
            try:
                loaded.append(self.add_ed25519_public(path.read_bytes()))
            except KeyMaterialError as exc:
                raise KeyMaterialError(f"{path}: {exc}") from exc
        for path in sorted(directory.glob("*.json")):
            try:
                record = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError) as exc:
                raise KeyMaterialError(f"{path}: not a readable JSON node key record ({type(exc).__name__})") from exc
            if not isinstance(record, Mapping):
                raise KeyMaterialError(f"{path}: a node key record must be a JSON object")
            loaded.append(self.add_node_record(record, source=str(path)))
        return loaded

    def load_local_nodes(self, nodes_dir: str | os.PathLike[str]) -> list[str]:
        """Trust every node key under ``<nodes_dir>/<name>/keys`` (explicit opt-in for a one-host
        grid: ``keyring.trust_local_nodes``).  Hash-token keys are read with their secret."""
        loaded = []
        for public_path in sorted(Path(nodes_dir).glob("*/keys/node.json")):
            try:
                record = json.loads(public_path.read_text("utf-8"))
                if record.get("algorithm") == "hash-token":
                    secret = bytes.fromhex((public_path.parent / "node.secret").read_text("utf-8").strip())
                    key = _LocalNodeKey(str(record["key_id"]), "hash-token", bytes.fromhex(str(record["public"])), secret)
                    loaded.append(self.add_node_key(key))
                else:
                    loaded.append(self.add_node_record(record, source=str(public_path)))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise KeyMaterialError(f"{public_path}: unreadable node key ({type(exc).__name__})") from exc
        return loaded

    def load_sources(self, sources: Iterable[Any]) -> list[dict[str, Any]]:
        """Run every ``log.keys.KeySource`` (``load_into(keyring)``); the per-source reports are kept."""
        for source in sources:
            report = {"source": getattr(source, "name", type(source).__name__), "loaded": list(source.load_into(self))}
            self.sources_loaded.append(report)
        return self.sources_loaded

    def note(self, key_id: str, **meta: Any) -> None:
        """Record what a source said about a key (role, lineage, expires_at, supersedes, announced_seq)."""
        entry = self._meta.setdefault(key_id, {})
        for k, v in meta.items():
            if v is None:
                continue
            if k == "supersedes":
                entry.setdefault("supersedes", [])
                for old in v:
                    if old not in entry["supersedes"]:
                        entry["supersedes"].append(old)
                    self._meta.setdefault(old, {})["superseded_by"] = key_id
            else:
                entry[k] = v
        if "role" in meta and meta["role"] is not None:
            self._roles[key_id] = str(meta["role"])
        if "lineage" in meta and meta["lineage"] is not None:
            self._lineage[key_id] = tuple(str(key) for key in meta["lineage"])

    def forget(self, key_id: str) -> None:
        """Drop a key and everything noted about it (a source that failed to verify it)."""
        self._ed25519.pop(key_id, None)
        self._hash_token.pop(key_id, None)
        self._node.pop(key_id, None)
        self._roles.pop(key_id, None)
        self._lineage.pop(key_id, None)
        self._meta.pop(key_id, None)

    # -- queries
    def _hmac_knows(self, key_id: str) -> bool:
        match = _HMAC_KEY_ID.match(key_id)
        if not match:
            return False
        label = match.group(1)
        return any(_hmac_key_id(_hmac_derive(s, label), label) == key_id for s in self._hmac_secrets)

    def meta(self, key_id: str) -> Mapping[str, Any]:
        result = dict(self._meta.get(key_id, {}))
        if key_id in self._roles:
            result.setdefault("role", self._roles[key_id])
        if key_id in self._lineage:
            result.setdefault("lineage", list(self._lineage[key_id]))
        return result

    def role_of(self, key_id: str) -> str | None:
        """The *attested* role (invite / local identity dir); a self-announced ``claimed_role`` never counts."""
        if is_null_key(key_id):
            return OPERATOR_ROLE if self.allow_null else None
        role = self._meta.get(key_id, {}).get("role", self._roles.get(key_id))
        if role:
            return str(role)
        if key_id in self._node:
            return NODE_KEY_ROLE
        if self._hmac_knows(key_id):
            return OPERATOR_ROLE
        return None

    def lineage_of(self, key_id: str) -> tuple[str, ...] | None:
        lineage = self._meta.get(key_id, {}).get("lineage", self._lineage.get(key_id))
        return tuple(str(key) for key in lineage) if lineage is not None else None

    def superseded_by(self, key_id: str) -> str:
        return str(self._meta.get(key_id, {}).get("superseded_by", ""))

    def is_revoked(self, key_id: str) -> bool:
        return bool(self.revocations is not None and self.revocations.is_revoked(key_id))

    def knows(self, key_id: str) -> bool:
        if is_null_key(key_id):
            return self.allow_null
        if key_id in self._ed25519 or key_id in self._node or key_id in self._hash_token:
            return True
        return self._hmac_knows(key_id)

    def __contains__(self, key_id: object) -> bool:
        return isinstance(key_id, str) and self.knows(key_id)

    def get(self, key_id: str) -> tuple[str, bytes] | None:
        """``(algorithm, material)`` for locally held ed25519/hash-token key material."""
        if key_id in self._ed25519:
            return "ed25519", self._ed25519[key_id]
        if key_id in self._hash_token:
            return "hash-token", self._hash_token[key_id]
        node = self._node.get(key_id)
        return node

    def public_of(self, key_id: str) -> bytes | None:
        if key_id in self._ed25519:
            return self._ed25519[key_id]
        node = self._node.get(key_id)
        return node[1] if node is not None and node[0] == "ed25519" else None

    def independent(self, producer_key: str, verifier_key: str) -> bool:
        """Whether two trusted keys have disjoint recorded invite ancestry.

        Missing lineage metadata means an explicitly trusted self-rooted key, not permission to
        trust an unknown key: both keys must already be present in this keyring.  This is the same
        disjoint-lineage rule used by ``worker.identity.independent`` without importing the worker
        package at module load time.
        """
        if producer_key == verifier_key or not self.knows(producer_key) or not self.knows(verifier_key):
            return False
        producer_lineage = frozenset((producer_key, *(self.lineage_of(producer_key) or ())))
        verifier_lineage = frozenset((verifier_key, *(self.lineage_of(verifier_key) or ())))
        return producer_lineage.isdisjoint(verifier_lineage)

    def key_ids(self) -> list[str]:
        return sorted(set(self._ed25519) | set(self._node) | set(self._hash_token))

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        if is_null_key(key_id):
            return self.allow_null and NullSigner().verify(key_id, data, signature)
        public = self._ed25519.get(key_id)
        if public is not None:
            if self._backend is None:
                self._backend = select_backend()
            return _ed25519_verify_bytes(public, data, signature, self._backend)
        node = self._node.get(key_id)
        if node is not None:
            algorithm_name, material = node
            if algorithm_name == "hash-token":
                return hash_token_verify(material, data, signature)
            if algorithm_name == "ed25519":
                if self._backend is None:
                    self._backend = select_backend()
                return _ed25519_verify_bytes(material, data, signature, self._backend)
            algorithms, _ = _node_algorithms()
            try:
                raw = _b64url_decode(signature)
            except (ValueError, UnicodeEncodeError):
                return False
            return bool(algorithms.get(algorithm_name).verify(material, data, raw))
        secret = self._hash_token.get(key_id)
        if secret is not None:
            return hash_token_verify(secret, data, signature)
        return any(_hmac_verify_with(s, key_id, data, signature) for s in self._hmac_secrets)

    def describe(self) -> dict[str, Any]:
        return {"allow_null": self.allow_null, "keys": {k: self.meta(k) for k in self.key_ids()},
                "revoked": list(self.revocations.key_ids()) if self.revocations is not None else [], "sources": list(self.sources_loaded)}

    @classmethod
    def from_config(cls, config: Mapping[str, Any], *, log: Any = None, objects: Any = None) -> Keyring:
        """``GridConfig.keyring_locator()`` -> a keyring filled from the configured ``KEY_SOURCES``
        (``log.keys.sources_from_config``); a source that cannot run here is recorded, not fatal."""
        from agentdecompile_grid.log.keys import RevocationList, sources_from_config

        ring = cls(allow_null=bool(config.get("allow_null", False)),
                   revocations=RevocationList.load(objects) if objects is not None else RevocationList())
        source_config = dict(config)
        if not bool(config.get("trust_local_nodes", False)):
            source_config["nodes_dir"] = ""
        ring.load_sources(sources_from_config(source_config, log=log, objects=objects))
        return ring


class _LocalNodeKey:
    """The four ``NodeKey`` fields ``Keyring.add_node_key`` reads, for keys loaded from disk."""

    def __init__(self, key_id: str, algorithm: str, public: bytes, secret: bytes) -> None:
        self.key_id, self.algorithm, self.public, self.secret = key_id, algorithm, public, secret


def verify_record(record: Record, keyring: Keyring) -> None:
    """Raise ``UnknownSigner``, ``RevokedSigner`` or ``BadSignature`` by name; return None when the record verifies."""
    if keyring.is_revoked(record.signer_key):
        raise RevokedSigner(f"record {record.partition!r}#{record.seq}: signer {record.signer_key!r} is revoked")
    if not keyring.knows(record.signer_key):
        raise UnknownSigner(f"record {record.partition!r}#{record.seq}: keyring has no key {record.signer_key!r}")
    if not keyring.verify(record.signer_key, unsigned_bytes(record), record.signature):
        raise BadSignature(f"record {record.partition!r}#{record.seq}: signature does not verify under {record.signer_key!r}")


def authorize_record(record: Record, keyring: Keyring) -> None:
    """``verify_record`` plus the role rule every reader applies before it trusts a record: a TASK
    or CHECKPOINT must be signed by an operator key.  Raises ``SignerNotAuthorized`` by name."""
    verify_record(record, keyring)
    if record.type in OPERATOR_ONLY_TYPES:
        role = keyring.role_of(record.signer_key)
        if role != OPERATOR_ROLE:
            raise SignerNotAuthorized(f"record {record.partition!r}#{record.seq}: a {record.type.value} record must be "
                                      f"signed by an operator key; {record.signer_key!r} has role {role!r}")


REFUSAL_REASONS: Mapping[type, str] = {
    UnknownSigner: "unknown-signer", RevokedSigner: "revoked-signer", BadSignature: "bad-signature",
    SignerNotAuthorized: "signer-not-authorized",
}


def refusal_reason(record: Record, keyring: Keyring | None) -> str | None:
    """``None`` when ``authorize_record`` accepts the record, else the refusal's short name
    (``unknown-signer`` / ``bad-signature`` / ``signer-not-authorized``).  ``keyring=None`` is an
    empty keyring: every record is refused (fail closed)."""
    try:
        authorize_record(record, keyring if keyring is not None else Keyring())
    except (UnknownSigner, RevokedSigner, BadSignature, SignerNotAuthorized) as exc:
        return REFUSAL_REASONS[type(exc)]
    return None


# --------------------------------------------------------------------------- config
DEFAULT_SIGNER = "ed25519"


def signer_from_config(config: Mapping[str, Any], *, environ: Mapping[str, str] | None = None) -> Signer:
    """``{"adapter": "ed25519"|"null"|"hmac"|..., ...}`` -> a signer; the adapter name resolves via ``SIGNERS``.

    An empty adapter means the default (``signing.default``, ``ed25519``): when no backend imports
    that is ``NotConfigured`` naming the packages and the explicit fallback ``signing.adapter=null``
    — never a silent downgrade to an unsigned grid.
    """
    adapter = str(config.get("adapter", "") or config.get("default", "") or DEFAULT_SIGNER)
    cls = SIGNERS.get(adapter)
    if cls is HMACSigner:
        return HMACSigner.from_config(config, environ=environ)
    return cls.from_config(config)


def register_signers(registry: Registry = SIGNERS) -> None:
    for cls in (Ed25519Signer, NullSigner, HMACSigner, HashTokenSigner, HsmSigner, SshAgentSigner):
        registry.register(cls.name, cls, replace=True)


def describe_signers() -> dict[str, Any]:
    return {name: cls.describe() for name, cls in SIGNERS.items()}


register_signers()


__all__ = [
    "Ed25519Signer", "HAVE_CRYPTOGRAPHY", "HMACSigner", "HashTokenSigner", "HsmSigner",
    "KeyMaterialError", "KeyMaterialMissing", "Keyring", "NODE_KEY_ROLE", "NullSigner",
    "OPERATOR_ONLY_TYPES", "OPERATOR_ROLE", "PyNaclBackend", "REFUSAL_REASONS", "RevokedSigner",
    "SIGNER_REGISTRY", "SIGNING_BACKENDS", "BACKEND_ORDER", "CryptographyBackend", "DEFAULT_SIGNER",
    "SigningBackend", "SignerNotAuthorized", "SignerRegistry", "SshAgentSigner", "UnknownSigner",
    "algorithm_of", "authorize_record", "describe_signers", "ed25519_key_id", "hash_token_public",
    "hash_token_sign", "hash_token_verify", "have_backend", "is_null_key", "key_id_of",
    "refusal_reason", "register_signers", "select_backend", "signer_from_config", "verify_record",
]
