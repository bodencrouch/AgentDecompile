"""agentdecompile_grid.objects.s3 — ``S3CompatibleStore``: bucket-backed store with conditional PUT.

Declared adapter.  The code is complete against the ``boto3`` API; it is usable the moment
``boto3``/``botocore`` are importable and ``objects.s3.bucket`` is set.  Without them every
operation raises ``NotConfigured`` naming exactly that.

Semantics:

* Keys: ``<prefix>/objects/<shard...>/<hex>``, ``<prefix>/named/<name>``, ``<prefix>/layout.json``.
* ``put`` sends ``If-None-Match: *`` (``conditional_put``); a 412 ``PreconditionFailed`` means the
  object already exists and is a no-op — the bucket, not this client, enforces write-once.
  A 409 ``ConditionalRequestConflict`` (concurrent conditional writers) is re-checked with a
  HEAD and treated as present.
* ``put_named`` is a plain PUT (last writer wins): named pointers are mutable by contract; CAS on
  named data is the head store's job, not the object store's.
* ``presigned_get`` / ``presigned_put`` return URLs valid for ``presign_ttl_s`` so a node without
  credentials (a donor) can read objects the operator chooses to expose, and a browser lane can
  upload a proposal.
* ``list`` walks ``list_objects_v2`` pages and yields refs sorted (S3 already returns keys in
  UTF-8 binary order; the client sorts anyway so the contract does not depend on it).
* No network I/O in ``__init__`` or ``describe()``; the client is created on first use.

Acceptance tests (named here, landed in the verification phase; need a bucket or a local
S3-compatible service and the ``s3`` extra):

* ``test_s3_conditional_put_is_noop_on_existing`` — the second PUT yields 412 and the bytes are unchanged.
* ``test_s3_presigned_get_serves_object_without_credentials``.
* ``test_s3_not_configured_names_extra`` — without boto3 every call raises ``NotConfigured`` mentioning ``boto3``.
"""
from __future__ import annotations

from typing import Any, Iterator

from ..core import NotConfigured, ObjectRef
from .base import (
    LAYOUT_FILE, NAMED_DIR, OBJECTS_DIR, BaseObjectStore, Layout, ObjectMissing, ref_prefix_hex,
    schema_from_dataclass, shard_parts, validate_name, validate_ref,
)

EXTRA_HINT = "install boto3/botocore (pip install boto3, the 'agentdecompile-grid[s3]' extra)"


