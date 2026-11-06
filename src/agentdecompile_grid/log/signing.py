"""Signers and keyrings: key ids are the node identity everywhere.

Three ``core.Signer`` implementations, all registered in ``core.SIGNERS``:

* ``NullSigner`` — hash-chain only.  ``sign`` returns ``null:<sha256 of the bytes>`` so a record is
  still tamper-evident (integrity), but nothing proves *who* wrote it (no authorship).  ``key_id``
  is ``null`` or ``null:<label>`` so a laptop grid can still tell its nodes apart.  A keyring only
  accepts null signatures when built with ``allow_null=True``.
* ``HMACSigner`` — shared secret for a single-operator grid.  Every node derives a per-label key
  from the one secret; ``key_id`` is ``hmac:<label>:<id>`` where ``id`` is an HMAC of a fixed tag
  under the derived key (never a bare hash of the secret, which would be an offline oracle).
  Anyone holding the secret can sign for any label: that is the stated trust model.
* ``Ed25519Signer`` — real public-key signatures through ``cryptography`` **if importable**.  Keys
  live in a directory (``ed25519.key`` raw 32-byte private, mode 0600; ``ed25519.pub`` raw public;
  ``key_id`` text); ``key_id`` is ``ed25519:<sha256 of the raw public key>``.  The class is always
  declared and registered; construction raises ``NotConfigured`` naming the missing package.

``Keyring`` holds public material for many key ids and is the ``verifier`` that ``records.verify_chain``
takes.  ``verify_record(record, keyring)`` raises ``UnknownSigner`` or ``BadSignature`` by name.
``authorize_record`` adds the role rule (a TASK or CHECKPOINT needs an operator key) and is what
every reader calls before it folds, indexes or applies a record; ``refusal_reason`` is its
non-raising form for readers that skip and report.  The trust root is the keyring a reader builds
from ``GridConfig.keyring_locator()``: nothing in a record body or an invite token adds a key.

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
from typing import Any
from collections.abc import Iterable, Iterator, Mapping

from agentdecompile_grid.core import SIGNERS, GridError, NotConfigured, Record, RecordType, Registry, Signer, digest
from agentdecompile_grid.log.records import BadSignature, SignerNotAuthorized, UnknownSigner, unsigned_bytes

try:
    from cryptography.exceptions import InvalidSignature as _InvalidSignature
    from cryptography.hazmat.primitives import serialization as _serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as _Ed25519PrivateKey
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey as _Ed25519PublicKey

    HAVE_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover - depends on the environment
    HAVE_CRYPTOGRAPHY = False

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


def ed25519_key_id(public_bytes: bytes) -> str:
    return f"ed25519:{hashlib.sha256(public_bytes).hexdigest()}"


def _need_cryptography() -> None:
    if not HAVE_CRYPTOGRAPHY:
        raise NotConfigured("Ed25519Signer needs the 'cryptography' package (pip install cryptography); "
                            "use signing.adapter=hmac or null until it is installed")


def _ed25519_verify_bytes(public_bytes: bytes, data: bytes, signature: str) -> bool:
    _need_cryptography()
    if not signature.startswith("ed25519:"):
        return False
    try:
        raw = bytes.fromhex(signature[len("ed25519:"):])
        _Ed25519PublicKey.from_public_bytes(public_bytes).verify(raw, data)
        return True
    except (ValueError, _InvalidSignature):
        return False


class Ed25519Signer:
    """Public-key signatures via ``cryptography``; declared always, usable when the package imports."""

    name = "ed25519"

    def __init__(self, private_bytes: bytes) -> None:
        _need_cryptography()
        if len(private_bytes) != 32:
            raise KeyMaterialError("ed25519 private key must be 32 raw bytes")
        self._private = _Ed25519PrivateKey.from_private_bytes(private_bytes)
        self.public_bytes = self._private.public_key().public_bytes(
            encoding=_serialization.Encoding.Raw, format=_serialization.PublicFormat.Raw)
        self.key_id = ed25519_key_id(self.public_bytes)

    def sign(self, data: bytes) -> str:
        return "ed25519:" + self._private.sign(data).hex()

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        """Only this node's own key; foreign keys need a ``Keyring``."""
        return key_id == self.key_id and _ed25519_verify_bytes(self.public_bytes, data, signature)

    @classmethod
    def generate(cls, key_dir: str | os.PathLike[str]) -> Ed25519Signer:
        """Create a fresh key pair under ``key_dir``; refuses to overwrite an existing one."""
        _need_cryptography()
        directory = Path(key_dir)
        directory.mkdir(parents=True, exist_ok=True)
        private_path = directory / _PRIVATE_FILE
        if private_path.exists():
            raise KeyMaterialError(f"{private_path} already exists; load it or choose another key_dir")
        private = _Ed25519PrivateKey.generate()
        raw = private.private_bytes(encoding=_serialization.Encoding.Raw, format=_serialization.PrivateFormat.Raw,
                                    encryption_algorithm=_serialization.NoEncryption())
        fd = os.open(str(private_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        signer = cls(raw)
        (directory / _PUBLIC_FILE).write_bytes(signer.public_bytes)
        (directory / _KEY_ID_FILE).write_text(signer.key_id + "\n", encoding="utf-8")
        return signer

    @classmethod
    def load(cls, key_dir: str | os.PathLike[str]) -> Ed25519Signer:
        _need_cryptography()
        private_path = Path(key_dir) / _PRIVATE_FILE
        if not private_path.is_file():
            raise KeyMaterialMissing(f"{private_path} does not exist; run Ed25519Signer.generate(key_dir) once")
        return cls(private_path.read_bytes())

    @classmethod
    def load_or_generate(cls, key_dir: str | os.PathLike[str]) -> Ed25519Signer:
        if (Path(key_dir) / _PRIVATE_FILE).is_file():
            return cls.load(key_dir)
        return cls.generate(key_dir)

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "adapter": {"const": "ed25519"},
            "key_dir": {"type": "string", "description": "directory holding ed25519.key / ed25519.pub / key_id"},
            "generate": {"type": "boolean", "default": True, "description": "create the pair when key_dir is empty"},
        }, "required": ["key_dir"]}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "working" if HAVE_CRYPTOGRAPHY else "declared",
                "requires": ["python package 'cryptography'", "signing.key_dir"], "config_schema": cls.config_schema(),
                "semantics": "Ed25519 over the canonical unsigned bytes; key_id = ed25519:<sha256(public key)>"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> Ed25519Signer:
        if not config.get("key_dir"):
            raise KeyMaterialMissing("ed25519 signer config needs key_dir")
        if config.get("generate", True):
            return cls.load_or_generate(str(config["key_dir"]))
        return cls.load(str(config["key_dir"]))


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

    Holds raw ed25519 public keys by key id (operator signers, ``Ed25519Signer`` format), node
    keys (``worker.identity.NodeKey`` format: 32-hex key id, base64url signatures), any number of
    HMAC secrets (a key id is accepted when one of them derives it) and a policy bit for null
    signatures.  Each trusted key has a role: ``*.pub`` keys and HMAC keys are operator keys, a
    null key is an operator key only while ``allow_null`` is on, and a node key has the role its
    trust file names (``node`` when it names none).  ``authorize_record`` uses the role.
    """

    def __init__(self, *, allow_null: bool = False) -> None:
        self.allow_null = allow_null
        self._ed25519: dict[str, bytes] = {}
        self._hmac_secrets: list[bytes] = []
        self._node: dict[str, tuple[str, bytes]] = {}
        self._roles: dict[str, str] = {}
        self._lineage: dict[str, tuple[str, ...]] = {}

    @classmethod
    def from_locator(cls, locator: Mapping[str, Any]) -> Keyring:
        """``GridConfig.keyring_locator()`` -> a keyring.  A missing ``key_dir`` is an empty keyring,
        not an error; ``trust_local_nodes`` also trusts every node key under ``nodes_dir``."""
        ring = cls(allow_null=bool(locator.get("allow_null", False)))
        if locator.get("key_dir"):
            ring.load_dir(str(locator["key_dir"]), missing_ok=True)
        if locator.get("trust_local_nodes") and locator.get("nodes_dir"):
            ring.load_local_nodes(str(locator["nodes_dir"]))
        return ring

    # -- population
    def _set_meta(self, key_id: str, role: str, lineage: Iterable[str]) -> None:
        self._roles[key_id] = str(role)
        self._lineage[key_id] = tuple(str(k) for k in lineage)

    def add_ed25519_public(self, public_bytes: bytes, *, role: str = OPERATOR_ROLE) -> str:
        if len(public_bytes) != 32:
            raise KeyMaterialError("ed25519 public key must be 32 raw bytes")
        key_id = ed25519_key_id(public_bytes)
        self._ed25519[key_id] = bytes(public_bytes)
        self._roles[key_id] = role
        return key_id

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

    def add_signer(self, signer: Signer) -> str:
        """Trust a signer's *public* part; for HMAC that is the shared secret, for null the policy bit."""
        if isinstance(signer, Ed25519Signer):
            return self.add_ed25519_public(signer.public_bytes)
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

    # -- queries
    def _hmac_knows(self, key_id: str) -> bool:
        match = _HMAC_KEY_ID.match(key_id)
        if not match:
            return False
        label = match.group(1)
        return any(_hmac_key_id(_hmac_derive(s, label), label) == key_id for s in self._hmac_secrets)

    def knows(self, key_id: str) -> bool:
        if is_null_key(key_id):
            return self.allow_null
        return key_id in self._ed25519 or key_id in self._node or self._hmac_knows(key_id)

    def role_of(self, key_id: str) -> str | None:
        """The trusted role of ``key_id``, or ``None`` when the keyring does not know it."""
        if is_null_key(key_id):
            return OPERATOR_ROLE if self.allow_null else None
        if key_id in self._ed25519 or key_id in self._node:
            return self._roles.get(key_id, NODE_KEY_ROLE)
        return OPERATOR_ROLE if self._hmac_knows(key_id) else None

    def lineage_of(self, key_id: str) -> tuple[str, ...] | None:
        """Invite lineage the operator recorded for a node key; ``None`` when none was recorded."""
        return self._lineage.get(key_id) if key_id in self._node else None

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

    def key_ids(self) -> Iterator[str]:
        return iter(sorted(set(self._ed25519) | set(self._node)))

    def verify(self, key_id: str, data: bytes, signature: str) -> bool:
        if is_null_key(key_id):
            return self.allow_null and NullSigner().verify(key_id, data, signature)
        public = self._ed25519.get(key_id)
        if public is not None:
            return _ed25519_verify_bytes(public, data, signature)
        node = self._node.get(key_id)
        if node is not None:
            algorithm_name, material = node
            algorithms, _ = _node_algorithms()
            try:
                raw = _b64url_decode(signature)
            except (ValueError, UnicodeEncodeError):
                return False
            return bool(algorithms.get(algorithm_name).verify(material, data, raw))
        return any(_hmac_verify_with(s, key_id, data, signature) for s in self._hmac_secrets)


