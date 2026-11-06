"""``S3ObjectLog``: declared adapter, object-per-record under a bucket, head store as ordering authority.

Protocol it would run (documented so the integrator can wire it without re-deriving it):

  keys      ``<prefix>/log/<partition>/objects/<digest>``  canonical record bytes, write-once
            (``If-None-Match: *``); orphan-safe because the key is the content address.
            ``<prefix>/log/<partition>/<seq:012d>``          index: the digest at that seq, written
            *after* the head CAS succeeded (``publish``), idempotent since one seq has one digest.
  append    write every record object; return.  Nothing is canonical yet.
  cas       the appender calls ``heads.cas(partition, expected, new)`` (``S3ConditionalHeads``:
            ``If-Match`` on the head object).  Success makes the run canonical; failure leaves
            orphans that the object GC removes (they are unreachable from any head).
  read      walk ``<seq:012d>`` from ``since_seq + 1`` upward; a missing index at seq N (a crash
            between CAS and publish) is repaired by walking ``prev`` back from the head's digest.
  last_seq  ``heads.get(partition)[0]``.
  partitions  ``ListObjectsV2`` with delimiter under ``<prefix>/log/``.

Needs: a client library, ``log.s3.bucket``/``prefix``, credentials, and conditional writes on the
bucket.  Every call raises ``NotConfigured`` naming that list until they exist.

Acceptance tests (named here, written in the verification phase):
  s3-declared: ``S3ObjectLog.describe()["status"] == "declared"`` and construction raises
  ``NotConfigured`` naming boto3 and the bucket; ``LOG_STORES.get("s3")`` resolves.
"""
from __future__ import annotations

from typing import Any
from collections.abc import Iterator, Mapping, Sequence

from agentdecompile_grid.core import NotConfigured, Record


class S3ObjectLog:
    name = "s3"
    ordering_authority = "heads"
    REQUIRES = ("python package 'boto3'", "log.s3.bucket", "log.s3.prefix",
                "credentials with s3:GetObject, s3:PutObject and s3:ListBucket",
                "a bucket with conditional writes (If-None-Match / If-Match) enabled",
                "an S3ConditionalHeads head store for the same bucket")

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self._unavailable()

    def _unavailable(self) -> None:
        missing = [k for k in ("bucket", "prefix") if not self.config.get(k)]
        raise NotConfigured(f"S3ObjectLog is declared, not wired: needs {list(self.REQUIRES)}; missing config keys {missing}")

    def append(self, records: Sequence[Record]) -> None:
        self._unavailable()

    def publish(self, records: Sequence[Record]) -> None:
        self._unavailable()

    def read(self, partition: str, since_seq: int = 0) -> Iterator[Record]:
        self._unavailable()
        return iter(())  # pragma: no cover

    def partitions(self) -> Iterator[str]:
        self._unavailable()
        return iter(())  # pragma: no cover

    def last_seq(self, partition: str) -> int:
        self._unavailable()
        return 0  # pragma: no cover

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "required": ["bucket", "prefix"], "properties": {
            "adapter": {"const": "s3"}, "bucket": {"type": "string"}, "prefix": {"type": "string"},
            "endpoint_url": {"type": "string"}, "region": {"type": "string"},
            "profile": {"type": "string", "description": "credentials profile; never inline keys in config"},
            "index_width": {"type": "integer", "default": 12, "description": "zero-padded seq width in index keys"}}}

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {"name": cls.name, "status": "declared", "requires": list(cls.REQUIRES), "config_schema": cls.config_schema(),
                "ordering_authority": cls.ordering_authority,
                "semantics": "record objects by digest (write-once), head CAS makes a run canonical, seq index written after"}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> S3ObjectLog:
        return cls(config)


__all__ = ["S3ObjectLog"]