class S3CompatibleStore(BaseObjectStore):
    """Bucket-backed content-addressed store (AWS S3, R2, MinIO, Backblaze, Ceph RGW, ...)."""

    name = "s3"
    kind = "object-store"
    status = "declared"

    def __init__(self, bucket: str, *, prefix: str = "", endpoint_url: str = "", region: str = "", profile: str = "",
                 presign_ttl_s: int = 3600, conditional_put: bool = True, shard_width: int = 2, shard_depth: int = 1,
                 verify_on_read: bool = True, client: Any = None) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self.region = region
        self.profile = profile
        self.presign_ttl_s = int(presign_ttl_s)
        self.conditional_put = bool(conditional_put)
        self.layout = Layout(shard_width=shard_width, shard_depth=shard_depth)
        self.verify_on_read = verify_on_read
        self._client = client
        self._layout_checked = False

    @classmethod
    def from_config(cls, cfg: Any) -> "S3CompatibleStore":
        s3 = cfg.objects.s3
        return cls(s3.bucket, prefix=s3.prefix, endpoint_url=s3.endpoint_url, region=s3.region, profile=s3.profile,
                   presign_ttl_s=s3.presign_ttl_s, conditional_put=s3.conditional_put,
                   shard_width=cfg.objects.shard_width, shard_depth=cfg.objects.shard_depth,
                   verify_on_read=cfg.objects.verify_on_read)

    # ---- wiring ------------------------------------------------------------------------------
    def _what_is_missing(self) -> str | None:
        if not self.bucket:
            return "set objects.s3.bucket (and objects.s3.endpoint_url for a non-AWS service)"
        try:
            import boto3  # noqa: F401
            import botocore  # noqa: F401
        except ImportError:
            return EXTRA_HINT
        return None

    def client(self) -> Any:
        """The boto3 S3 client, created on first use; ``NotConfigured`` names what is missing."""
        if self._client is not None:
            return self._client
        missing = self._what_is_missing()
        if missing:
            raise NotConfigured(f"S3CompatibleStore is not usable here: {missing}")
        import boto3
        session = boto3.session.Session(profile_name=self.profile or None, region_name=self.region or None)
        self._client = session.client("s3", endpoint_url=self.endpoint_url or None)
        return self._client

    def _key(self, relpath: str) -> str:
        return f"{self.prefix}/{relpath}" if self.prefix else relpath

    def _object_key(self, ref: ObjectRef) -> str:
        return self._key(self.layout.relpath(ref))

    def _named_key(self, name: str) -> str:
        return self._key(f"{NAMED_DIR}/{validate_name(name)}")

    @staticmethod
    def _error_code(exc: Exception) -> str:
        response = getattr(exc, "response", None) or {}
        error = response.get("Error", {}) if isinstance(response, dict) else {}
        code = str(error.get("Code", ""))
        status = str(response.get("ResponseMetadata", {}).get("HTTPStatusCode", "")) if isinstance(response, dict) else ""
        return code or status

    def _ensure_layout(self) -> None:
        if self._layout_checked:
            return
        client = self.client()
        key = self._key(LAYOUT_FILE)
        try:
            body = client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            Layout.from_json(body).check(self.layout, f"bucket {self.bucket}/{self.prefix or ''}")
        except Exception as exc:  # botocore ClientError
            if self._error_code(exc) not in ("NoSuchKey", "404"):
                raise
            self._conditional_put(key, self.layout.to_json())
        self._layout_checked = True

    def _conditional_put(self, key: str, data: bytes) -> bool:
        client = self.client()
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": key, "Body": data}
        if self.conditional_put:
            kwargs["IfNoneMatch"] = "*"
        try:
            client.put_object(**kwargs)
            return True
        except Exception as exc:
            code = self._error_code(exc)
            if code in ("PreconditionFailed", "412"):
                return False
            if code in ("ConditionalRequestConflict", "409"):
                return not self._head(key)
            raise

    def _head(self, key: str) -> dict[str, Any] | None:
        try:
            return self.client().head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._error_code(exc) in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    # ---- core protocol -----------------------------------------------------------------------
    def put(self, data: bytes, *, expect: ObjectRef | None = None) -> ObjectRef:
        data = bytes(data)
        ref = self.expected_ref(data, expect)
        self._ensure_layout()
        self._conditional_put(self._object_key(ref), data)
        return ref

    def get(self, ref: ObjectRef) -> bytes:
        validate_ref(ref)
        try:
            body = self.client().get_object(Bucket=self.bucket, Key=self._object_key(ref))["Body"].read()
        except Exception as exc:
            if self._error_code(exc) in ("NoSuchKey", "404"):
                raise ObjectMissing(f"{self.name}: no object {ref} in bucket {self.bucket}") from None
            raise
        return self.check_integrity(ref, body)

    def exists(self, ref: ObjectRef) -> bool:
        validate_ref(ref)
        return self._head(self._object_key(ref)) is not None

    def size(self, ref: ObjectRef) -> int:
        validate_ref(ref)
        head = self._head(self._object_key(ref))
        if head is None:
            raise ObjectMissing(f"{self.name}: no object {ref} in bucket {self.bucket}")
        return int(head["ContentLength"])

    def list(self, prefix: str = "") -> Iterator[ObjectRef]:
        hexprefix = ref_prefix_hex(prefix)
        width, depth = self.layout.shard_width, self.layout.shard_depth
        parts = shard_parts(hexprefix.ljust(width * depth, "0"), width, depth) if depth else ()
        usable: list[str] = []
        consumed = 0
        for part in parts:
            if len(hexprefix) >= consumed + width:
                usable.append(part)
                consumed += width
            else:
                break
        key_prefix = self._key("/".join((OBJECTS_DIR, *usable)) + "/")
        paginator = self.client().get_paginator("list_objects_v2")
        found: list[ObjectRef] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=key_prefix):
            for item in page.get("Contents", []):
                hexname = item["Key"].rsplit("/", 1)[-1]
                if len(hexname) == 64 and hexname.startswith(hexprefix):
                    found.append(ObjectRef(f"sha256:{hexname}"))
        yield from sorted(found)

    def put_named(self, name: str, data: bytes) -> None:
        self.client().put_object(Bucket=self.bucket, Key=self._named_key(name), Body=bytes(data))

    def get_named(self, name: str) -> bytes | None:
        try:
            return self.client().get_object(Bucket=self.bucket, Key=self._named_key(name))["Body"].read()
        except Exception as exc:
            if self._error_code(exc) in ("NoSuchKey", "404"):
                return None
            raise

    # ---- NamedIndexStore ---------------------------------------------------------------------
    def list_named(self, prefix: str = "") -> Iterator[str]:
        base = self._key(f"{NAMED_DIR}/")
        paginator = self.client().get_paginator("list_objects_v2")
        found: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=base + prefix):
            for item in page.get("Contents", []):
                found.append(item["Key"][len(base):])
        yield from sorted(found)

    def delete_named(self, name: str) -> bool:
        key = self._named_key(name)
        if self._head(key) is None:
            return False
        self.client().delete_object(Bucket=self.bucket, Key=key)
        return True

    # ---- presigned URLs ----------------------------------------------------------------------
    def presigned_get(self, ref: ObjectRef, *, ttl_s: int | None = None) -> str:
        return self.client().generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": self._object_key(ref)},
            ExpiresIn=int(ttl_s or self.presign_ttl_s))

    def presigned_put(self, ref: ObjectRef, *, ttl_s: int | None = None) -> str:
        """A URL a credential-less node may PUT the bytes of ``ref`` to; the bucket still checks nothing
        about content, so the reader side must ``verify_on_read`` (it does by default)."""
        return self.client().generate_presigned_url(
            "put_object", Params={"Bucket": self.bucket, "Key": self._object_key(ref)},
            ExpiresIn=int(ttl_s or self.presign_ttl_s))

    def describe(self) -> dict[str, Any]:
        info = super().describe()
        missing = self._what_is_missing()
        info.update({
            "bucket": self.bucket, "prefix": self.prefix, "endpoint_url": self.endpoint_url, "region": self.region,
            "profile": self.profile, "presign_ttl_s": self.presign_ttl_s, "conditional_put": self.conditional_put,
            "shard_width": self.layout.shard_width, "shard_depth": self.layout.shard_depth,
            "usable": missing is None, "needs": missing or "",
            "supports": ["named-index", "presigned-get", "presigned-put", "conditional-put"],
        })
        return info


def _build_schema() -> dict[str, Any]:
    from ..config import S3StoreConfig
    return schema_from_dataclass(S3StoreConfig, title="s3 object store")


S3CompatibleStore.config_schema = _build_schema()

__all__ = ["S3CompatibleStore", "EXTRA_HINT"]