class _LocalNodeKey:
    """The four ``NodeKey`` fields ``Keyring.add_node_key`` reads, for keys loaded from disk."""

    def __init__(self, key_id: str, algorithm: str, public: bytes, secret: bytes) -> None:
        self.key_id, self.algorithm, self.public, self.secret = key_id, algorithm, public, secret


def verify_record(record: Record, keyring: Keyring) -> None:
    """Raise ``UnknownSigner`` or ``BadSignature`` by name; return None when the record verifies."""
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
    UnknownSigner: "unknown-signer", BadSignature: "bad-signature", SignerNotAuthorized: "signer-not-authorized",
}


def refusal_reason(record: Record, keyring: Keyring | None) -> str | None:
    """``None`` when ``authorize_record`` accepts the record, else the refusal's short name
    (``unknown-signer`` / ``bad-signature`` / ``signer-not-authorized``).  ``keyring=None`` is an
    empty keyring: every record is refused (fail closed)."""
    try:
        authorize_record(record, keyring if keyring is not None else Keyring())
    except (UnknownSigner, BadSignature, SignerNotAuthorized) as exc:
        return REFUSAL_REASONS[type(exc)]
    return None


# --------------------------------------------------------------------------- config
def signer_from_config(config: Mapping[str, Any], *, environ: Mapping[str, str] | None = None) -> Signer:
    """``{"adapter": "null"|"hmac"|"ed25519", ...}`` -> a signer; the adapter name resolves via ``SIGNERS``."""
    adapter = str(config.get("adapter", "null"))
    cls = SIGNERS.get(adapter)
    if cls is HMACSigner:
        return HMACSigner.from_config(config, environ=environ)
    return cls.from_config(config)


def register_signers(registry: Registry = SIGNERS) -> None:
    for cls in (NullSigner, HMACSigner, Ed25519Signer):
        registry.register(cls.name, cls, replace=True)


__all__ = [
    "Ed25519Signer", "HAVE_CRYPTOGRAPHY", "HMACSigner", "KeyMaterialError", "KeyMaterialMissing", "Keyring",
    "NODE_KEY_ROLE", "NullSigner", "OPERATOR_ONLY_TYPES", "OPERATOR_ROLE", "REFUSAL_REASONS", "SIGNER_REGISTRY",
    "SignerRegistry", "authorize_record", "ed25519_key_id", "is_null_key", "refusal_reason", "register_signers",
    "signer_from_config", "verify_record",
]
