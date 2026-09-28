"""agentdecompile_grid.objects.peer — ``PeerHTTPStore``: outbound-only HTTP to another node's read endpoint.

Declared adapter.  Reads are implemented with ``urllib`` against the wire contract below; the
serving side (a node's read endpoint) is the transport/worker layer's to provide, so this class is
usable the moment a peer speaks the contract and ``objects.peer.base_url`` is set.  Writes are
refused by name unless ``allow_put`` is on *and* the peer accepts them.

Wire contract (all paths relative to ``base_url``; every request carries
``Authorization: Bearer <token>`` when the env var named by ``token_env`` is set)::

    GET  objects/<shard...>/<hex>   -> 200 bytes | 404
    HEAD objects/<shard...>/<hex>   -> 200 (Content-Length) | 404
    GET  objects/?prefix=<hex>      -> 200 JSON {"refs": ["sha256:<hex>", ...]} sorted
    GET  named/<name>               -> 200 bytes | 404
    GET  named/?prefix=<name>       -> 200 JSON {"names": ["...", ...]} sorted
    GET  layout.json                -> 200 JSON layout (optional)
    PUT  objects/<shard...>/<hex>   -> 201 created | 200 already present | 403 refused | 409 hash mismatch
    PUT  named/<name>               -> 204 | 403 refused

The node never listens for inbound peer connections itself here; this is the client side only.
Every read re-hashes (``verify_on_read``): a peer is a proposal source, never a trusted one.

Acceptance tests (named here, landed in the verification phase; a stub server speaking the
contract is enough):

* ``test_peer_reads_verify_and_list_uses_json_endpoint``.
* ``test_peer_put_refused_unless_allow_put`` — ``ReadOnly`` names ``objects.peer.allow_put`` and the token env.
* ``test_peer_token_never_in_describe`` — ``describe()`` shows the env var name, never its value.
"""
from __future__ import annotations

import json
import os
import urllib.error
from typing import Any, Iterator, Mapping

from ..core import NotConfigured, ObjectRef
from .base import (
    LAYOUT_FILE, NAMED_DIR, OBJECTS_DIR, BaseObjectStore, IntegrityError, Layout, ObjectMissing, ReadOnly,
    ref_prefix_hex, schema_from_dataclass, validate_name, validate_ref,
)
from .static import HttpReadMixin


