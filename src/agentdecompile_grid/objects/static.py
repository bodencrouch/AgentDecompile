"""agentdecompile_grid.objects.static — ``StaticMirrorStore``: read-only HTTP(S) mirror.

Working for reads.  Any static file server (a bucket website endpoint, a CDN, ``python -m
http.server`` over a rsync'd ``LocalDirStore`` root) that serves::

    <base_url>/objects/<shard...>/<hex>      object bytes
    <base_url>/named/<name>                  named pointer bytes
    <base_url>/index/all.txt                 one hex per line, sorted (optional; needed by list())
    <base_url>/index/<shard>.txt             per top-level shard (optional; used when present)
    <base_url>/layout.json                   the mirrored store's layout (optional; checked when present)

is a mirror.  ``write_mirror_index(store, dest)`` publishes the index files next to a
``LocalDirStore`` root so ``rsync root/ host:/srv/mirror/`` is a complete mirror.

Writes raise ``ReadOnly`` (a ``NotConfigured``) naming where writes go: the store that feeds the
mirror.  Every read re-hashes (``verify_on_read``), because a mirror is untrusted by construction.
No network I/O at construction or in ``describe()``.

Acceptance tests (named here, landed in the verification phase; use a local http.server over
a LocalDirStore root):

* ``test_mirror_get_verifies_and_exists_uses_head``.
* ``test_mirror_list_reads_published_index_and_names_missing_index`` — without ``index/`` ``list``
  raises ``NotConfigured`` naming ``write_mirror_index``.
* ``test_mirror_put_is_read_only_by_name``.
"""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator, Mapping

from ..core import NotConfigured, ObjectRef, ObjectStore
from .base import (
    INDEX_DIR, LAYOUT_FILE, NAMED_DIR, BaseObjectStore, Layout, ObjectMissing, ReadOnly, atomic_replace, FsyncPolicy,
    ref_prefix_hex, schema_from_dataclass, validate_name, validate_ref,
)

USER_AGENT = "agentdecompile-grid-objects/1"


class HttpReadMixin:
    """urllib-based GET/HEAD with timeout and bounded retries on transient failures."""

    base_url: str
    timeout_s: float
    retries: int
    headers: Mapping[str, str]

    def _url(self, relpath: str) -> str:
        return self.base_url.rstrip("/") + "/" + urllib.parse.quote(relpath, safe="/")

    def _request(self, relpath: str, *, method: str = "GET", data: bytes | None = None,
                 extra_headers: Mapping[str, str] | None = None) -> tuple[int, bytes, Mapping[str, str]]:
        """(status, body, headers); 404 is returned, other HTTP errors raise after retries."""
        headers = {"User-Agent": USER_AGENT, **dict(self.headers), **dict(extra_headers or {})}
        req = urllib.request.Request(self._url(relpath), method=method, data=data, headers=headers)
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - caller-configured URL
                    body = b"" if method == "HEAD" else resp.read()
                    return int(resp.status), body, {k.lower(): v for k, v in resp.headers.items()}
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    return exc.code, b"", {}
                if exc.code == 405 and method == "HEAD":
                    return 405, b"", {}
                if exc.code >= 500 and attempt < self.retries:
                    attempt += 1
                    time.sleep(min(2.0, 0.2 * (2 ** attempt)))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt < self.retries:
                    attempt += 1
                    time.sleep(min(2.0, 0.2 * (2 ** attempt)))
                    continue
                raise