class PeerHTTPStore(HttpReadMixin, BaseObjectStore):
    """Client for another node's read endpoint.  Outbound-only; token from the environment by name."""

    name = "peer"
    kind = "object-store"
    status = "declared"

    def __init__(self, base_url: str, *, token_env: str = "ADGRID_PEER_TOKEN", timeout_s: float = 30.0, retries: int = 2,
                 allow_put: bool = False, shard_width: int = 2, shard_depth: int = 1, verify_on_read: bool = True,
                 env: Mapping[str, str] | None = None) -> None:
        if not base_url:
            raise NotConfigured("PeerHTTPStore needs objects.peer.base_url (another node's read endpoint root)")
        self.base_url = base_url.rstrip("/")
        self.token_env = token_env
        self.timeout_s = float(timeout_s)
        self.retries = int(retries)
        self.allow_put = bool(allow_put)
        self.layout = Layout(shard_width=shard_width, shard_depth=shard_depth)
        self.verify_on_read = verify_on_read
        self._env = os.environ if env is None else env
        self._layout_checked = False

    @classmethod
    def from_config(cls, cfg: Any, env: Mapping[str, str] | None = None) -> "PeerHTTPStore":
        p = cfg.objects.peer
        return cls(p.base_url, token_env=p.token_env, timeout_s=p.timeout_s, allow_put=p.allow_put,
                   shard_width=cfg.objects.shard_width, shard_depth=cfg.objects.shard_depth,
                   verify_on_read=cfg.objects.verify_on_read, env=env)

    @property
    def headers(self) -> Mapping[str, str]:  # type: ignore[override]
        token = self._env.get(self.token_env, "") if self.token_env else ""
        return {"Authorization": f"Bearer {token}"} if token else {}

    def has_token(self) -> bool:
        return bool(self.token_env and self._env.get(self.token_env))

    def _check_layout_once(self) -> None:
        if self._layout_checked:
            return
        self._layout_checked = True
        status, body, _ = self._request(LAYOUT_FILE)
        if status == 200 and body:
            try:
                Layout.from_json(body).check(self.layout, f"peer {self.base_url}")
            except ValueError:
                pass

    # ---- reads -------------------------------------------------------------------------------
    def get(self, ref: ObjectRef) -> bytes:
        validate_ref(ref)
        self._check_layout_once()
        status, body, _ = self._request(self.layout.relpath(ref))
        if status != 200:
            raise ObjectMissing(f"{self.name}: no object {ref} at {self.base_url}")
        return self.check_integrity(ref, body)

    def exists(self, ref: ObjectRef) -> bool:
        validate_ref(ref)
        self._check_layout_once()
        status, _, _ = self._request(self.layout.relpath(ref), method="HEAD")
        if status == 405:
            status, _, _ = self._request(self.layout.relpath(ref))
        return status == 200

    def size(self, ref: ObjectRef) -> int:
        validate_ref(ref)
        self._check_layout_once()
        status, body, headers = self._request(self.layout.relpath(ref), method="HEAD")
        if status == 405:
            status, body, headers = self._request(self.layout.relpath(ref))
            if status == 200:
                return len(body)
        if status != 200:
            raise ObjectMissing(f"{self.name}: no object {ref} at {self.base_url}")
        length = headers.get("content-length")
        return int(length) if length is not None else len(self.get(ref))

    def list(self, prefix: str = "") -> Iterator[ObjectRef]:
        hexprefix = ref_prefix_hex(prefix)
        status, body, _ = self._request(f"{OBJECTS_DIR}/?prefix={hexprefix}")
        if status != 200:
            raise NotConfigured(f"peer {self.base_url} does not serve GET {OBJECTS_DIR}/?prefix= (status {status}); "
                                f"it must implement the read-endpoint listing contract")
        doc = json.loads(body.decode("utf-8"))
        refs = doc.get("refs", []) if isinstance(doc, dict) else doc
        yield from sorted(validate_ref(r) for r in refs if isinstance(r, str) and r.split(":", 1)[-1].startswith(hexprefix))

    def get_named(self, name: str) -> bytes | None:
        status, body, _ = self._request(f"{NAMED_DIR}/{validate_name(name)}")
        return body if status == 200 else None

    def list_named(self, prefix: str = "") -> Iterator[str]:
        status, body, _ = self._request(f"{NAMED_DIR}/?prefix={prefix}")
        if status != 200:
            raise NotConfigured(f"peer {self.base_url} does not serve GET {NAMED_DIR}/?prefix= (status {status})")
        doc = json.loads(body.decode("utf-8"))
        names = doc.get("names", []) if isinstance(doc, dict) else doc
        yield from sorted(n for n in names if isinstance(n, str) and n.startswith(prefix))

    def delete_named(self, name: str) -> bool:
        raise ReadOnly(f"{self.name} at {self.base_url}: named pointers are deleted on the owning node, not through a peer")

    # ---- writes ------------------------------------------------------------------------------
    def _refuse_write(self, what: str) -> ReadOnly:
        needs = []
        if not self.allow_put:
            needs.append("objects.peer.allow_put = true")
        if not self.has_token():
            needs.append(f"a bearer token in ${self.token_env}")
        return ReadOnly(f"{self.name} at {self.base_url} refuses {what}: needs {', '.join(needs) or 'the peer to accept PUT'}")

    def put(self, data: bytes, *, expect: ObjectRef | None = None) -> ObjectRef:
        data = bytes(data)
        ref = self.expected_ref(data, expect)
        if not self.allow_put or not self.has_token():
            raise self._refuse_write("put")
        try:
            status, _, _ = self._request(self.layout.relpath(ref), method="PUT", data=data,
                                         extra_headers={"Content-Type": "application/octet-stream"})
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise ReadOnly(f"peer {self.base_url} refused PUT of {ref} (403): the token is not allowed to write") from None
            if exc.code == 409:
                raise IntegrityError(f"peer {self.base_url} says the bytes do not hash to {ref} (409)") from None
            raise
        if status not in (200, 201, 204):
            raise NotConfigured(f"peer {self.base_url} answered {status} to PUT; it does not implement the write contract")
        return ref

    def put_named(self, name: str, data: bytes) -> None:
        if not self.allow_put or not self.has_token():
            raise self._refuse_write("put_named")
        try:
            status, _, _ = self._request(f"{NAMED_DIR}/{validate_name(name)}", method="PUT", data=bytes(data))
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise ReadOnly(f"peer {self.base_url} refused PUT of named {name!r} (403)") from None
            raise
        if status not in (200, 201, 204):
            raise NotConfigured(f"peer {self.base_url} answered {status} to PUT named; it does not implement the write contract")

    def describe(self) -> dict[str, Any]:
        info = super().describe()
        info.update({"base_url": self.base_url, "token_env": self.token_env, "token_present": self.has_token(),
                     "timeout_s": self.timeout_s, "retries": self.retries, "allow_put": self.allow_put,
                     "shard_width": self.layout.shard_width, "shard_depth": self.layout.shard_depth,
                     "usable": True, "needs": "" if self.allow_put and self.has_token() else
                     f"for writes: objects.peer.allow_put and ${self.token_env}",
                     "supports": ["read", "named-read", "named-index", "json-list"] + (["put"] if self.allow_put else [])})
        return info


def _build_schema() -> dict[str, Any]:
    from ..config import PeerStoreConfig
    return schema_from_dataclass(PeerStoreConfig, title="peer object store")


PeerHTTPStore.config_schema = _build_schema()

__all__ = ["PeerHTTPStore"]