class StaticMirrorStore(HttpReadMixin, BaseObjectStore):
    """Read-only content-addressed store behind a static HTTP(S) root."""

    name = "static-mirror"
    kind = "object-store"
    status = "working"

    def __init__(self, base_url: str, *, timeout_s: float = 30.0, retries: int = 2, index_path: str = INDEX_DIR,
                 shard_width: int = 2, shard_depth: int = 1, verify_on_read: bool = True,
                 headers: Mapping[str, str] | None = None) -> None:
        if not base_url:
            raise NotConfigured("StaticMirrorStore needs objects.mirror.base_url (an http(s) root serving objects/ and named/)")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)
        self.retries = int(retries)
        self.index_path = index_path.strip("/") or INDEX_DIR
        self.layout = Layout(shard_width=shard_width, shard_depth=shard_depth)
        self.verify_on_read = verify_on_read
        self.headers = dict(headers or {})
        self._layout_checked = False

    @classmethod
    def from_config(cls, cfg: Any) -> "StaticMirrorStore":
        m = cfg.objects.mirror
        return cls(m.base_url, timeout_s=m.timeout_s, retries=m.retries, index_path=m.index_path,
                   shard_width=cfg.objects.shard_width, shard_depth=cfg.objects.shard_depth,
                   verify_on_read=cfg.objects.verify_on_read)

    def _check_layout_once(self) -> None:
        if self._layout_checked:
            return
        self._layout_checked = True
        status, body, _ = self._request(LAYOUT_FILE)
        if status == 200 and body:
            try:
                Layout.from_json(body).check(self.layout, f"mirror {self.base_url}")
            except ValueError:
                pass  # not a layout file; the mirror may be served from a plain directory

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
        if length is None:
            return len(self.get(ref))
        return int(length)

    def list(self, prefix: str = "") -> Iterator[ObjectRef]:
        """From the published index: per-shard file when the prefix covers a shard, else ``all.txt``."""
        hexprefix = ref_prefix_hex(prefix)
        width = self.layout.shard_width
        relpath = f"{self.index_path}/all.txt"
        if width and self.layout.shard_depth and len(hexprefix) >= width:
            relpath = f"{self.index_path}/{hexprefix[:width]}.txt"
        status, body, _ = self._request(relpath)
        if status != 200:
            if relpath.endswith("all.txt"):
                raise NotConfigured(
                    f"mirror {self.base_url} publishes no {relpath}; run write_mirror_index() on the feeding "
                    f"LocalDirStore root (or 'adgrid objects index') before mirroring, or list the feeding store")
            status, body, _ = self._request(f"{self.index_path}/all.txt")
            if status != 200:
                raise NotConfigured(f"mirror {self.base_url} publishes no {self.index_path}/all.txt; run write_mirror_index()")
        found = sorted({line.strip() for line in body.decode("ascii", "replace").splitlines()
                        if len(line.strip()) == 64 and line.strip().startswith(hexprefix)})
        yield from (ObjectRef(f"sha256:{h}") for h in found)

    def get_named(self, name: str) -> bytes | None:
        status, body, _ = self._request(f"{NAMED_DIR}/{validate_name(name)}")
        return body if status == 200 else None

    # ---- writes: refused by name -------------------------------------------------------------
    def put(self, data: bytes, *, expect: ObjectRef | None = None) -> ObjectRef:
        raise ReadOnly(f"{self.name} at {self.base_url} is read-only; write to the store that feeds the mirror "
                       f"(a LocalDirStore or S3CompatibleStore) and republish")

    def put_named(self, name: str, data: bytes) -> None:
        raise ReadOnly(f"{self.name} at {self.base_url} is read-only; named pointers are written on the feeding store")

    def describe(self) -> dict[str, Any]:
        info = super().describe()
        info.update({"base_url": self.base_url, "timeout_s": self.timeout_s, "retries": self.retries,
                     "index_path": self.index_path, "shard_width": self.layout.shard_width,
                     "shard_depth": self.layout.shard_depth, "read_only": True, "supports": ["read", "named-read", "index-list"]})
        return info


def write_mirror_index(store: ObjectStore, dest_root: str | os.PathLike[str], *, shard_width: int = 2,
                       fsync: FsyncPolicy | str = FsyncPolicy.DATA) -> dict[str, int]:
    """Publish ``index/all.txt`` and ``index/<shard>.txt`` under ``dest_root`` from ``store.list()``.

    Deterministic: sorted hex, one per line, trailing newline.  Returns ``{"all": n, "shards": k}``.
    """
    dest = os.path.join(os.fspath(dest_root), INDEX_DIR)
    os.makedirs(dest, exist_ok=True)
    hexes = sorted(validate_ref(r).hex for r in store.list())
    policy = FsyncPolicy(fsync)
    atomic_replace(os.path.join(dest, "all.txt"), ("\n".join(hexes) + ("\n" if hexes else "")).encode("ascii"), fsync=policy, tag="index")
    shards: dict[str, list[str]] = {}
    if shard_width > 0:
        for h in hexes:
            shards.setdefault(h[:shard_width], []).append(h)
        for shard, items in sorted(shards.items()):
            atomic_replace(os.path.join(dest, f"{shard}.txt"), ("\n".join(items) + "\n").encode("ascii"), fsync=policy, tag="index")
    return {"all": len(hexes), "shards": len(shards)}


def _build_schema() -> dict[str, Any]:
    from ..config import MirrorStoreConfig
    return schema_from_dataclass(MirrorStoreConfig, title="static mirror object store")


StaticMirrorStore.config_schema = _build_schema()

__all__ = ["StaticMirrorStore", "HttpReadMixin", "write_mirror_index", "USER_AGENT"]
